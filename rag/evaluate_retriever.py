"""Run 50 deterministic tests against the Nutrition RAG retriever."""

from __future__ import annotations

from dataclasses import dataclass
import sys
import time

from .retriever import NutritionRetriever


@dataclass(frozen=True)
class TestCase:
    name: str
    query: str
    expected_condition: str | None
    expected_plan_group: str | None
    expected_retrieval_group: str
    expected_field: str


def _cases() -> list[TestCase]:
    cases: list[TestCase] = []

    for i, query in enumerate(
        [
            "Người bị tiểu đường nên quan tâm GL của món này không?",
            "Món này có tải lượng đường huyết cao không với người tiểu đường?",
            "Người đái tháo đường cần xem chỉ số nào của món ăn?",
            "Carbohydrate trong món này có ý nghĩa gì với tiểu đường?",
            "GL của món này có phù hợp để tham khảo cho bệnh tiểu đường không?",
            "Tiểu đường có cần quan tâm khẩu phần của món này không?",
            "Món này ảnh hưởng đường huyết người tiểu đường thế nào?",
            "Người bệnh diabetes cần xem GL hay GI?",
            "Tải lượng GL món này được tính ra sao cho người tiểu đường?",
            "Giải thích dinh dưỡng món này cho người đái tháo đường.",
        ],
        1,
    ):
        cases.append(TestCase(f"diabetes_{i:02d}", query, "diabetes", "tieu_duong", "tieu_duong", "adj_glycemic_load"))

    for i, query in enumerate(
        [
            "Người bị tăng huyết áp cần quan tâm natri trong món này không?",
            "Món này có nhiều muối với người cao huyết áp không?",
            "Sodium của món ăn có ý nghĩa gì với tăng huyết áp?",
            "Người bệnh hypertension cần xem chỉ số nào?",
            "Nước mắm trong món này ảnh hưởng natri ra sao với huyết áp?",
            "Giải thích sodium safety score cho người tăng huyết áp.",
            "Món này có phù hợp để tham khảo cho người cao huyết áp không?",
            "Natri điều chỉnh theo cách nấu được hiểu thế nào?",
            "Tăng huyết áp và lượng sodium trong một serving món ăn.",
            "Chỉ số muối của món này đối với người bệnh huyết áp.",
        ],
        1,
    ):
        expected_condition = "hypertension" if "tăng huyết áp" in query.casefold() or "cao huyết áp" in query.casefold() or "hypertension" in query.casefold() or "huyết áp" in query.casefold() else None
        expected_plan_group = "tang_huyet_ap" if expected_condition else None
        cases.append(TestCase(f"hypertension_{i:02d}", query, expected_condition, expected_plan_group, "tang_huyet_ap" if expected_condition else "dinh_duong", "adj_sodium_total"))

    for i, query in enumerate(
        [
            "Người bị gout cần quan tâm purine trong món này không?",
            "Món này có phù hợp để tham khảo cho người bị gút không?",
            "Gout risk score của món này có ý nghĩa gì?",
            "Người có axit uric cao nên đọc chỉ số nào của món?",
            "Purine trong nguyên liệu ảnh hưởng đánh giá gout ra sao?",
            "Giải thích món này theo góc nhìn bệnh gout.",
            "Món này có nguy cơ gout cao hay thấp theo hệ thống?",
            "Gout và phương pháp nấu món ăn liên quan thế nào?",
            "Người bệnh gút cần xem gout risk score hay sodium?",
            "Giải thích purine và gout risk score của món.",
        ],
        1,
    ):
        cases.append(TestCase(f"gout_{i:02d}", query, "gout", "gout", "gout", "gout_risk_score"))

    for i, query in enumerate(
        [
            "Người bị IBS cần quan tâm gia vị trong món này không?",
            "Người IBS có thể quan tâm thành phần kích thích ruột trong món này không?",
            "Giải thích món này cho người có hội chứng ruột kích thích.",
            "IBS và chất xơ trong món ăn có ý nghĩa gì?",
            "Người bệnh ruột kích thích cần chú ý chỉ số nào của món?",
        ],
        1,
    ):
        cases.append(TestCase(f"ibs_{i:02d}", query, "ibs", "ibs", "ibs", "adj_energy_total"))

    for i, query in enumerate(
        [
            "Món này có bao nhiêu calo?",
            "Giải thích năng lượng của món ăn.",
            "Món này có nhiều natri không?",
            "Sodium của món này là bao nhiêu?",
            "GL của món ăn được tính thế nào?",
            "Món này có tải lượng đường huyết bao nhiêu?",
            "Chỉ số hydration và satiety của món có ý nghĩa gì?",
            "Món ăn này có no lâu không theo dữ liệu?",
            "Giải thích raw và adjusted value của món.",
            "Các chỉ số dinh dưỡng cơ bản của món này là gì?",
        ],
        1,
    ):
        lowered = query.casefold()
        if "natri" in lowered or "sodium" in lowered:
            field = "sodium_per_serving"
        elif "gl" in lowered or "đường huyết" in lowered:
            field = "adj_glycemic_load"
        elif "hydration" in lowered:
            field = "dish_hydration_score"
        elif "satiety" in lowered or "no lâu" in lowered:
            field = "dish_satiety_score"
        else:
            field = "energy_per_serving"
        cases.append(TestCase(f"general_{i:02d}", query, None, None, "dinh_duong", field))

    for i, query in enumerate(
        [
            "Tôi không bị tiểu đường nhưng bị đau răng, cần quan tâm chỉ số nào?",
            "Tôi không mắc gout, chỉ muốn biết dinh dưỡng món này.",
            "Tôi không bị tăng huyết áp, món này có chỉ số gì?",
            "Không bị IBS, hãy cho biết thông tin dinh dưỡng chung.",
            "Tôi bị đau răng, món này có thông tin dinh dưỡng cơ bản nào?",
        ],
        1,
    ):
        cases.append(TestCase(f"negation_{i:02d}", query, None, None, "dinh_duong", "energy_per_serving"))

    assert len(cases) == 50
    return cases


