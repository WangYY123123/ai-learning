# call_llm.py — 阶段 1 第一课：用 Python 调用一次大模型 API
import json
import urllib.request


def load_key():
    """从 .env 文件里读出 DEEPSEEK_API_KEY 的值。"""
    with open(".env", encoding="utf-8") as f:
        for line in f:
            if line.startswith("DEEPSEEK_API_KEY="):
                return line.strip().split("=", 1)[1]
    raise SystemExit("在 .env 里没找到 DEEPSEEK_API_KEY，先按教程建好 .env")


api_key = load_key()

# 请求三要素：网址（URL）+ 请求头（headers）+ 请求体（body，JSON 格式）
url = "https://api.deepseek.com/chat/completions"
headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {api_key}",  # 相当于出示钥匙，证明你是谁
}
body = {
    "model": "deepseek-chat",
    "messages": [
        {"role": "user", "content": "用一句话解释什么是 API，要通俗"},
    ],
}

# 发出 POST 请求，等服务器响应
req = urllib.request.Request(
    url,
    data=json.dumps(body).encode("utf-8"),
    headers=headers,
    method="POST",
)
with urllib.request.urlopen(req) as resp:
    print("状态码（status code）:", resp.status)  # 200 = 成功
    data = json.loads(resp.read().decode("utf-8"))

# 从响应 JSON 里取出模型的回答
print("模型回答：", data["choices"][0]["message"]["content"])
