# server_jwt.py —— 阶段4第四课：JWT（自带防伪的令牌）
# 第二课的令牌是随机串、存服务器内存，重启就没；JWT 把身份写进令牌本身，
# 再盖一个只有服务器能盖的"签名"防伪章：服务器不存记录，只验章。
# 结构：header.payload.signature 三段，用点连起来。
import base64
import hashlib
import hmac
import json
import os
import sqlite3
import time

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

app = FastAPI()


def get_env(name):
    """读配置：先查环境变量（Docker／服务器运行时注入），没有再查 .env 文件（本地开发用）。"""
    if name in os.environ:
        return os.environ[name]
    with open(".env", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith(name + "="):
                return line.split("=", 1)[1].strip()
    return ""


SECRET = get_env("JWT_SECRET").encode()  # 签名密钥，只放 .env，绝不进代码和仓库


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
    conn = sqlite3.connect("auth2.db")  # 沿用第三课的库，alice/bob 都在里面
    conn.execute(
        "CREATE TABLE IF NOT EXISTS users "
        "(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE, "
        "pw_hash TEXT, role TEXT)"
    )
    return conn


def b64e(data: bytes) -> str:
    """bytes -> base64url 文本（去掉末尾的 = 填充）。"""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def b64d(text: str) -> bytes:
    """base64url 文本 -> bytes（先把 = 填充补回去）。"""
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def make_jwt(name, role):
    """造令牌：把身份写进 payload，盖上签名章。"""
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {"name": name, "role": role, "exp": int(time.time()) + 3600}  # 1 小时过期
    h = b64e(json.dumps(header).encode())
    p = b64e(json.dumps(payload).encode())
    sig = hmac.new(SECRET, f"{h}.{p}".encode(), hashlib.sha256).digest()
    return f"{h}.{p}.{b64e(sig)}"


def read_jwt(token):
    """验令牌：拆三段 -> 重算签名比对 -> 查过期。通过才返回 (用户名, 角色)。"""
    try:
        h, p, s = token.split(".")
    except ValueError:
        raise HTTPException(401, "令牌格式不对")
    sig = hmac.new(SECRET, f"{h}.{p}".encode(), hashlib.sha256).digest()
    if not hmac.compare_digest(b64e(sig).encode(), s.encode()):
        raise HTTPException(401, "令牌签名不对")
    try:
        payload = json.loads(b64d(p))
    except Exception:
        raise HTTPException(401, "令牌格式不对")
    if payload.get("exp", 0) < time.time():
        raise HTTPException(401, "令牌已过期")
    return payload["name"], payload["role"]


class UserIn(BaseModel):
    name: str
    password: str


@app.post("/register")
def register(u: UserIn):
    conn = get_db()
    count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    role = "admin" if count == 0 else "user"  # 第一个注册者当管理员（同第三课）
    try:
        conn.execute(
            "INSERT INTO users (name, pw_hash, role) VALUES (?, ?, ?)",
            (u.name, hash_password(u.password), role),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(400, "用户名已存在")
    conn.close()
    return {"ok": True, "name": u.name, "role": role}


@app.post("/login")
def login(u: UserIn):
    conn = get_db()
    row = conn.execute(
        "SELECT pw_hash, role FROM users WHERE name = ?", (u.name,)
    ).fetchone()
    conn.close()
    if not row or not check_password(u.password, row[0]):
        raise HTTPException(401, "用户名或密码错误")
    return {"token": make_jwt(u.name, row[1])}  # 发的不是随机串，是 JWT


@app.get("/me")
def me(x_token: str = Header(default="")):
    name, role = read_jwt(x_token)
    return {"name": name, "role": role}


@app.get("/users")
def list_users(x_token: str = Header(default="")):
    name, role = read_jwt(x_token)  # 角色直接从令牌里读，不查库
    if role != "admin":
        raise HTTPException(403, "只有管理员能看用户列表")
    conn = get_db()
    rows = conn.execute("SELECT name, role FROM users ORDER BY id").fetchall()
    conn.close()
    return [{"name": n, "role": r} for n, r in rows]
