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
    "calories": {
        "label": "Món này có nhiều năng lượng không?",
        "icon": "calories",
        "query": "Giải thích năng lượng và khẩu phần của món ăn",
        "fields": ("energy_per_serving", "energy_per_100g"),
    },
    "weight_loss": {
        "label": "Món này có phù hợp với mục tiêu giảm cân không?",
        "icon": "weight_loss",
        "query": "Mục tiêu giảm cân cần quan tâm năng lượng và cảm giác no của món ăn như thế nào?",
        "fields": ("energy_per_serving", "dish_satiety_score", "adj_satiety_score"),
    },
    "energy_goal": {
        "label": "Món này có đủ năng lượng cho mục tiêu của tôi không?",
        "icon": "energy_goal",
        "query": "Mục tiêu tăng năng lượng cần quan tâm chỉ số năng lượng và cảm giác no của món ăn như thế nào?",
        "fields": ("energy_per_serving", "energy_per_100g", "dish_satiety_score"),
    },
    "satiety": {
        "label": "Món này có giúp no lâu không?",
        "icon": "satiety",
        "query": "Giải thích chỉ số cảm giác no của món ăn",
        "fields": ("dish_satiety_score", "adj_satiety_score"),
    },
    "weather_fit": {
        "label": "Vì sao món này hợp với thời tiết hôm nay?",
        "icon": "weather_fit",
        "query": "Giải thích mối liên hệ giữa món ăn, thời tiết, cấp nước và làm ấm làm mát",
        "fields": ("dish_hydration_score", "adj_hydration_score", "dish_warming_score", "dish_cooling_score"),
    },
    "allergy_check": {
        "label": "Món này có nguyên liệu cần tránh theo hồ sơ của tôi không?",
        "icon": "allergy",
        "query": "Cách kiểm tra nguyên liệu gây dị ứng trong món ăn",
        "fields": (),
    },
    "diet_type": {
        "label": "Món này có phù hợp với chế độ ăn của tôi không?",
        "icon": "diet_type",
        "query": "Kiểm tra món ăn có phù hợp với chế độ ăn chay hoặc hạn chế thực phẩm nào không",
        "fields": (),
    },
    "ingredient_impact": {
        "label": "Nguyên liệu nào ảnh hưởng nhiều đến chỉ số món?",
        "icon": "ingredient_impact",
        "query": "Giải thích nguyên liệu và định lượng nào đóng góp nhiều vào chỉ số dinh dưỡng của món ăn",
        "fields": (),
    },
    "cooking_method": {
        "label": "Cách chế biến ảnh hưởng đến món thế nào?",
        "icon": "cooking_method",
        "query": "Giải thích cách chế biến ảnh hưởng đến chỉ số dinh dưỡng của món ăn",
        "fields": (),
    },
}


