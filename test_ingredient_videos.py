"""
test_ingredient_videos.py — Automated Unit and Integration Tests for Ingredient Videos API.
Tests:
1. Secret key authentication (missing, invalid, valid).
2. Request payload validation (empty name, missing url, invalid youtube url).
3. Vietnamese slugification and YouTube URL parsing.
4. Idempotent upsert by slug (updates existing record, does not create duplicates).
5. Public GET endpoint for mobile app (no auth required, search/filter).
"""

import json
import os
import unittest
from dotenv import load_dotenv

load_dotenv()

# Set test environment
os.environ["INGREDIENT_VIDEO_ADMIN_KEY"] = "test_secret_admin_key_12345"

from app import app
from ingredient_video_utils import slugify_vietnamese, is_valid_youtube_url
import ingredient_video_store


class TestIngredientVideoUtils(unittest.TestCase):
    def test_slugify_vietnamese(self):
        self.assertEqual(slugify_vietnamese("Cà chua"), "ca-chua")
        self.assertEqual(slugify_vietnamese("Rau muống"), "rau-muong")
        self.assertEqual(slugify_vietnamese("Đậu bắp"), "dau-bap")
        self.assertEqual(slugify_vietnamese("Thịt bò bít tết"), "thit-bo-bit-tet")
        self.assertEqual(slugify_vietnamese("  Hành lá & Tiêu đen!!  "), "hanh-la-tieu-den")
        self.assertEqual(slugify_vietnamese("Ớt hiểm"), "ot-hiem")
        self.assertEqual(slugify_vietnamese("Trứng gà"), "trung-ga")

    def test_is_valid_youtube_url(self):
        # Valid URLs
        self.assertTrue(is_valid_youtube_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ"))
        self.assertTrue(is_valid_youtube_url("https://youtube.com/watch?v=dQw4w9WgXcQ"))
        self.assertTrue(is_valid_youtube_url("http://m.youtube.com/watch?v=dQw4w9WgXcQ&t=10s"))
        self.assertTrue(is_valid_youtube_url("https://youtu.be/dQw4w9WgXcQ"))
        self.assertTrue(is_valid_youtube_url("https://www.youtube.com/shorts/dQw4w9WgXcQ"))
        self.assertTrue(is_valid_youtube_url("https://www.youtube.com/embed/dQw4w9WgXcQ"))

        # Invalid URLs
        self.assertFalse(is_valid_youtube_url(""))
        self.assertFalse(is_valid_youtube_url(None))
        self.assertFalse(is_valid_youtube_url("https://vimeo.com/12345678"))
        self.assertFalse(is_valid_youtube_url("https://facebook.com/video/123456"))
        self.assertFalse(is_valid_youtube_url("https://www.youtube.com/watch"))
        self.assertFalse(is_valid_youtube_url("https://youtu.be/"))
        self.assertFalse(is_valid_youtube_url("not a url"))


class TestIngredientVideosAPI(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self.admin_key = "test_secret_admin_key_12345"

    def test_post_missing_key(self):
        resp = self.client.post(
            "/api/v1/ingredient-videos",
            json={
                "ingredient_name": "Cà chua",
                "video_url": "https://www.youtube.com/watch?v=abc123xyz",
            },
        )
        self.assertEqual(resp.status_code, 401)
        data = resp.get_json()
        self.assertFalse(data["success"])
        self.assertIn("invalid ingredient video key", data["error"])

    def test_post_invalid_key(self):
        resp = self.client.post(
            "/api/v1/ingredient-videos",
            headers={"X-Ingredient-Video-Key": "wrong_key_xyz"},
            json={
                "ingredient_name": "Cà chua",
                "video_url": "https://www.youtube.com/watch?v=abc123xyz",
            },
        )
        self.assertEqual(resp.status_code, 401)
        data = resp.get_json()
        self.assertFalse(data["success"])

    def test_post_missing_name(self):
        resp = self.client.post(
            "/api/v1/ingredient-videos",
            headers={"X-Ingredient-Video-Key": self.admin_key},
            json={
                "ingredient_name": "",
                "video_url": "https://www.youtube.com/watch?v=abc123xyz",
            },
        )
        self.assertEqual(resp.status_code, 400)
        data = resp.get_json()
        self.assertFalse(data["success"])
        self.assertIn("ingredient_name is required", data["error"])

    def test_post_missing_or_invalid_url(self):
        # Missing URL
        resp1 = self.client.post(
            "/api/v1/ingredient-videos",
            headers={"X-Ingredient-Video-Key": self.admin_key},
            json={"ingredient_name": "Cà chua", "video_url": ""},
        )
        self.assertEqual(resp1.status_code, 400)

        # Invalid YouTube URL
        resp2 = self.client.post(
            "/api/v1/ingredient-videos",
            headers={"X-Ingredient-Video-Key": self.admin_key},
            json={
                "ingredient_name": "Cà chua",
                "video_url": "https://tiktok.com/@chef/video/123456",
            },
        )
        self.assertEqual(resp2.status_code, 400)
        data2 = resp2.get_json()
        self.assertIn("valid YouTube URL", data2["error"])

    def test_post_create_and_update_idempotent(self):
        # 1. First POST: Create "Cà chua"
        resp1 = self.client.post(
            "/api/v1/ingredient-videos",
            headers={"X-Ingredient-Video-Key": self.admin_key},
            json={
                "ingredient_name": "Cà chua",
                "video_url": "https://www.youtube.com/watch?v=tomato_v1",
                "category": "Rau củ",
            },
        )
        self.assertEqual(resp1.status_code, 200)
        data1 = resp1.get_json()
        self.assertTrue(data1["success"])
        self.assertEqual(data1["item"]["ingredient_name"], "Cà chua")
        self.assertEqual(data1["item"]["slug"], "ca-chua")
        self.assertEqual(data1["item"]["video_url"], "https://www.youtube.com/watch?v=tomato_v1")
        self.assertEqual(data1["item"]["category"], "Rau củ")

        # 2. Second POST: Update "Cà chua" with new URL and same slug
        resp2 = self.client.post(
            "/api/v1/ingredient-videos",
            headers={"X-Ingredient-Video-Key": self.admin_key},
            json={
                "ingredient_name": "Cà chua",
                "video_url": "https://www.youtube.com/watch?v=tomato_v2_updated",
                "category": "Rau củ quả",
            },
        )
        self.assertEqual(resp2.status_code, 200)
        data2 = resp2.get_json()
        self.assertTrue(data2["success"])
        self.assertEqual(data2["item"]["slug"], "ca-chua")
        self.assertEqual(data2["item"]["video_url"], "https://www.youtube.com/watch?v=tomato_v2_updated")
        self.assertEqual(data2["item"]["category"], "Rau củ quả")

        # 3. Create another ingredient "Rau muống"
        resp3 = self.client.post(
            "/api/v1/ingredient-videos",
            headers={"X-Ingredient-Video-Key": self.admin_key},
            json={
                "ingredient_name": "Rau muống",
                "video_url": "https://youtu.be/water_spinach_v1",
                "category": "Rau củ",
            },
        )
        self.assertEqual(resp3.status_code, 200)
        self.assertEqual(resp3.get_json()["item"]["slug"], "rau-muong")

    def test_get_public_ingredient_videos(self):
        # Insert test items first
        self.client.post(
            "/api/v1/ingredient-videos",
            headers={"X-Ingredient-Video-Key": self.admin_key},
            json={
                "ingredient_name": "Cà chua",
                "video_url": "https://www.youtube.com/watch?v=tomato_v1",
                "category": "Rau củ",
            },
        )
        self.client.post(
            "/api/v1/ingredient-videos",
            headers={"X-Ingredient-Video-Key": self.admin_key},
            json={
                "ingredient_name": "Rau muống",
                "video_url": "https://youtu.be/water_spinach_v1",
                "category": "Rau củ",
            },
        )

        # Public GET without headers
        resp = self.client.get("/api/v1/ingredient-videos")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn("items", data)
        self.assertIn("total", data)
        self.assertIsInstance(data["items"], list)
        self.assertGreaterEqual(data["total"], 2)

        # Check fields of each item
        for item in data["items"]:
            self.assertIn("ingredient_name", item)
            self.assertIn("slug", item)
            self.assertIn("video_url", item)
            self.assertTrue(bool(item["video_url"]))

        # Filter by search
        resp_search = self.client.get("/api/v1/ingredient-videos?search=ca-chua")
        self.assertEqual(resp_search.status_code, 200)
        search_items = resp_search.get_json()["items"]
        self.assertTrue(any(i["slug"] == "ca-chua" for i in search_items))

        # Filter by category
        resp_cat = self.client.get("/api/v1/ingredient-videos?category=Rau+củ")
        self.assertEqual(resp_cat.status_code, 200)
        cat_items = resp_cat.get_json()["items"]
        self.assertGreaterEqual(len(cat_items), 1)


if __name__ == "__main__":
    unittest.main()
