"""
fcm_service.py — Gửi push notification qua Expo Push Service.
Không cần Firebase service account — Expo tự relay sang FCM/APNs.
Token format: "ExponentPushToken[xxxxxxxxxxxxxxxxxxxxxx]"
"""

import logging
import requests

logger = logging.getLogger(__name__)

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"
_HEADERS = {
    "Accept":       "application/json",
    "Content-Type": "application/json",
}


def send_push_notification(expo_token: str, title: str, body: str, data: dict = None) -> bool | str:
    """
    Gửi 1 push notification đến 1 device.
    Returns:
        True  — gửi thành công
        False — lỗi chung
        "invalid_token" — token hết hạn, nên xóa khỏi DB
    """
    if not expo_token or not expo_token.startswith("ExponentPushToken"):
        logger.warning(f"Invalid Expo token format: {expo_token[:20]}")
        return False

    try:
        payload = {
            "to":        expo_token,
            "title":     title,
            "body":      body,
            "sound":     "default",
            "channelId": "meal-reminders",
            "priority":  "high",
            "data":      data or {},
        }

        res = requests.post(EXPO_PUSH_URL, json=payload, headers=_HEADERS, timeout=10)
        res.raise_for_status()

        ticket = res.json().get("data", {})
        if ticket.get("status") == "error":
            err = ticket.get("details", {}).get("error", "")
            logger.error(f"Expo push error: {ticket.get('message')} [{err}]")
            if err == "DeviceNotRegistered":
                return "invalid_token"
            return False

        logger.info(f"Expo push OK — ticket: {ticket.get('id')}")
        return True

    except Exception as e:
        logger.error(f"send_push_notification failed: {e}")
        return False


def send_batch_notifications(messages: list) -> list:
    """
    Gửi nhiều notifications trong 1 request (Expo hỗ trợ tối đa 100/batch).
    messages = list of dicts với keys: to, title, body, data, channelId, ...
    Returns: list of ticket dicts từ Expo
    """
    if not messages:
        return []
    try:
        res = requests.post(EXPO_PUSH_URL, json=messages, headers=_HEADERS, timeout=30)
        res.raise_for_status()
        return res.json().get("data", [])
    except Exception as e:
        logger.error(f"send_batch_notifications failed: {e}")
        return []
