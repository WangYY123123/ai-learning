# chat_cli.py —— 进阶第2课：多轮对话客户端（终端里连续追问）
# 用法：先起服务 uvicorn server_chat:app --port 8003，再 python chat_cli.py
# 输入 exit 退出。把 SESSION_ID 改个名字、或重启服务，就是一段全新对话。
import requests

SESSION_ID = "test-2"

print("N2 语法多轮问答（输入 exit 退出）")
while True:
    q = input("\n你：").strip()
    if q.lower() in ("exit", "quit"):
        break
    if not q:
        continue
    r = requests.post(
        "http://localhost:8003/chat",
        json={"session_id": SESSION_ID, "question": q},
        timeout=120,
    )
    d = r.json()
    print(f"\n助手：{d['answer']}")
    print(f"（第 {d['turns']} 轮，本轮 total_tokens {d['usage'].get('total_tokens')}）")
