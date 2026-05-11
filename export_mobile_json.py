"""
export_mobile_json.py
Tạo 2 file JSON slim dùng cho mobile app:
  1. mobile_ingredients.json  — chỉ giữ id/name/name_en/category (MarketBasket)
  2. mobile_provinces.json    — transform provinces sang format mobile cần (TasteProfile)

Chạy: python export_mobile_json.py
Output: data/mobile_ingredients.json, data/mobile_provinces.json
"""
import json, pathlib, sys

BASE = pathlib.Path(__file__).parent / "data"

REGION_LABEL = {
    "red_river_delta":   "Vừa phải, thanh đạm",
    "northern_highland": "Đậm, chua, mắm",
    "central_coast":     "Cay, mặn đậm",
    "central_highland":  "Nhẹ, ít gia vị",
    "southeast":         "Ngọt vừa, đa dạng",
    "mekong_delta":      "Ngọt, cốt dừa, béo",
    "urban_major":       "Fusion, đa dạng",
}

def region_label(food_region):
    return REGION_LABEL.get(food_region, "Đa dạng")

# ── 1. Ingredients slim ────────────────────────────────────────────────────────
src_ing = BASE / "ingredients.json"
if not src_ing.exists():
    print(f"[ERROR] Không tìm thấy {src_ing}"); sys.exit(1)

with open(src_ing, encoding="utf-8") as f:
    raw = json.load(f)

slim_ing = []
for item in raw["data"]:
    slim_ing.append({
        "id":       item["id"],
        "name":     item.get("name", ""),
        "name_en":  item.get("name_en", ""),
        "category": item.get("category", "other"),
    })

out_ing = {
    "version":     "1.0",
    "exported_at": raw["exported_at"],
    "count":       len(slim_ing),
    "data":        slim_ing,
}
out_ing_path = BASE / "mobile_ingredients.json"
with open(out_ing_path, "w", encoding="utf-8") as f:
    json.dump(out_ing, f, ensure_ascii=False, indent=2)
print(f"[OK] ingredients: {len(slim_ing)} items  ->  {out_ing_path}")

# ── 2. Provinces transform ─────────────────────────────────────────────────────
src_prov = BASE / "provinces.json"
if not src_prov.exists():
    print(f"[ERROR] Không tìm thấy {src_prov}"); sys.exit(1)

with open(src_prov, encoding="utf-8") as f:
    raw_p = json.load(f)

slim_prov = []
for item in raw_p["data"]:
    rf = item.get("regional_flavor", "{}")
    if isinstance(rf, str):
        try:
            rf = json.loads(rf)
        except Exception:
            rf = {}

    food_region = item.get("food_region", "")
    slim_prov.append({
        "id":                    item["id"],
        "name":                  item.get("province_name", ""),
        "food_region":           food_region,
        "climate_type":          item.get("climate_type", ""),
        "cuisine_culture":       item.get("cuisine_culture", ""),
        "taste":                 rf,
        "regional_flavor_label": region_label(food_region),
    })

out_prov = {
    "version":     "1.0",
    "exported_at": raw_p["exported_at"],
    "count":       len(slim_prov),
    "data":        slim_prov,
}
out_prov_path = BASE / "mobile_provinces.json"
with open(out_prov_path, "w", encoding="utf-8") as f:
    json.dump(out_prov, f, ensure_ascii=False, indent=2)
print(f"[OK] provinces : {len(slim_prov)} items  ->  {out_prov_path}")
