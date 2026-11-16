# server_auth.py —— 阶段4第二课：带登录的服务（注册 / 登录发令牌 / 令牌验身份）
# HTTP 是无状态的：服务器记不住你登录过，所以登录成功后发一个令牌（token），
# 之后每次请求带上令牌出示身份。本课令牌先存内存，重启即失效——下一课改进。
import hashlib
import os
import secrets
import sqlite3

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

app = FastAPI()

TOKENS = {}  # 令牌 -> 用户名（内存版：服务一重启就清空）


def hash_password(password):
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100_000)
    return salt.hex() + "$" + digest.hex()


def check_password(password, stored):
    salt_hex, digest_hex = stored.split("$")
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), bytes.fromhex(salt_hex), 100_000
    )
    return digest.hex() == digest_hex


def get_db():
    conn = sqlite3.connect("auth.db")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS users "
        "(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE, pw_hash TEXT)"
    )
    return conn


class UserIn(BaseModel):
    name: str
    password: str


@app.post("/register")
def register(u: UserIn):
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO users (name, pw_hash) VALUES (?, ?)",
            (u.name, hash_password(u.password)),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(400, "用户名已存在")
    conn.close()
    return {"ok": True, "name": u.name}


@app.post("/login")
def login(u: UserIn):
    conn = get_db()
    row = conn.execute(
        "SELECT pw_hash FROM users WHERE name = ?", (u.name,)
    ).fetchone()
    conn.close()
    if not row or not check_password(u.password, row[0]):
        raise HTTPException(401, "用户名或密码错误")
    token = secrets.token_hex(16)  # 发一张随机工牌
    TOKENS[token] = u.name
    return {"token": token}


@app.get("/me")
def me(x_token: str = Header(default="")):
    name = TOKENS.get(x_token)
    if not name:
        raise HTTPException(401, "未登录或令牌无效")
    return {"name": name}
