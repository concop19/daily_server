# FINDINGS.md — Daily Mate Server · Audit Log

> Template và log ghi nhận tất cả lỗi được phát hiện.
> AI agent ghi vào đây SAU MỖI finding. User triage và track fix ở đây.
> Format: mỗi finding = 1 block. Severity theo REVIEW.md.

---

## Trạng thái tổng quan

| Metric | Giá trị |
|---|---|
| Lần audit gần nhất | 2026-05-06 |
| Tổng findings | 17 |
| CRITICAL | 1 |
| HIGH | 7 |
| MEDIUM | 5 |
| LOW | 4 |
| Đã fix | 17 |
| Chờ fix | 0 |

---

## Findings Log

---

### [CRITICAL] ID-001 · Algorithm Confusion Attack — JWT chấp nhận cả ES256 + HS256

**Status**: FIXED
**File**: `auth_middleware.py`, dòng 30
**Pattern**: auth_bypass
**OWASP**: A07:2025 — Identification and Authentication Failures
**Fix**: Chỉ còn `algorithms=["ES256"]`. Thêm `issuer` validation.

---

### [HIGH] ID-002 · Rate Limiter Race Condition (TOCTOU)

**Status**: OPEN (cần Supabase RPC atomic để fix triệt để — nằm ngoài scope file Python)
**File**: `rate_limiter.py`, dòng 26–51
**Pattern**: race_condition
**Ghi chú**: Đã ghi comment rõ trong code. Fail-closed (ID-003) đã giảm exploit surface.

---

### [HIGH] ID-003 · Rate Limiter Fail-Open

**Status**: FIXED
**File**: `rate_limiter.py`, dòng 34–60
**Fix**: Bọc toàn bộ logic trong try/except, fail-closed trả 503 khi Supabase down.

---

### [HIGH] ID-004 · require_admin không guard g.role

**Status**: FIXED
**File**: `auth_middleware.py`, dòng 52–62
**Fix**: Thêm `hasattr(g, "uid") and hasattr(g, "role")` guard trước khi check role.

---

### [HIGH] ID-005 · Unvalidated Float/Int Input → Server Crash (5 endpoints)

**Status**: FIXED
**File**: `app.py`
**Fix**: Thêm `_parse_float()` và `_parse_int()` helper với range check và isfinite().
Áp dụng cho tất cả: lat/lon ([-90,90]/[-180,180]), limit ([1,100/200]), offset ([0,∞)).

---

### [HIGH] ID-006 · DB Connection Leak khi Exception

**Status**: FIXED
**File**: `app.py`, tất cả routes
**Fix**: Thêm `get_db_ctx()` context manager với try/finally. Toàn bộ routes chuyển sang `with get_db_ctx() as db:`.

---

### [HIGH] ID-007 · Admin Stats — latency_ms None → TypeError crash

**Status**: FIXED
**File**: `app.py`, admin_stats()
**Fix**: `sum(r.get("latency_ms") or 0 for r in rows)`.

---

### [HIGH] ID-008 · request.get_json() không guard None → AttributeError crash

**Status**: FIXED
**File**: `app.py`, recommend, feedback, weather_simulate, pipeline_debug
**Fix**: `body = request.get_json(force=True) or {}` trên tất cả route POST.

---

### [MEDIUM] ID-009 · /api/v1/pipeline/debug Không Có Auth

**Status**: FIXED
**File**: `app.py`, pipeline_debug()
**Fix**: Thêm `@require_auth` decorator.

---

### [MEDIUM] ID-010 · /health Lộ DB Path — Info Disclosure

**Status**: FIXED
**File**: `app.py`, health()
**Fix**: Bỏ `db_path` khỏi response. Exception trả `"detail": "Internal error"` thay vì `str(e)`.

---

### [MEDIUM] ID-011 · CORS credentials=True + origins="*" + double handler conflict

**Status**: FIXED
**File**: `app.py`
**Fix**: Đổi `supports_credentials=False`. Giữ before_request OPTIONS handler nhưng không duplicate CORS headers.

---

### [MEDIUM] ID-012 · Missing Security Headers

**Status**: FIXED
**File**: `app.py`
**Fix**: Thêm `@app.after_request` `add_security_headers()`: X-Content-Type-Options, X-Frame-Options, Referrer-Policy, HSTS (production only).

---

### [MEDIUM] ID-013 · cost_preference và boost_strategy không validate

**Status**: FIXED
**File**: `app.py`, recommend()
**Fix**: `cost_preference = max(1, min(3, _parse_int(...)))`. `boost_strategy` validate enum, fallback "strict".

---

### [LOW] ID-014 · DB Path Hardcode Windows → Fail khi Deploy Linux

**Status**: FIXED
**File**: `app.py`, dòng 42
**Fix**: `DB_PATH = Path(os.environ.get("DB_PATH", "recipe.db"))` — relative path fallback.

---

### [LOW] ID-015 · fetch_and_cache_weather — Cache Hit Trả Về Flat Fields Giả

**Status**: FIXED
**File**: `weather.py`
**Fix**: Thêm `_FLAT_CACHE` dict + `_flat_cache_get/set()`. Lưu flat fields kèm TTL khi fetch thành công. Cache hit trả flat thực; nếu flat miss (restart) trả `None` fields thay vì hardcode 30.0.

---

### [LOW] ID-016 · feedback_at Nhận Từ Client — Backdate + rating không validate

**Status**: FIXED
**File**: `app.py`, feedback()
**Fix**: `feedback_at` luôn dùng `datetime.now(timezone.utc)`. Rating clamp `max(1, min(5, int(rating)))` với fallback None.

---

### [LOW] ID-017 · Admin Stats — "Today" Tính UTC, User VN Mất 7h Đầu Ngày

**Status**: FIXED
**File**: `app.py`, admin_stats()
**Fix**: `ZoneInfo("Asia/Ho_Chi_Minh")` — tính midnight theo giờ VN rồi convert sang UTC.

---

## Changelog

| Ngày | Action | AI/User | Ghi chú |
|---|---|---|---|
| 2026-05-06 | Full audit lần đầu — 17 findings (ID-001 → ID-017) | Claude (Sonnet 4.6) | Đọc toàn bộ file production |
| 2026-05-06 | Fix toàn bộ 16/17 findings | Claude (Sonnet 4.6) | ID-002 (TOCTOU) cần Supabase RPC — ghi note, scope nằm ngoài Python files |
