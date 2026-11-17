# embed1.py —— 阶段6第一课：向量（embedding）入门
# 把文字变成一串数字（向量）：意思越接近的句子，向量越"靠近"。
# 用本机 Ollama 的 bge-m3 模型（多语言，中日英都行，免费本地跑）。
import json
import math
import urllib.request

OLLAMA = "http://localhost:11434/api/embed"
MODEL = "bge-m3"


def embed(text):
    """把一句话送进 embedding 模型，拿回它的向量。"""
    body = json.dumps({"model": MODEL, "input": text}).encode()
    req = urllib.request.Request(
        OLLAMA, data=body, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read())
    return data["embeddings"][0]


def cosine(a, b):
    """余弦相似度：1 = 方向完全一致（意思极近），越低越不相关。"""
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb)


sentences = [
    "コンクリートの養生期間は7日間です",  # 日语：混凝土的养护期是 7 天
    "混凝土的养护时间是7天",  # 中文：同一句话
    "鉄筋の定着長さを確認してください",  # 日语：请确认钢筋的锚固长度（同领域、不同义）
    "今天晚上吃拉面吧",  # 完全无关
]

vectors = []
for s in sentences:
    v = embed(s)
    vectors.append(v)
    print(f"{s}  -> 向量维度 {len(v)}")

print()
for i in range(len(sentences)):
    for j in range(i + 1, len(sentences)):
        sim = cosine(vectors[i], vectors[j])
        print(f"相似度 {sim:.3f}  {sentences[i][:12]} <-> {sentences[j][:12]}")
