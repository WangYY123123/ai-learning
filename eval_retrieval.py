# eval_retrieval.py —— 进阶第3课：检索评测集（只测检索层，不调模型）
# 每条用例 = 问题 + 期望命中的资料（用标题里的关键词判断）。
# 指标 Hit@k：期望资料出现在前 k 条里的比例。跑得快、不花钱，
# 以后改切分、改检索方式、调 TOPK，全靠它量"变好还是变坏"。
import json
import os
import urllib.request

import psycopg

MODEL = "bge-m3"
FETCH = 5  # 每题取前 5 条，一次算出 @1 / @3 / @5

CASES = [
    # 直问（问题里带语法原词）
    ("〜ざるを得ない是什么意思", "ざるを得ない"),
    ("〜ばかりか怎么用", "ばかりか"),
    ("〜に加えて的接续是什么", "に加えて"),
    ("〜以上は是什么意思", "以上は"),
    ("〜がたい是什么意思", "がたい"),
    # 意思问（问题里没有原词，考语义检索）
    ("想表达不得不去，用哪个语法", "ざるを得ない"),
    ("不仅……而且……，用哪个语法", "ばかりか"),
    ("难以相信，用哪个语法", "がたい"),
    ("有可能发生，用哪个语法", "得る"),
    ("最好的办法是……、……莫过于，用哪个语法", "に限る"),
    ("一办完就马上通知，用哪个语法", "次第"),
    # 易混问（近义语法扎堆，最容易捞错）
    ("想说并不是讨厌他，用哪个语法", "わけではない"),
]


def get_env(name):
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


def main():
    conn = psycopg.connect(
        host=get_env("PG_HOST") or "localhost",
        port=int(get_env("PG_PORT") or 5433),
        dbname="postgres",
        user="postgres",
        password=get_env("PGVEC_PASSWORD"),
    )
    hits = {1: 0, 3: 0, 5: 0}
    for i, (question, expect) in enumerate(CASES, 1):
        rows = conn.execute(
            "SELECT content FROM jp_chunks ORDER BY embedding <=> %s::vector LIMIT %s",
            (str(embed(question)), FETCH),
        ).fetchall()
        rank = next(
            (j + 1 for j, r in enumerate(rows) if expect in r[0]), None
        )
        for k in hits:
            if rank is not None and rank <= k:
                hits[k] += 1
        mark = f"命中 @{rank}" if rank else "未命中"
        print(f"[{i:2d}] {mark:8s} 期望「{expect}」 ← {question}")
    n = len(CASES)
    print()
    for k in (1, 3, 5):
        print(f"Hit@{k}: {hits[k]}/{n} = {hits[k] / n:.0%}")
    conn.close()


if __name__ == "__main__":
    main()
