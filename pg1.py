# pg1.py — 阶段 2 第五课：换上真正的数据库 PostgreSQL
import psycopg


def get_env(name):
    """从 .env 里按名字读一个值（load_key 的通用版，读任何配置都用它）。"""
    with open(".env", encoding="utf-8") as f:
        for line in f:
            if line.startswith(name + "="):
                return line.strip().split("=", 1)[1]
    raise SystemExit(f"在 .env 里没找到 {name}，先把 {name}=... 加进 .env")


# 连接五件套：主机、端口、库名、用户名、密码（密码从 .env 读，不写死在代码里）
conn = psycopg.connect(
    host="localhost",
    port=5432,
    dbname="postgres",
    user="postgres",
    password=get_env("PG_PASSWORD"),
)
cur = conn.cursor()

# 建表：id 的写法变成 SERIAL（意思和 AUTOINCREMENT 一样：自动编号）
# created_at 给了默认值 now()，插入时不用再管时间
cur.execute("""
CREATE TABLE IF NOT EXISTS notes (
    id SERIAL PRIMARY KEY,
    content TEXT,
    created_at TIMESTAMP DEFAULT now()
)
""")

# 插入一行。注意：PostgreSQL 的占位符是 %s，不是 SQLite 的 ?
cur.execute("INSERT INTO notes (content) VALUES (%s)", ("第一条存进 PostgreSQL 的笔记",))
conn.commit()  # 一样要 commit 才落盘

# 查出来看看（和 SQLite 完全一样的 SELECT）
cur.execute("SELECT id, content, created_at FROM notes ORDER BY id")
rows = cur.fetchall()
print(f"PostgreSQL 里一共有 {len(rows)} 条：")
for row in rows:
    print(row)

conn.close()
