import sqlite3, sys
sys.stdout.reconfigure(encoding='utf-8')
db = sqlite3.connect(r'D:\dream_project\daily_mate_code\demo_server\recipe.db')
rows = db.execute('SELECT context_type, trigger_dim, template_text, priority FROM advice_templates ORDER BY context_type, trigger_dim').fetchall()
print("=== ALL TEMPLATES ===")
for r in rows:
    print(f"[{r[0]}/{r[1]}] P{r[3]}: {r[2][:120]}")
print(f"\nTotal: {len(rows)} templates")

# Check weather templates
print("\n=== WEATHER section (missing!) ===")
rows2 = db.execute("SELECT * FROM advice_templates WHERE context_type='weather'").fetchall()
print(f"Weather templates: {len(rows2)}")

# Check season templates
print("\n=== SEASON section (missing!) ===")
rows3 = db.execute("SELECT * FROM advice_templates WHERE context_type='season'").fetchall()
print(f"Season templates: {len(rows3)}")
