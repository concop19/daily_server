import sys, re
sys.stdout.reconfigure(encoding='utf-8')

path = r'D:\dream_project\daily_mate_code\demo_server\advice_engine.py'
with open(path, 'r', encoding='utf-8') as f:
    src = f.read()

OLD_BODY = '''    # ── Hypertension ──────────────────────────────────────────────────────────
    if df.get("hypertension") and sodium:
        if sodium < 400:
            parts.append(f"Rất ít sodium ({sodium:.0f}mg/serving) — lý tưởng cho huyết áp cao.")
        elif sodium < 500:
            parts.append(f"Ít sodium ({sodium:.0f}mg/serving) — phù hợp với huyết áp cao.")
        else:
            # 500-600mg: gần threshold → warning
            parts.append(
                f"⚠️ Sodium ở mức {sodium:.0f}mg/serving (giới hạn 600mg) — "
                f"không nên thêm nước mắm hoặc muối khi ăn."
            )

    # ── Diabetes ──────────────────────────────────────────────────────────────
    if df.get("diabetes") and gl:
        if gl < 7:
            parts.append(f"Chỉ số đường huyết rất thấp (GL {gl:.1f}) — lý tưởng kiểm soát đường máu.")
        elif gl < 10:
            parts.append(f"Chỉ số đường huyết thấp (GL {gl:.1f}) — an toàn cho người tiểu đường.")
        else:
            # 10-25: gần threshold → ăn kèm rau
            parts.append(
                f"⚠️ Glycemic load {gl:.1f} — ăn chậm, kết hợp rau xanh nhiều xơ "
                f"để giảm tốc độ hấp thụ đường."
            )

    # ── Gout ──────────────────────────────────────────────────────────────────
    if df.get("gout"):
        if gout_s is not None:
            if gout_s >= 0.8:
                parts.append("Hàm lượng purine rất thấp — hoàn toàn phù hợp với người bị gout.")
            elif gout_s >= 0.5:
                parts.append(
                    "Purine ở mức trung bình — ăn lượng vừa phải, "
                    "uống nhiều nước để hỗ trợ thải acid uric."
                )
            else:
                parts.append(
                    "⚠️ Món này có thể chứa purine ở mức trung bình — "
                    "hạn chế khẩu phần và theo dõi phản ứng cơ thể."
                )
        else:
            parts.append("Ưu tiên rau củ và ngũ cốc — hạn chế hải sản và nội tạng.")

    # ── IBS ───────────────────────────────────────────────────────────────────
    if df.get("ibs"):
        parts.append(
            "Nguyên liệu dễ tiêu hoá — phù hợp đường ruột nhạy cảm. "
            "Tránh ăn quá nhanh hoặc quá no."
        )

    # ── BMI ───────────────────────────────────────────────────────────────────
    bmi = profile.get("BMI", 22)
    if bmi and bmi > 25 and cal:
        parts.append(f"Ít calo ({cal:.0f}kcal/serving) — hỗ trợ kiểm soát cân nặng.")
    elif bmi and bmi < 18.5 and cal:
        parts.append(f"Giàu năng lượng ({cal:.0f}kcal/serving) — bổ sung đủ dinh dưỡng.")

    # ── Diet type ─────────────────────────────────────────────────────────────
    diet = profile.get("diet_type", "omnivore")
    if diet == "vegan":
        parts.append("100% thực vật — không chứa nguyên liệu động vật.")
    elif diet == "vegetarian" and dish.get("is_vegetarian"):
        parts.append("Món chay — không có thịt, phù hợp chế độ ăn của bạn.")'''

