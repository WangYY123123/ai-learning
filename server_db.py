# server_db.py — 阶段 2 第三课：让服务把聊天记录存进数据库
# 启动（start）：uvicorn server_db:app --port 8000
import json
import sqlite3
import urllib.error
import urllib.request

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel


def load_key():
    """从 .env 文件里读出 DEEPSEEK_API_KEY 的值。"""
    with open(".env", encoding="utf-8") as f:
        for line in f:
            if line.startswith("DEEPSEEK_API_KEY="):
                return line.strip().split("=", 1)[1]
    raise SystemExit("在 .env 里没找到 DEEPSEEK_API_KEY，先按教程建好 .env")


API_KEY = load_key()
LLM_URL = "https://api.deepseek.com/chat/completions"
DB_FILE = "chat.db"


def init_db():
    """启动时先把存聊天记录的表建好（有了就跳过）。"""
    conn = sqlite3.connect(DB_FILE)
    conn.execute("""
    CREATE TABLE IF NOT EXISTS chat_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        question TEXT,
        answer TEXT,
        created_at TEXT
    )
    """)
    conn.commit()
    conn.close()


def save_log(question, answer):
    """把一次问答存进数据库：开连接 → 插入 → 提交 → 关连接，四步固定动作。"""
    conn = sqlite3.connect(DB_FILE)
    conn.execute(
        "INSERT INTO chat_logs (question, answer, created_at) VALUES (?, ?, datetime('now'))",
        (question, answer),
    )
    conn.commit()
    conn.close()


init_db()
app = FastAPI()


class ChatRequest(BaseModel):
    question: str


@app.post("/chat")
def chat(req: ChatRequest):
    """收下问题，问大模型，回答存档后再递回去。"""
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}",
    }
    body = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": req.question}],
    }
    request = urllib.request.Request(
        LLM_URL,
        data=json.dumps(body).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        # 不是我出错，是我背后的模型服务出错：回 502（上游出错）
        raise HTTPException(status_code=502, detail=f"模型服务返回了 {e.code}")
    answer = data["choices"][0]["message"]["content"]
    save_log(req.question, answer)  # ← 本课新增的一行：回答完，顺手存进数据库
    return {"question": req.question, "answer": answer}


@app.get("/history")
def history(limit: int = 5):
    """取出最近的几条聊天记录（新的在前）。"""
    conn = sqlite3.connect(DB_FILE)
    rows = conn.execute(
        "SELECT id, question, answer, created_at FROM chat_logs ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    logs = []
    for row in rows:
        logs.append(
            {"id": row[0], "question": row[1], "answer": row[2], "created_at": row[3]}
        )
    return {"count": len(logs), "logs": logs}