def run() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    cases = _cases()
    retriever = NutritionRetriever()
    passed = 0
    condition_ok = 0
    group_ok = 0
    field_ok = 0
    retrieval_ok = 0
    failures: list[str] = []
    started = time.perf_counter()

    for index, case in enumerate(cases, 1):
        result = retriever.retrieve(case.query, n_results=5)
        plan = result["plan"]
        metadatas = result["results"].get("metadatas", [[]])[0]
        top_groups = {metadata.get("group") for metadata in metadatas}
        checks = {
            "condition": plan.condition == case.expected_condition,
            "group": plan.group == case.expected_plan_group,
            "field": case.expected_field in plan.nutrition_fields,
            "retrieval": case.expected_retrieval_group in top_groups,
        }
        condition_ok += checks["condition"]
        group_ok += checks["group"]
        field_ok += checks["field"]
        retrieval_ok += checks["retrieval"]
        if all(checks.values()):
            passed += 1
            status = "PASS"
        else:
            status = "FAIL"
            failures.append(
                f"{case.name}: {checks} | condition={plan.condition} group={plan.group} "
                f"fields={plan.nutrition_fields} top_groups={top_groups}"
            )
        print(f"[{index:02d}/50] {status} {case.name}")

    elapsed = time.perf_counter() - started
    print("\n=== SUMMARY ===")
    print(f"passed: {passed}/50 ({passed / 50:.1%})")
    print(f"condition_accuracy: {condition_ok}/50 ({condition_ok / 50:.1%})")
    print(f"group_accuracy: {group_ok}/50 ({group_ok / 50:.1%})")
    print(f"field_accuracy: {field_ok}/50 ({field_ok / 50:.1%})")
    print(f"retrieval_group_hit: {retrieval_ok}/50 ({retrieval_ok / 50:.1%})")
    print(f"elapsed_seconds: {elapsed:.1f}")
    if failures:
        print("\nFAILURES:")
        for failure in failures:
            print(f"- {failure}")
    return 0 if passed == 50 else 1


if __name__ == "__main__":
    raise SystemExit(run())
