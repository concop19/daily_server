# LOGIC.md — Daily Mate Server · Business Logic Audit Checklist

> Mục tiêu: phát hiện lỗi logic ẩn, edge case không được xử lý,
> và hành vi không nhất quán trong recommendation engine.
> Không phải security issue nhưng ảnh hưởng UX, độ chính xác và reliability.

---

## A. RATE LIMITER LOGIC

### A1. Request KHÔNG được log sau khi pass
- [ ] rate_limiter.py đếm request nhưng KHÔNG ghi log sau khi cho phép
      → logging phải nằm ở monitoring.py
      → Kiểm tra: monitoring.py có được gọi TRƯỚC hay SAU rate_limit decorator?
      → Thứ tự decorator ảnh hưởng đến request có được log không khi bị 429

### A2. Window Boundary
- [ ] Sliding window dùng `now() - window_seconds` — chính xác
- [ ] Nhưng nếu server clock drift với Supabase clock → window sai
- [ ] Không có sync mechanism

---

## B. RECOMMENDATION PIPELINE LOGIC (pipeline.py)

### B1. Fallback Cascade
```python
# Trong recommend():
if basket_for_filter and len(full_pool) == 0:    # fallback 1: bỏ basket filter
    full_pool = filter_dishes(...)
if not dish_pool:                                  # fallback 2: bỏ dish_type_filter
    dish_pool = filter_dishes(..., "all")
if not dish_pool:                                  # fallback 3: bỏ cuisine_scope
    dish_pool = filter_dishes("global", ...)
```
- [ ] Fallback cascade có thể trả về món hoàn toàn không phù hợp với user profile
- [ ] User không được thông báo fallback đã xảy ra (trong response có flag không?)
- [ ] Kiểm tra: response JSON có trường nào indicate fallback level không?

### B2. Score Manipulation
- [ ] `score_dish()` nhận input từ user body (personal, weather, basket)
      → user có thể craft request để boost score của món cụ thể
- [ ] Ví dụ: gửi fake weather vector → ảnh hưởng demand → thay đổi ranking
- [ ] `/api/v1/weather/simulate` không cần auth → bất kỳ ai có thể test manipulation

### B3. recent_dish_ids Anti-repetition
- [ ] `recent_dish_ids_ordered` được nhận từ client, không được verify
      → client có thể gửi empty list để reset anti-repetition filter
      → hoặc gửi fake IDs để suppress món cụ thể khỏi kết quả
- [ ] Không có server-side storage của recent dishes per user

### B4. basket_ingredient_ids Validation
- [ ] `{int(x) for x in basket.get("selected_ingredient_ids", []) if str(x).strip().isdigit()}`
- [ ] Ingredient IDs không được verify tồn tại trong DB
      → gửi IDs không tồn tại → filter_dishes sẽ trả pool rỗng → trigger fallback
- [ ] Có thể exploit để force fallback và get global dish pool

### B5. cost_preference
- [ ] `int(body.get("cost_preference", 2))` — không validate range
- [ ] cost_preference=999 → undefined behavior trong scoring
- [ ] Nên clamp về [1, 3] hoặc validate enum

---

## C. WEATHER INTEGRATION (weather.py)

### C1. External API Dependency
- [ ] Nếu weather API down, `fetch_and_cache_weather` trả về gì?
- [ ] Có fallback weather vector không? Hay return error?
- [ ] `/api/weather` trả 200 kèm "warning" khi cache miss + API down — user nhận data gì?

### C2. Weather Cache Poisoning
- [ ] Cache key dựa trên lat/lon rounded — nếu rounding không consistent → cache miss
- [ ] Kiểm tra: `round(lat, 1)` hay `round(lat, 2)`? Consistency với rate_limiter?

### C3. Weather Override
- [ ] `body.get("weather")` trong /recommend cho phép client override weather data
- [ ] Không validate weather vector format/range
- [ ] wind_speed=-1, temperature=999 → undefined behavior trong compute_weather_vector

