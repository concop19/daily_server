# 🔔 Push Notification via FCM — Daily Mate Backend

> **Mục tiêu**: Server tự động gửi push notification đến thiết bị người dùng
> 8 lần/ngày (10:00, 10:30, 11:00, 11:30, 16:00, 16:30, 17:00, 17:30, 18:00)
> kèm 1 món ăn được recommend dựa trên vị trí + thời tiết của user.
> App không cần mở — notification hiện trực tiếp trên màn hình khóa.

---

## 1. Tổng quan kiến trúc

```
Mobile app khởi động
    ↓
Lấy FCM token (expo-notifications)
    ↓
POST /api/v1/device/register → lưu token vào SQLite (bảng device_tokens)
    ↓
APScheduler chạy cron 8 lần/ngày
    ↓
Với mỗi device_token trong DB:
    → Gọi pipeline recommend (dùng location + weather cache của device đó)
    → Lấy món #1
    → Gửi FCM push notification đến token
    ↓
Điện thoại nhận → hiện notification dù app đóng hoàn toàn
```

---

## 2. Chuẩn bị: Firebase project

### 2.1 Tạo Firebase project
1. Vào https://console.firebase.google.com
2. Tạo project mới (hoặc dùng project cũ nếu có)
3. Vào **Project Settings → Service accounts**
4. Nhấn **"Generate new private key"** → tải file JSON về
5. Đặt file vào `demo_server/firebase-service-account.json`

### 2.2 Lấy FCM Server Key (legacy) hoặc dùng OAuth2 (v1 API)
> Khuyên dùng **FCM HTTP v1 API** (OAuth2) thay vì legacy key vì Google deprecated legacy từ 2024.

File `firebase-service-account.json` sẽ dùng để generate OAuth2 access token.

---

## 3. Thay đổi Backend (Flask)

### 3.1 Cài thêm dependencies

```bash
pip install google-auth==2.29.0 APScheduler==3.10.4
```

Thêm vào `requirements.txt`:
```
google-auth>=2.29.0
APScheduler>=3.10.4
```

---

### 3.2 Tạo bảng `device_tokens` trong SQLite

Thêm vào hàm `init_db()` trong `app.py`:

```python
# Trong hàm init_db() — thêm sau các CREATE TABLE hiện có
db.execute("""
    CREATE TABLE IF NOT EXISTS device_tokens (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        device_id   TEXT NOT NULL,
        fcm_token   TEXT NOT NULL,
        platform    TEXT DEFAULT 'android',
        lat         REAL,
        lon         REAL,
        province    TEXT,
        created_at  TEXT DEFAULT (datetime('now')),
        updated_at  TEXT DEFAULT (datetime('now')),
        UNIQUE(device_id)
    )
""")
```

---

### 3.3 Tạo file `fcm_service.py`

```python
# fcm_service.py
"""
Gửi push notification qua FCM HTTP v1 API (OAuth2).
Dùng google-auth để generate access token từ service account.
"""

import json
import logging
import os
from pathlib import Path

import requests
from google.oauth2 import service_account
from google.auth.transport.requests import Request

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
SERVICE_ACCOUNT_FILE = Path(__file__).parent / "firebase-service-account.json"
FCM_SCOPES = ["https://www.googleapis.com/auth/firebase.messaging"]

def _get_access_token():
    """Generate OAuth2 access token từ service account."""
    credentials = service_account.Credentials.from_service_account_file(
        str(SERVICE_ACCOUNT_FILE),
        scopes=FCM_SCOPES,
    )
    credentials.refresh(Request())
    return credentials.token

def _get_project_id():
    with open(SERVICE_ACCOUNT_FILE) as f:
        data = json.load(f)
    return data["project_id"]

def send_push_notification(fcm_token: str, title: str, body: str, data: dict = None) -> bool:
    """
    Gửi 1 push notification đến 1 device.
    
    Args:
        fcm_token: FCM registration token của device
        title: Tiêu đề notification
        body: Nội dung notification
        data: Dict data payload (optional) — app nhận được khi tap notification
    
    Returns:
        True nếu gửi thành công, False nếu thất bại
    """
    try:
        project_id  = _get_project_id()
        access_token = _get_access_token()

        url = f"https://fcm.googleapis.com/v1/projects/{project_id}/messages:send"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type":  "application/json",
        }

        message = {
            "message": {
                "token": fcm_token,
                "notification": {
                    "title": title,
                    "body":  body,
                },
                "android": {
                    "notification": {
                        "channel_id": "meal-reminders",
                        "priority":   "HIGH",
                        "sound":      "default",
                    }
                },
                "apns": {
                    "payload": {
                        "aps": {
                            "sound": "default",
                            "badge": 1,
                        }
                    }
                },
            }
        }

        # Thêm data payload nếu có
        if data:
            message["message"]["data"] = {k: str(v) for k, v in data.items()}

        res = requests.post(url, headers=headers, json=message, timeout=10)
        res.raise_for_status()
        logger.info(f"FCM sent OK to token ...{fcm_token[-8:]}")
        return True

    except requests.HTTPError as e:
        # Token hết hạn / invalid → xóa khỏi DB
        if e.response.status_code in (400, 404):
            logger.warning(f"FCM token invalid: {fcm_token[-8:]} — should remove from DB")
        else:
            logger.error(f"FCM HTTP error: {e}")
        return False
    except Exception as e:
        logger.error(f"FCM send failed: {e}")
        return False
```

