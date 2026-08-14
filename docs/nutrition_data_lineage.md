# Daily Mate — Nutrition Data Lineage

Tài liệu mô tả nguồn gốc và công thức hình thành các chỉ số của `dish`.
Các chỉ số được tổng hợp từ `ingredients`, `dish_ingredients.quantity_g`,
`dish_ingredients.is_main` và `cooking_methods`.

## 1. Luồng dữ liệu

```text
ingredients + dish_ingredients.quantity_g + cooking_methods.mult_*
        ↓
dish raw values → adjusted values → safety scores → recommendation
        ↓
data/dishes.json → JSON DataStore → Nutrition RAG
```

Các script tính toán dữ liệu gốc có thể chạy trên SQLite trước, sau đó cần
export lại sang JSON để server sử dụng.

## 2. Nguồn dữ liệu

### ingredients.json

```text
energy_density, sodium_density, carb_density, glycemic_index
purine_score, hydration_score, thermogenic_score, warming_score
cooling_score, satiety_score, electrolyte_density, cost_level
allergen_tags, flavor_profile, seasonal_availability
regional_availability, distribution_reach, source_type
```

### dish_ingredients.json

```text
recipe_id → dishes.id
ingredient_id → ingredients.id
quantity_g → khối lượng và trọng số tính toán
is_main → nguyên liệu chính
is_optional → nguyên liệu tùy chọn
```

### cooking_methods.json

Chứa multiplier cho energy, hydration, thermogenic, warming, cooling, satiety,
glycemic load và sodium.

## 3. Tổng khối lượng

```text
total_weight_g = Σ quantity_g
```

## 4. Các score dạng weighted average

```text
dish_score = Σ(quantity_g × ingredient_score) ÷ total_weight_g
```

Áp dụng cho `dish_hydration_score`, `dish_thermogenic_score`,
`dish_warming_score`, `dish_cooling_score` và `dish_satiety_score`.

Ví dụ:

```text
dish_hydration_score = Σ(quantity_g × ingredient.hydration_score) ÷ total_weight_g
```

Các kết quả thực tế trong `dishes.json` khớp với công thức này.

## 5. Năng lượng

Nếu `energy_density` là kcal/100g:

```text
dish_energy_total = Σ(quantity_g × energy_density ÷ 100)
energy_per_100g = dish_energy_total ÷ total_weight_g × 100
```

Hiện tại `energy_per_serving` thường bằng `dish_energy_total`, nghĩa là toàn
bộ công thức đang được xem như một serving nếu chưa có số phần riêng.

## 6. Sodium

Nếu `sodium_density` là mg/100g:

```text
dish_sodium_total = Σ(quantity_g × sodium_density ÷ 100)
sodium_per_100g = dish_sodium_total ÷ total_weight_g × 100
sodium_per_serving = dish_sodium_total
```

Sodium có thể bao gồm gia vị, muối, nước mắm hoặc thực phẩm chế biến nếu các
thành phần đó xuất hiện trong `dish_ingredient` và có `sodium_density`.

## 7. Glycemic Load

```text
dish_glycemic_load = Σ(quantity_g × carb_density × glycemic_index ÷ 10000)
glycemic_load_per_100g = dish_glycemic_load ÷ total_weight_g × 100
```

Trong đó `carb_density` là carbohydrate g/100g và `glycemic_index` dùng thang
GI thông thường.

## 8. Adjusted values theo phương pháp nấu

Phase 4 áp dụng:

```text
adjusted_value = raw_dish_value × cooking_method_multiplier
```

Áp dụng cho `adj_energy_total`, `adj_hydration_score`,
`adj_thermogenic_score`, `adj_warming_score`, `adj_cooling_score`,
`adj_satiety_score`, `adj_glycemic_load` và `adj_sodium_total`.

```text
adj_glycemic_load_per_100g = adj_glycemic_load ÷ total_weight_g × 100
```

