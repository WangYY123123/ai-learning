# agent1.py —— 进阶第4课：工具调用（function calling）
# 前几课的模型只会"动嘴"：检索是我们在外面做好塞给它的。
# 这一课给它装"手"：把检索、查清单做成工具，模型自己决定调哪个、传什么参数，
# 我们负责真正执行，再把结果塞回去让它接着答。这就是 Agent 的最小骨架。
import json
import os
import urllib.request

import psycopg

MODEL = "bge-m3"
MAX_ROUNDS = 5  # 工具循环上限，防止模型反复调工具停不下来

SYSTEM = (
    "你是日语学习助手，正在辅导一位备考 JLPT N2 的中国学生。"
    "需要查语法资料时，调用工具获取，不要凭记忆编造。"
    "拿到资料后用中文讲解，包含含义、接续、例句（带翻译）。"
)


def get_env(name):
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


# ---------- 工具本体：就是普通的 Python 函数 ----------

def search_grammar(keyword):
    """按关键词语义检索语法资料，返回最相关的 3 条原文。"""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT content FROM jp_chunks ORDER BY embedding <=> %s::vector LIMIT 3",
            (str(embed(keyword)),),
        ).fetchall()
    return "\n\n".join(r[0] for r in rows)


def list_grammar():
    """列出资料库收录的全部语法标题（只给标题，不给全文）。"""
    with get_conn() as conn:
        rows = conn.execute("SELECT content FROM jp_chunks").fetchall()
    titles = [r[0].split("\n")[0] for r in rows]
    return f"共 {len(titles)} 条：\n" + "\n".join(titles)


FUNCTIONS = {"search_grammar": search_grammar, "list_grammar": list_grammar}

# ---------- 工具说明书：模型靠这份说明决定调哪个、传什么参数 ----------
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_grammar",
            "description": "按关键词语义检索 N2 语法资料，返回最相关的 3 条原文（接续/含义/例句）",
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {
                        "type": "string",
                        "description": "检索关键词，如某个语法点「ざるを得ない」或意思「不得不」",
                    }
                },
                "required": ["keyword"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_grammar",
            "description": "列出资料库收录的全部语法标题。用于回答「收录了哪些/一共有几个」这类需要盘点的问题",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]


def call_llm(messages):
    body = json.dumps({
        "model": "deepseek-chat",
        "messages": messages,
        "tools": TOOLS,
        "tool_choice": "auto",
    }).encode()
    req = urllib.request.Request(
        "https://api.deepseek.com/chat/completions",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + get_env("DEEPSEEK_API_KEY"),
        },
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def run(question):
    print(f"\n===== 问：{question}")
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": question},
    ]
    for _ in range(MAX_ROUNDS):
        data = call_llm(messages)
        msg = data["choices"][0]["message"]
        tool_calls = msg.get("tool_calls")
        if not tool_calls:
            print(f"答：{msg.get('content', '')}")
            return
        messages.append(msg)  # 把模型这轮的原始回复（含 tool_calls）原样入列
        for tc in tool_calls:
            name = tc["function"]["name"]
            args = json.loads(tc["function"]["arguments"] or "{}")
            print(f"[工具调用] {name}({args})")
            result = FUNCTIONS[name](**args)
            print(f"[工具返回] {len(result)} 字")
            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": result,
            })
    print("（工具调用轮数超上限，停了）")


if __name__ == "__main__":
    run("〜ものだから是什么意思？")
    run("资料里带「わけ」的语法一共有几个？分别是哪些？")
    run("帮我找出「〜くせに」的接续和例句")
