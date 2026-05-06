# SECURITY.md — Daily Mate Server · Security Audit Checklist

> Mục tiêu: rà soát toàn bộ lỗ hổng bảo mật theo OWASP Top 10 (2025)
> và các pattern đặc thù của Flask + Supabase + SQLite.
> Mỗi mục có câu hỏi kiểm tra cụ thể và file liên quan.

---

## A. AUTHENTICATION & JWT (auth_middleware.py)

### A1. Algorithm Confusion Attack
- [ ] JWT decode cho phép cả ES256 và HS256 — kiểm tra xem attacker có thể
      gửi token HS256 dùng public key làm secret không
- [ ] `algorithms=["ES256", "HS256"]` — nên giới hạn chỉ 1 algorithm
- [ ] PyJWKClient có enforce algorithm matching từ JWKS header không?

### A2. Token Validation
- [ ] `audience="authenticated"` đã đủ chưa? Có cần thêm `issuer` không?
- [ ] Token expiry có được check không? (ExpiredSignatureError đã catch — OK)
- [ ] Replay attack: không có `jti` (JWT ID) blacklist cho revoked tokens

### A3. require_admin decorator
- [ ] `require_admin` đọc `g.role` nhưng KHÔNG gọi `require_auth` trước
      → nếu route chỉ dùng `@require_admin` mà quên `@require_auth`, g.role
      sẽ không tồn tại → AttributeError hoặc bypass
- [ ] Kiểm tra toàn bộ routes: route nào dùng @require_admin mà thiếu @require_auth?

### A4. JWKS Cache
- [ ] `cache_keys=True` — khi Supabase rotate key, cache có tự invalidate không?
- [ ] Nếu JWKS endpoint down, server xử lý thế nào?

---

## B. RATE LIMITING (rate_limiter.py)

### B1. Race Condition (TOCTOU)
- [ ] **CRITICAL**: Count-then-allow pattern không atomic
      → 2 request đồng thời đều thấy count=9 (max=10), cả 2 đều pass
      → Thực tế cho phép 2x max_calls trong burst
- [ ] Không có lock hay Redis atomic counter
- [ ] Giải pháp đề xuất: dùng Supabase RPC với atomic increment,
      hoặc Redis INCR + EXPIRE

### B2. Fail-Open Behavior
- [ ] Nếu Supabase timeout (2s), exception lan ra → route crash với 500
      thay vì rate limit → attacker có thể trigger DoS để bypass rate limit
- [ ] Cần thêm try/except trong rate_limiter, fail-closed: trả 429 khi Supabase down

### B3. Rate Limit Logging
- [ ] Rate limiter CHỈ đếm, không ghi log khi request bị từ chối
      → không có visibility vào ai đang bị rate limit
- [ ] Không có alert khi user liên tục bị 429

### B4. Rate Limit Scope
- [ ] Rate limit chỉ theo uid + endpoint name (f.__name__)
      → nếu 2 route khác nhau map vào cùng function name → conflict
- [ ] Không có global rate limit per IP (chỉ per uid)
      → unauthenticated endpoint có thể bị abuse không giới hạn

---

## C. INPUT VALIDATION & INJECTION (app.py)

### C1. Unvalidated Float Inputs
- [ ] `float(request.args.get("lat", 16.047))` — không có try/except
      → ?lat=abc → ValueError → 500 crash
- [ ] Không validate range: lat phải [-90, 90], lon phải [-180, 180]
      → lat=999 hoặc lat=NaN/Inf có thể gây undefined behavior trong pipeline
- [ ] Ảnh hưởng: /api/weather, /api/v1/challenge, /api/v1/pipeline/debug

### C2. Unvalidated Integer Inputs
- [ ] `int(request.args.get("limit", 20))` — không có try/except
      → ?limit=abc → ValueError → 500 crash
- [ ] `int(request.args.get("offset", 0))` — tương tự
- [ ] Negative limit/offset không bị chặn → undefined behavior trong SQL

### C3. SQL Injection
- [ ] Tất cả query đang dùng parameterized (?, ?) — TỐTVÌ
- [ ] Kiểm tra lại pipeline.py và weather.py có dùng f-string trong SQL không

### C4. JSON Body Parsing
- [ ] `request.get_json(force=True)` — nếu body không phải JSON hợp lệ → None
      → `.get()` trên None → AttributeError → 500
- [ ] Ảnh hưởng: /api/v1/recommend, /api/v1/feedback, /api/v1/pipeline/debug

