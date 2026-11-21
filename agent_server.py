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
    "需要确认用户以前说过的话时，用 search_memory 工具查档案原文，不要凭印象编。"
    "用户问日语语法条目的意思或用法时，用 search_docs 工具查知识库原文。"


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
    # 工具调用循环：模型说要调工具就执行、把结果喂回去，直到它给出最终回答（最多 5 轮）
    answer = ""
    for _ in range(5):
        resp = requests.post(
            OLLAMA_CHAT,
            json={"model": MODEL, "messages": messages, "tools": TOOLS, "stream": False},
            timeout=300,
        )
        resp.raise_for_status()
        msg = resp.json()["message"]
        calls = msg.get("tool_calls") or []
        if not calls:
            answer = msg.get("content", "")
            break
        messages.append(msg)
        for call in calls:
            fn = call["function"]["name"]
            args = call["function"].get("arguments", {})
            result = _call_tool(fn, args)

            print(f"[tool] {fn}({args})", flush=True)
            messages.append({"role": "tool", "content": result})
    if not answer:
        answer = "（工具调用轮数用尽，没能得出回答）"

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


def _run_tools(messages):
    """工具轮（非流式）：模型要调工具就执行、把结果喂回，直到它给出最终回答。
    返回 (messages, answer, last_data)；answer 为空串表示轮数用尽仍未答。
    与 /chat 的循环同构——那边内联，这边抽成函数给 /v1 的两个分支共用。"""
    last_data = {}
    for _ in range(5):
        resp = requests.post(
            OLLAMA_CHAT,
            json={"model": MODEL, "messages": messages, "tools": TOOLS, "stream": False},
            timeout=300,
        )
        resp.raise_for_status()
        last_data = resp.json()
        msg = last_data["message"]
        calls = msg.get("tool_calls") or []
        if not calls:
            return messages, msg.get("content", ""), last_data
        messages.append(msg)
        for call in calls:
            fn = call["function"]["name"]
            args = call["function"].get("arguments", {})
            result = _call_tool(fn, args)

            print(f"[tool] {fn}({args})", flush=True)
            messages.append({"role": "tool", "content": result})
    return messages, "", last_data


def _stream_answer(answer, question=""):
    """把已生成的完整回答切成小块按 SSE 吐出（网页版流式通道用），吐完存档。
    两段式：工具轮先非流式跑完，最终答再切片成流——网页上仍是逐字出现的效果。"""
    step = 12
    for i in range(0, len(answer), step):
        chunk = _oai_chunk(content=answer[i : i + step])
        yield "data: " + json.dumps(chunk, ensure_ascii=True) + "\n\n"
    end = _oai_chunk(finish="stop")
    yield "data: " + json.dumps(end, ensure_ascii=True) + "\n\n"
    if question and answer:
        save_memory("webui", question, answer)
    yield "data: [DONE]\n\n"

    if question and answer:
        save_memory("webui", question, answer)

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
    # 先跑工具轮：该查查、该算算，拿到最终回答再往外发（流式与非流式共用）
    messages, answer, data = _run_tools(messages)
    if not answer:
     answer = "（工具调用轮数用尽，没能得出回答）"
    if body.stream:
       return StreamingResponse(
        _stream_answer(answer, question), media_type="text/event-stream"
    )
    if question:
     save_memory("webui", question, answer)


    payload = {
        "id": "chatcmpl-local",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": MODEL,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": answer},

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
# ===== 工具层（三期第 1 步）=====
# 工具 = 普通 Python 函数 + 一张给模型看的说明书（TOOLS）。
# 模型只负责"决定调哪个、传什么参数"，真正干活的是函数——工具长在服务里，不长在模型里。


