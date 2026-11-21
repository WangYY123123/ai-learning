# ingest_docs.py —— 把 docs/ 文件夹里的 txt/md 文档切块、向量化，灌进 docs_chunks 表。
# 用法：文档放进仓库根目录的 docs/ 文件夹，运行 python ingest_docs.py
# 可重复执行：每个文件入库前先删它自己的旧块，改完文档重跑即可，不会重复堆积。
# 连接与向量化直接复用 agent_server 里的 db_conn / embed，不再抄一份。
import glob
import os

import agent_server as a

DOCS_DIR = "docs"
CHUNK_SIZE = 500


def split_text(text, size=CHUNK_SIZE):
    """先按空行分段，段太长就按 size 硬切（先求简单可控，重叠优化以后再说）。"""
    chunks = []
    for para in text.split("\n\n"):
        para = para.strip()
        if not para:
            continue
        while len(para) > size:
            chunks.append(para[:size])
            para = para[size:]
        if para:
            chunks.append(para)
    return chunks



def main():
    files = sorted(
        glob.glob(os.path.join(DOCS_DIR, "*.txt"))
        + glob.glob(os.path.join(DOCS_DIR, "*.md"))
    )
    if not files:
        print(f"{DOCS_DIR}/ 里没有 .txt 或 .md 文件，先放文档进来")
        return
    with a.db_conn() as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS docs_chunks "
            "(id SERIAL PRIMARY KEY, source TEXT, content TEXT, embedding vector(1024))"
        )
        total = 0
        for path in files:
            name = os.path.basename(path)
            with open(path, encoding="utf-8") as f:
                text = f.read()
            chunks = split_text(text)
            conn.execute("DELETE FROM docs_chunks WHERE source = %s", (name,))
            for ch in chunks:
                vec = a.embed(ch)
                vec_str = "[" + ",".join(str(x) for x in vec) + "]"
                conn.execute(
                    "INSERT INTO docs_chunks (source, content, embedding) "
                    "VALUES (%s, %s, %s::vector)",
                    (name, ch, vec_str),
                )
            total += len(chunks)
            print(f"{name}：{len(chunks)} 块")
    print(f"入库完成：共 {total} 块")


if __name__ == "__main__":
    main()

