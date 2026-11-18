# server_chat.py —— 进阶第2课：多轮对话记忆（N2 语法问答）
# 和 server_jp.py 的区别：服务端按 session_id 存对话历史，
# 每轮把历史一起发给模型——模型本身不记事，"记忆"是应用层拼出来的。
import json
import os
import urllib.error
import urllib.request

import psycopg
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI()

MODEL = "bge-m3"
TOPK = 3
MAX_TURNS = 6  # 历史最多留最近 6 轮（12 条消息），再老的主动丢掉
SYSTEM = (
    "你是日语学习助手，正在辅导一位备考 JLPT N2 的中国学生。"
    "只根据下面提供的资料回答问题，不要编造；"
    "资料里没有收录的语法点，就明确说资料里还没有收录。"
    "用中文讲解，回答包含：含义、接续、至少一个例句（带中文翻译）。"
    "并在回答最后标注用到的资料编号，如 [1]。"
)

# 会话历史：{session_id: [message, message, ...]}，只存在内存里，
# 服务一重启就清空——真实项目会存数据库，这里先学机制。
sessions = {}


def get_env(name):
    """读配置：先查环境变量，没有再查 .env 文件（同前几课）。"""
    if name in os.environ:
        return os.environ[name]
    try:
        with open(".env", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith(name + "="):
                    return line.split("=", 1)[1].strip()
    except FileNotFoundError:
        pass
    return ""


def embed(text):
    base = get_env("OLLAMA_URL") or "http://localhost:11434"
    body = json.dumps({"model": MODEL, "input": text}).encode()
    req = urllib.request.Request(
        base + "/api/embed", data=body, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read())
    return data["embeddings"][0]


def get_conn():
    return psycopg.connect(
        host=get_env("PG_HOST") or "localhost",
        port=int(get_env("PG_PORT") or 5433),
        dbname="postgres",
        user="postgres",
        password=get_env("PGVEC_PASSWORD"),
    )


def ask_llm(messages):
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
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise HTTPException(502, f"模型服务返回了 {e.code}")


class ChatRequest(BaseModel):
    session_id: str
    question: str


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/chat")
def chat(req: ChatRequest):
    history = sessions.setdefault(req.session_id, [])
    # 追问往往信息不全（"它的接续是什么"里的"它"），
    # 检索时拼上上一问，命中率立刻不一样——这是最朴素的查询重写。
    last_user = next(
        (m["content"] for m in reversed(history) if m["role"] == "user"), ""
    )
    search_text = (last_user + " " + req.question) if last_user else req.question
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT content FROM jp_chunks ORDER BY embedding <=> %s::vector LIMIT %s",
            (str(embed(search_text)), TOPK),
        ).fetchall()
    context = "\n".join(f"[{i + 1}] {r[0]}" for i, r in enumerate(rows))
    messages = (
        [{"role": "system", "content": SYSTEM}]
        + history
        + [{"role": "user", "content": f"资料：\n{context}\n\n问题：{req.question}"}]
    )
    data = ask_llm(messages)
    answer = data["choices"][0]["message"]["content"]
    # 历史里只存"干净版"：用户原话 + 助手回答。
    # 不存塞了资料的那版——资料每轮都不同，存进去又费 token 又互相污染。
    history.append({"role": "user", "content": req.question})
    history.append({"role": "assistant", "content": answer})
    if len(history) > 2 * MAX_TURNS:
        del history[: len(history) - 2 * MAX_TURNS]
    return {
        "answer": answer,
        "sources": [r[0] for r in rows],
        "usage": data.get("usage", {}),
        "turns": len(history) // 2,
    }
