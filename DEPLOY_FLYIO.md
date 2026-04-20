# 🚀 Hướng dẫn Deploy Daily Mate Server lên Fly.io + SQLite

## Tổng quan

```
React Native APK  →  Fly.io Server (Flask + Gunicorn)  →  SQLite (Persistent Volume 3GB free)
                                ↕
                        OpenWeather API
```

---

## Bước 1 — Cài Fly CLI

**Windows (PowerShell):**
```powershell
pwsh -Command "iwr https://fly.io/install.ps1 -useb | iex"
```

**Sau khi cài xong, đăng ký / login:**
```bash
    # lần đầu
# hoặc
fly auth login    # đã có tài khoản
```

> Fly.io không yêu cầu thẻ tín dụng cho free tier.

---

## Bước 2 — Chuẩn bị code

### 2.1 Sửa DB_PATH trong `server_patched.py`

Tìm dòng:
```python
DB_PATH = Path(os.environ.get("DB_PATH", r"D:\dream_project\...recipe.db"))
```

Thay thành:
```python
DB_PATH = Path(os.environ.get("DB_PATH", "/data/recipe.db"))
```

### 2.2 Sửa `app.run()` cuối file

```python
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False)
```

### 2.3 Thêm trick tự copy DB lần đầu

Thêm vào ngay sau dòng khai báo `DB_PATH`:
```python
import shutil
BUNDLED_DB = Path(__file__).parent / "recipe.db"
if not DB_PATH.exists() and BUNDLED_DB.exists():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(BUNDLED_DB, DB_PATH)
    print(f"[INIT] Copied DB to {DB_PATH}")
```


---

## Bước 3 — Tạo các file config cho Fly.io

### 3.1 Tạo `Procfile`
```
web: gunicorn server_patched:app --bind 0.0.0.0:$PORT --workers 2
```

### 3.2 Tạo `fly.toml` (file config chính)

```toml
app = "daily-mate-server"   # đổi tên app tùy ý, phải unique trên fly.io
primary_region = "sin"      # Singapore - gần VN nhất

[build]
  builder = "paketobuildpacks/builder:base"

[env]
  PORT = "8080"
  DB_PATH = "/data/recipe.db"

[http_service]
  internal_port = 8080
  force_https = true
  auto_stop_machines = true
  auto_start_machines = true
  min_machines_running = 0

[[mounts]]
  source = "mydata"
  destination = "/data"

[[vm]]
  memory = "256mb"
  cpu_kind = "shared"
  cpus = 1
```

### 3.3 Tạo `.env.example` (để team biết cần set gì, không commit .env thật)

```
OPENWEATHER_API_KEY=your_key_here
DB_PATH=/data/recipe.db
PORT=8080
```

---

## Bước 4 — Xử lý recipe.db (file 64MB)

Vì db quá lớn để commit lên GitHub, dùng Fly.io để upload thẳng:

```bash
# Sau khi deploy lần đầu, copy db lên volume
fly sftp shell
# Trong sftp shell:
put recipe.db /data/recipe.db
exit
```

**Hoặc dùng lệnh nhanh hơn:**
```bash
fly ssh console -C "ls /data"   # kiểm tra volume đã mount chưa
```


---

## Bước 5 — Deploy lên Fly.io

```bash
# Di chuyển vào thư mục project
cd D:\dream_project\daily_mate_code\demo_server

# Khởi tạo app (chỉ chạy lần đầu)
fly launch --no-deploy

# Tạo persistent volume (3GB free)
fly volumes create mydata --region sin --size 1

# Set API key (không lưu trong code)
fly secrets set OPENWEATHER_API_KEY=your_actual_key_here

# Deploy!
fly deploy
```

**Kiểm tra deploy thành công:**
```bash
fly logs          # xem log realtime
fly status        # xem trạng thái app
```

---

## Bước 6 — Upload recipe.db lên Volume

```bash
# Mở SFTP vào máy Fly
fly sftp shell

# Trong sftp prompt:
sftp> put recipe.db /data/recipe.db
sftp> ls /data
sftp> exit
```

**Test sau khi upload:**
```bash
fly ssh console -C "python -c \"import sqlite3; c=sqlite3.connect('/data/recipe.db'); print(c.execute('SELECT COUNT(*) FROM dishes').fetchone())\""
```

---

## Bước 7 — Lấy URL và test

```bash
# Lấy URL app
fly info
```

URL sẽ có dạng: `https://daily-mate-server.fly.dev`

**Test các endpoint:**
```bash
# Health check
curl https://daily-mate-server.fly.dev/health

# Test recommend
curl -X POST https://daily-mate-server.fly.dev/api/v1/recommend \
  -H "Content-Type: application/json" \
  -d '{"lat": 16.047, "lon": 108.206, "personal": {}}'
```

---

## Bước 8 — Cập nhật React Native

Trong file config app, thay localhost bằng URL Fly.io:

```javascript
// config.js hoặc constants.js
export const API_BASE_URL = "https://daily-mate-server.fly.dev";
```


---

## Checklist trước khi share beta

- [ ] `DB_PATH` = `/data/recipe.db` trong `server_patched.py`
- [ ] `app.run(host="0.0.0.0", port=8080)` đã set
- [ ] `fly.toml` đã tạo với mount `/data`
- [ ] Volume `mydata` đã tạo trên Fly.io
- [ ] `recipe.db` đã upload lên `/data/` qua sftp
- [ ] `OPENWEATHER_API_KEY` đã set qua `fly secrets set`
- [ ] `/health` trả về `status: ok` và đúng số dishes
- [ ] React Native đã trỏ URL mới
- [ ] APK build xong, test được trên thiết bị thật

---

## Chi phí Fly.io free tier

| Tài nguyên | Free |
|-----------|------|
| Shared CPU + 256MB RAM | ✅ 3 máy free |
| Volume storage | ✅ 3GB free |
| Outbound bandwidth | ✅ 160GB/tháng |
| **Tổng** | **$0/tháng** |

> App sẽ tự sleep khi không có request (`auto_stop_machines = true`).
> Request đầu tiên sẽ chậm ~2-3s để wake up — bình thường cho free tier.

---

## Xử lý sự cố thường gặp

**Lỗi `Database not found`**
→ Chạy `fly ssh console -C "ls /data"` — nếu trống, upload lại db qua sftp

**App không start được**
→ Chạy `fly logs` xem lỗi cụ thể

**Lỗi port**
→ Đảm bảo `internal_port = 8080` trong `fly.toml` khớp với PORT env

**Volume không mount**
→ Kiểm tra tên `source = "mydata"` trong `fly.toml` khớp với tên volume đã tạo
→ Chạy `fly volumes list` để xem danh sách volume

**Đổi API key OpenWeather (vì đã bị lộ lên GitHub)**
→ Vào openweathermap.org → xóa key cũ → tạo key mới
→ `fly secrets set OPENWEATHER_API_KEY=key_moi`