NEW_BODY = '''    def _pick_health(trigger_dim: str, fill_vars: dict, fallback: str) -> str:
        """Query context_type='health', random-weighted, điền biến."""
        if db is None:
            return _fill(fallback, **fill_vars)
        rows = db.execute(
            "SELECT template_text, priority FROM advice_templates "
            "WHERE context_type='health' AND trigger_dim=? "
            "ORDER BY priority ASC LIMIT 5",
            (trigger_dim,)
        ).fetchall()
        if not rows:
            return _fill(fallback, **fill_vars)
        wm = {1: 9, 2: 3, 3: 1}
        weights = [wm.get(r[1], 1) for r in rows]
        chosen = random.choices(rows, weights=weights, k=1)[0]
        return _fill(chosen[0], **fill_vars)

    # ── Hypertension ──────────────────────────────────────────────────────────
    if df.get("hypertension") and sodium:
        if sodium < 400:
            parts.append(_pick_health("hypertension",
                {"sodium_mg": f"{sodium:.0f}"},
                f"Rất ít sodium ({sodium:.0f}mg/serving) — lý tưởng cho huyết áp cao."))
        elif sodium < 600:
            parts.append(_pick_health("hypertension_warn",
                {"sodium_mg": f"{sodium:.0f}"},
                f"Sodium {sodium:.0f}mg/serving — phù hợp kiểm soát huyết áp."))
        else:
            parts.append(_pick_health("hypertension_high",
                {"sodium_mg": f"{sodium:.0f}"},
                f"⚠️ Sodium {sodium:.0f}mg/serving — không nên thêm muối khi ăn."))

    # ── Diabetes ──────────────────────────────────────────────────────────────
    if df.get("diabetes") and gl:
        if gl < 7:
            parts.append(_pick_health("diabetes",
                {"glycemic_load": f"{gl:.1f}"},
                f"GL {gl:.1f} rất thấp — lý tưởng kiểm soát đường máu."))
        elif gl < 10:
            parts.append(_pick_health("diabetes_fiber",
                {"glycemic_load": f"{gl:.1f}"},
                f"GL {gl:.1f} thấp — an toàn cho người tiểu đường."))
        else:
            parts.append(_pick_health("diabetes_warn",
                {"glycemic_load": f"{gl:.1f}"},
                f"⚠️ GL {gl:.1f} — ăn chậm, kết hợp rau xanh nhiều chất xơ."))

    # ── Gout ──────────────────────────────────────────────────────────────────
    if df.get("gout"):
        if gout_s is not None and gout_s >= 0.8:
            parts.append(_pick_health("gout", {},
                "Purine rất thấp — phù hợp người bị gout."))
        elif gout_s is not None and gout_s >= 0.5:
            parts.append(_pick_health("gout_warn", {},
                "Purine trung bình — ăn vừa phải, uống nhiều nước thải acid uric."))
        else:
            parts.append(_pick_health("gout_warn", {},
                "⚠️ Có thể chứa purine — hạn chế khẩu phần và theo dõi cơ thể."))

    # ── IBS ───────────────────────────────────────────────────────────────────
    if df.get("ibs"):
        parts.append(_pick_health("ibs", {},
            "Nguyên liệu dễ tiêu hoá — phù hợp đường ruột nhạy cảm."))

    # ── BMI ───────────────────────────────────────────────────────────────────
    bmi = profile.get("BMI", 22)
    if bmi and bmi > 27 and cal:
        parts.append(_pick_health("high_bmi_strong",
            {"calorie": f"{cal:.0f}"},
            f"Ít calo ({cal:.0f}kcal/serving) — hỗ trợ kiểm soát cân nặng."))
    elif bmi and bmi > 25 and cal:
        parts.append(_pick_health("high_bmi_mild",
            {"calorie": f"{cal:.0f}"},
            f"Cân bằng calo ({cal:.0f}kcal/serving) — vừa no mà không dư thừa."))
    elif bmi and bmi < 18.5 and cal:
        parts.append(_pick_health("underweight",
            {"calorie": f"{cal:.0f}"},
            f"Giàu năng lượng ({cal:.0f}kcal/serving) — bổ sung đủ dinh dưỡng."))

    # ── Diet type ─────────────────────────────────────────────────────────────
    diet = profile.get("diet_type", "omnivore")
    if diet == "vegan":
        parts.append(_pick_health("vegan", {},
            "100% thực vật — không chứa nguyên liệu động vật."))
    elif diet == "vegetarian" and dish.get("is_vegetarian"):
        parts.append(_pick_health("vegetarian", {},
            "Món chay — không có thịt, phù hợp chế độ ăn của bạn."))'''

if OLD_BODY in src:
    src = src.replace(OLD_BODY, NEW_BODY, 1)
    print("BODY REPLACED OK")
else:
    print("OLD_BODY NOT FOUND — checking snippet...")
    snippet = '    if df.get("hypertension") and sodium:'
    print(f"snippet present: {snippet in src}")

with open(path, 'w', encoding='utf-8') as f:
    f.write(src)
print("SAVED")
