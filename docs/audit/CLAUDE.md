# CLAUDE.md — Daily Mate Server · AI Agent Instructions

> **Đọc file này trước mọi thao tác.** Đây là bản đồ dự án, nguyên tắc vận hành,
> và context cần thiết để AI audit chính xác mà không gây hồi quy.

---

## 1. Tổng quan dự án

| Thuộc tính | Giá trị |
|---|---|
| Tên | Daily Mate — Food Recommendation Server |
| Stack | Python 3.12 · Flask · JSON DataStore · Supabase (PostgreSQL) |
| Auth | Supabase JWT (ES256 / HS256) · PyJWKClient |
| Data chính | `data/*.json` — catalog được nạp vào memory (dishes, ingredients, relations) |
| Data phụ | Supabase — `request_log`, `session_feedback`, `weather_cache` |
| Push state | `data/device_tokens.json` — được persist sau mỗi upsert |
| Deploy | Fly.io / Railway (xem DEPLOY_FLYIO.md, DEPLOY_RAILWAY.md) |
| Entry point | `app.py` |

---

## 2. Cấu trúc file quan trọng

```
demo_server/
├── app.py                  ← Routes chính, CORS, entry point
├── auth_middleware.py       ← require_auth / require_admin decorator
├── rate_limiter.py          ← Sliding window rate limit (Supabase-backed)
├── pipeline.py              ← Scoring engine, filter_dishes, rank_and_explain
├── weather.py               ← Fetch & cache weather, compute_weather_vector
├── cache_manager.py         ← In-memory cache helper
├── monitoring.py            ← Request logging middleware
├── advice_engine.py         ← AI advice/template generation
├── docs/audit/              ← BỘ AUDIT DOCS (thư mục này)
│   ├── CLAUDE.md            ← File này — context cho AI agent
│   ├── SECURITY.md          ← Checklist bảo mật chi tiết
│   ├── LOGIC.md             ← Checklist logic nghiệp vụ
│   ├── REVIEW.md            ← Rules cho code review agent
│   └── FINDINGS.md          ← Template & log ghi nhận lỗi
```

---

## 3. Nguyên tắc vận hành khi AI audit

### ĐƯỢC làm
- Đọc toàn bộ file `.py` trước khi đưa ra kết luận bất kỳ
- Đặt câu hỏi khi không chắc về intent của business logic
- Báo cáo severity theo thang: CRITICAL / HIGH / MEDIUM / LOW / INFO
- Ghi mọi finding vào FINDINGS.md với format chuẩn (xem file đó)
- Cross-reference giữa các file (ví dụ: route trong app.py → decorator trong auth_middleware.py)

### KHÔNG được làm
- KHÔNG sửa code mà chưa được user xác nhận rõ ràng
- KHÔNG chạy bất kỳ lệnh nào thay đổi DB (INSERT/UPDATE/DELETE trên production)
- KHÔNG bỏ qua lỗi nhỏ — mọi finding đều được log, user sẽ triage sau
- KHÔNG đoán mò business logic — hỏi user nếu mơ hồ
- KHÔNG bỏ file __pycache__/, backup/, .env ra khỏi scope review

---

## 4. Thứ tự audit được khuyến nghị

```
Ưu tiên cao (security-critical):
  1. auth_middleware.py     → xác thực, JWT algorithm confusion
  2. rate_limiter.py        → race condition, bypass
  3. app.py (routes)        → input validation, CORS, unprotected endpoints

Ưu tiên trung (logic & robustness):
  4. pipeline.py            → scoring manipulation, edge cases
  5. weather.py             → external API dependency, cache poisoning
  6. monitoring.py          → log injection, info disclosure
  7. cache_manager.py       → cache bypass, TTL issues

Ưu tiên thấp (config & deps):
  8. advice_engine.py       → prompt injection nếu dùng LLM call
  9. supabase_migration.sql → RLS policy, privilege escalation
 10. requirements.txt       → CVE trong dependencies
```

---

## 5. Biến môi trường nhạy cảm

```bash
SUPABASE_URL               # không được hardcode trong code
SUPABASE_SERVICE_ROLE_KEY  # admin key — bypass toàn bộ RLS, RẤT nhạy cảm
DATA_DIR                   # thư mục JSON dataset; mặc định là ./data
```

> CẢNH BÁO: SUPABASE_SERVICE_ROLE_KEY là admin key, bypass toàn bộ Row Level
> Security của Supabase. Key này lộ = attacker có full read/write quyền trên DB.
> Key này đang được dùng trực tiếp trong rate_limiter.py và app.py.

---

## 6. Known quirks — không phải bug, đừng flag

| Pattern | Lý do chấp nhận |
|---|---|
| OPTIONS request bypass auth | CORS preflight yêu cầu, cố ý |
| JSON DataStore load vào memory | Cố ý để giảm latency lookup |
| _random.seed(seed) trong /challenge | Seeded random để reproducible, không cần CSPRNG |
| L1 weather cache mất khi restart | Chỉ là cache tốc độ; L2 Supabase phục hồi được |
| datetime.utcnow() còn sót | Technical debt, chưa phải security issue |
