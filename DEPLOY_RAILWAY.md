# 🚂 Hướng dẫn Deploy Daily Mate Server lên Railway + SQLite

## Tổng quan

```
React Native APK  →  Railway Server (Flask)  →  SQLite (Volume)
                          ↕
                   OpenWeather API
```

---

## Bước 1 — Chuẩn bị code trước khi deploy

### 1.1 Sửa DB_PATH trong `server_patched.py`

Tìm dòng:
```python
DB_PATH = Path(os.environ.get("DB_PATH", r"D:\dream_project\...recipe.db"))
```

Thay thành:
```python
DB_PATH = Path(os.environ.get("DB_PATH", "/app/data/recipe.db"))
```

### 1.2 Sửa dòng `app.run()` cuối file

Đảm bảo cuối `server_patched.py` có:
```python
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
```

### 1.3 Tạo file `Procfile` (cùng thư mục với server_patched.py)

```
web: gunicorn server_patched:app --bind 0.0.0.0:$PORT --workers 2
```

---

## Bước 2 — Tạo project trên Railway

1. Vào [railway.app](https://railway.app) → **New Project**
2. Chọn **Deploy from GitHub repo** → connect repo của bạn
3. Railway sẽ tự detect Python và cài `requirements.txt`

---

## Bước 3 — Thêm Persistent Volume (giữ SQLite)

> ⚠️ Bỏ qua bước này → mỗi lần redeploy sẽ **mất toàn bộ data**

1. Trong Railway project → click service của bạn
2. Vào tab **Volumes** → **Add Volume**
3. Cấu hình:
   - **Mount Path:** `/app/data`
   - **Size:** 1 GB (đủ dùng cho giai đoạn beta)
4. Click **Create**


## Bước 4 — Upload file SQLite lên Volume

Railway Volume không tự lấy file từ repo. Cần upload `recipe.db` lên.

**Cách đơn giản nhất — dùng Railway CLI:**

```bash
# Cài Railway CLI
npm install -g @railway/cli

# Login
railway login

# Link project
railway link

# Copy file db lên volume
railway run cp /local/path/recipe.db /app/data/recipe.db
```

**Hoặc dùng script upload khi server start:**

Thêm vào đầu `server_patched.py`:
```python
import shutil

# Nếu DB chưa tồn tại trong volume → copy từ bundle
BUNDLED_DB = Path(__file__).parent / "recipe.db"
if not DB_PATH.exists() and BUNDLED_DB.exists():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(BUNDLED_DB, DB_PATH)
    print(f"[INIT] Copied DB from bundle to {DB_PATH}")
```

> ✅ Cách này đơn giản nhất: để `recipe.db` trong repo, lần đầu deploy sẽ tự copy vào volume.

---

## Bước 5 — Cấu hình Environment Variables

Trong Railway → tab **Variables**, thêm:

| Key | Value |
|-----|-------|
| `DB_PATH` | `/app/data/recipe.db` |
| `OPENWEATHER_API_KEY` | `<api_key_của_bạn>` |
| `PORT` | (Railway tự set, không cần thêm) |

---

## Bước 6 — Deploy

1. Push code lên GitHub → Railway tự động deploy
2. Kiểm tra log trong tab **Deployments**
3. Sau deploy, lấy URL từ tab **Settings** → **Domains**

**Test nhanh:**
```bash
curl https://your-app.railway.app/health
```

Kết quả mong đợi:
```json
{"status": "ok", "dishes": 1234, "ingredients": 456}
```

---

## Bước 7 — Cấu hình React Native trỏ vào server mới

Trong file config của app, thay `localhost:8081` bằng URL Railway:

```javascript
// config.js hoặc .env
API_BASE_URL=https://your-app.railway.app
```


---

## Bước 8 — Build APK React Native để share

### Dùng Expo (nếu project dùng Expo)

```bash
# Cài EAS CLI
npm install -g eas-cli

# Login Expo
eas login

# Cấu hình (lần đầu)
eas build:configure

# Build APK preview (không cần Google Play)
eas build --platform android --profile preview
```

Trong `eas.json`, đảm bảo có profile preview:
```json
{
  "build": {
    "preview": {
      "android": {
        "buildType": "apk"
      }
    }
  }
}
```

Sau khi build xong → tải APK từ link Expo → share qua Google Drive hoặc link trực tiếp.

> 📱 Người dùng cần bật **"Cài đặt từ nguồn không xác định"** trên Android.

---

## Checklist trước khi share beta

- [ ] `DB_PATH` trỏ đúng `/app/data/recipe.db`
- [ ] `app.run(host="0.0.0.0")` đã set
- [ ] `Procfile` đã tạo với gunicorn
- [ ] Volume `/app/data` đã mount trên Railway
- [ ] `OPENWEATHER_API_KEY` đã set trong Railway Variables
- [ ] `/health` endpoint trả về `status: ok`
- [ ] React Native đã trỏ đúng URL Railway
- [ ] APK build xong và test được trên thiết bị thật

---

## Chi phí ước tính (Railway)

| Tài nguyên | Chi phí |
|-----------|---------|
| Compute (server) | ~$5/tháng (free tier $5 credit) |
| Volume 1GB | ~$0.25/tháng |
| **Tổng giai đoạn beta** | **~$0 - $5.25/tháng** |

> Free tier $5 credit/tháng của Railway đủ cover giai đoạn thử nghiệm.

---

## Xử lý sự cố thường gặp

**Lỗi `Database not found`**
→ Kiểm tra `DB_PATH` env var và volume đã mount chưa

**Lỗi `Address already in use`**
→ Đảm bảo dùng `$PORT` từ env, không hardcode port

**App crash sau redeploy, mất data**
→ Volume chưa được mount → xem lại Bước 3

**OpenWeather trả 401**
→ Kiểm tra `OPENWEATHER_API_KEY` trong Railway Variables