### C5. dish_id Validation
- [ ] `dish_id` trong /api/v1/feedback là free-form string, không validate format
- [ ] `session_uuid` không validate format UUID

---

## D. AUTHORIZATION & ACCESS CONTROL (app.py routes)

### D1. Unprotected Endpoints
- [ ] `/api/v1/challenge` — NO AUTH — có thể scrape toàn bộ recommendation logic
- [ ] `/api/v1/dishes` — NO AUTH — expose full dish catalog không giới hạn
- [ ] `/api/v1/ingredients` — NO AUTH — expose full ingredient DB
- [ ] `/api/v1/locations` — NO AUTH — expose all provinces data
- [ ] `/api/v1/weather/simulate` — NO AUTH — free compute endpoint, abuse-able
- [ ] `/api/v1/pipeline/debug` — NO AUTH — expose internal scoring params,
      demand vectors, constraint profiles → information disclosure
- [ ] `/health` — NO AUTH — expose DB path, row counts → info disclosure

### D2. Horizontal Privilege Escalation
- [ ] `/api/v1/feedback`: user A có thể submit feedback với session_uuid của user B
      vì không có ownership check (chỉ check auth, không check uid == session owner)

### D3. Admin Route
- [ ] `/admin/stats` cần cả @require_auth VÀ @require_admin — đã có
- [ ] Kiểm tra: có admin route nào khác không require_admin không?

---

## E. CORS & HEADERS (app.py)

### E1. Wildcard CORS
- [ ] `origins="*"` trên tất cả /api/* và /admin/* với `supports_credentials=True`
      → Theo spec CORS, `credentials=True` + `origins="*"` bị browser reject
      → Nhưng nếu server chấp nhận → CSRF risk
- [ ] Production nên whitelist domain cụ thể thay vì "*"

### E2. Security Headers thiếu
- [ ] Không có X-Content-Type-Options: nosniff
- [ ] Không có X-Frame-Options
- [ ] Không có Content-Security-Policy
- [ ] Không có Strict-Transport-Security (HSTS)
- [ ] Khuyến nghị: dùng flask-talisman

### E3. Double CORS Handler
- [ ] Vừa dùng `CORS(app)` vừa có `@app.before_request` xử lý OPTIONS thủ công
      → 2 layer có thể conflict → duplicate headers hoặc logic gap

---

## F. SECRETS & CONFIG

### F1. Service Role Key Exposure
- [ ] SUPABASE_SERVICE_ROLE_KEY được dùng làm Bearer token trong mọi request
      → nếu bị log (ví dụ trong monitoring.py), key bị expose trong logs
- [ ] Key này nên chỉ dùng server-side, không bao giờ trả về client

### F2. .env trong Git
- [ ] Kiểm tra .gitignore có exclude .env không
- [ ] Kiểm tra git history: `git log --all --full-history -- .env`

### F3. DB Path Hardcode
- [ ] `r"D:\dream_project\...\recipe.db"` hardcode trong app.py
      → khi deploy lên server Linux → path Windows này sẽ fail silently

---

## G. ERROR HANDLING & INFO DISCLOSURE

### G1. Exception Leak
- [ ] `/health`: `return jsonify({"detail": str(e)})` → stack trace, DB path lộ ra
- [ ] `/api/v1/feedback`: `str(e)` được trả về client → leak internal error
- [ ] Nên dùng generic message ở production, log chi tiết server-side

### G2. Timing Attack
- [ ] Auth check có thể bị timing attack để detect valid vs invalid user IDs
      (nhỏ, nhưng đáng note)

---

## H. DEPENDENCY SECURITY

Kiểm tra các package sau (chạy `pip-audit` hoặc `safety check`):

```bash
pip install pip-audit
pip-audit -r requirements.txt
```

- [ ] `requests` — có CVE nào trong version đang dùng không?
- [ ] `PyJWT` — version >= 2.4.0 (fix algorithm confusion CVE-2022-29217)?
- [ ] `flask` — version >= 3.0?
- [ ] `flask-cors` — version mới nhất?

---

## Severity Reference

| Level | Ý nghĩa | Ví dụ |
|---|---|---|
| CRITICAL | Có thể exploit ngay, impact cao | Auth bypass, data leak |
| HIGH | Cần fix trước khi production | Race condition, no input validation |
| MEDIUM | Nên fix sớm | Info disclosure, missing headers |
| LOW | Best practice, không urgent | Deprecated API, minor hardening |
| INFO | Ghi nhận, không cần fix | Known quirk, technical debt |
