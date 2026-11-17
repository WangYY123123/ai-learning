# server_rag.py —— 阶段6第四课：把 RAG 包成 API 服务
# rag1.py 是命令行版，一个人用；包成服务后，任何程序都能调它问答。
# 还顺带把每次问答的 token 用量亮出来——成本控制的第一步是看得见账。
import json
import os
import urllib.error
import urllib.request

import psycopg
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI()

OLLAMA = "http://localhost:11434/api/embed"
MODEL = "bge-m3"
TOPK = 3
SYSTEM = (
    "你是施工安全助手。只根据下面提供的资料回答问题，不要编造；"
    "资料里没有的内容，就明确说资料里没有。用提问者使用的语言回答，"
    "并在回答最后标注用到的资料编号，如 [1]。"
)


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
    body = json.dumps({"model": MODEL, "input": text}).encode()
    req = urllib.request.Request(
        OLLAMA, data=body, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read())
    return data["embeddings"][0]


def get_conn():
    # 连接参数全走环境变量：本地默认连 5433 的 pgvec 容器，
    # 以后进 compose 时改成 PG_HOST=db、PG_PORT=5432 即可，代码不动
    return psycopg.connect(
        host=get_env("PG_HOST") or "localhost",
        port=int(get_env("PG_PORT") or 5433),
        dbname="postgres",
        user="postgres",
        password=get_env("PGVEC_PASSWORD"),
    )


def ask_llm(messages):
    """调 DeepSeek，返回完整响应（要用到里面的 usage 记账）。"""
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


class AskRequest(BaseModel):
    question: str


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/ask")
def ask(req: AskRequest):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT content FROM chunks ORDER BY embedding <=> %s::vector LIMIT %s",
            (str(embed(req.question)), TOPK),
        ).fetchall()
    context = "\n".join(f"[{i + 1}] {r[0]}" for i, r in enumerate(rows))
    data = ask_llm([
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": f"资料：\n{context}\n\n问题：{req.question}"},
    ])
    return {
        "question": req.question,
        "answer": data["choices"][0]["message"]["content"],
        "sources": [r[0] for r in rows],  # 用到的资料原文，方便核查
        "usage": data.get("usage", {}),  # 本次问答的 token 账单
    }
