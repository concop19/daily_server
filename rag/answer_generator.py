"""Generate Vietnamese answers from Nutrition RAG context using Groq."""

from __future__ import annotations

import json
import os
from typing import Any

import requests


GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.1-8b-instant")


def generate_nutrition_answer(
    *,
    question: str,
    context: dict[str, Any],
    profile: dict[str, Any] | None = None,
    language: str = "vi",
) -> str:
    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GROQ_API_KEY chưa được cấu hình")

    dish = context.get("dish") or {}
    evidence = context.get("evidence") or {}
    prompt_context = {
        "profile": profile or {},
        "dish": dish,
        "evidence": evidence,
    }
    if str(language).lower().split("-", 1)[0] == "en":
        system = (
            "You are Daily Mate's nutrition assistant. Answer only in clear English in 2-4 sentences. "
            "Use dish numbers as the source of truth and never invent missing fields. Use evidence to explain, "
            "not to make a certain medical diagnosis. Mention serving_size whenever using numbers, do not give "
            "treatment instructions or suggest changing the recipe, and end with: 'This information is for "
            "reference only and does not replace medical advice.'"
        )
    else:
        system = (
            "Bạn là trợ lý dinh dưỡng của Daily Mate. Chỉ trả lời bằng tiếng Việt, dễ hiểu, "
            "dài 2-4 câu. Bắt buộc dùng các số liệu trong dish làm nguồn sự thật; không tự đoán "
            "field bị thiếu. Dùng tài liệu evidence để giải thích, không biến thông tin thành "
            "kết luận y khoa chắc chắn. Nêu điều kiện như 'có thể phù hợp nếu kiểm soát khẩu phần' "
            "khi cần. Luôn nói rõ serving_size nếu dùng số liệu. Không đưa hướng dẫn điều trị, "
            "không tự đề xuất sửa công thức. Kết thúc bằng: 'Thông tin mang tính tham khảo, "
            "không thay thế tư vấn y tế.'"
        )
    user = "Câu hỏi: %s\nContext RAG (chỉ dùng dữ liệu này):\n%s" % (
        question,
        json.dumps(prompt_context, ensure_ascii=False, default=str),
    )
    response = requests.post(
        GROQ_URL,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": GROQ_MODEL,
            "temperature": 0.2,
            "max_tokens": 350,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        },
        timeout=25,
    )
    response.raise_for_status()
    content = response.json()["choices"][0]["message"]["content"].strip()
    if not content:
        raise RuntimeError("Model trả về câu trả lời rỗng")
    return content
