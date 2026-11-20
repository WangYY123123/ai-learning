# agent_server.py —— 本地智能体 · 一期地基 v0.1
# 骨架沿用 server_chat.py（会话记忆），大脑换成本地 Ollama 的 Qwen。
# 印证手册第 41 节：换大脑不用换身体——变的只有地址、模型名和回包的取法。
import json

import requests
from fastapi import FastAPI
from fastapi.responses import Response
from pydantic import BaseModel

OLLAMA_CHAT = "http://localhost:11434/api/chat"
MODEL = "qwen3.6:35b-a3b"
MAX_TURNS = 6  # 每个会话最多保留最近 6 轮，防上下文无限膨胀

SYSTEM = (
    "你是一个运行在用户本地电脑上的私人智能助理。"
    "回答简洁、准确；不知道的事情就直说不知道，不要编造。"
)

app = FastAPI()

# 会话记忆：{session_id: [ {role, content}, ... ]}，只存干净的问答原文
sessions = {}


class ChatIn(BaseModel):
    session_id: str
    message: str


@app.get("/health")
def health():
    return {"status": "ok", "model": MODEL}


@app.post("/chat")
def chat(body: ChatIn):
    history = sessions.setdefault(body.session_id, [])
    messages = (
        [{"role": "system", "content": SYSTEM}]
        + history
        + [{"role": "user", "content": body.message}]
    )
    resp = requests.post(
        OLLAMA_CHAT,
        json={"model": MODEL, "messages": messages, "stream": False},
        timeout=300,
    )
    resp.raise_for_status()
    answer = resp.json()["message"]["content"]

    # 把这一轮干净问答存进记忆，并裁掉太老的轮次
    history.append({"role": "user", "content": body.message})
    history.append({"role": "assistant", "content": answer})
    del history[:-MAX_TURNS * 2]

    # 回包把中文转义成 \uXXXX 纯 ASCII 再发：PowerShell 5.1 等老客户端
    # 按错误编码解 UTF-8 原文会乱码，转义后任何客户端都能无损还原。
    payload = {"answer": answer, "history_turns": len(history) // 2}
    return Response(
    content=json.dumps(payload, ensure_ascii=True),
    media_type="application/json",
    )

