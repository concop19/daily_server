"""
notification_scheduler.py — APScheduler cron gửi push notification 8 lần/ngày.
Mỗi lần: lấy tất cả device tokens → recommend 1 món → gửi Expo push batch.
"""

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from fcm_service import send_batch_notifications

logger = logging.getLogger(__name__)
VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")

# ── Lịch gửi notification (giờ Việt Nam) ─────────────────────────────────────
SLOTS = [
    {"hour": 10, "minute":  0, "meal": "lunch",  "label": "Bữa trưa"},
    {"hour": 10, "minute": 30, "meal": "lunch",  "label": "Bữa trưa"},
    {"hour": 11, "minute":  0, "meal": "lunch",  "label": "Bữa trưa"},
    {"hour": 11, "minute": 30, "meal": "lunch",  "label": "Bữa trưa"},
    {"hour": 16, "minute":  0, "meal": "dinner", "label": "Bữa tối"},
    {"hour": 16, "minute": 30, "meal": "dinner", "label": "Bữa tối"},
    {"hour": 17, "minute":  0, "meal": "dinner", "label": "Bữa tối"},
    {"hour": 17, "minute": 30, "meal": "dinner", "label": "Bữa tối"},
]


def _get_current_slot():
    """Trả về slot hiện tại nếu đúng giờ gửi, ngược lại None."""
    now = datetime.now(VN_TZ)
    return next(
        (s for s in SLOTS if s["hour"] == now.hour and s["minute"] == now.minute),
        None,
    )


def _build_body(dish: dict) -> str:
    """Build notification body từ dish info."""
    hint = (dish.get("explanation") or [None])[0]
    if hint:
        return hint
    cal     = int(dish.get("estimated_calories") or 0)
    protein = int(dish.get("estimated_protein") or 0)
    if cal:
        return f"🔥 {cal}kcal · 🥩 {protein}g đạm"
    return "Hôm nay thử món này đi~ 😋"


def _cleanup_invalid_tokens(messages: list, tickets: list):
    """Xóa device token bị DeviceNotRegistered khỏi data_store."""
    import data_store as _ds
    invalid = [
        msg["to"] for msg, ticket in zip(messages, tickets)
        if ticket.get("status") == "error"
        and ticket.get("details", {}).get("error") == "DeviceNotRegistered"
    ]
    if not invalid:
        return
    invalid_set = set(invalid)
    # Upsert với fcm_token rỗng không đủ — xóa hẳn khỏi _device_tokens
    with _ds._tokens_lock:
        before = len(_ds._device_tokens)
        _ds._device_tokens = [t for t in _ds._device_tokens if t.get("fcm_token") not in invalid_set]
        _ds._persist_tokens()
    logger.info(f"[Push] Removed {before - len(_ds._device_tokens)} invalid tokens")


def run_notification_job(recommend_fn):
    """Job chính — chạy mỗi 30 phút, tự check có phải giờ gửi không."""
    slot = _get_current_slot()
    if not slot:
        return

    logger.info(f"[Push] Slot {slot['hour']}:{slot['minute']:02d} — {slot['label']}")

    # Lấy tất cả devices từ data_store
    import data_store as _ds
    devices = [d for d in _ds.get_all_device_tokens() if d.get("fcm_token")]

    if not devices:
        logger.info("[Push] No devices registered, skipping")
        return

    # Build batch messages
    messages = []
    for device in devices:
        try:
            dish = recommend_fn(dict(device), slot["meal"])
            if not dish:
                continue

            messages.append({
                "to":        device["fcm_token"],
                "title":     f"🍽️ {slot['label']} — {dish['title']}",
                "body":      _build_body(dish),
                "sound":     "default",
                "channelId": "meal-reminders",
                "priority":  "high",
                "data": {
                    "screen":   "MealReminder",
                    "mealId":   slot["meal"],
                    "dishName": dish["title"],
                    "calories": str(int(dish.get("estimated_calories") or 0)),
                    "protein":  str(int(dish.get("estimated_protein") or 0)),
                },
            })
        except Exception as e:
            logger.error(f"[Push] recommend failed for device {device['device_id']}: {e}")

    if not messages:
        return

    # Gửi batch (tối đa 100/lần)
    for i in range(0, len(messages), 100):
        chunk   = messages[i:i + 100]
        tickets = send_batch_notifications(chunk)
        logger.info(f"[Push] Sent {len(chunk)} notifications")
        if tickets:
            _cleanup_invalid_tokens(chunk, tickets)


def init_scheduler(recommend_fn):
    """
    Khởi động APScheduler. Gọi 1 lần trong app.py sau khi Flask init xong.
    Args:
        recommend_fn: hàm (device_dict, meal_type) -> dish dict | None
    """
    scheduler = BackgroundScheduler(timezone=str(VN_TZ))
    scheduler.add_job(
        func=lambda: run_notification_job(recommend_fn),
        trigger=CronTrigger(minute="0,30", timezone=str(VN_TZ)),
        id="meal_push_job",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("[Push] APScheduler started — 8 slots/day active")

    import atexit
    atexit.register(lambda: scheduler.shutdown(wait=False))
    return scheduler