---

## D. SCORING EDGE CASES (pipeline.py)

### D1. Division by Zero
- [ ] `sum(r["latency_ms"] for r in rows) / max(len(rows), 1)` — đã handle
- [ ] Kiểm tra trong score_dish() và rank_and_explain(): có phép chia nào không guard không?

### D2. Empty dish_pool
- [ ] Sau toàn bộ fallback cascade, nếu vẫn empty → response ra sao?
- [ ] Kiểm tra: có return 404/503 hay return empty ranked_dishes list?
- [ ] Client có handle empty list không?

### D3. Negative/Zero Weights
- [ ] `weights = [max(scores.get(d["id"], 0.01), 0.01) for d in dish_pool]`
      trong /challenge — đã guard bằng max(..., 0.01) — OK
- [ ] Kiểm tra /recommend có guard tương tự không

### D4. Boost Strategy
- [ ] `boost_strategy` nhận từ client: "strict" / "none" / ?
- [ ] Có validate enum không? boost_strategy="sql_injection_attempt" → crash?

---

## E. DATABASE LOGIC (app.py + pipeline.py)

### E1. JSON DataStore consistency
- [ ] `data_store.load_all()` phải chạy trước khi route xử lý request
- [ ] Các dataset read-only nên được index bằng dict để giữ tốc độ lookup
- [ ] Các thao tác ghi `device_tokens.json` phải dùng `_tokens_lock`
- [ ] Lỗi đọc/parse JSON phải được báo rõ khi server khởi động, không âm thầm dùng dataset rỗng

### E2. JSON persistence và concurrency
- [ ] Ghi file phải dùng UTF-8 và payload JSON hợp lệ
- [ ] Không để nhiều Gunicorn worker cùng ghi `device_tokens.json`; production nên dùng một worker hoặc storage dùng chung
- [ ] Khi file ghi lỗi, không được làm mất toàn bộ token đang có trong memory

### E3. dish_detail JSON Parsing
```python
for f in ("allergen_summary", "season_suitability", ...):
    try:
        dish[f] = json.loads(dish[f] or "null")
    except Exception:
        pass  # silent fail
```
- [ ] Silent fail khi JSON malformed → field bị bỏ qua, không báo lỗi
- [ ] Client nhận thiếu field mà không biết

---

## F. MONITORING & OBSERVABILITY (monitoring.py)

- [ ] Request log có ghi uid không? (Cần để debug per-user issues)
- [ ] Response body có được log không? (Có thể chứa PII)
- [ ] Latency đo từ đâu đến đâu? Có include DB query time không?
- [ ] Khi monitoring.py ghi log fail, request vẫn hoàn thành không?

---

## G. FEEDBACK ENDPOINT LOGIC

### G1. Feedback Integrity
- [ ] `feedback_at` lấy từ client body — client có thể backdate feedback
- [ ] Không validate rating range (nếu action="rated"): rating=999 hoặc rating=-1
- [ ] `session_uuid` không được validate là UUID format
- [ ] Không verify dish_id tồn tại trong DB trước khi ghi Supabase

### G2. Duplicate Feedback
- [ ] Không có dedup check: user có thể gửi cùng feedback nhiều lần
- [ ] Không có idempotency key

---

## H. ADMIN STATS LOGIC

### H1. Data Aggregation
```python
"avg_latency_ms": round(sum(r["latency_ms"] for r in rows) / max(len(rows), 1), 1)
```
- [ ] Nếu `latency_ms` là None cho một số rows → TypeError khi sum()
- [ ] Nên: `sum(r["latency_ms"] or 0 for r in rows)`

### H2. Time Boundary
- [ ] Stats tính từ `today_iso` (UTC midnight)
- [ ] Nếu server ở UTC+7, "today" theo UTC vs local time khác nhau 7h
- [ ] User ở VN có thể thấy stats "hôm nay" thiếu 7h đầu ngày
