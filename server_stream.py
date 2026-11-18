# server_stream.py —— 进阶第1课：流式输出（N2 语法问答，打字机效果）
# 和 server_jp.py 只差一件事：回答不再等全篇生成完才返回，
# 而是模型吐一个字就往外推一个字（SSE 流）。检索、规矩、表都不变。
import json
import os
import urllib.error
import urllib.request

import psycopg
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
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


def stream_llm(messages):
    """流式调用 DeepSeek：逐个吐出 (类型, 内容)。
    token = 一小段文字；usage = 最后一包带回的用量。"""
    body = json.dumps({
        "model": "deepseek-chat",
        "messages": messages,
        "stream": True,
        "stream_options": {"include_usage": True},
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
        for raw in resp:
            line = raw.decode("utf-8").strip()
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            obj = json.loads(data)
            if obj.get("usage"):
                yield ("usage", obj["usage"])
            choices = obj.get("choices") or []
            if choices:
                piece = choices[0].get("delta", {}).get("content") or ""
                if piece:
                    yield ("token", piece)


class AskRequest(BaseModel):
    question: str


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/ask_stream")
def ask_stream(req: AskRequest):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT content FROM jp_chunks ORDER BY embedding <=> %s::vector LIMIT %s",
            (str(embed(req.question)), TOPK),
        ).fetchall()
    context = "\n".join(f"[{i + 1}] {r[0]}" for i, r in enumerate(rows))
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": f"资料：\n{context}\n\n问题：{req.question}"},
    ]

    def gen():
        # 流一旦开始，HTTP 状态码已经发出去了，
        # 中途出错没法再改状态码，只能发一个 error 事件告诉客户端。
        try:
            for kind, val in stream_llm(messages):
                if kind == "token":
                    yield "data: " + json.dumps(
                        {"type": "token", "text": val}, ensure_ascii=False
                    ) + "\n\n"
                else:
                    yield "data: " + json.dumps(
                        {"type": "usage", "usage": val}, ensure_ascii=False
                    ) + "\n\n"
        except Exception as e:
            yield "data: " + json.dumps(
                {"type": "error", "message": str(e)}, ensure_ascii=False
            ) + "\n\n"
            return
        yield "data: " + json.dumps(
            {"type": "done", "sources": [r[0] for r in rows]}, ensure_ascii=False
        ) + "\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")