---

### 3.4 Tạo file `notification_scheduler.py`

```python
# notification_scheduler.py
"""
APScheduler chạy cron 8 lần/ngày.
Mỗi lần: lấy tất cả device tokens → recommend 1 món → gửi FCM.
"""

import logging
from contextlib import contextmanager
from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from fcm_service import send_push_notification

logger = logging.getLogger(__name__)

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")

# ── Giờ gửi notification (giờ Việt Nam) ──────────────────────────────────────
# Bữa trưa: 10:00, 10:30, 11:00, 11:30
# Bữa tối:  16:00, 16:30, 17:00, 17:30, 18:00  (đã bỏ 18:00 theo yêu cầu)
NOTIFICATION_SCHEDULE = [
    {"hour": 10, "minute": 0,  "meal": "lunch",  "label": "Bữa trưa"},
    {"hour": 10, "minute": 30, "meal": "lunch",  "label": "Bữa trưa"},
    {"hour": 11, "minute": 0,  "meal": "lunch",  "label": "Bữa trưa"},
    {"hour": 11, "minute": 30, "meal": "lunch",  "label": "Bữa trưa"},
    {"hour": 16, "minute": 0,  "meal": "dinner", "label": "Bữa tối"},
    {"hour": 16, "minute": 30, "meal": "dinner", "label": "Bữa tối"},
    {"hour": 17, "minute": 0,  "meal": "dinner", "label": "Bữa tối"},
    {"hour": 17, "minute": 30, "meal": "dinner", "label": "Bữa tối"},
]

def send_meal_notifications(get_db, run_recommend_for_device):
    """
    Job chạy theo cron — gửi notification đến tất cả devices.
    
    Args:
        get_db: context manager trả về SQLite connection
        run_recommend_for_device: hàm (device_row) -> dish dict | None
    """
    now = datetime.now(VN_TZ)
    slot = next(
        (s for s in NOTIFICATION_SCHEDULE
         if s["hour"] == now.hour and s["minute"] == now.minute),
        None
    )
    if not slot:
        return  # Không phải giờ gửi

    logger.info(f"[Scheduler] Firing notification slot {slot['hour']}:{slot['minute']:02d}")

    with get_db() as db:
        devices = db.execute(
            "SELECT device_id, fcm_token, lat, lon, province FROM device_tokens"
        ).fetchall()

    for device in devices:
        try:
            dish = run_recommend_for_device(device, slot["meal"])
            if not dish:
                continue

            title = f"🍽️ {slot['label']} — {dish['title']}"
            body  = _build_body(dish)

            send_push_notification(
                fcm_token=device["fcm_token"],
                title=title,
                body=body,
                data={
                    "screen":    "MealReminder",
                    "mealId":    slot["meal"],
                    "dishName":  dish["title"],
                    "dishId":    str(dish.get("dish_id", "")),
                    "calories":  str(int(dish.get("estimated_calories", 0))),
                    "protein":   str(int(dish.get("estimated_protein", 0))),
                }
            )
        except Exception as e:
            logger.error(f"Notification failed for device {device['device_id']}: {e}")

def _build_body(dish: dict) -> str:
    """Build notification body text từ dish info."""
    parts = []
    cal = dish.get("estimated_calories")
    protein = dish.get("estimated_protein")
    if cal:
        parts.append(f"🔥 {int(cal)}kcal")
    if protein:
        parts.append(f"🥩 {int(protein)}g đạm")
    hint = dish.get("explanation", [None])[0] if dish.get("explanation") else None
    if hint:
        return hint
    return " · ".join(parts) if parts else "Hôm nay thử món này đi~ 😋"

def init_scheduler(app, get_db, run_recommend_for_device):
    """
    Khởi động APScheduler. Gọi hàm này trong app.py sau khi Flask app init xong.
    
    Args:
        app: Flask app instance
        get_db: hàm context manager SQLite
        run_recommend_for_device: hàm lấy dish cho 1 device
    """
    scheduler = BackgroundScheduler(timezone=str(VN_TZ))

    # Tạo 1 job duy nhất chạy mỗi 30 phút — tự check xem có phải giờ gửi không
    scheduler.add_job(
        func=lambda: send_meal_notifications(get_db, run_recommend_for_device),
        trigger=CronTrigger(minute="0,30", timezone=str(VN_TZ)),
        id="meal_notification_job",
        replace_existing=True,
    )

    scheduler.start()
    logger.info("[Scheduler] APScheduler started — meal notifications active")

    # Shutdown gracefully khi Flask tắt
    import atexit
    atexit.register(lambda: scheduler.shutdown(wait=False))

    return scheduler
```

