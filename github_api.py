# github_api.py — 阶段 1 第三课：GET 请求，调 GitHub 的 API
import json
import urllib.request

url = "https://api.github.com/repos/WangYY123123/ai-learning/commits?per_page=3"
# 请求头里带上 User-Agent，表明"我是谁"——很多 API 都要求这一项
req = urllib.request.Request(url, headers={"User-Agent": "ai-learning"})

with urllib.request.urlopen(req) as resp:
    print("状态码（status code）:", resp.status)  # 200 = 成功
    data = json.loads(resp.read().decode("utf-8"))

# data 是一张清单（list），每个元素是一次提交的完整记录（字典）
print(f"最近 {len(data)} 次提交：")
for item in data:
    msg = item["commit"]["message"]
    date = item["commit"]["author"]["date"]
    print("-", date, msg)
