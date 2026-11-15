# organize.py — 阶段 0 第一个脚本：按扩展名整理文件夹
# Stage 0 first script: sort files in a folder into subfolders by type.
# 只用 Python 自带功能，不用装任何库。先在测试文件夹上跑，确认无误再用在真文件夹上。
import shutil
from pathlib import Path

# 扩展名（extension）→ 文件夹名：想加一种类型，就在这里加一行
RULES = {
    ".pdf": "PDF文档",
    ".docx": "Word文档",
    ".xlsx": "Excel表格",
    ".jpg": "图片",
    ".jpeg": "图片",
    ".png": "图片",
    ".mp4": "视频",
    ".zip": "压缩包",
    ".mp3": "音频",
    ".txt": "文本文件",
    ".webp": "图片"
}

def organize(folder):
    """把 folder 里的文件按扩展名分进子文件夹，返回 {文件夹名: [文件名]}。"""
    folder = Path(folder)
    moved = {}
    for item in folder.iterdir():  # iterdir() = 列出文件夹里的每一项
        if item.is_dir():  # 已经是文件夹的跳过
            continue
        if item.name in ("organize.py", "清单.txt"):  # 脚本自己和清单不参与整理
            continue
        target_name = RULES.get(item.suffix.lower(), "其他")  # 不在表里的进“其他”
        target = folder / target_name
        target.mkdir(exist_ok=True)  # 文件夹不存在就新建
        dest = target / item.name
        if dest.exists():  # 同名文件不覆盖，改名加 _1
            dest = target / f"{item.stem}_1{item.suffix}"
        shutil.move(str(item), str(dest))
        moved.setdefault(target_name, []).append(item.name)
    return moved

def write_list(folder, moved):
    """把整理结果写进 清单.txt，方便核对。"""
    lines = ["整理清单", ""]
    for target_name, names in moved.items():
        lines.append(f"[{target_name}] {len(names)} 个")
        lines += [f"  - {name}" for name in names]
    (Path(folder) / "清单.txt").write_text("\n".join(lines), encoding="utf-8")

if __name__ == "__main__":
    folder = input("要整理的文件夹路径（直接回车用当前文件夹）: ").strip()
    if not folder:
        folder = "."
    moved = organize(folder)
    write_list(folder, moved)
    total = sum(len(names) for names in moved.values())
    print(f"共整理了 {total} 个文件：")
    for target_name, names in moved.items():
        print(f"  {target_name}: {len(names)} 个")
    print("结果已写入 清单.txt")
