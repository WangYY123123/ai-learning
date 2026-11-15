# db1.py — 阶段 2 第一课：第一次用数据库存东西（SQLite）
import sqlite3

# 连接（connect）数据库：文件不存在就新建，这一个文件就是整个数据库
conn = sqlite3.connect("notes.db")
cur = conn.cursor()

# 建表（table）：先说好这张表有几列、每列存什么
# IF NOT EXISTS = 表已经在了就跳过，不报错（所以第二次运行没事）
cur.execute("""
CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content TEXT,
    created_at TEXT
)
""")

# 插入（INSERT）一行：内容 + 存入时间（datetime('now') 是数据库自带的时间）
# 注意写法：命令里留 ? 占位，数据单独放在后面——命令和数据分开，是防黑客注入的基本功
cur.execute(
    "INSERT INTO notes (content, created_at) VALUES (?, datetime('now'))",
    ("我的第一条笔记",),
)
conn.commit()  # 提交（commit）：真正落盘保存，没这一步，关掉就没了

# 查询（SELECT）：把表里的东西按 id 顺序全取出来
cur.execute("SELECT id, content, created_at FROM notes ORDER BY id")
rows = cur.fetchall()
print(f"表里一共有 {len(rows)} 条：")
for row in rows:
    print(row)

conn.close()
