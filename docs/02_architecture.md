# Daily Mate — Demo Server
# Architecture

**Ngày tạo:** 2026-05-06
**Phiên bản:** Demo / MVP

---

## 1. Tổng quan kiến trúc

Daily Mate Demo Server theo kiến trúc **Monolithic Flask App** với phân tách
rõ ràng theo trách nhiệm qua các module Python. Toàn bộ logic gợi ý chạy
in-process, không có message queue hay microservice.

```
┌─────────────────────────────────────────────────────┐
│                   CLIENT (Mobile / Web)              │
└───────────────────────┬─────────────────────────────┘
                        │ HTTPS + JWT Bearer Token
                        ▼
┌─────────────────────────────────────────────────────┐
│              FLASK APPLICATION (app.py)             │
│  ┌──────────────┐  ┌─────────────┐  ┌────────────┐ │
│  │ Auth Middle  │  │ Rate Limiter│  │ Monitoring │ │
│  │ (auth_middle │  │(rate_limiter│  │(monitoring │ │
│  │  ware.py)    │  │  .py)       │  │  .py)      │ │
│  └──────────────┘  └─────────────┘  └────────────┘ │
│                                                     │
│  ┌───────────────────────────────────────────────┐  │
│  │           RECOMMENDATION PIPELINE            │  │
│  │                 (pipeline.py)                │  │
│  │  Location → Personal → Demand → Constraint  │  │
│  │  → Filter → Score → Rank → Explain          │  │
│  └───────────────────────────────────────────────┘  │
│                                                     │
│  ┌─────────────────┐   ┌──────────────────────────┐ │
│  │   weather.py    │   │    advice_engine.py      │ │
│  │  (Weather API   │   │  (Explanation Builder)   │ │
│  │   + Cache)      │   │                          │ │
│  └─────────────────┘   └──────────────────────────┘ │
└──────────┬──────────────────────────┬───────────────┘
           │                          │
           ▼                          ▼
┌──────────────────┐      ┌────────────────────────┐
│  SQLite (local)  │      │  Supabase (cloud PG)   │
│  recipe.db       │      │  - session_feedback    │
│  - dishes        │      │  - request_log         │
│  - ingredients   │      │  - auth (JWT/JWKS)     │
│  - locations     │      └────────────────────────┘
│  - weather_cache │
│  - advice_tmpls  │
└──────────────────┘
           │
           ▼
┌──────────────────┐
│ OpenWeatherMap   │
│   API (ngoài)    │
└──────────────────┘
```

---

## 2. Các module và trách nhiệm


### 2.1 app.py — Entry Point & HTTP Layer
**Trách nhiệm:** Khởi tạo Flask app, định nghĩa routes, kết nối DB, xử lý CORS/preflight.

- Tạo kết nối SQLite mỗi request qua get_db() (không dùng connection pool)
- Xử lý tất cả OPTIONS preflight trả 204 trước khi middleware chạy
- Fallback DB: nếu DB_PATH không tồn tại, copy từ bundled recipe.db
- Giao tiếp với Supabase qua requests thẳng (không ORM)

**Routes quan trọng:**
- POST /api/v1/recommend → gọi toàn bộ pipeline
- GET /api/v1/challenge → pipeline rút gọn + seeded random
- POST /api/v1/feedback → write thẳng vào Supabase REST

---

### 2.2 pipeline.py — Recommendation Logic
**Trách nhiệm:** Toàn bộ logic gợi ý 9 bước (Steps 01–09).

**Các hàm chính:**
- resolve_location() — Tìm tỉnh/thành gần nhất theo Haversine
- compute_personal_vector() — Tính BMI, TDEE, disease_flags, taste_weight
- compute_demand() — Tính nhu cầu sinh lý từ weather vector + personal vector
- build_constraint_profile() — Tổng hợp ràng buộc cứng (sodium limit, GL limit, allergy)
- filter_dishes() — Lọc pool món theo tất cả ràng buộc cứng (O(n) pass)
- compute_soft_mult() — Hệ số mềm: prep time, mùa vụ, cost preference
- compute_dish_boost() — Basket coverage boost từ nguyên liệu người dùng
- score_dish() — Tính điểm cuối: demand (50–65%) + disease (0–15%) + taste (15%) + loc (10%) + boost (10%)
- rank_and_explain() — Xếp hạng + gọi advice_engine cho mỗi món

**Hàm nội bộ quan trọng:**
- _compute_disease_score() — Tổng hợp sodium_safety, gl_safety, gout_risk
- resolve_allergy_ingredient_ids() — Map allergy groups → ingredient IDs
- _get_dish_ingredient_ids() — Batch query N+1 prevention

---

### 2.3 weather.py — Weather Data Layer
**Trách nhiệm:** Fetch, cache và tính toán weather vector.

**Luồng ưu tiên cache:**
  Override dict → In-memory cache (_WEATHER_CACHE) → SQLite DB → OpenWeather API → Hardcode fallback

**Hàm chính:**
- compute_weather_vector() — Chuẩn hoá 7 biến khí tượng → 6 chỉ số [0,1]
- fetch_and_cache_weather() — Dùng cho GET /api/weather (trả full flat + vector)
- get_or_compute_weather() — Dùng nội bộ trong pipeline (trả chỉ vector)
- _adaptive_ttl() — TTL ngắn hơn khi thời tiết cực đoan
- _grid_key() — Snap GPS vào ô lưới 0.1° để tối ưu cache hit

---

### 2.4 advice_engine.py — Explanation Builder
**Trách nhiệm:** Sinh object giải thích JSON cho mỗi món gợi ý.

