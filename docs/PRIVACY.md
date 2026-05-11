# 🔒 Daily Mate — Privacy & Data Documentation (Backend Server)
> Phiên bản: 1.0 | Cập nhật: May 2026  
> Phạm vi: Python Flask backend — `demo_server/`

---

## 1. Vai trò của Server trong Luồng Dữ liệu

Backend server là **lớp xử lý trung tâm** — không lưu trữ profile người dùng lâu dài
mà chủ yếu nhận dữ liệu từ client, tính toán, rồi trả kết quả.

```
Mobile Client ──(JWT)──► Flask API ──► SQLite (recipe DB)
                                  └──► Supabase (request_log)
                                  └──► OpenWeatherMap API
                                  └──► SQLite device_tokens
```

---

## 2. Dữ liệu đầu vào từ Client (Request Payload)

Mọi request đến `/api/recommend` và các endpoint chính đều nhận payload sau:

| Trường | Kiểu | Lưu vĩnh viễn? | Ghi chú |
|---|---|---|---|
| `profile.age` | Integer | ❌ | Dùng trong request scope, không lưu |
| `profile.gender` | String | ❌ | Dùng trong request scope |
| `profile.goal` | String | ❌ | Dùng để điều chỉnh scoring |
| `profile.allergies` | Array | ❌ | Filter logic, không log |
| `profile.taste_vector` | Array[7 float] | ❌ | Scoring, không log |
| `metrics.weight` | Float | ❌ | Không bao giờ ghi vào DB |
| `metrics.height` | Float | ❌ | Không bao giờ ghi vào DB |
| `location.lat` | Float | Tạm thời (weather cache) | Xem mục 3 |
| `location.lon` | Float | Tạm thời (weather cache) | Xem mục 3 |
| `market_basket` | Array[int] | ❌ | Ingredient IDs, không log |

**Nguyên tắc**: Server hoạt động theo mô hình **stateless per-request** —
dữ liệu nhạy cảm của user (profile, metrics) **không bao giờ được ghi vào DB**.

---

## 3. Dữ liệu Weather Cache (SQLite)

Bảng `weather_cache` (trong `recipe.db`):

| Cột | Nội dung | Thời gian giữ |
|---|---|---|
| `lat`, `lon` | Tọa độ GPS (làm tròn 2 chữ số thập phân) | Tự động expire sau 1 giờ |
| `weather_json` | Temp, humidity, condition, AQI | Tự động expire sau 1 giờ |
| `fetched_at` | Timestamp UTC | Xóa khi row expire |

> **Lưu ý**: `lat/lon` được làm tròn đến độ chính xác ~1km trước khi dùng làm cache key.
> Không lưu tọa độ chính xác từng mét. Không liên kết tọa độ với `uid`.

---

## 4. Request Logging (Supabase `request_log`)

Bảng `request_log` trên Supabase ghi lại:

| Cột | Nội dung | Nhạy cảm? |
|---|---|---|
| `uid` | Supabase user ID (UUID) | ⚠️ Có (nhận dạng user) |
| `endpoint` | Tên route Flask (e.g. `recommend`) | Không |
| `method` | HTTP method | Không |
| `status_code` | HTTP status | Không |
| `latency_ms` | Thời gian xử lý | Không |
| `logged_at` | Timestamp UTC | Không |

**Điều KHÔNG ghi log:**
- Nội dung request body (profile, allergies, taste...)
- IP address
- Device info / User-Agent
- Kết quả trả về (ranked dishes)

**Mục đích log**: Chỉ để monitoring performance và debug lỗi — không dùng cho analytics marketing.

**Retention**: Log nên được purge định kỳ sau 90 ngày (cần implement cron job hoặc Supabase policy).

---

## 5. Device Tokens (Push Notification)

Bảng `device_tokens` (SQLite `recipe.db`):

| Cột | Nội dung | PII? |
|---|---|---|
| `device_id` | UUID do client tạo | Thấp — không gắn với identity |
| `fcm_token` | Expo Push Token | ⚠️ Có thể dùng để target device |
| `platform` | `android` / `ios` | Không |
| `lat`, `lon` | Vị trí gần nhất khi đăng ký | ⚠️ Có |
| `province` | Tỉnh/thành phố | Thấp |
| `created_at`, `updated_at` | Timestamps | Không |

**Xóa token**: Khi Expo trả về `DeviceNotRegistered`, token bị xóa tự động (`fcm_service.py`).

**Không có cột `uid`**: `device_tokens` chỉ liên kết với `device_id` — không thể
map ngược về Supabase user account từ bảng này.

---

## 6. Authentication & Authorization

