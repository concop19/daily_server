"""
Sync advice_templates từ DB chính sang demo_server DB.
Chỉ copy bảng advice_templates, không đụng đến data khác.
"""
import sqlite3, sys
sys.stdout.reconfigure(encoding='utf-8')

SRC = r'D:\dream_project\daily_mate_code\daily_mate_all\database\recipe.db'
DST = r'D:\dream_project\daily_mate_code\demo_server\recipe.db'

src = sqlite3.connect(SRC)
dst = sqlite3.connect(DST)

# Lấy toàn bộ từ nguồn
rows = src.execute(
    "SELECT context_type,trigger_dim,intensity_min,intensity_max,"
    "template_text,priority,lang,notes FROM advice_templates"
).fetchall()

# Xoá bảng cũ ở đích và insert lại sạch
dst.execute("DELETE FROM advice_templates")
dst.executemany(
    "INSERT INTO advice_templates "
    "(context_type,trigger_dim,intensity_min,intensity_max,template_text,priority,lang,notes) "
    "VALUES (?,?,?,?,?,?,?,?)",
    rows
)
dst.commit()

total = dst.execute("SELECT COUNT(*) FROM advice_templates").fetchone()[0]
print(f"✅ Synced {total} templates → {DST}")

src.close()
dst.close()