**Kiến trúc nội bộ:**
- FitChecker: kiểm tra 9 khía cạnh (weather x4, disease x3, BMI x2, location/season)
  với hard threshold trước khi cho phép sinh giải thích
- _query_templates() — Query DB lấy template theo (context_type, trigger_dim, intensity)
- _build_ingredient_source_note() — Truy nguyên chỉ số từ nguyên liệu chính
- build_explanation() — Hàm public: assemble tất cả lý do active thành dict 7 chiều

---

### 2.5 auth_middleware.py — Authentication
**Trách nhiệm:** Xác thực JWT Supabase cho mọi protected route.

- Dùng PyJWKClient để fetch và cache public key tự động từ Supabase JWKS endpoint
- Hỗ trợ cả ES256 và HS256 (tương thích nhiều phiên bản Supabase)
- g.uid, g.email, g.role được set vào Flask request context
- require_admin() decorator kiểm tra g.role == "admin"
- OPTIONS request bypass auth để CORS preflight luôn pass

---

### 2.6 monitoring.py — Request Logging
**Trách nhiệm:** Ghi log mỗi HTTP request vào Supabase sau khi response xong.

- before_request: lưu timestamp bắt đầu vào g.req_start
- after_request: tính latency_ms, ghi vào Supabase bảng request_log
- Timeout 2s và try/except để log failure không crash app chính
- Bỏ qua /health và static

---

### 2.7 rate_limiter.py — Rate Limiting
**Trách nhiệm:** Giới hạn số request per user per window.

- In-process dict theo uid (từ g.uid sau auth)
- @rate_limit(max_calls=10, window_seconds=60) decorator
- Chỉ áp dụng trên POST /api/v1/recommend


---

## 3. Cấu trúc dữ liệu chính

### 3.1 Weather Vector (dict)
```
{
  "heat_stress_index":     float [0,1],   # nóng + ẩm
  "dehydration_risk":      float [0,1],   # nguy cơ mất nước
  "cold_stress_index":     float [0,1],   # lạnh + gió
  "oxidative_stress_risk": float [0,1],   # UV + AQI + mùa hè
  "infection_risk":        float [0,1],   # áp suất thấp + AQI
  "immune_load":           float [0,1]    # tổng tải miễn dịch
}
```

### 3.2 Personal Vector (dict)
```
{
  "BMI": float,
  "bmr": float,
  "energy_need": float,          # TDEE (kcal/day)
  "disease_flags": {             # boolean flags
    "hypertension": bool,
    "diabetes": bool,
    "gout": bool,
    "ibs": bool
  },
  "taste_weight": dict,          # {spicy, sweet, sour, umami, salty, bitter, astringent}
  "diet_type": str,              # omnivore | vegan | vegetarian
  "allergies": list,
  "max_prep_time": int
}
```

### 3.3 Dish Score Breakdown
```
Không có bệnh:
  final = 0.65 * demand_score
        + 0.15 * taste_score
        + 0.10 * loc_bonus
        + 0.10 * ingredient_boost
        * soft_mult * repetition_decay

Có bệnh:
  final = 0.50 * demand_score
        + 0.15 * disease_score
        + 0.15 * taste_score
        + 0.10 * loc_bonus
        + 0.10 * ingredient_boost
        * soft_mult * repetition_decay
```

### 3.4 Recommend Response (JSON)
```json
{
  "status": "ok",
  "elapsed_s": 0.123,
  "location": { "province": "...", "food_region": "...", "climate_type": "..." },
  "weather_vector": { ... },
  "demand_snapshot": { ... },
  "ranked_dishes": [
    {
      "rank": 1,
      "dish_id": 123,
      "title": "Canh chua cá lóc",
      "final_score": 0.876,
      "score_breakdown": { "hydration": 0.7, "warming": 0.2, "boost": 0.3 },
      "cook_time_min": 30,
      "serving_suggestion": "Ăn kèm nước dừa tươi",
      "explanation": {
        "headline": "...",
        "weather_reason": "...",
        "dish_match": "...",
        "nutrition_note": null,
        "ingredient_note": null,
        "seasonal_note": "...",
        "tags": ["cooling", "hydration"]
      }
    }
  ],
  "page_size": 10,
  "fallback_ids": [...]
}
```

---

## 4. Dependency Map

```
app.py
  ├── auth_middleware.py  (require_auth, require_admin)
  ├── monitoring.py       (init_monitoring)
  ├── rate_limiter.py     (rate_limit)
  ├── weather.py          (fetch_and_cache_weather, get_or_compute_weather,
  │                        compute_weather_vector, get_current_season)
  └── pipeline.py         (filter_dishes, score_dish, rank_and_explain, ...)
        ├── weather.py    (compute_weather_vector, get_current_season)
        └── advice_engine.py  (build_explanation)
```

---

## 5. Môi trường & Biến môi trường

| Biến | Bắt buộc | Mô tả |
|---|---|---|
| SUPABASE_URL | Có | URL Supabase project |
| SUPABASE_SERVICE_ROLE_KEY | Có | Service role key để ghi log + admin stats |
| OPENWEATHER_API_KEY | Không | API key OpenWeatherMap (fallback nếu thiếu) |
| DB_PATH | Không | Đường dẫn tuyệt đối tới recipe.db (mặc định: bundled) |

---

## 6. Môi trường chạy

- **Development:** `python app.py` — Flask dev server cổng 5001
- **Production:** `gunicorn app:app` via Procfile
- **DB init:** Tự động copy bundled recipe.db nếu DB_PATH chưa tồn tại
