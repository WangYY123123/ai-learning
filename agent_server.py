# agent_server.py —— 本地智能体 · 一期地基 v0.1
# 骨架沿用 server_chat.py（会话记忆），大脑换成本地 Ollama 的 Qwen。
# 印证手册第 41 节：换大脑不用换身体——变的只有地址、模型名和回包的取法。
import json
from pyexpat.errors import messages

import requests
from fastapi import FastAPI
import time
from fastapi.responses import Response, StreamingResponse
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
    # ===== OpenAI 兼容层 =====
    # 让生态里的现成界面（如 Open WebUI）把本服务当成 OpenAI 来用。
    # 与 /chat 的区别：这里服务端不记会话，历史由客户端每次全量带来——这是 OpenAI 协议的约定。


class OAIMessage(BaseModel):
        role: str
        content: str


class OAIChatIn(BaseModel):
        model: str = MODEL
        messages: list[OAIMessage]
        stream: bool = False


@app.get("/v1/models")
def oai_models():
        return {
        "object": "list",
        "data": [
            {"id": MODEL, "object": "model", "created": 0, "owned_by": "local-agent"}
        ],
    }


def _oai_chunk(content=None, finish=None):
        delta = {}
        if content is not None:
            delta["content"] = content
        return {
        "id": "chatcmpl-local",
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": MODEL,
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
    }


def _stream_oai(messages):
        # 把 Ollama 的流（NDJSON，一行一块）逐块翻译成 OpenAI 的流（SSE，一块一条 data:）
        with requests.post(
        OLLAMA_CHAT,
        json={"model": MODEL, "messages": messages, "stream": True},
        stream=True,
        timeout=300,
    ) as resp:
            resp.raise_for_status()
        for line in resp.iter_lines():
            if not line:
                continue
            part = json.loads(line)
            text = part.get("message", {}).get("content", "")
            if text:
                chunk = _oai_chunk(content=text)
                yield "data: " + json.dumps(chunk, ensure_ascii=True) + "\n\n"
            if part.get("done"):
                end = _oai_chunk(finish="stop")
                yield "data: " + json.dumps(end, ensure_ascii=True) + "\n\n"
        yield "data: [DONE]\n\n"


@app.post("/v1/chat/completions")
def oai_chat(body: OAIChatIn):
    # 不管哪个界面进来，先垫上自己的人设，保证助理性格一致
            messages = [{"role": "system", "content": SYSTEM}] + [
        {"role": m.role, "content": m.content} for m in body.messages
    ]
            if body.stream:
                return StreamingResponse(_stream_oai(messages), media_type="text/event-stream")
            resp = requests.post(
        OLLAMA_CHAT,
        json={"model": MODEL, "messages": messages, "stream": False},
        timeout=300,
    )
            resp.raise_for_status()
            data = resp.json()
            payload = {
        "id": "chatcmpl-local",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": MODEL,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": data["message"]["content"]},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": data.get("prompt_eval_count", 0),
            "completion_tokens": data.get("eval_count", 0),
            "total_tokens": data.get("prompt_eval_count", 0) + data.get("eval_count", 0),
        },
    }
            return Response(
        content=json.dumps(payload, ensure_ascii=True),
        media_type="application/json",
    )