---

### 3.5 Thêm endpoints vào `app.py`

```python
# Thêm vào app.py

from fcm_service import send_push_notification
from notification_scheduler import init_scheduler

# ── Endpoint: Register FCM token ──────────────────────────────────────────────
@app.route("/api/v1/device/register", methods=["POST"])
def register_device():
    """
    Mobile gọi endpoint này khi khởi động để lưu FCM token.
    Body JSON:
    {
        "device_id": "abc123",     ← unique device identifier
        "fcm_token": "fcm:...",    ← expo push token hoặc FCM token
        "lat": 10.762,             ← vị trí gần nhất (optional)
        "lon": 106.660,
        "province": "Ho Chi Minh"
    }
    """
    data = request.get_json()
    device_id = data.get("device_id")
    fcm_token  = data.get("fcm_token")

    if not device_id or not fcm_token:
        return jsonify({"error": "device_id and fcm_token required"}), 400

    with get_db() as db:
        db.execute("""
            INSERT INTO device_tokens (device_id, fcm_token, lat, lon, province, updated_at)
            VALUES (?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(device_id) DO UPDATE SET
                fcm_token  = excluded.fcm_token,
                lat        = excluded.lat,
                lon        = excluded.lon,
                province   = excluded.province,
                updated_at = datetime('now')
        """, (
            device_id,
            fcm_token,
            data.get("lat"),
            data.get("lon"),
            data.get("province"),
        ))
        db.commit()

    return jsonify({"status": "ok"}), 200


# ── Endpoint: Update location (gọi khi user cho phép GPS) ────────────────────
@app.route("/api/v1/device/location", methods=["PUT"])
def update_device_location():
    data = request.get_json()
    with get_db() as db:
        db.execute("""
            UPDATE device_tokens
            SET lat=?, lon=?, province=?, updated_at=datetime('now')
            WHERE device_id=?
        """, (data.get("lat"), data.get("lon"), data.get("province"), data.get("device_id")))
        db.commit()
    return jsonify({"status": "ok"}), 200


# ── Endpoint: Test push (dev only) ───────────────────────────────────────────
@app.route("/api/v1/device/test-push", methods=["POST"])
def test_push():
    """Gửi test notification ngay lập tức — chỉ dùng khi dev."""
    data = request.get_json()
    fcm_token = data.get("fcm_token")
    ok = send_push_notification(
        fcm_token=fcm_token,
        title="🍽️ Test từ Daily Mate",
        body="Push notification đang hoạt động!",
        data={"screen": "MealReminder", "mealId": "lunch"}
    )
    return jsonify({"sent": ok}), 200 if ok else 500


# ── Khởi động scheduler (thêm vào cuối file, sau khi app được tạo) ───────────
def run_recommend_for_device(device, meal_type):
    """
    Chạy recommend pipeline cho 1 device → trả về top dish.
    Dùng location của device, weather cache nếu có.
    """
    try:
        lat = device["lat"] or 10.762
        lon = device["lon"] or 106.660

        weather = get_or_compute_weather(lat, lon)  # dùng cache nếu có
        
        # Build params tối thiểu để recommend
        params = {
            "lat": lat, "lon": lon,
            "weather": weather,
            "personal": {},          # dùng default — chưa có profile từ device
            "cuisine_scope": "all",
            "cost_preference": 2,
        }

        # Gọi pipeline trực tiếp (không qua HTTP)
        from pipeline import rank_and_explain, filter_dishes, build_constraint_profile
        with get_db() as db:
            dishes = filter_dishes(db, build_constraint_profile(params))
            ranked = rank_and_explain(dishes, params, weather, top_k=1)
            return ranked[0] if ranked else None
    except Exception as e:
        logger.error(f"recommend_for_device failed: {e}")
        return None

# Gọi init_scheduler sau khi app và DB đã sẵn sàng
if os.environ.get("ENABLE_PUSH_SCHEDULER", "false").lower() == "true":
    init_scheduler(app, get_db, run_recommend_for_device)
```

