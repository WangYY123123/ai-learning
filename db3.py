# db3.py — 阶段 2 第四课：两张表与 JOIN（把分开存的数据拼起来查）
import sqlite3

conn = sqlite3.connect("notes.db")
cur = conn.cursor()

# 表一：人（users）——只存人本身的信息
cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT
)
""")
# 表二：笔记（posts）——user_id 存"作者的编号"，是连回 users 表的一根线
cur.execute("""
CREATE TABLE IF NOT EXISTS posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    title TEXT
)
""")
# 先清空，保证每次运行结果一样
cur.execute("DELETE FROM users")
cur.execute("DELETE FROM posts")
conn.commit()

# 放两个人。编号是数据库自动给的，用 lastrowid 当场接住，不要靠猜
cur.execute("INSERT INTO users (name) VALUES (?)", ("WANG",))
wang_id = cur.lastrowid
cur.execute("INSERT INTO users (name) VALUES (?)", ("小陈",))
chen_id = cur.lastrowid
conn.commit()

# 放三条笔记：每条只记作者的编号，不重复抄作者的名字
posts = [
    (wang_id, "Python 学习笔记"),
    (wang_id, "日语单词本"),
    (chen_id, "买菜清单"),
]
cur.executemany("INSERT INTO posts (user_id, title) VALUES (?, ?)", posts)
conn.commit()

# JOIN：顺着 user_id 这根线，把作者名拼回来一起看
print("--- 全部笔记（带作者名）---")
cur.execute("""
SELECT posts.title, users.name
FROM posts
JOIN users ON posts.user_id = users.id
ORDER BY posts.id
""")
for row in cur.fetchall():
    print(row)

# JOIN + WHERE：只看某个人的笔记
print("--- 只看 WANG 的笔记 ---")
cur.execute("""
SELECT posts.title
FROM posts
JOIN users ON posts.user_id = users.id
WHERE users.name = ?
""", ("WANG",))
for row in cur.fetchall():
    print(row)

conn.close()
