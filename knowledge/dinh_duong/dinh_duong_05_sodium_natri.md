---
doc_id: doc_dinh_duong_05
group: dinh_duong
topic: sodium_natri
health_conditions:
  - general_nutrition
  - hypertension
language: vi
source_ids:
  - source_001
  - source_003
  - source_004
generated_by: antigravity
generated_at: 2026-08-12
confidence: high
---

# Sodium (Natri) trong Dinh Dưỡng Món Ăn

## Khái niệm chính

**Sodium (Natri)** là một khoáng chất thiết yếu giúp duy trì cân bằng điện giải, áp suất thẩm thấu và hoạt động thần kinh cơ trong cơ thể. 

- **Chuyển đổi Muối ăn và Natri:** 1 gram muối ăn ($\text{NaCl}$) chứa khoảng $400\text{mg}$ Natri.
- **Mốc tham chiếu quốc tế (WHO):** Mức dưới $2000\text{mg}$ Natri/ngày ở người trưởng thành tương đương khoảng $5\text{g}$ muối ăn/ngày.

## Ý nghĩa đối với món ăn

Trong ẩm thực Việt Nam, Natri đến từ hai nguồn chính:
1. **Natri tự nhiên:** Có sẵn trong thực phẩm thô (thịt, cá, hải sản, một số loại rau).
2. **Natri gia vị (chiếm tỷ trọng lớn nhất):** Đến từ muối ăn, nước mắm, mắm tôm, hạt nêm, nước tương, mì chính (MSG).

Dung nạp quá nhiều Natri làm tăng giữ nước trong lòng mạch, gây áp lực lên tim và hệ mạch máu.

## Cách hệ thống Daily Mate sử dụng chỉ số

Trong Daily Mate, chỉ số `sodium` được tính toán cho 1 serving món ăn:
- **Tích hợp tất cả gia vị:** Lượng natri từ muối, nước mắm, hạt nêm trong `dish_ingredients` đều được quy đổi ra mg Natri dựa trên khối lượng nguyên liệu (`quantity_g`).
- **Phân biệt Raw Sodium và Adjusted Sodium:**
  - **`dish_sodium_total` (Raw Value):** Tổng hàm lượng Natri tính trực tiếp từ các nguyên liệu và gia vị thô theo `quantity_g`.
  - **`adj_sodium_total` (Adjusted Value):** $\text{Raw Value} \times \text{Hệ số Cooking Method}$. Đây là giá trị ước tính theo mô hình Daily Mate, **không phải kết quả xét nghiệm hoặc phân tích phòng thí nghiệm**.
- **`sodium_safety_score`:** Được tính toán dựa trên khoảng cách giữa `adj_sodium_total` và mốc tham chiếu nội bộ $600\text{mg/serving}$.

## Cách diễn đạt cho người dùng

- Cung cấp thông tin lượng Natri ước tính rõ ràng, giúp người dùng hiểu đặc tính món ăn.
- Ví dụ diễn đạt:
  - "Món ăn này có hàm lượng natri ước tính trong giới hạn vừa phải cho 1 phần ăn tiêu chuẩn."
  - "Món ăn chứa lượng natri ước tính cao hơn do thành phần gia vị mặn trong công thức."

## Giới hạn của thông tin

- Lượng natri thực tế phụ thuộc vào khẩu vị nêm nếm khi nấu tại nhà hoặc nhà hàng.
- Thông tin mang tính tham khảo, không thay thế tư vấn y tế.

## Nguồn tham khảo

- Bảng thành phần thực phẩm Việt Nam - Viện Dinh dưỡng Quốc gia (NIN).
- Guideline: Sodium intake for adults and children - WHO (2012).
- Quyết định 5968/QĐ-BYT Hướng dẫn chẩn đoán và điều trị tăng huyết áp - Bộ Y tế.
