# server_rbac.py —— 阶段4第三课：授权（给用户分角色 RBAC）
# 认证解决"你是谁"，授权解决"你能干什么"。
# 本课：users 表加 role 列；第一个注册的人自动当 admin，其余都是 user；
# /users 是 admin 专属接口：没登录 401，登录了但角色不够 403。
import hashlib
import os
import secrets
import sqlite3

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

app = FastAPI()

TOKENS = {}  # 令牌 -> 用户名（内存版，同第二课）


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
    conn = sqlite3.connect("auth2.db")  # 本课用新库，带 role 列
    conn.execute(
        "CREATE TABLE IF NOT EXISTS users "
        "(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE, "
        "pw_hash TEXT, role TEXT)"
    )
    return conn


def current_user(x_token):
    """凭令牌认人：返回 (用户名, 角色)；令牌无效就抛 401。"""
    name = TOKENS.get(x_token)
    if not name:
        raise HTTPException(401, "未登录或令牌无效")
    conn = get_db()
    row = conn.execute(
        "SELECT role FROM users WHERE name = ?", (name,)
    ).fetchone()
    conn.close()
    return name, row[0]


class UserIn(BaseModel):
    name: str
    password: str


@app.post("/register")
def register(u: UserIn):
    conn = get_db()
    count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    role = "admin" if count == 0 else "user"  # 第一个注册者当管理员
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
        "SELECT pw_hash FROM users WHERE name = ?", (u.name,)
    ).fetchone()
    conn.close()
    if not row or not check_password(u.password, row[0]):
        raise HTTPException(401, "用户名或密码错误")
    token = secrets.token_hex(16)
    TOKENS[token] = u.name
    return {"token": token}


@app.get("/me")
def me(x_token: str = Header(default="")):
    name, role = current_user(x_token)
    return {"name": name, "role": role}


@app.get("/users")
def list_users(x_token: str = Header(default="")):
    name, role = current_user(x_token)  # 先认证：没牌 401
    if role != "admin":  # 再授权：牌对了但角色不够 403
        raise HTTPException(403, "只有管理员能看用户列表")
    conn = get_db()
    rows = conn.execute("SELECT name, role FROM users ORDER BY id").fetchall()
    conn.close()
    return [{"name": n, "role": r} for n, r in rows]
