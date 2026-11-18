# test_stream.py —— 进阶第1课：流式客户端，看打字机效果 + 量首字时间
import json
import time

import requests

QUESTION = "〜ざるを得ない是什么意思？"

t0 = time.time()
first_token_at = None
with requests.post(
    "http://localhost:8002/ask_stream",
    json={"question": QUESTION},
    stream=True,
    timeout=120,
) as r:
    r.raise_for_status()
    for line in r.iter_lines(decode_unicode=True):
        if not line or not line.startswith("data:"):
            continue
        obj = json.loads(line[5:])
        if obj["type"] == "token":
            if first_token_at is None:
                first_token_at = time.time() - t0
                print(f"（首字时间 {first_token_at:.2f} 秒）", flush=True)
            print(obj["text"], end="", flush=True)
        elif obj["type"] == "usage":
            print(f"\n--- usage: {obj['usage']}", flush=True)
        elif obj["type"] == "done":
            print(f"--- 出处 {len(obj['sources'])} 条，总时长 {time.time() - t0:.2f} 秒")
        elif obj["type"] == "error":
            print(f"\n[出错] {obj['message']}")