---

### 3.6 Thêm biến môi trường vào `.env`

```env
# Push Notification
ENABLE_PUSH_SCHEDULER=true
GOOGLE_APPLICATION_CREDENTIALS=./firebase-service-account.json
```

---

## 4. Thay đổi Mobile (React Native)

### 4.1 Lấy FCM token và gửi lên server

Thêm vào `App.js` trong `useEffect` khởi động:

```js
import * as Notifications from 'expo-notifications';
import { api } from './services/api';
import { getDeviceId } from './utils/database';

async function registerDeviceToken(location) {
  try {
    // Lấy Expo Push Token (hoạt động cả Expo Go lẫn standalone)
    const { data: expoPushToken } = await Notifications.getExpoPushTokenAsync({
      projectId: 'your-expo-project-id', // lấy từ app.json > expo.extra.eas.projectId
    });

    const deviceId = await getDeviceId();

    await api.post('/api/v1/device/register', {
      device_id: deviceId,
      fcm_token:  expoPushToken,  // server nhận Expo token, Expo tự convert sang FCM
      lat:      location?.lat,
      lon:      location?.lon,
      province: location?.province,
    });
  } catch (e) {
    console.warn('registerDeviceToken failed:', e);
  }
}
```

> ⚠️ **Lưu ý**: Nếu dùng **Expo Push Token** (`ExponentPushToken[...]`) thì gửi qua
> `https://exp.host/--/api/v2/push/send` thay vì FCM trực tiếp — đơn giản hơn nhiều,
> không cần service account. Xem mục 5 bên dưới.

---

## 5. Hướng đơn giản hơn: Expo Push Service (khuyên dùng)

Thay vì dùng FCM trực tiếp (cần service account, OAuth2), dùng **Expo Push API** —
Expo đóng vai trò relay, server chỉ cần gửi HTTP POST đơn giản:

```python
# fcm_service.py — phiên bản đơn giản dùng Expo Push API

import requests

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"

def send_push_notification(expo_token: str, title: str, body: str, data: dict = None) -> bool:
    """Gửi push notification qua Expo Push Service."""
    try:
        payload = {
            "to":    expo_token,   # "ExponentPushToken[xxxxxx]"
            "title": title,
            "body":  body,
            "sound": "default",
            "channelId": "meal-reminders",
            "data":  data or {},
        }
        res = requests.post(EXPO_PUSH_URL, json=payload, timeout=10)
        res.raise_for_status()
        result = res.json()
        # Check Expo response
        ticket = result.get("data", {})
        if ticket.get("status") == "error":
            print(f"Expo push error: {ticket.get('message')}")
            return False
        return True
    except Exception as e:
        print(f"Expo push failed: {e}")
        return False
```

**Ưu điểm Expo Push:**
- Không cần Firebase service account
- Không cần OAuth2
- Hoạt động với cả Android (FCM) và iOS (APNs) tự động
- Free tier đủ dùng cho app cá nhân

---

## 6. Thứ tự implement

```
Bước 1: Tạo Firebase project → tải service-account.json
        HOẶC dùng Expo Push (bỏ qua Firebase hoàn toàn)

Bước 2: pip install google-auth APScheduler
        Thêm vào requirements.txt

Bước 3: Tạo fcm_service.py (chọn FCM hoặc Expo Push)

Bước 4: Tạo notification_scheduler.py

Bước 5: Thêm bảng device_tokens vào init_db() trong app.py

Bước 6: Thêm 3 endpoints vào app.py
        POST /api/v1/device/register
        PUT  /api/v1/device/location
        POST /api/v1/device/test-push

Bước 7: Thêm init_scheduler() call vào cuối app.py

Bước 8: Thêm ENABLE_PUSH_SCHEDULER=true vào .env

Bước 9: Mobile — thêm registerDeviceToken() vào App.js

Bước 10: Test với /api/v1/device/test-push trước khi deploy
```

---

## 7. Lưu ý khi deploy

| Vấn đề | Giải pháp |
|--------|-----------|
| APScheduler không chạy trên Gunicorn multi-worker | Thêm `--workers 1` hoặc dùng `--preload` |
| Firebase service account không nên commit lên Git | Thêm `firebase-service-account.json` vào `.gitignore` |
| Device token hết hạn | Kiểm tra response FCM, xóa token lỗi khỏi DB |
| Server timezone sai | Set `TZ=Asia/Ho_Chi_Minh` trong env hoặc Procfile |
| Expo token vs FCM token | Expo token bắt đầu bằng `ExponentPushToken[` — dùng Expo API. FCM token dùng FCM API |

---

*Tạo: 07/05/2026 — Daily Mate Push Notification Planning*
