"""
setup_ingredient_videos_supabase.py — Check Supabase ingredient_videos table status.
Usage: python setup_ingredient_videos_supabase.py
"""

import os
import sys
import requests
from dotenv import load_dotenv

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

HEADERS = {
    "apikey":        SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type":  "application/json",
}


def check_table_exists() -> bool:
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("[!] SUPABASE_URL hoặc SUPABASE_SERVICE_ROLE_KEY chưa được cấu hình trong .env")
        return False
    try:
        resp = requests.get(
            f"{SUPABASE_URL}/rest/v1/ingredient_videos",
            params={"limit": "1", "select": "id,slug"},
            headers=HEADERS,
            timeout=5,
        )
        return resp.status_code == 200
    except Exception as e:
        print(f"[!] Lỗi kết nối Supabase: {e}")
        return False


if __name__ == "__main__":
    print("=" * 60)
    print("  Daily Mate — Kiểm tra bảng ingredient_videos trên Supabase")
    print("=" * 60)

    if check_table_exists():
        print("\n✅ Bảng ingredient_videos đã tồn tại và sẵn sàng trên Supabase!")
    else:
        print("\n⚠️  Bảng ingredient_videos chưa được tạo trên Supabase.")
        print("   Vui lòng thực hiện các bước sau để kích hoạt trên Supabase:")
        print("   1. Mở Supabase SQL Editor:")
        if SUPABASE_URL:
            project_id = SUPABASE_URL.replace("https://", "").split(".")[0]
            print(f"      https://supabase.com/dashboard/project/{project_id}/sql")
        else:
            print("      https://supabase.com/dashboard")
        print("   2. Sao chép và chạy nội dung trong file:")
        print("      supabase_ingredient_videos_migration.sql")
        print("\n   Hệ thống backend đã tích hợp sẵn cơ chế local fallback an toàn trong khi chờ tạo bảng.")
