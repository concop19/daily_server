# Daily Mate — Chiến lược cải thiện Personalization theo BMI & Tuổi
**Ngày tạo:** 2026-05-06  
**Phiên bản:** v1.1  
**Phạm vi:** `pipeline.py` · `advice_engine.py`  
**Tác giả:** Technical review từ test session 2026-05-06

---

## 1. Vấn đề

### 1.1 Quan sát từ test

Chạy 4 test cases với cùng location (Hà Nội), cùng thời tiết, chỉ khác tuổi và BMI:

| Test | Tuổi | BMI | TDEE tính được | Top 1 kết quả |
|---|---|---|---|---|
| TC031 | 70 | ~25 | 1 624 kcal | Canh chua mực tôm |
| TC033 | 40 | ~39 | 2 323 kcal | **Canh chua mực tôm** ← y hệt |
| TC032 | 18 | ~21 | 2 759 kcal | Cua hấp lò vi sóng |
| TC034 | 22 | ~15 | 1 471 kcal | Cua hấp lò vi sóng |

TC031 (người cao tuổi, TDEE thấp) và TC033 (người béo phì BMI 39, TDEE cao) cho ra **top2 y hệt nhau hoàn toàn**. Tương tự TC032 và TC034 — kết quả giống nhau dù thể trạng khác xa.

Nói cách khác: **hệ thống đang bỏ qua BMI và tuổi khi xếp hạng món ăn.**

---

### 1.2 Kỳ vọng thực tế

Dựa trên kiến thức dinh dưỡng:

**Người béo phì (BMI ≥ 30)** cần:
- Món ít calo, no lâu (satiety cao), nhiều xơ
- Tránh món chiên, nhiều mỡ, carb tinh chế
- Ưu tiên canh thanh, rau luộc, protein nạc

**Người thiếu cân (BMI < 18.5)** cần:
- Món calo dày đặc, giàu protein và chất béo lành mạnh
- Cháo bổ dưỡng, thịt kho, canh có protein cao
- Tránh canh loãng ít dinh dưỡng

**Người cao tuổi (> 60 tuổi)** cần:
- Món mềm, dễ tiêu hóa (hấp, luộc, canh loãng)
- Ít gia vị mạnh, ít dầu mỡ
- Kiểm soát calo dù TDEE không quá cao

Với BMI 39, hệ thống lý tưởng nên ưu tiên **Canh rau cải luộc** hơn **Canh chua mực tôm** (calo cao hơn, ít satiety hơn).

---

### 1.3 Root cause — tìm trong code

**Bước 1: Kiểm tra `compute_demand()` trong `pipeline.py`**

```python
def compute_demand(wv: dict, pv: dict, climate_type: str) -> dict:
    ...
    return {
        "hydration_need":        round(h,  4),
        "electrolyte_need":      round(e,  4),
        "thermoregulation_need": round(th, 4),
        "energy_need":           round(en, 2),   # ← raw kcal, e.g. 1624.0
        "warming_food_need":     round(w,  4),
        "cooling_food_need":     round(c,  4),
        "sodium_control_need":   ...,
        ...
    }
```

BMI và tuổi được tính đúng ở `compute_personal_vector()` — `bmi`, `energy_need` (TDEE) đều có giá trị chính xác. Nhưng chúng **không được đưa vào demand dict** dưới dạng dimension có thể dùng để score.

`energy_need` có trong demand dict nhưng là số kcal thô (1624.0) — không phải score [0,1] và không được dùng ở bất kỳ đâu trong scoring.

---

**Bước 2: Kiểm tra `score_dish()` — hàm DIMS**

```python
DIMS = [
    ("hydration_need",        "adj_hydration_score",   "dish_hydration_score"),
    ("electrolyte_need",      "adj_hydration_score",   None),
    ("thermoregulation_need", "adj_thermogenic_score", "dish_thermogenic_score"),
    ("warming_food_need",     "adj_warming_score",     "dish_warming_score"),
    ("cooling_food_need",     "adj_cooling_score",     "dish_cooling_score"),
]
```

**DIMS chỉ có 5 dimension — toàn bộ là thời tiết / khí hậu.** Không có dimension nào map tới:
- `adj_satiety_score` (đã có trong DB, đã được fetch vào dish dict)
- `adj_energy_total` (đã có trong DB, đã được fetch vào dish dict)

Hai cột này ngồi trong dish dict qua từng lần scoring **mà không được dùng**.

---

**Bước 3: Kiểm tra `build_constraint_profile()`**

```python
"calorie_target": round(pv["energy_need"] * 0.35, 0),
```

`calorie_target` được tính (35% TDEE / serving) nhưng chỉ truyền sang `advice_engine.py` để **sinh text giải thích** trong `check_fit_reasons()`. Nó không ảnh hưởng đến điểm số.

