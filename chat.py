# chat.py — 阶段 1 第二课：能多轮对话的聊天程序
import json
import urllib.error
import urllib.request


def load_key():
    """从 .env 文件里读出 DEEPSEEK_API_KEY 的值。"""
    with open(".env", encoding="utf-8") as f:
        for line in f:
            if line.startswith("DEEPSEEK_API_KEY="):
                return line.strip().split("=", 1)[1]
    raise SystemExit("在 .env 里没找到 DEEPSEEK_API_KEY，先按教程建好 .env")


API_KEY = load_key()
URL = "https://api.deepseek.com/chat/completions"


def ask(messages):
    """把整个对话记录发给模型，返回它这一轮的回答。"""
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}",
    }
    body = {"model": "deepseek-chat", "messages": messages}
    req = urllib.request.Request(
        URL,
        data=json.dumps(body).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        # 服务器拒绝时（如 401 钥匙不对），把状态码和原因打出来
        print("请求失败，状态码（status code）:", e.code)
        print("服务器返回：", e.read().decode("utf-8"))
        raise SystemExit(1)
    return data["choices"][0]["message"]["content"]


# 对话记录：一张清单（list），一问一答往里追加，顺序就是聊天顺序
messages = [
    {"role": "system", "content": "你是一个耐心的编程老师，回答简短、通俗。"},
]

print("开始聊天（输入 exit 结束）：")
while True:
    question = input("你：")
    if question.strip().lower() in ("exit", "quit"):
        print("结束聊天。")
        break
    messages.append({"role": "user", "content": question})
    answer = ask(messages)
    print("AI：", answer)
    # 关键一行：把 AI 的回答也存回记录，它下一轮才记得自己说过什么
    messages.append({"role": "assistant", "content": answer})
