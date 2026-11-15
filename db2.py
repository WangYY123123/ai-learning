# db2.py — 阶段 2 第二课：增删改查（CRUD）+ 条件查询 WHERE
import sqlite3

conn = sqlite3.connect("notes.db")
cur = conn.cursor()

# 新建一张待办表（tasks）：id 编号、title 内容、done 是否完成（0=没完成，1=完成）
cur.execute("""
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT,
    done INTEGER
)
""")
# 先清空，保证每次运行结果一样
# ⚠️ 记住：DELETE 不带 WHERE 就是删光全表——真实工作里这是能出大事的一行
cur.execute("DELETE FROM tasks")
conn.commit()


def show(label):
    """把表里现在的内容全打出来看一眼。"""
    cur.execute("SELECT id, title, done FROM tasks ORDER BY id")
    print(f"--- {label} ---")
    for row in cur.fetchall():
        print(row)


# 增（INSERT）：一次塞三条
tasks = [
    ("学 Python", 0),
    ("背日语单词", 0),
    ("看施工管理真题", 0),
]
cur.executemany("INSERT INTO tasks (title, done) VALUES (?, ?)", tasks)
conn.commit()
show("刚插入后")

# 查（SELECT + WHERE）：只找标题里带"日语"的（LIKE + % = 模糊匹配）
cur.execute("SELECT id, title, done FROM tasks WHERE title LIKE ?", ("%日语%",))
print("--- 查带'日语'的 ---")
for row in cur.fetchall():
    print(row)

# 改（UPDATE）：把"学 Python"标记为已完成
# ⚠️ UPDATE 也一样：忘了 WHERE，全表的行会被一起改掉
cur.execute("UPDATE tasks SET done = 1 WHERE title = ?", ("学 Python",))
conn.commit()
show("把'学 Python'标为完成后")

# 删（DELETE）：删掉"看施工管理真题"这一条
cur.execute("DELETE FROM tasks WHERE title = ?", ("看施工管理真题",))
conn.commit()
show("删掉一条后")

conn.close()