---

**Bước 4: Kiểm tra `check_fit_reasons()` trong `advice_engine.py`**

```python
if bmi > 25 and dish_cal and float(dish_cal) <= calorie_target * 1.1:
    reasons.add("bmi_overweight")
if bmi < 18.5 and dish_cal and float(dish_cal) >= calorie_target * 0.9:
    reasons.add("bmi_underweight")
```

FitChecker **có check BMI** nhưng chỉ dùng để quyết định có sinh giải thích text hay không — không feed ngược lại vào score.

---

**Sơ đồ luồng hiện tại:**

```
BMI, Tuổi
    │
    ▼
compute_personal_vector()
    ├── BMI = 39 ✓ tính đúng
    ├── energy_need = 2323 kcal ✓ tính đúng
    └── calorie_target = 813 kcal ✓ tính đúng
    │
    ▼
compute_demand()
    └── energy_need: 2323  ← raw kcal, không normalize, không vào DIMS
    
score_dish() DIMS
    └── [hydration, electrolyte, thermoreg, warming, cooling]
        ← BMI/tuổi KHÔNG có mặt ở đây
    │
    ▼
final_score  ← như nhau cho BMI 25 và BMI 39 (cùng thời tiết + location)
```

---

**Bước 5: Verify bằng dữ liệu thực từ test**

Demand snapshot của TC031 và TC033 (cùng HN, cùng thời tiết):

```json
TC031: { "warming_food_need": 0.5354, "cooling_food_need": 0.4344,
         "hydration_need": 0.2966, "energy_need": 1623.63 }

TC033: { "warming_food_need": 0.5354, "cooling_food_need": 0.4344,
         "hydration_need": 0.2966, "energy_need": 2323.29 }
```

5 dimension đầu **y hệt nhau**. `energy_need` khác nhau nhưng không được dùng trong DIMS → score giống nhau → top2 giống nhau.

---

**Tóm tắt vấn đề:**

> `adj_satiety_score` và `adj_energy_total` đã có đủ trong DB (7 228 món),  
> đã được fetch vào dish dict qua `filter_dishes()`,  
> nhưng **không có demand dimension nào map tới chúng trong `score_dish()`**.  
> BMI và tuổi tính đúng nhưng chết ở giữa đường — không reach được scoring layer.

---

## 2. Chiến lược fix — 3 phases

### Phase 1 · Quick win (1–2 giờ)
Thêm BMI calorie dimension vào DIMS. Chỉ sửa `pipeline.py`, không đụng DB.

### Phase 2 · Full personalization (nửa ngày)
Thêm `satiety_need` và `age_modifier` vào demand vector + soft_mult.

### Phase 3 · Long-term (roadmap)
Age-aware cooking method preference, nutrition density scoring. Cần thêm data DB.

---

## 3. Hướng dẫn implement chi tiết

### Phase 1 — Thêm BMI Calorie Dimension

#### 3.1.A Thêm helper `_normalize_dish_energy()` vào `pipeline.py`

Đặt ngay sau hàm `_dv()` (khoảng dòng 435):

```python
def _normalize_dish_energy(dish: dict, calorie_target: float) -> float:
    """
    Chuyển adj_energy_total (kcal) thành score [0,1] relative to calorie_target.

    Dùng cho high_energy_need (người gầy): score cao nếu dish calo cao.
    calorie_target = 35% TDEE / serving — từ build_constraint_profile().
    """
    if calorie_target <= 0:
        return 0.5
    cal = dish.get("adj_energy_total") or dish.get("dish_energy_total") or 0.0
    if cal <= 0:
        return 0.5
    # Normalize: 1.0 nếu đúng bằng target, giảm dần cả 2 phía
    # /2 vì calorie_target là 35% TDEE, dish thực tế có thể lên đến 70%
    ratio = float(cal) / calorie_target
    return round(min(1.0, ratio / 2.0), 4)
```

#### 3.1.B Thêm 2 demand dimension mới vào `compute_demand()`

Thêm `bmi = pv.get("BMI", 22.0)` và tính 2 dimension mới vào cuối return dict:

