# auth1.py —— 阶段4第一课：注册/登录，密码只存哈希
# 核心规矩：数据库里永远不存密码本身，只存"加盐哈希"后的指纹。
import hashlib
import os
import sqlite3


def hash_password(password):
    """把密码变成指纹：随机盐 + pbkdf2 迭代 10 万次，盐和哈希一起存。"""
    salt = os.urandom(16)  # 每人一份随机盐
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100_000)
    return salt.hex() + "$" + digest.hex()


def check_password(password, stored):
    """登录校验：拿输入的密码按同样的盐再算一遍，比对指纹是否一致。"""
    salt_hex, digest_hex = stored.split("$")
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), bytes.fromhex(salt_hex), 100_000
    )
    return digest.hex() == digest_hex


conn = sqlite3.connect("auth.db")
conn.execute(
    "CREATE TABLE IF NOT EXISTS users "
    "(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE, pw_hash TEXT)"
)
conn.commit()

mode = input("注册还是登录？(r/l): ").strip()
name = input("用户名: ").strip()
password = input("密码: ")

if mode == "r":
    try:
        conn.execute(
            "INSERT INTO users (name, pw_hash) VALUES (?, ?)",
            (name, hash_password(password)),
        )
        conn.commit()
        print("注册成功")
    except sqlite3.IntegrityError:
        print("用户名已存在")
else:
    row = conn.execute(
        "SELECT pw_hash FROM users WHERE name = ?", (name,)
    ).fetchone()
    if row and check_password(password, row[0]):
        print("登录成功")
    else:
        print("用户名或密码错误")

conn.close()
