# embed2.py —— 阶段6第二课：把向量存进 PostgreSQL（pgvector），按意思检索
# embed1 是每次现算现比；真实项目是几万段文档：预先算好存进库，
# 提问时只算问题一个向量，用 SQL 按距离找最近的几段。
import json
import os
import urllib.request

import psycopg

OLLAMA = "http://localhost:11434/api/embed"
MODEL = "bge-m3"


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
    """把一句话送进 embedding 模型，拿回它的向量。"""
    body = json.dumps({"model": MODEL, "input": text}).encode()
    req = urllib.request.Request(
        OLLAMA, data=body, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read())
    return data["embeddings"][0]


DOCS = [
    "コンクリートの養生期間は7日間です",
    "混凝土的养护时间是7天",
    "鉄筋の定着長さを確認してください",
    "型枠の存置期間は構造計算で決まります",
    "足場の組立ては有資格者が行います",
    "工程表は毎週金曜日に更新します",
    "今天晚上吃拉面吧",
    "明日の天気は晴れのち曇りです",
]

conn = psycopg.connect(
    host="localhost",
    port=5433,  # 容器映射出来的端口（避开本机 PG 的 5432）
    dbname="postgres",
    user="postgres",
    password=get_env("PGVEC_PASSWORD"),
)
conn.execute("CREATE EXTENSION IF NOT EXISTS vector")  # 给 PG 装上向量能力
conn.execute(
    "CREATE TABLE IF NOT EXISTS chunks "
    "(id SERIAL PRIMARY KEY, content TEXT, embedding vector(1024))"
)
conn.execute("DELETE FROM chunks")  # 每次重跑从干净开始
for doc in DOCS:
    conn.execute(
        "INSERT INTO chunks (content, embedding) VALUES (%s, %s::vector)",
        (doc, str(embed(doc))),  # 向量以 "[...]" 文本形式传，::vector 让 PG 按向量解析
    )
conn.commit()
print(f"已存入 {len(DOCS)} 段文档")

question = "混凝土养护需要多少天？"
rows = conn.execute(
    "SELECT content, embedding <=> %s::vector AS dist "
    "FROM chunks ORDER BY dist LIMIT 3",  # <=> 是余弦距离：越小越近
    (str(embed(question)),),
).fetchall()
print(f"\n问题：{question}")
for content, dist in rows:
    print(f"距离 {dist:.3f}  {content}")
conn.close()
