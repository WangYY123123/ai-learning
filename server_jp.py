# server_jp.py —— 阶段6第八课：日语学习 RAG 服务（N2 语法问答）
# 结构和 server_rag.py 一模一样，只换两样：查的表（jp_chunks）和 SYSTEM 规矩。
# 一个领域一套（表 + 规矩），互不干扰——这是真实项目里的常见分法。
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
SYSTEM = (
    "你是日语学习助手，正在辅导一位备考 JLPT N2 的中国学生。"
    "只根据下面提供的资料回答问题，不要编造；"
    "资料里没有收录的语法点，就明确说资料里还没有收录。"
    "用中文讲解，回答包含：含义、接续、至少一个例句（带中文翻译）。"
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
    # Ollama 地址走环境变量（和 server_rag 同一套规矩）
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


class AskRequest(BaseModel):
    question: str


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/ask")
def ask(req: AskRequest):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT content FROM jp_chunks ORDER BY embedding <=> %s::vector LIMIT %s",
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
        "sources": [r[0] for r in rows],
        "usage": data.get("usage", {}),
    }
