# server.py — 阶段 1 第五课：给自己的服务加上 POST /chat，接通大模型
import json
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

app = FastAPI()


@app.get("/")
def home():
    return {"message": "我的第一个 API 服务跑起来了"}


@app.get("/hello/{name}")
def hello(name: str):
    return {"message": f"你好，{name}！"}


@app.get("/add")
def add(a: int, b: int):
    return {"a": a, "b": b, "result": a + b}


class ChatRequest(BaseModel):
    """规定来客递的单子长什么样：必须有一个 question，内容是文字（str）。"""

    question: str


@app.post("/chat")
def chat(req: ChatRequest):
    """收下问题，转手问大模型，再把回答递回去。"""
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
        # 不是我出错，是我背后的模型服务出错：回 502（上游出错，bad gateway）
        raise HTTPException(status_code=502, detail=f"模型服务返回了 {e.code}")
    answer = data["choices"][0]["message"]["content"]
    return {"question": req.question, "answer": answer}
