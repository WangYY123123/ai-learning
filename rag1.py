# rag1.py —— 阶段6第三课：RAG 全链路（检索 + 生成）
# RAG = 先按意思检索出相关资料，再把资料和问题一起交给大模型作答。
# 模型从"凭记忆答"变成"看着资料答"：答得准、能标出处、还不容易编。
import json
import os
import urllib.error
import urllib.request

import psycopg

OLLAMA = "http://localhost:11434/api/embed"
MODEL = "bge-m3"
TOPK = 3  # 每次取最相关的 3 段资料


def get_env(name):
    """读配置：先查环境变量，没有再查 .env 文件（同前几课）。"""
    if name in os.environ:
        return os.environ[name]
    with open(".env", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith(name + "="):
                return line.split("=", 1)[1].strip()
    return ""


def embed(text):
    """把一句话送进 embedding 模型，拿回它的向量。"""
    body = json.dumps({"model": MODEL, "input": text}).encode()
    req = urllib.request.Request(
        OLLAMA, data=body, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read())
    return data["embeddings"][0]


def ask_llm(messages):
    """把消息列表交给 DeepSeek，拿回回答文本。"""
    body = json.dumps({"model": "deepseek-chat", "messages": messages}).encode()
    req = urllib.request.Request(
        "https://api.deepseek.com/chat/completions",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + get_env("DEEPSEEK_API_KEY"),
        },
    )
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"模型服务返回了 {e.code}")
    return data["choices"][0]["message"]["content"]


# 本课的"公司安全规章"（虚构示例，中日混排，一段一条）
DOCS = [
    "高さ2メートル以上の高所作業では、墜落制止用器具（安全帯）の使用が義務付けられています。",
    "工事現場では保護帽（ヘルメット）の着用が必須です。あごひもを正しく締めてください。",
    "足場の組立て・解体・変更の作業は、足場の組立て等作業主任者の指揮のもとで行います。",
    "コンクリート打設後は湿潤養生を行い、養生期間は原則として7日間とします。",
    "夏季の作業では、1時間ごとに10分の休憩を取り、水分と塩分を補給してください。",
    "クレーンの作業半径内は立入禁止とし、合図者以外は近づきません。",
    "雨天に電気作業を行う場合は、漏電遮断器が正常に作動することを事前に確認します。",
    "毎朝の朝礼では、当日の作業内容と危険予知（KY活動）の確認を行います。",
]

# 1) 入库：和 embed2 共用 chunks 表，换成本课的文档
conn = psycopg.connect(
    host="localhost",
    port=5433,
    dbname="postgres",
    user="postgres",
    password=get_env("PGVEC_PASSWORD"),
)
conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
conn.execute(
    "CREATE TABLE IF NOT EXISTS chunks "
    "(id SERIAL PRIMARY KEY, content TEXT, embedding vector(1024))"
)
conn.execute("DELETE FROM chunks")
for doc in DOCS:
    conn.execute(
        "INSERT INTO chunks (content, embedding) VALUES (%s, %s::vector)",
        (doc, str(embed(doc))),
    )
conn.commit()
print(f"资料库就绪：{len(DOCS)} 段")

# 2) 问答循环：检索 -> 拼 prompt -> 生成
SYSTEM = (
    "你是施工安全助手。只根据下面提供的资料回答问题，不要编造；"
    "资料里没有的内容，就明确说资料里没有。用提问者使用的语言回答，"
    "并在回答最后标注用到的资料编号，如 [1]。"
)

while True:
    q = input("\n问（输入 exit 退出）: ").strip()
    if q.lower() in ("exit", "quit"):
        break
    if not q:
        continue
    rows = conn.execute(
        "SELECT content FROM chunks ORDER BY embedding <=> %s::vector LIMIT %s",
        (str(embed(q)), TOPK),
    ).fetchall()
    context = "\n".join(f"[{i + 1}] {r[0]}" for i, r in enumerate(rows))
    print("\n--- 检索到的资料 ---")
    print(context)
    answer = ask_llm([
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": f"资料：\n{context}\n\n问题：{q}"},
    ])
    print("\n--- 回答 ---")
    print(answer)

conn.close()
