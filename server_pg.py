# server_pg.py —— 阶段5第三课：把聊天记录存进 PostgreSQL
# 和阶段2的 server_db.py 是同一个服务，只把 SQLite 换成 PostgreSQL。
# 连接参数全从环境变量读；数据库主机名在 compose 里就是服务名 db。
import json
import os
import time
import urllib.error
import urllib.request

import psycopg
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI()


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


def get_conn():
    return psycopg.connect(
        host=get_env("PG_HOST") or "localhost",
        dbname=get_env("PG_DB") or "appdb",
        user=get_env("PG_USER") or "postgres",
        password=get_env("PG_PASSWORD"),
    )


def init_db():
    """建表。数据库可能还没就绪（compose 只保证一起启动），所以带重试。"""
    for _ in range(15):
        try:
            with get_conn() as conn:
                conn.execute(
                    "CREATE TABLE IF NOT EXISTS chat_logs "
                    "(id SERIAL PRIMARY KEY, question TEXT, answer TEXT, "
                    "created_at TIMESTAMP DEFAULT now())"
                )
            return
        except Exception:
            time.sleep(2)
    raise RuntimeError("等了 30 秒还是连不上数据库")


init_db()


def save_log(question, answer):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO chat_logs (question, answer) VALUES (%s, %s)",
            (question, answer),
        )


def ask_llm(question):
    body = json.dumps({
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": question}],
    }).encode()
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
        raise HTTPException(502, f"模型服务返回了 {e.code}")
    return data["choices"][0]["message"]["content"]


class ChatRequest(BaseModel):
    question: str


@app.post("/chat")
def chat(req: ChatRequest):
    answer = ask_llm(req.question)
    save_log(req.question, answer)
    return {"question": req.question, "answer": answer}


@app.get("/history")
def history(limit: int = 10):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT question, answer FROM chat_logs ORDER BY id DESC LIMIT %s",
            (limit,),
        ).fetchall()
    return [{"question": q, "answer": a} for q, a in rows]
