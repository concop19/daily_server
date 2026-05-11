"""
export_db_to_json.py -- Script chay 1 lan: xuat recipe.db -> JSON files.
Chay: python export_db_to_json.py
"""
import json
import sqlite3
from pathlib import Path
from datetime import datetime, timezone

DB_PATH = Path(r"D:\dream_project\daily_mate_code\daily_mate_all\database\recipe.db")
OUT_DIR = Path(__file__).parent / "data"
OUT_DIR.mkdir(exist_ok=True)


def to_dict_list(cursor, rows):
    cols = [d[0] for d in cursor.description]
    return [dict(zip(cols, row)) for row in rows]


def export_table(conn, table: str, out_file: str, order_by: str = None):
    cur = conn.cursor()
    q = f"SELECT * FROM {table}"
    if order_by:
        q += f" ORDER BY {order_by}"
    cur.execute(q)
    rows = to_dict_list(cur, cur.fetchall())
    payload = {
        "version": "1.0",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "table": table,
        "count": len(rows),
        "data": rows,
    }
    path = OUT_DIR / out_file
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  [OK] {table:<42} -> {out_file} ({len(rows)} rows)")
    return len(rows)


def main():
    if not DB_PATH.exists():
        print(f"[ERROR] DB not found: {DB_PATH}")
        return

    print(f"[EXPORT] Exporting {DB_PATH}")
    print(f"[EXPORT] Output dir: {OUT_DIR}\n")

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    tables = [
        ("dishes",                         "dishes.json",               "id"),
        ("ingredients",                    "ingredients.json",          "id"),
        ("dish_ingredient",                "dish_ingredients.json",     "id"),
        ("cooking_methods",                "cooking_methods.json",      "method_id"),
        ("vn_administrative_unit",         "provinces.json",            "id"),
        ("ingredient_availability_matrix", "availability_matrix.json",  None),
        ("advice_templates",               "advice_templates.json",     "id"),
    ]

    total = 0
    for (table, out_file, order_col) in tables:
        try:
            n = export_table(conn, table, out_file, order_by=order_col)
            total += n
        except Exception as e:
            print(f"  [ERR] {table}: {e}")

    tokens_path = OUT_DIR / "device_tokens.json"
    if not tokens_path.exists():
        init_payload = {
            "version": "1.0",
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "table": "device_tokens",
            "count": 0,
            "data": [],
        }
        tokens_path.write_text(json.dumps(init_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  [OK] device_tokens (init empty)            -> device_tokens.json (0 rows)")

    conn.close()
    print(f"\n[DONE] Export complete. Total rows: {total}")
    print(f"[DONE] Files in {OUT_DIR}:")
    for f in sorted(OUT_DIR.glob("*.json")):
        size_kb = f.stat().st_size / 1024
        print(f"   {f.name:<42} {size_kb:8.1f} KB")


if __name__ == "__main__":
    main()
