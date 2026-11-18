# ingest_jp.py —— 阶段6第八课：把 N2 语法语料入库
# 语料是"一条一条"的结构化文档，所以按条切分（不是按固定长度硬切）：
# 条目之间用 ==== 分隔，只收以「开头的段落，文件头的说明会自动跳过。
# 本脚本可重复执行：每次先清空 jp_chunks 再重灌，加完新条目重跑一次即可。
import json
import os
import urllib.request

import psycopg

OLLAMA = "http://localhost:11434/api/embed"
MODEL = "bge-m3"
SOURCE = "jlpt_n2_grammar.txt"


def get_env(name):
    """读配置：先查环境变量，没有再查 .env 文件（同前几课）。"""
    if name in os.environ:
        return os.environ[name]
    with open(".env", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith(name + "="):
                return line.split("=", 1)[1].strip()
    return ""


def embed(text):
    body = json.dumps({"model": MODEL, "input": text}).encode()
    req = urllib.request.Request(
        OLLAMA, data=body, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read())
    return data["embeddings"][0]


def load_entries(path):
    """读语料文件，按 ==== 切开，只留以「开头的条目。"""
    with open(path, encoding="utf-8") as f:
        text = f.read()
    parts = [p.strip() for p in text.split("====")]
    return [p for p in parts if p.startswith("「")]


def main():
    entries = load_entries(SOURCE)
    print(f"读到 {len(entries)} 条语法，开始入库……")
    conn = psycopg.connect(
        host="localhost",
        port=5433,
        dbname="postgres",
        user="postgres",
        password=get_env("PGVEC_PASSWORD"),
    )
    conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS jp_chunks "
        "(id SERIAL PRIMARY KEY, content TEXT, embedding vector(1024))"
    )
    conn.execute("DELETE FROM jp_chunks")
    for entry in entries:
        conn.execute(
            "INSERT INTO jp_chunks (content, embedding) VALUES (%s, %s::vector)",
            (entry, str(embed(entry))),
        )
    conn.commit()
    conn.close()
    print(f"入库完成：jp_chunks 共 {len(entries)} 条")


if __name__ == "__main__":
    main()
