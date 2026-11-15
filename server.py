# server.py — 阶段 1 第四课：自己当服务器，写第一个 API
from fastapi import FastAPI

app = FastAPI()


@app.get("/")
def home():
    """根路径（root）：打开服务的首页地址时，回一句话。"""
    return {"message": "我的第一个 API 服务跑起来了"}


@app.get("/hello/{name}")
def hello(name: str):
    """路径参数（path parameter）：网址里 {name} 的位置写什么，name 就是什么。"""
    return {"message": f"你好，{name}！"}


@app.get("/add")
def add(a: int, b: int):
    """查询参数（query parameter）：网址尾巴 ?a=3&b=5 这样传进来的数。"""
    return {"a": a, "b": b, "result": a + b}
