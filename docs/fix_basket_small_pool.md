# Fix: Basket Market – Small Pool Fallback

## Vấn đề

Khi user chọn nguyên liệu trong market basket, `filter_dishes()` dùng `basket_ingredient_ids`
để lọc DB — chỉ trả về món có **ít nhất 1 nguyên liệu** trong giỏ (non-pantry).

Nếu user chọn **2-3 nguyên liệu ít phổ biến**, pool có thể chỉ còn 1–5 món.
Hiện tại chỉ có 1 fallback duy nhất trong `app.py`:

```python
if basket_for_filter and len(full_pool) == 0:   # ← chỉ khi = 0
    full_pool = filter_dishes(...)               #   bỏ basket filter
```

Vậy nếu pool trả về **1–9 món** thì không fallback → user nhận < 10 gợi ý,
trải nghiệm kém.

---

## Phân tích root cause

| File | Vị trí | Hiện tại |
|------|--------|----------|
| `app.py` | route `/api/v1/recommend` | fallback chỉ khi `len == 0` |
| `pipeline.py` | `filter_dishes()` | basket filter đúng, không cần sửa |
| `pipeline.py` | `compute_dish_boost()` | boost đúng, không cần sửa |

Nguyên nhân đơn giản: **ngưỡng fallback quá thấp (0 thay vì < 10)**.

---

## Giải pháp

### Nguyên tắc

> Nếu số món sau khi lọc basket **< 10**, ta bỏ basket constraint khi filter
> nhưng **vẫn giữ boost** để món có nguyên liệu trong giỏ được điểm cao hơn,
> tự nhiên nổi lên đầu danh sách.

Điều này đảm bảo:
- User luôn thấy **ít nhất 10 gợi ý** (hoặc tối đa pool cho phép).
- Món khớp giỏ hàng **vẫn được ưu tiên** nhờ `ingredient_boost` trong `score_dish()`.
- Không phá vỡ các filter khác (allergy, diet, sodium, gout…).

### Ngưỡng

```
BASKET_SMALL_POOL_THRESHOLD = 10
```

Giá trị 10 hợp lý vì `page_size = 10` (response trả `ranked_dishes` tối đa 10 món mặc định).

---

## Thay đổi cụ thể

### Chỉ sửa 1 chỗ: `app.py` — route `/api/v1/recommend`

**Trước (hiện tại):**

```python
basket_for_filter = selected_ids if (not is_skipped and selected_ids) else None
full_pool = filter_dishes(db, cuisine_scope, selected_nation, profile, season,
                          dish_type_filter, basket_ingredient_ids=basket_for_filter)

if basket_for_filter and len(full_pool) == 0:
    full_pool = filter_dishes(db, cuisine_scope, selected_nation, profile, season, dish_type_filter)
```

**Sau (fix):**

```python
BASKET_SMALL_POOL_THRESHOLD = 10

basket_for_filter = selected_ids if (not is_skipped and selected_ids) else None
full_pool = filter_dishes(db, cuisine_scope, selected_nation, profile, season,
                          dish_type_filter, basket_ingredient_ids=basket_for_filter)

# Nếu basket filter trả về quá ít món (< 10), bỏ basket constraint khi filter
# nhưng GIỮ NGUYÊN boost_strategy để ingredient_boost vẫn ưu tiên món khớp giỏ.
if basket_for_filter and len(full_pool) < BASKET_SMALL_POOL_THRESHOLD:
    full_pool = filter_dishes(db, cuisine_scope, selected_nation, profile, season, dish_type_filter)
```

Chỉ đổi:
1. `== 0` → `< BASKET_SMALL_POOL_THRESHOLD`
2. Thêm hằng số `BASKET_SMALL_POOL_THRESHOLD = 10` (đặt trên route hoặc top-level module)

### Không cần sửa

| File | Lý do |
|------|-------|
| `pipeline.py` → `filter_dishes()` | Logic đúng, basket SQL filter vẫn dùng khi pool lớn |
| `pipeline.py` → `compute_dish_boost()` | Boost vẫn tính từ `selected_ids` — không phụ thuộc pool size |
| `pipeline.py` → `score_dish()` | Không đổi |
| `pipeline.py` → `rank_and_explain()` | Không đổi |

---

## Flow sau khi fix

```
User chọn 3 nguyên liệu → selected_ids = {12, 45, 78}
         │
         ▼
filter_dishes(..., basket_ingredient_ids={12,45,78})
         │
         ▼
full_pool = [2 món]   ← < 10
         │
         ▼  fallback
filter_dishes(..., basket_ingredient_ids=None)
         │
         ▼
full_pool = [800 món]
         │
         ▼
score_dish() cho từng món
  compute_dish_boost(recipe_id, selected_ids={12,45,78}, "strict", db)
  → Món có nguyên liệu 12, 45, 78 → boost cao → điểm cao → rank đầu
         │
         ▼
rank_and_explain() → top 10
  → 2 món khớp giỏ ở vị trí 1, 2
  → 8 món phù hợp thời tiết/sức khỏe phía sau
```

---

## Điều không thay đổi với user

- Món khớp giỏ hàng vẫn lên đầu (boost tính độc lập với filter).
- Các ràng buộc health (allergy, sodium, diabetes, gout) vẫn được áp dụng đầy đủ.
- Nếu user bỏ qua basket (`is_skipped = true`), luồng hoàn toàn không đổi.

---

## Rủi ro & lưu ý

| Rủi ro | Đánh giá | Xử lý |
|--------|----------|-------|
| Pool 800 món → scoring chậm hơn | Thấp – chỉ xảy ra khi basket nhỏ, pipeline đã tối ưu | Chấp nhận được |
| Threshold 10 quá cao/thấp | Thấp – page_size = 10 nên 10 là điểm tự nhiên | Có thể điều chỉnh sau |
| Fallback lần 2 (pool vẫn = 0 sau fallback) | Đã có: `if not dish_pool: filter global` | Không cần thêm |

---

## Tóm tắt thay đổi

```
Lines changed : 2 dòng trong app.py
Files changed : 1 (app.py)
Risk          : Rất thấp — chỉ nới lỏng ngưỡng fallback
Behavior diff : User với basket nhỏ nhận đủ 10 gợi ý thay vì 1–9
```
