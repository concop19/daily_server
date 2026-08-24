"""
ingredient_video_utils.py — Helper utilities for ingredient video management:
1. Vietnamese slug generation (slugify_vietnamese)
2. YouTube URL validation (is_valid_youtube_url)
"""

import re
import unicodedata
from urllib.parse import parse_qs, urlparse

_VIETNAMESE_SPECIAL_MAP = {
    "đ": "d",
    "Đ": "d",
    "ð": "d",
    "Ð": "d",
}


def slugify_vietnamese(text: str) -> str:
    """
    Convert a Vietnamese string into an ASCII slug.
    Examples:
        "Cà chua" -> "ca-chua"
        "Rau muống" -> "rau-muong"
        "Đậu bắp" -> "dau-bap"
        "Hành lá & Tiêu đen" -> "hanh-la-tieu-den"
    """
    if not text:
        return ""

    s = str(text).strip()
    for src, target in _VIETNAMESE_SPECIAL_MAP.items():
        s = s.replace(src, target)

    # Decompose unicode characters into base + combining accents, then remove combining marks (Mn)
    nfd = unicodedata.normalize("NFD", s)
    stripped = "".join(c for c in nfd if unicodedata.category(c) != "Mn")

    # Lowercase
    lowered = stripped.lower()

    # Replace any non-alphanumeric character with hyphen
    hyphenated = re.sub(r"[^a-z0-9]+", "-", lowered)

    # Strip extra hyphens
    slug = hyphenated.strip("-")
    return slug


_YOUTUBE_HOSTS = frozenset({
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
    "www.youtu.be",
})


def is_valid_youtube_url(url: str) -> bool:
    """
    Validate whether a given URL is a valid YouTube video link.
    Supports formats:
        - https://www.youtube.com/watch?v=VIDEO_ID
        - https://youtu.be/VIDEO_ID
        - https://www.youtube.com/shorts/VIDEO_ID
        - https://www.youtube.com/embed/VIDEO_ID
        - https://m.youtube.com/watch?v=VIDEO_ID
    """
    if not url or not isinstance(url, str):
        return False

    url = url.strip()
    try:
        parsed = urlparse(url)
    except Exception:
        return False

    if parsed.scheme not in ("http", "https"):
        return False

    hostname = (parsed.hostname or "").lower()
    if hostname not in _YOUTUBE_HOSTS:
        return False

    path = parsed.path or ""

    # Case 1: youtu.be/VIDEO_ID
    if "youtu.be" in hostname:
        video_id = path.lstrip("/").split("/")[0].split("?")[0]
        return len(video_id) >= 5

    # Case 2: youtube.com/watch?v=VIDEO_ID
    if path == "/watch" or path.startswith("/watch/"):
        qs = parse_qs(parsed.query)
        v_list = qs.get("v")
        if v_list and len(v_list[0].strip()) >= 5:
            return True
        return False

    # Case 3: youtube.com/shorts/VIDEO_ID, youtube.com/embed/VIDEO_ID, youtube.com/v/VIDEO_ID
    for prefix in ("/shorts/", "/embed/", "/v/"):
        if path.startswith(prefix):
            video_id = path[len(prefix):].split("/")[0].split("?")[0]
            return len(video_id) >= 5

    return False