```python
def compute_demand(wv: dict, pv: dict, climate_type: str) -> dict:
    # ... code hiện tại giữ nguyên ...

    # ── BMI-aware dimensions ─────────────────────────────────────────────
    bmi = pv.get("BMI", 22.0)

    # Người gầy (BMI < 18.5): cần calo cao → ưu tiên dish energy cao
    # Giá trị: 0.583 tại BMI 15, 0.0 tại BMI 18.5 trở lên
    high_energy_need = round(max(0.0, min(1.0, (18.5 - bmi) / 6.0)), 4)

    # Người thừa cân (BMI > 25): cần no lâu với ít calo → ưu tiên satiety cao
    # Giá trị: 0.0 tại BMI 25, 0.333 tại BMI 30, 0.933 tại BMI 39
    # Cap tại 0.70 để tránh BMI dimension lấn át weather hoàn toàn
    low_calorie_need = round(min(0.70, max(0.0, (bmi - 25.0) / 15.0)), 4)

    return {
        "hydration_need":        round(h,  4),
        "electrolyte_need":      round(e,  4),
        "thermoregulation_need": round(th, 4),
        "energy_need":           round(en, 2),
        "warming_food_need":     round(w,  4),
        "cooling_food_need":     round(c,  4),
        "high_energy_need":      high_energy_need,   # ← NEW
        "low_calorie_need":      low_calorie_need,   # ← NEW
        "sodium_control_need":   1.0 if df.get("hypertension") else 0.0,
        "glycemic_control_need": 1.0 if df.get("diabetes")     else 0.0,
        "gout_control_need":     1.0 if df.get("gout")         else 0.0,
        "ibs_control_need":      1.0 if df.get("ibs")          else 0.0,
    }
```

**Bảng giá trị minh hoạ:**

| BMI | high_energy_need | low_calorie_need | Ý nghĩa |
|---|---|---|---|
| 15.0 | 0.583 | 0.0 | Cần calo cao |
| 18.5 | 0.0 | 0.0 | Ngưỡng dưới — bình thường |
| 22.0 | 0.0 | 0.0 | Bình thường |
| 25.0 | 0.0 | 0.0 | Ngưỡng trên — bình thường |
| 30.0 | 0.0 | 0.333 | Cần no lâu |
| 35.0 | 0.0 | 0.567 | Cần satiety mạnh |
| 39.0 | 0.0 | 0.700 | Cap — không át weather |

#### 3.1.C Sửa `score_dish()` — thêm 2 DIMS mới + xử lý `high_energy_need`

Thay toàn bộ block tính `raw_score` trong `score_dish()`:

```python
def score_dish(dish, demand, soft_mult, taste_weight,
               trad_compat, dish_avail, ingredient_boost,
               profile=None, recent_ids_ordered=None):

    DIMS = [
        ("hydration_need",        "adj_hydration_score",   "dish_hydration_score"),
        ("electrolyte_need",      "adj_hydration_score",   None),
        ("thermoregulation_need", "adj_thermogenic_score", "dish_thermogenic_score"),
        ("warming_food_need",     "adj_warming_score",     "dish_warming_score"),
        ("cooling_food_need",     "adj_cooling_score",     "dish_cooling_score"),
        ("low_calorie_need",      "adj_satiety_score",     "dish_satiety_score"),  # ← NEW
        ("high_energy_need",      None,                    None),                  # ← NEW (xử lý riêng)
    ]

    # Pre-compute normalized energy score cho high_energy_need
    _profile       = profile or {}
    calorie_target = _profile.get("calorie_target", 0)
    _dish_energy_score = (
        _normalize_dish_energy(dish, calorie_target)
        if calorie_target > 0 and demand.get("high_energy_need", 0) > 0
        else 0.0
    )

    # Tính raw_score — thay thế block gốc
    demand_sum = 0.0
    raw_score  = 0.0
    for d, a, r in DIMS:
        d_val = demand.get(d, 0.0)
        if d_val <= 0:
            continue
        if d == "high_energy_need":
            dish_val = _dish_energy_score
        else:
            dish_val = _dv(dish, a, r) if a else 0.0
        demand_sum += d_val
        raw_score  += d_val * dish_val

    raw_score = raw_score / demand_sum if demand_sum > 0 else 0.0

    # ... phần còn lại của score_dish() giữ nguyên ...
```

---

### Phase 2 — Age-aware Scoring

#### 3.2.A Thêm `age` vào `compute_personal_vector()` return dict

```python
return {
    "BMI":                  bmi,
    "age":                  age,   # ← NEW
    "bmr":                  round(bmr, 2),
    ...
}
```

#### 3.2.B Thêm `age` vào `build_constraint_profile()` return dict

```python
return {
    ...
    "calorie_target": round(pv["energy_need"] * 0.35, 0),
    "age":            pv.get("age", 30),   # ← NEW — cần cho soft_mult
    ...
}
```

#### 3.2.C Thêm age modifier vào cuối `compute_soft_mult()`

Ngay trước `return round(mult, 4)`:

```python
    # ── Age modifier ─────────────────────────────────────────────────────
    age = profile.get("age", 30)

    if age >= 60:
        # Giảm nhẹ món có tính nhiệt cao (chiên, nướng nhiều dầu) cho người cao tuổi
        thermogenic = dish.get("adj_thermogenic_score") or dish.get("dish_thermogenic_score") or 0
        if float(thermogenic) > 0.75:
            mult *= 0.90   # giảm 10%

    elif age <= 22:
        # Bonus nhẹ món đủ năng lượng cho người trẻ
        cal = dish.get("adj_energy_total") or dish.get("dish_energy_total") or 0
        calorie_target = profile.get("calorie_target", 700)
        if calorie_target > 0 and float(cal) >= calorie_target * 0.9:
            mult *= 1.05   # bonus 5%

    return round(mult, 4)
```

