# REVIEW.md — Daily Mate Server · AI Code Review Rules

> File này inject vào mọi AI review agent với priority cao nhất.
> Rules ở đây OVERRIDE default review behavior.
> Tham khảo chuẩn: Anthropic Code Review docs + OWASP Top 10 (2025) + CWE Top 25.

---

## 1. Severity Definitions (Custom cho project này)

### CRITICAL — Phải fix TRƯỚC khi production
- Auth bypass hoặc privilege escalation
- Key/secret lộ ra ngoài (log, response, git)
- SQL injection hoặc command injection có thể exploit
- Unhandled crash trên production route

### HIGH — Fix trong sprint hiện tại
- Race condition có thể exploit (rate limit bypass)
- Unvalidated user input gây server crash (ValueError/TypeError)
- Endpoint nhạy cảm không có auth
- Connection/resource leak (DB, file handle)

### MEDIUM — Backlog ưu tiên cao
- Missing security headers (HSTS, CSP, X-Frame-Options)
- Info disclosure qua error message
- Logic inconsistency trong scoring/filtering
- Silent exception handling che giấu lỗi

### LOW — Best practice
- Deprecated API usage (datetime.utcnow)
- Code duplication giữa các route
- Missing input range validation (không crash nhưng undefined behavior)

### INFO — Ghi nhận, không cần action
- Known quirks đã document trong CLAUDE.md
- Style/convention issues
- Technical debt không urgent

---

## 2. Findings Cap (tránh noise)

- Tối đa **5 findings MEDIUM** mỗi file — gộp các instance tương tự vào 1 finding
- Tối đa **10 findings tổng** mỗi lần review — ưu tiên severity cao
- CRITICAL và HIGH không có cap — báo cáo tất cả

---

## 3. Skip Rules — KHÔNG flag những thứ này

```
- __pycache__/          ← generated
- backup/               ← không dùng trong production
- *.pyc                 ← compiled
- run_tests.py          ← test runner, không phải production code
- check_*.py            ← maintenance scripts
- patch_*.py            ← migration scripts, one-off
- seed_*.py             ← data seeding, one-off
- sync_templates.py     ← sync script
- setup_supabase.py     ← setup script
```

Với các file migration/setup: chỉ flag nếu **severity CRITICAL** (ví dụ: hardcoded password).

---

## 4. Repo-Specific Rules — Phải flag trên mọi PR

```
[ ] Mọi route mới PHẢI có @require_auth (trừ /health)
[ ] Mọi float/int từ request.args PHẢI có try/except và range check
[ ] Mọi request.get_json() PHẢI có None check trước khi .get()
[ ] Mọi DB connection PHẢI được close trong finally block
[ ] SUPABASE_SERVICE_ROLE_KEY KHÔNG được xuất hiện trong logs hay responses
[ ] Mọi route POST mới PHẢI có rate limiting
[ ] Endpoint /admin/* PHẢI có cả @require_auth VÀ @require_admin
```

---

## 5. Patterns để tìm chủ động

### 5.1 Fail-Open Patterns (HIGH)
```python
# NGUY HIỂM: nếu external call fail → pass through
try:
    count = check_rate_limit()
except:
    pass  # ← fail open, bypass rate limit
```

### 5.2 Unguarded Type Conversion (HIGH)
```python
# NGUY HIỂM: crash với input không hợp lệ
float(request.args.get("lat"))    # ← thiếu try/except
int(request.args.get("limit"))    # ← thiếu try/except
```

### 5.3 DB Connection Leak (HIGH)
```python
# NGUY HIỂM: db.close() bị skip khi exception
db = get_db()
result = db.execute(...)    # ← nếu crash ở đây
db.close()                  # ← bị bỏ qua
```

### 5.4 f-string trong SQL (CRITICAL nếu có)
```python
# NGUY HIỂM: SQL injection
db.execute(f"SELECT * FROM dishes WHERE nation='{nation}'")
# AN TOÀN:
db.execute("SELECT * FROM dishes WHERE nation=?", (nation,))
```

### 5.5 Secret trong Response (CRITICAL)
```python
# NGUY HIỂM: trả config/secret về client
return jsonify({"config": os.environ})
```

### 5.6 Decorator Order (HIGH)
```python
# SAI: require_admin chạy trước require_auth → g.role chưa được set
@app.route("/admin/x")
@require_admin     # ← sai thứ tự
@require_auth
def admin_x():
    ...

# ĐÚNG:
@app.route("/admin/x")
@require_auth      # ← phải trước
@require_admin
def admin_x():
    ...
```

---

## 6. Output Format Bắt buộc

Mỗi finding phải theo format:

```
### [SEVERITY] Tên ngắn gọn

**File**: `tên_file.py`, dòng N
**Pattern**: loại lỗi (input validation / auth / race condition / ...)
**Mô tả**: giải thích lỗi và tại sao nguy hiểm
**Reproduce**: cách trigger lỗi (nếu có)
**Fix đề xuất**: code snippet hoặc hướng dẫn cụ thể
```

---

## 7. Không flag những thứ này (false positive suppression)

- `OPTIONS` bypass auth → đã document là cố ý (CORS)
- `_random.seed()` trong challenge → không cần CSPRNG, cố ý
- `algorithms=["ES256", "HS256"]` → Supabase dùng cả 2, nhưng CẦN check algorithm confusion riêng
- `datetime.utcnow()` → technical debt, không phải security issue
- CORS `origins="*"` chỉ INFO nếu không có `credentials=True`; nhưng là HIGH nếu có cả 2

---

## 8. Khi nào DỪNG và hỏi user

1. Logic nghiệp vụ không rõ (ví dụ: tại sao fallback cascade có 3 levels?)
2. Finding liên quan đến production DB schema không thấy trong code
3. Phát hiện potential backdoor hoặc intentional vulnerability
4. Cần chạy code để confirm finding → PHẢI hỏi trước
