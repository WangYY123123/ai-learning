# agent_server.py —— 本地智能体 · 一期地基 v0.1
# 骨架沿用 server_chat.py（会话记忆），大脑换成本地 Ollama 的 Qwen。
# 印证手册第 41 节：换大脑不用换身体——变的只有地址、模型名和回包的取法。
import json
import os
import time

import psycopg

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
# 长期记忆检索：先翻档案，把相关旧对话垫进系统提示
    memory_text = recall_memory(body.message)
    system_content = SYSTEM + ("\n\n" + memory_text if memory_text else "")
    messages = (
    [{"role": "system", "content": system_content}]
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
    # 长期记忆存档（支线，失败不影响回答）
    save_memory(body.session_id, body.message, answer)


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


def _stream_oai(messages, question=""):
    # 把 Ollama 的流（NDJSON，一行一块）逐块翻译成 OpenAI 的流（SSE，一块一条 data:）
    # think=False：关掉思考区，正文直接进 content，流式客户端不会收到长段空块。
    parts = []
    with requests.post(
        OLLAMA_CHAT,
        json={"model": MODEL, "messages": messages, "stream": True, "think": False},
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
                parts.append(text)
                chunk = _oai_chunk(content=text)
                yield "data: " + json.dumps(chunk, ensure_ascii=True) + "\n\n"
            if part.get("done"):
                end = _oai_chunk(finish="stop")
                yield "data: " + json.dumps(end, ensure_ascii=True) + "\n\n"
    # 流结束：把完整问答存进长期记忆（网页版通道记为 webui）
    if question and parts:
        save_memory("webui", question, "".join(parts))
    yield "data: [DONE]\n\n"





@app.post("/v1/chat/completions")
def oai_chat(body: OAIChatIn):
    # 取最后一条用户消息当问题：检索要用、存档也要用
    question = ""
    for m in reversed(body.messages):
        if m.role == "user":
            question = m.content
            break
    # 长期记忆检索：翻档案垫进系统提示（和人设拼在一起）
    memory_text = recall_memory(question) if question else ""
    system_content = SYSTEM + ("\n\n" + memory_text if memory_text else "")
    # 不管哪个界面进来，先垫上自己的人设，保证助理性格一致
    messages = [{"role": "system", "content": system_content}] + [
        {"role": m.role, "content": m.content} for m in body.messages
    ]
    if body.stream:
        return StreamingResponse(
            _stream_oai(messages, question), media_type="text/event-stream"
        )

        resp = requests.post(
        OLLAMA_CHAT,
        json={"model": MODEL, "messages": messages, "stream": False},
        timeout=300,
    )
        resp.raise_for_status()
        data = resp.json()
        if question:
         save_memory("webui", question, data["message"]["content"])

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
# ===== 长期记忆 · 存档（二期第 1 步）=====
# 每轮 /chat 问答后，把问答原文＋向量存进 PostgreSQL，攒长期记忆的原料。
# 连接参数与日语语法系统同一套（localhost:5433 / postgres / PGVEC_PASSWORD）。
# 存档是支线：失败只打日志，绝不拖垮回答。

OLLAMA_EMBED = "http://localhost:11434/api/embed"
EMBED_MODEL = "bge-m3"


def get_env(name):
    if name in os.environ:
        return os.environ[name]
    try:
        with open(".env", encoding="utf-8") as f:
            for line in f:
                if line.startswith(name + "="):
                    return line.split("=", 1)[1].strip()
    except FileNotFoundError:
        pass
    return None


def db_conn():
    return psycopg.connect(
        host="localhost",
        port=5433,
        dbname="postgres",
        user="postgres",
        password=get_env("PGVEC_PASSWORD"),
        connect_timeout=5,

    )


def embed(text):
    resp = requests.post(
        OLLAMA_EMBED, json={"model": EMBED_MODEL, "input": text}, timeout=120
    )
    resp.raise_for_status()
    return resp.json()["embeddings"][0]


def init_memory():
    with db_conn() as conn:
        conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS agent_memory ("
            "id SERIAL PRIMARY KEY, "
            "session_id TEXT, "
            "question TEXT, "
            "answer TEXT, "
            "embedding vector(1024), "
            "created_at TIMESTAMPTZ DEFAULT now())"
        )


def save_memory(session_id, question, answer):
    try:
        text = f"问：{question}\n答：{answer}"
        vec = embed(text)
        vec_str = "[" + ",".join(str(x) for x in vec) + "]"
        with db_conn() as conn:
            conn.execute(
                "INSERT INTO agent_memory (session_id, question, answer, embedding) "
                "VALUES (%s, %s, %s, %s::vector)",
                (session_id, question, answer, vec_str),
            )
    except Exception as e:
        print(f"[memory] 存档失败（不影响回答）：{e}", flush=True)


try:
    init_memory()
    print("[memory] 记忆表就绪", flush=True)
except Exception as e:
    print(f"[memory] 记忆库连不上，存档功能停用：{e}", flush=True)
def recall_memory(question, k=3):
    """按向量距离从 agent_memory 捞最相关的 k 条旧问答，拼成一段可垫进提示词的文本。
    全局检索（不分 session）——长期记忆本来就是跨会话的；失败或无结果都返回空串。"""
    try:
        vec = embed(question)
        vec_str = "[" + ",".join(str(x) for x in vec) + "]"
        with db_conn() as conn:
            rows = conn.execute(
                "SELECT question, answer FROM agent_memory "
                "ORDER BY embedding <=> %s::vector LIMIT %s",
                (vec_str, k),
            ).fetchall()
    except Exception as e:
        print(f"[memory] 检索失败（不影响回答）：{e}", flush=True)
        return ""
    if not rows:
        return ""
    lines = ["以下是从长期记忆中检索到的相关旧对话，供参考："]
    for q, a in rows:
        lines.append(f"- 问：{q} 答：{a}")
    return "\n".join(lines)
