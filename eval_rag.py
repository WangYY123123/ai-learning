# eval_rag.py —— 阶段6第五课：给 RAG 服务做评测
# 没有评测集，改 prompt、换模型、调 top-k 就都只能凭感觉。
# 做法：固定一组带"期望"的问题，反复打真实服务，用分数说话。
# 判定还顺带分清故障在哪一半：检索没命中，还是资料对但回答不对。
import json
import urllib.error
import urllib.request

API = "http://localhost:8000/ask"
# "老实说没有"的常见说法（中日两种语言）
REFUSAL_WORDS = ["资料里没有", "没有", "資料にありません", "記載がありません", "記載されていません"]

# source = 期望命中的资料里应含的词；answer = 回答里应含的词
CASES = [
    {"q": "高处作业多高要系安全带？", "source": "2メートル", "answer": "2"},
    {"q": "コンクリートの養生は何日？", "source": "養生期間", "answer": "7"},
    {"q": "クレーンの作業半径内に入ってもいいですか？", "source": "立入禁止", "answer": "禁止"},
    {"q": "夏の作業では何分休憩しますか？", "source": "休憩", "answer": "10"},
    {"q": "公司的年假有几天？", "refuse": True},      # 资料里没有，必须拒答
    {"q": "作業員の日給はいくらですか？", "refuse": True},  # 同上
]


def ask(question):
    body = json.dumps({"question": question}).encode()
    req = urllib.request.Request(
        API, data=body, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def check(case, resp):
    """判定一条用例过没过，返回 (过没过, 没过的原因)。"""
    answer = resp.get("answer", "")
    sources = resp.get("sources", [])
    if case.get("refuse"):
        ok = any(w in answer for w in REFUSAL_WORDS)
        return ok, "" if ok else "没拒答，可能在编造"
    if case["source"] not in " ".join(sources):
        return False, "检索没命中对的资料"
    if case["answer"] not in answer:
        return False, "资料对但回答不对"
    return True, ""


def main():
    passed = 0
    for i, case in enumerate(CASES, 1):
        try:
            resp = ask(case["q"])
        except urllib.error.URLError:
            print("连不上服务——先在另一个终端把服务起起来：uvicorn server_rag:app")
            return
        ok, why = check(case, resp)
        passed += ok
        mark = "✅ 通过" if ok else f"❌ 未过（{why}）"
        print(f"[{i}] {mark}  问：{case['q']}")
        print(f"     答：{resp.get('answer', '')[:60]}")
    print(f"\n总分：{passed}/{len(CASES)}")


if __name__ == "__main__":
    main()