---

### Phase 3 — Nutrition density scoring (Roadmap)

Cần thêm cột vào DB:

| Tính năng | Cột cần thêm | Bảng |
|---|---|---|
| Protein dễ tiêu cho người già | `protein_easy_digest_score` REAL | `dishes` |
| Hàm lượng xơ | `fiber_g_per_serving` REAL | `dishes` |
| Độ mềm của món | `texture_hardness` TINYINT (1–5) | `dishes` |
| Mật độ vi chất | `micronutrient_score` REAL | `dishes` |

---

## 4. Tác động dự kiến

### Trước fix — demand vector của TC033 (BMI 39, HN)

```
warming_food_need:  0.535  │
cooling_food_need:  0.434  │  5 dims này giống hệt TC031
hydration_need:     0.297  │  → cùng kết quả
thermoreg_need:     0.521  │
electrolyte_need:   0.198  │
low_calorie_need:   0.000  ← không có
high_energy_need:   0.000  ← không có
```

### Sau fix — demand vector của TC033 (BMI 39, HN)

```
warming_food_need:  0.535  │
cooling_food_need:  0.434  │  giống TC031
hydration_need:     0.297  │
thermoreg_need:     0.521  │
electrolyte_need:   0.198  │
low_calorie_need:   0.700  ← DOMINANT, map sang adj_satiety_score
high_energy_need:   0.000
```

`demand_sum` tăng từ `1.985 → 2.685`.  
`low_calorie_need` chiếm **26% trọng số demand** — đủ để đẩy món có satiety cao lên top, hạ món calo dày xuống.

### So sánh kỳ vọng sau fix

| | Trước fix | Sau fix |
|---|---|---|
| TC031 (70 tuổi, BMI 25) | Canh chua mực tôm | Canh chua mực tôm (không đổi, BMI bình thường) |
| TC033 (BMI 39) | Canh chua mực tôm | Canh rau / món satiety cao hơn |
| TC034 (BMI 15) | Cua hấp | Cháo bổ / món calo cao hơn |

---

## 5. Verify sau khi implement

### 5.1 Kiểm tra DB trước khi chạy

```sql
-- Đảm bảo adj_satiety_score populated (đã confirm: 7228/7228)
SELECT COUNT(*), AVG(adj_satiety_score), MIN(adj_satiety_score), MAX(adj_satiety_score)
FROM dishes WHERE adj_satiety_score IS NOT NULL;

-- Đảm bảo adj_energy_total populated
SELECT COUNT(*), AVG(adj_energy_total), MIN(adj_energy_total), MAX(adj_energy_total)
FROM dishes WHERE adj_energy_total IS NOT NULL;
```

### 5.2 Chạy lại test sau fix

Chạy `run_tests.py` với 4 test cases TC031, TC032, TC033, TC034 và kiểm tra:

1. TC031 và TC033 cho top5 **khác nhau** ít nhất 3/5 món
2. TC033 (BMI 39) top5 có `adj_satiety_score` trung bình **cao hơn** TC031
3. TC034 (BMI 15) top5 có `adj_energy_total` trung bình **cao hơn** TC032 (BMI bình thường)
4. Người BMI bình thường (18.5–25): kết quả **không thay đổi** so với trước fix

### 5.3 Regression check

Sau fix, chạy lại toàn bộ 44 test case và đảm bảo:
- TC004–TC010 (health filtering): kết quả không thay đổi đáng kể
- TC011, TC012 (vegan/vegetarian): pool size không đổi
- TC019, TC020 (prep time): cook time vẫn trong ngưỡng

---

## 6. Files cần sửa — tóm tắt

| File | Hàm | Thay đổi |
|---|---|---|
| `pipeline.py` | `_normalize_dish_energy()` | **Thêm mới** — helper normalize kcal → [0,1] |
| `pipeline.py` | `compute_personal_vector()` | Thêm `"age": age` vào return |
| `pipeline.py` | `compute_demand()` | Thêm `high_energy_need`, `low_calorie_need` vào return |
| `pipeline.py` | `build_constraint_profile()` | Thêm `"age": pv.get("age", 30)` vào return |
| `pipeline.py` | `score_dish()` | Thêm 2 DIMS mới + xử lý `high_energy_need` bằng pre-computed score |
| `pipeline.py` | `compute_soft_mult()` | Thêm age-based mult modifier (Phase 2) |
| `advice_engine.py` | `check_fit_reasons()` | Đã có BMI check — **không cần sửa** |
