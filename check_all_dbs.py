import sqlite3, sys, os
sys.stdout.reconfigure(encoding='utf-8')

dbs = [
    r'D:\dream_project\daily_mate_code\demo_server\recipe.db',
    r'D:\dream_project\daily_mate_code\daily_mate_all\database\recipe.db',
    r'D:\dream_project\daily_mate_code\daily_mate_all\demo_server\recipe.db',
    r'D:\dream_project\daily_mate_code\daily_mate_all\data_engine\recipe.db',
]

for path in dbs:
    if not os.path.exists(path):
        print(f"[NOT FOUND] {path}")
        continue
    try:
        db = sqlite3.connect(path)
        tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        if 'advice_templates' in tables:
            total = db.execute("SELECT COUNT(*) FROM advice_templates").fetchone()[0]
            by_ctx = db.execute("SELECT context_type, COUNT(*) FROM advice_templates GROUP BY context_type ORDER BY context_type").fetchall()
            print(f"\n[FOUND] {path}")
            print(f"  Total: {total} templates")
            for r in by_ctx:
                print(f"  {r[0]:20}: {r[1]}")
        else:
            print(f"\n[NO advice_templates] {path} — tables: {tables[:5]}")
        db.close()
    except Exception as e:
        print(f"[ERROR] {path}: {e}")