def get_question_specs(
    dish: dict[str, Any],
    profile: dict[str, Any] | None = None,
    recommendation_context: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Generate prioritized questions from the active profile and dish context."""
    profile = profile or {}
    conditions = {str(value).casefold() for value in (profile.get("health_condition") or [])}
    goal = str(profile.get("dietary_goal") or "").casefold()
    diet_type = str(profile.get("diet_type") or "").casefold()
    allergies = profile.get("allergies") or []
    active_reasons = set(recommendation_context.get("active_reasons") or []) if recommendation_context else set()

    selected: list[str] = ["general_nutrition"]
    if any("tiểu đường" in x or "diabetes" in x for x in conditions):
        selected.append("diabetes")
    if any("huyết áp" in x or "hypertension" in x for x in conditions):
        selected.append("hypertension")
    if any("gout" in x or "gút" in x for x in conditions):
        selected.append("gout")
    if any("ibs" in x or "ruột kích thích" in x for x in conditions):
        selected.append("ibs")
    if goal in {"weight_loss", "lose_weight", "giảm cân", "giam_can"}:
        selected.extend(("weight_loss", "calories", "satiety"))
    if goal in {"weight_gain", "gain_weight", "tăng cân", "tang_can"}:
        selected.extend(("energy_goal", "calories"))
    if allergies:
        selected.append("allergy_check")
    if diet_type in {"vegetarian", "vegan", "chay", "thuần chay", "thuan_chay"}:
        selected.append("diet_type")
    if active_reasons & {"weather_cooling", "weather_warming", "weather_hydration", "weather_energy"}:
        selected.append("weather_fit")

    # Sau nhóm ưu tiên theo profile, bổ sung các câu hỏi có dữ liệu thật của món.
    # Đây là nhóm "Xem thêm", không biến thành câu hỏi bệnh lý cá nhân mặc định.
    selected.extend((
        "calories", "satiety", "hypertension", "diabetes", "gout", "ibs", "weather_fit",
        "ingredient_impact", "cooking_method",
    ))

    result = []
    for question_id in dict.fromkeys(selected):
        spec = QUESTION_SPECS[question_id]
        if question_id == "diabetes" and dish.get("adj_glycemic_load") is None:
            continue
        if question_id == "hypertension" and dish.get("sodium_per_serving") is None:
            continue
        if question_id == "gout" and dish.get("gout_risk_score") is None:
            continue
        if question_id in {"calories", "weight_loss", "energy_goal"} and dish.get("energy_per_serving") is None:
            continue
        if question_id == "satiety" and dish.get("dish_satiety_score") is None and dish.get("adj_satiety_score") is None:
            continue
        result.append({"id": question_id, "label": spec["label"], "icon": spec["icon"]})
    return result[:11]


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
        return f"Với toàn bộ công thức món ăn, các chỉ số hiện có gồm {summary}. Đây là số liệu ước tính từ dữ liệu nguyên liệu, định lượng gram và cách chế biến. Vì serving size là toàn bộ công thức, khi ăn một phần nhỏ hơn thì lượng thực tế sẽ thay đổi theo phần ăn."

    if question_id == "diabetes":
        gl = _fmt(dish.get("adj_glycemic_load"))
        if gl is None:
            return "Món này chưa có đủ dữ liệu GL để đánh giá theo câu hỏi này. Hiện chỉ nên tham khảo các chỉ số món đang được hiển thị."
        return f"Tải lượng đường huyết ước tính của toàn bộ công thức là GL {gl}; mốc tham chiếu thường dùng trong tài liệu là GL ≤ 10 cho một khẩu phần. Chỉ số này phụ thuộc vào lượng carbohydrate và khẩu phần thực tế, không chỉ tên món. Món có thể phù hợp hơn nếu khẩu phần được kiểm soát, nhưng đây không phải kết luận y khoa cá nhân."

    if question_id == "hypertension":
        sodium = _fmt(dish.get("sodium_per_serving"))
        if sodium is None:
            return "Món này chưa có đủ dữ liệu natri để nhận xét. Bạn chỉ nên tham khảo các chỉ số hiện có trên trang món ăn."
        return f"Món có khoảng {sodium} mg natri cho toàn bộ công thức; đây là chỉ số nên quan tâm khi theo dõi huyết áp. Natri có thể đến từ nguyên liệu, muối, nước mắm và gia vị trong công thức. Mức phù hợp còn phụ thuộc khẩu phần và tổng lượng natri trong ngày, nên không nên xem đây là kết luận y khoa."

    if question_id == "gout":
        risk = _fmt(dish.get("gout_risk_score"))
        if risk is None:
            return "Món này chưa có điểm nguy cơ gout để tham khảo. Hiện hệ thống chưa đủ dữ liệu để nhận xét riêng chỉ số này."
        return f"Điểm gout của món là {risk} theo thang điểm nội bộ được ước tính từ nguyên liệu, định lượng gram và cách chế biến. Điểm này không phải hàm lượng purine tuyệt đối; nó chỉ giúp tham khảo mức cần lưu ý khi so sánh các món. Người dùng nên xem thêm thành phần thực tế và tình trạng cá nhân, không thay thế tư vấn y tế."

    if question_id == "ibs":
        names = [str(item.get("name")) for item in ingredients if item.get("name")]
        ingredient_text = ", ".join(names[:4])
        if len(names) > 4:
            ingredient_text += " và các nguyên liệu khác"
        suffix = f" Thành phần nổi bật hiện có: {ingredient_text}." if ingredient_text else ""
        return f"Món này chưa có một điểm IBS riêng trong dữ liệu hiện tại.{suffix} Mức phù hợp có thể khác nhau theo từng người và cách dung nạp, nên thông tin này chỉ mang tính tham khảo."

    if question_id == "calories":
        energy = _fmt(dish.get("energy_per_serving"))
        return f"Toàn bộ công thức món ăn cung cấp khoảng {energy or 'chưa xác định'} kcal. Đây là năng lượng của cả công thức, không nhất thiết là lượng bạn sẽ ăn trong một lần. Khi đánh giá mục tiêu cá nhân, nên xem cùng khẩu phần, các món ăn còn lại và mức vận động trong ngày."

    if question_id == "weight_loss":
        energy = _fmt(dish.get("energy_per_serving"))
        satiety = _fmt(dish.get("adj_satiety_score", dish.get("dish_satiety_score")))
        return f"Món có khoảng {energy or 'chưa xác định'} kcal cho toàn bộ công thức và điểm no ước tính {satiety or 'chưa có'}. Hai chỉ số này chỉ là dữ liệu tham khảo, không tự quyết định món có phù hợp với mục tiêu giảm cân hay không. Khẩu phần và tổng năng lượng cả ngày vẫn là yếu tố cần xem xét."

    if question_id == "energy_goal":
        energy = _fmt(dish.get("energy_per_serving"))
        return f"Toàn bộ công thức có khoảng {energy or 'chưa xác định'} kcal. Mức này cần được xem cùng nhu cầu năng lượng, khẩu phần và hoạt động trong ngày của từng người. Hệ thống chưa đủ thông tin để kết luận món đã đáp ứng mục tiêu năng lượng cá nhân."

    if question_id == "satiety":
        satiety = _fmt(dish.get("adj_satiety_score", dish.get("dish_satiety_score")))
        return f"Điểm cảm giác no ước tính của món là {satiety or 'chưa có'} theo thang điểm nội bộ. Điểm được suy ra từ dữ liệu nguyên liệu và định lượng, nên cảm giác no thực tế có thể khác giữa từng người. Khẩu phần và cách ăn cùng món cũng ảnh hưởng đến kết quả."

    if question_id == "weather_fit":
        return "Món được recommendation vì có các điểm liên quan đến thời tiết như cấp nước, làm mát hoặc giữ ấm. Các điểm này được tính từ nguyên liệu, định lượng và cách chế biến của món. Đây là giải thích cho cơ chế recommendation, không phải khẳng định món phù hợp tuyệt đối với mọi người."

    if question_id == "allergy_check":
        names = [str(item.get("name")) for item in ingredients if item.get("name")]
        return f"Danh sách nguyên liệu hiện có gồm: {', '.join(names[:8]) or 'chưa tải được dữ liệu'}. Hệ thống cần đối chiếu danh sách này với dị ứng đã khai báo trong profile; không nên xem món là an toàn nếu chưa kiểm tra từng thành phần và nguy cơ nhiễm chéo."

    if question_id == "diet_type":
        names = [str(item.get("name")) for item in ingredients if item.get("name")]
        return f"Món có các nguyên liệu chính hiện được ghi nhận gồm: {', '.join(names[:8]) or 'chưa tải được dữ liệu'}. Việc phù hợp với chế độ ăn cần dựa trên toàn bộ nguyên liệu, gia vị và cách chế biến, không chỉ tên món."

    if question_id == "ingredient_impact":
        names = [str(item.get("name")) for item in ingredients if item.get("name")]
        return f"Các nguyên liệu được dùng để tính chỉ số món gồm: {', '.join(names[:8]) or 'chưa tải được dữ liệu'}. Mức ảnh hưởng phụ thuộc cả loại nguyên liệu và định lượng gram, vì vậy không nên suy luận chỉ từ một thành phần riêng lẻ."

    if question_id == "cooking_method":
        method = dish.get("cooking_method_id")
        return f"Món được tính với cooking_method_id là {method if method is not None else 'chưa có dữ liệu'}. Cách chế biến có thể làm thay đổi lượng nước, mức cô đặc và khả năng giữ lại một số thành phần; đây là ước tính của hệ thống, không phải kết luận tuyệt đối."

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