### Cơ chế xác thực
- **JWT ES256** — sử dụng Supabase JWKS public key (không dùng shared secret)
- Token validated tại `auth_middleware.py` qua `PyJWKClient`
- Mọi endpoint `/api/*` đều yêu cầu `Authorization: Bearer <token>` hợp lệ
- Token expire → trả `401` ngay, không retry tự động

### Algorithm Confusion Prevention
```python
# auth_middleware.py
payload = jwt.decode(
    token,
    signing_key.key,
    algorithms=["ES256"],      # ← Chỉ cho phép ES256, KHÔNG có HS256
    audience="authenticated",
    issuer=f"{SUPABASE_URL}/auth/v1",
)
```
Tường minh loại bỏ HS256 để tránh tấn công algorithm confusion.

### Admin Routes
- `/admin/*` yêu cầu cả `require_auth` VÀ `require_admin` (role = "admin")
- Admin role được set trong Supabase, không thể tự nâng quyền

---

## 7. Security Headers

Mọi response từ server đều có:

```
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
Referrer-Policy: strict-origin-when-cross-origin
Strict-Transport-Security: max-age=31536000; includeSubDomains  ← chỉ production HTTPS
```

---

## 8. Rate Limiting

`rate_limiter.py` áp dụng giới hạn theo `uid`:

| Endpoint | Giới hạn | Mục đích |
|---|---|---|
| `/api/recommend` | (xem rate_limiter.py) | Tránh abuse, bảo vệ DB |
| `/api/weather` | Riêng | OpenWeatherMap quota |

Khi vượt giới hạn → HTTP 429, không log nội dung request.

---

## 9. Dữ liệu KHÔNG được thu thập

Server **không** thu thập:
- ❌ Số điện thoại
- ❌ Địa chỉ thực (chỉ tỉnh/thành phố)
- ❌ Thông tin thanh toán
- ❌ Danh bạ / contacts
- ❌ Camera / ảnh
- ❌ Lịch sử bữa ăn (lưu local trên client)
- ❌ Body metrics (weight, height) — chỉ dùng trong request, không ghi DB

---

## 10. Data Residency

| Dữ liệu | Lưu tại |
|---|---|
| `recipe.db` (SQLite) | Server local (on-premise hoặc VPS) |
| `request_log` | Supabase cloud (region tùy cấu hình project) |
| Auth data (email, JWT) | Supabase cloud |
| Weather cache | Server local SQLite |
| Push tokens | Server local SQLite |

> Khi deploy production, cần xác định Supabase region phù hợp (ưu tiên Singapore `ap-southeast-1` cho user Việt Nam).

---

## 11. Incident Response

### Nếu DB bị compromise
1. Rotate Supabase Service Role Key ngay lập tức
2. Invalidate tất cả JWT đang active (qua Supabase dashboard)
3. Xóa `device_tokens` table và yêu cầu client re-register
4. Review `request_log` để xác định scope của breach

### Dữ liệu nhạy cảm nhất cần bảo vệ
1. **Supabase Service Role Key** (trong `.env`) — full access DB, không được commit git
2. **`request_log.uid`** — có thể dùng để profile activity của user cụ thể
3. **`device_tokens.fcm_token`** — có thể gửi notification giả

---

## 12. Biến môi trường nhạy cảm

File `.env` (không commit vào git):

```
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_SERVICE_ROLE_KEY=eyJ...       ← KHÔNG chia sẻ
OPENWEATHER_API_KEY=...                ← Quota riêng, rotate khi lộ
DB_PATH=/path/to/recipe.db
```

Kiểm tra `.gitignore` đã có `.env` trước khi push.

---

## 13. Tuân thủ & Khuyến nghị tương lai

| Hành động | Ưu tiên | Ghi chú |
|---|---|---|
| Purge `request_log` sau 90 ngày | 🔴 Cao | Implement Supabase Row Policy hoặc cron |
| Xóa `device_tokens` khi user delete account | 🔴 Cao | Cần endpoint hoặc webhook từ Supabase Auth |
| Tách `lat/lon` khỏi `device_tokens` | 🟡 Trung bình | Vị trí đăng ký token không cần thiết lưu lâu dài |
| CORS: thay `"*"` bằng domain production | 🔴 Cao | Hiện tại chỉ an toàn vì app mobile (không browser) |
| Supabase region = `ap-southeast-1` | 🟡 Trung bình | Giảm latency + data sovereignty VN |
| Privacy Policy công khai (App Store) | 🔴 Cao | Bắt buộc khi publish |

---

*Tài liệu nội bộ — xem xét lại mỗi khi thêm tính năng mới thu thập dữ liệu người dùng.*