def tool_search_memory(keyword):
    """按关键词在 agent_memory 里做文本搜索，返回命中的旧问答原文（近的在前，最多 5 条）。"""
    try:
        with db_conn() as conn:
            rows = conn.execute(
                "SELECT question, answer FROM agent_memory "
                "WHERE question ILIKE %s OR answer ILIKE %s "
                "ORDER BY id DESC LIMIT 5",
                (f"%{keyword}%", f"%{keyword}%"),
            ).fetchall()
    except Exception as e:
        return f"搜索记忆失败：{e}"
    if not rows:
        return f"档案里没有找到包含「{keyword}」的旧对话。"
    lines = [f"找到 {len(rows)} 条包含「{keyword}」的旧对话："]
    for q, a in rows:
        lines.append(f"- 问：{q} 答：{a}")
    return "\n".join(lines)


def tool_now(detail=""):
    """返回当前日期时间（本机时区）。模型天生不知道现在几点，靠这件工具。
    detail 参数只是占位（无参数工具调用容易被模型写坏格式），忽略不用。"""

    from datetime import datetime

    now = datetime.now()
    weekdays = "一二三四五六日"
    return now.strftime("%Y-%m-%d %H:%M:%S") + f" 星期{weekdays[now.weekday()]}"


def tool_calc(expression):
    """安全计算一个四则运算表达式。先过字符白名单，绝不直接 eval 模型给的原文。"""
    import re

    if len(expression) > 100 or not re.fullmatch(r"[0-9+\-*/%.() ]+", expression):
        return "表达式不合规：只允许数字与 + - * / % ** 和括号，长度不超过 100。"
    try:
        return str(eval(expression, {"__builtins__": {}}, {}))
    except Exception as e:
        return f"算不了「{expression}」：{e}"

def tool_search_docs(query):
    """按语义在文档知识库（日语语法库 jp_chunks）里检索，返回最相关的 3 条原文。
    与 search_memory 的区别：那件是关键词搜对话档案，这件是向量搜文档——语义相近就能命中。"""
    try:
        vec = embed(query)
        vec_str = "[" + ",".join(str(x) for x in vec) + "]"
        with db_conn() as conn:
            rows = conn.execute(
                "SELECT content FROM jp_chunks "
                "ORDER BY embedding <=> %s::vector LIMIT 3",
                (vec_str,),
            ).fetchall()
    except Exception as e:
        return f"搜索知识库失败：{e}"
    if not rows:
        return "知识库里没有找到相关内容。"
    return "\n\n".join(r[0] for r in rows)


TOOL_FUNCS = {
    "search_memory": tool_search_memory,
    "now": tool_now,
    "calc": tool_calc,
}


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_memory",
            "description": "按关键词在长期记忆档案里搜索以前的对话原文。当用户问起以前聊过的事、或需要确认用户说过的话时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {
                        "type": "string",
                        "description": "要搜索的关键词，如人名、店名、数字相关的词",
                    }
                },
                "required": ["keyword"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "now",
            "description": "获取当前日期和时间（含星期）。当用户问现在几点、今天几号，或任何需要知道当前时间的问题时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "detail": {"type": "string", "description": "占位参数，可留空"}
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_docs",
            "description": "按语义在文档知识库里检索原文（当前库为日语 N2 语法库）。当用户问某个语法条目的意思、用法、接续或例句时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "要检索的问题或条目，如「ざるを得ない 的意思」",
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calc",
            "description": "计算一个数学表达式并返回精确结果。当用户要求算账、算价格、做四则运算时调用，不要自己心算。",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "要计算的表达式，如 (250000-13200)*12 或 3980*1.1",
                    }
                },
                "required": ["expression"],
            },
        },
    },
]

def _call_tool(fn, args):
    """执行一次工具调用（带装甲）：模型传参不可信——先过滤掉函数不认识的参数，
    执行出错也不许炸请求，转成文字喂回给模型，让它自己改口重问。"""
    import inspect

    func = TOOL_FUNCS.get(fn)
    if func is None:
        return f"没有名为 {fn} 的工具"
    if not isinstance(args, dict):
        args = {}
    allowed = set(inspect.signature(func).parameters)
    clean = {k: v for k, v in args.items() if k in allowed}
    try:
        return func(**clean)
    except Exception as e:
        return f"工具 {fn} 执行失败：{e}"




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
