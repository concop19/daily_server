"""Fixed, safe health-question catalog and deterministic answer layer."""

from __future__ import annotations

from typing import Any

import data_store


QUESTION_SPECS: dict[str, dict[str, Any]] = {
    "general_nutrition": {
        "label": "Món này có những chỉ số dinh dưỡng nào?",
        "icon": "nutrition",
        "query": "Giải thích các chỉ số dinh dưỡng cơ bản của món ăn",
        "fields": ("energy_per_serving", "sodium_per_serving", "adj_glycemic_load"),
    },
    "diabetes": {
        "label": "Người tiểu đường cần lưu ý gì?",
        "icon": "diabetes",
        "query": "Người bị tiểu đường cần lưu ý tải lượng đường huyết của món ăn như thế nào?",
        "fields": ("adj_glycemic_load", "adj_glycemic_load_per_100g", "gl_safety_score"),
    },
    "hypertension": {
        "label": "Món này có nhiều natri không?",
        "icon": "hypertension",
        "query": "Người bị tăng huyết áp cần quan tâm lượng natri trong món ăn như thế nào?",
        "fields": ("sodium_per_serving", "sodium_per_100g", "adj_sodium_total", "sodium_safety_score"),
    },
    "gout": {
        "label": "Người bị gout cần quan tâm gì?",
        "icon": "gout",
        "query": "Người bị gout cần lưu ý purine và nguy cơ gout của món ăn như thế nào?",
        "fields": ("gout_risk_score",),
    },
    "ibs": {
        "label": "IBS có cần lưu ý gì với món này không?",
        "icon": "ibs",
        "query": "Người có IBS cần lưu ý gì khi xem nguyên liệu và gia vị của món ăn?",
        "fields": (),
    },
}


def get_question_specs(dish: dict[str, Any]) -> list[dict[str, Any]]:
    """Return stable questions; availability is decided by server-side fields."""
    result = []
    for question_id, spec in QUESTION_SPECS.items():
        if question_id == "diabetes" and dish.get("adj_glycemic_load") is None:
            continue
        if question_id == "hypertension" and dish.get("sodium_per_serving") is None:
            continue
        if question_id == "gout" and dish.get("gout_risk_score") is None:
            continue
        result.append({"id": question_id, "label": spec["label"], "icon": spec["icon"]})
    return result


def _fmt(value: Any, digits: int = 2) -> str | None:
    if value is None:
        return None
    try:
        return f"{float(value):.{digits}f}".rstrip("0").rstrip(".")
    except (TypeError, ValueError):
        return str(value)


def build_answer(question_id: str, dish: dict[str, Any], ingredients: list[dict[str, Any]]) -> str:
    if question_id == "general_nutrition":
        parts = []
        if dish.get("energy_per_serving") is not None:
            parts.append(f"năng lượng {_fmt(dish['energy_per_serving'])} kcal")
        if dish.get("sodium_per_serving") is not None:
            parts.append(f"natri {_fmt(dish['sodium_per_serving'])} mg")
        if dish.get("adj_glycemic_load") is not None:
            parts.append(f"GL {_fmt(dish['adj_glycemic_load'])}")
        summary = ", ".join(parts) or "chưa có đủ chỉ số định lượng"
        return f"Với toàn bộ công thức món ăn, các chỉ số hiện có gồm {summary}. Đây là số liệu ước tính từ dữ liệu nguyên liệu và công thức, nên nên xem cùng khẩu phần thực tế."

    if question_id == "diabetes":
        gl = _fmt(dish.get("adj_glycemic_load"))
        if gl is None:
            return "Món này chưa có đủ dữ liệu GL để đánh giá theo câu hỏi này. Hiện chỉ nên tham khảo các chỉ số món đang được hiển thị."
        return f"Tải lượng đường huyết ước tính của toàn bộ công thức là GL {gl}; mốc tham chiếu thường dùng trong tài liệu là GL ≤ 10 cho một khẩu phần. Món có thể phù hợp hơn nếu khẩu phần được kiểm soát, nhưng đây không phải kết luận y khoa cá nhân."

    if question_id == "hypertension":
        sodium = _fmt(dish.get("sodium_per_serving"))
        if sodium is None:
            return "Món này chưa có đủ dữ liệu natri để nhận xét. Bạn chỉ nên tham khảo các chỉ số hiện có trên trang món ăn."
        return f"Món có khoảng {sodium} mg natri cho toàn bộ công thức; đây là chỉ số nên quan tâm khi theo dõi huyết áp. Mức phù hợp còn phụ thuộc khẩu phần và tổng lượng natri trong ngày, nên không nên xem đây là kết luận y khoa."

    if question_id == "gout":
        risk = _fmt(dish.get("gout_risk_score"))
        if risk is None:
            return "Món này chưa có điểm nguy cơ gout để tham khảo. Hiện hệ thống chưa đủ dữ liệu để nhận xét riêng chỉ số này."
        return f"Điểm gout của món là {risk} theo thang điểm nội bộ được ước tính từ nguyên liệu và cách chế biến. Điểm này chỉ giúp tham khảo mức cần lưu ý, không thay thế đánh giá purine và tư vấn cá nhân."

    if question_id == "ibs":
        names = [str(item.get("name")) for item in ingredients if item.get("name")]
        ingredient_text = ", ".join(names[:4])
        if len(names) > 4:
            ingredient_text += " và các nguyên liệu khác"
        suffix = f" Thành phần nổi bật hiện có: {ingredient_text}." if ingredient_text else ""
        return f"Món này chưa có một điểm IBS riêng trong dữ liệu hiện tại.{suffix} Mức phù hợp có thể khác nhau theo từng người và cách dung nạp, nên thông tin này chỉ mang tính tham khảo."

    raise KeyError(f"question_id không hợp lệ: {question_id}")


def source_summaries(evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    seen = set()
    for item in evidence:
        metadata = item.get("metadata") or {}
        source_id = metadata.get("source_id")
        if not source_id or source_id in seen:
            continue
        seen.add(source_id)
        result.append({"source_id": source_id, "title": metadata.get("title"), "topic": metadata.get("topic")})
    return result
