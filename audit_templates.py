import sqlite3, sys
sys.stdout.reconfigure(encoding='utf-8')

DB = r'D:\dream_project\daily_mate_code\daily_mate_all\database\recipe.db'
db = sqlite3.connect(DB)

# Chi tiet tung context_type
for ctx in ['weather', 'season', 'headline', 'health', 'ingredient', 'tag']:
    rows = db.execute(
        "SELECT trigger_dim, intensity_min, intensity_max, priority, template_text "
        "FROM advice_templates WHERE context_type=? ORDER BY trigger_dim, priority",
        (ctx,)
    ).fetchall()
    print(f"\n{'='*60}")
    print(f"  context_type = '{ctx}'  ({len(rows)} rows)")
    print(f"{'='*60}")
    dims = {}
    for r in rows:
        dims.setdefault(r[0], []).append(r)
    for dim, items in dims.items():
        print(f"\n  [{dim}]  — {len(items)} template(s)")
        for item in items:
            print(f"    P{item[3]} [{item[1]:.2f}-{item[2]:.2f}]: {item[4][:90]}")

db.close()