## 9. Gout score

Giữ nguyên quy ước hiện tại của hệ thống:

```text
gout_risk_score cao = an toàn hơn; gout_risk_score thấp = nguy cơ cao hơn
```

Tên field giữ nguyên để tương thích với dữ liệu và pipeline, nhưng về ý nghĩa
nó gần với `gout_safety_score` hơn.

### Purine weighted score

Ưu tiên nguyên liệu chính:

```text
main_purine = Σ(main quantity_g × ingredient.purine_score) ÷ Σ(main quantity_g)
```

Nếu không có nguyên liệu chính có `purine_score`, dùng toàn bộ nguyên liệu:

```text
all_purine = Σ(quantity_g × ingredient.purine_score) ÷ Σ(quantity_g)
```

### Cooking factor và condiment penalty

```text
gout_risk_score = min(1.0, purine_weighted × cooking_method_factor + condiment_penalty)
```

Cooking factor hiện được quy định theo phương pháp nấu. Ví dụ: luộc `0.50`,
hấp `0.85`, chiên `1.25`, xào `1.10`, nướng `1.25`, hầm `0.55`, rang `1.30`,
nấu canh `0.70`, trộn gỏi/ăn sống `1.00`.

Condiment hoặc thực phẩm chế biến có `purine_score > 0.7` tạo penalty tối đa
`0.08`, tính theo khối lượng trên tổng khối lượng món.

## 10. Safety scores

```text
sodium_safety_score = max(0.0, 1.0 - adj_sodium_total ÷ 600)
gl_safety_score = max(0.0, 1.0 - adj_glycemic_load ÷ 10)
```

Quy ước: `1.0` là an toàn hơn và `0.0` là đạt/vượt ngưỡng. Ngưỡng sodium là
600mg/serving; ngưỡng GL là 10.

`gout_risk_score` cũng được pipeline sử dụng theo quy ước safety: `1.0` an
toàn hơn, `0.0` nguy cơ cao hơn. Không đảo ngược field này trong Nutrition RAG.

## 11. Cost level

`cost_level` bắt nguồn từ `ingredients.cost_level`, nhưng không phải weighted
average thuần túy:

```text
Có nguyên liệu chính cost >= 3 → cost_level = 3
AVG(cost nguyên liệu chính) >= 2 hoặc có >= 2 nguyên liệu phụ cost >= 3 → level 2
Còn lại → cost_level = 1
```

`quantity_g` không được dùng trực tiếp trong công thức cost hiện tại.

## 12. Các field nhiều khả năng cũng đến từ ingredient

Các field sau cần script nguồn để xác nhận tuyệt đối:

```text
taste_profile ≈ weighted average của ingredient.flavor_profile
allergen_summary = UNION(ingredient.allergen_tags)
season_suitability ≈ weighted average của seasonal_availability
climate_suitability ≈ regional_availability + distribution_reach + source_type
```

## 13. Các chỉ số chưa có nguồn định lượng đầy đủ

Dataset hiện chưa có density rõ ràng cho `protein`, `fat`, `sugar`, `fiber` và
`purine_mg`. Nutrition RAG không được tự tuyên bố các giá trị này nếu chưa bổ
sung nguồn. `purine_score` là điểm rủi ro, không phải số mg purine.

## 14. Quy tắc sử dụng cho Nutrition RAG

```text
Raw/adjusted dish values = số liệu định lượng
Knowledge documents = giải thích ý nghĩa dinh dưỡng
Sources = nguồn tham khảo
Pipeline = quyết định lọc và xếp hạng
RAG = giải thích, không tự thay đổi kết quả pipeline
```

RAG nên ưu tiên `adj_energy_total`, `adj_sodium_total`, `adj_glycemic_load`,
`gout_risk_score`, `adj_hydration_score` và `adj_satiety_score`. Mọi câu trả
lời cần ghi rõ khẩu phần và không suy đoán field còn thiếu.
