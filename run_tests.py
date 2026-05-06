"""
run_tests.py — Chạy 44 test cases gọi API /api/v1/recommend
Lưu kết quả chi tiết vào test_results.csv

Cách dùng:
  1. Tắt @require_auth trong app.py
  2. Chạy server: python app.py
  3. Chạy script này: python run_tests.py
"""

import csv
import json
import time
import requests
from datetime import datetime

BASE_URL = "http://localhost:5001"
INPUT_CSV = "test_cases.csv"
OUTPUT_CSV = "test_results.csv"

# ── Helpers ───────────────────────────────────────────────────────────────────

def parse_list(val: str) -> list:
    """'a;b;c' → ['a','b','c'], '' → []"""
    if not val or not val.strip():
        return []
    return [x.strip() for x in val.split(";") if x.strip()]

def parse_int_list(val: str) -> list:
    items = parse_list(val)
    result = []
    for x in items:
        try:
            result.append(int(x))
        except ValueError:
            pass
    return result

def build_payload(row: dict) -> dict:
    health = parse_list(row["health_conditions"])
    allergies = parse_list(row["allergies"])
    tastes = parse_list(row["taste_preferences"])
    recent = parse_int_list(row["recent_dish_ids"])
    basket_ids = parse_int_list(row["basket_ids"])

    payload = {
        "lat": float(row["lat"]),
        "lon": float(row["lon"]),
        "cuisine_scope": row["cuisine_scope"] or "vietnam",
        "dish_type_filter": {"main": "main_dish"}.get(row["dish_type_filter"], row["dish_type_filter"] or "all"),
        "cost_preference": int(row["cost_preference"] or 2),
        "recent_dish_ids": recent,
        "market_basket": {
            "selected_ingredient_ids": basket_ids,
            "is_skipped": len(basket_ids) == 0,
            "boost_strategy": "strict" if basket_ids else "none",
        },
        "personal": {
            "age": int(row["age"]),
            "gender": row["gender"],
            "height": float(row["height"]),
            "weight": float(row["weight"]),
            "activity_level": row["activity_level"],
            "health_condition": health,
            "diet_type": row["diet_type"] or "omnivore",
            "allergies": allergies,
            "taste_preference": tastes,
            "max_prep_time": int(row["max_prep_time"] or 60),
        },
        # Override weather bằng giá trị manual từ CSV
        "weather": {
            "temperature": float(row["temp"]),
            "humidity": float(row["humidity"]),
            "wind_speed": float(row["wind_kph"]),
            "aqi": int(row["aqi"]) if row.get("aqi", "").strip() else 50,
            "pressure": 1013,
            "uv_index": 5,
        },
    }
    return payload

def call_recommend(payload: dict) -> tuple[dict | None, str, float]:
    """Trả về (response_json, error_msg, elapsed_s)"""
    t0 = time.time()
    try:
        resp = requests.post(
            f"{BASE_URL}/api/v1/recommend",
            json=payload,
            timeout=30,
        )
        elapsed = round(time.time() - t0, 3)
        if resp.status_code == 200:
            return resp.json(), "", elapsed
        else:
            return None, f"HTTP {resp.status_code}: {resp.text[:200]}", elapsed
    except Exception as e:
        elapsed = round(time.time() - t0, 3)
        return None, str(e), elapsed

def extract_summary(data: dict) -> dict:
    """Rút gọn response thành các trường cần đánh giá."""
    if not data:
        return {}

    ranked = data.get("ranked_dishes", [])
    top5 = ranked[:5]

    summary = {
        "dish_pool_size": data.get("dish_pool_size", 0),
        "ranked_count": len(ranked),
        "elapsed_s": data.get("elapsed_s", 0),
        "location_province": data.get("location", {}).get("province", ""),
        "location_region": data.get("location", {}).get("food_region", ""),
        "weather_vector": json.dumps(data.get("weather_vector", {}), ensure_ascii=False),
        "demand_snapshot": json.dumps(data.get("demand_snapshot", {}), ensure_ascii=False),
        "top5_dishes": json.dumps(
            [
                {
                    "rank": d.get("rank"),
                    "dish_id": d.get("dish_id"),
                    "title": d.get("title"),
                    "final_score": d.get("final_score"),
                    "cook_time_min": d.get("cook_time_min"),
                    "score_breakdown": d.get("score_breakdown", {}),
                    "explanation_headline": (d.get("explanation") or {}).get("headline", ""),
                    "explanation_weather": (d.get("explanation") or {}).get("weather_reason", ""),
                    "explanation_dish": (d.get("explanation") or {}).get("dish_match", ""),
                    "tags": (d.get("explanation") or {}).get("tags", []),
                }
                for d in top5
            ],
            ensure_ascii=False,
        ),
        "fallback_used": len(data.get("fallback_ids", [])) > 0,
    }
    return summary

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    # Đọc test cases
    with open(INPUT_CSV, newline="", encoding="utf-8") as f:
        cases = list(csv.DictReader(f))

    print(f"[INFO] Loaded {len(cases)} test cases từ {INPUT_CSV}")
    print(f"[INFO] Server: {BASE_URL}")
    print(f"[INFO] Output: {OUTPUT_CSV}")
    print("-" * 60)

    # Kiểm tra server sống không
    try:
        health = requests.get(f"{BASE_URL}/health", timeout=5).json()
        print(f"[OK] Server alive — dishes={health.get('dishes')}, ingr={health.get('ingredients')}")
    except Exception as e:
        print(f"[ERROR] Server không phản hồi: {e}")
        print("  → Hãy chạy: python app.py  (và đảm bảo đã tắt @require_auth)")
        return

    results = []

    for i, row in enumerate(cases):
        test_id = row["test_id"]
        desc = row["description"]
        note = row["note"]
        print(f"[{i+1:02d}/{len(cases)}] {test_id} — {desc}")

        payload = build_payload(row)
        data, error, elapsed = call_recommend(payload)

        result_row = {
            "test_id": test_id,
            "description": desc,
            "note": note,
            "status": "OK" if data else "ERROR",
            "error_msg": error,
            "elapsed_s": elapsed,
            "dish_pool_size": "",
            "ranked_count": "",
            "location_province": "",
            "location_region": "",
            "weather_vector": "",
            "demand_snapshot": "",
            "top5_dishes": "",
            "fallback_used": "",
            "payload_sent": json.dumps(payload, ensure_ascii=False),
        }

        if data:
            summary = extract_summary(data)
            result_row.update(summary)
            print(f"  → pool={summary['dish_pool_size']} ranked={summary['ranked_count']} "
                  f"elapsed={elapsed}s loc={summary['location_province']}")
        else:
            print(f"  → ERROR: {error}")

        results.append(result_row)
        time.sleep(0.3)  # tránh quá tải server

    # Ghi output
    fieldnames = [
        "test_id", "description", "note",
        "status", "error_msg", "elapsed_s",
        "dish_pool_size", "ranked_count",
        "location_province", "location_region",
        "weather_vector", "demand_snapshot",
        "top5_dishes", "fallback_used",
        "payload_sent",
    ]

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    ok_count = sum(1 for r in results if r["status"] == "OK")
    err_count = sum(1 for r in results if r["status"] == "ERROR")
    print("-" * 60)
    print(f"[DONE] {ok_count} OK / {err_count} ERROR → {OUTPUT_CSV}")
    print(f"[DONE] Thời gian: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

if __name__ == "__main__":
    main()
