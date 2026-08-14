---
doc_id: doc_tang_huyet_ap_02
group: tang_huyet_ap
topic: raw_vs_adjusted_sodium
health_conditions:
  - hypertension
language: vi
source_ids:
  - source_001
  - source_003
generated_by: antigravity
generated_at: 2026-08-12
confidence: high
---

# Biến Đổi Hàm Lượng Sodium Trước và Sau Chế Biến Món Ăn

## Khái niệm chính

Hàm lượng Natri trong món ăn được mô hình hóa qua hai cấp độ:

1. **Raw Sodium (Sodium thô - `dish_sodium_total`):** Tổng lượng Natri tính từ nguyên liệu thô và gia vị theo khối lượng (`quantity_g`).
2. **Adjusted Sodium (Sodium điều chỉnh - `adj_sodium_total`):** Tính bằng công thức:
   $$\text{Adjusted Sodium} = \text{Raw Sodium} \times \text{Hệ số Cooking Method}$$
   Đây là giá trị **ước tính theo mô hình Daily Mate**, **không phải kết quả xét nghiệm hoặc phân tích phòng thí nghiệm**.

## Ý nghĩa đối với món ăn

Các phương pháp chế biến có hệ số điều chỉnh khác nhau:
- **Món kho / rim / xào khô:** Nước bay hơi trong quá trình nấu làm gia vị cô đặc trên bề mặt thực phẩm.
- **Món luộc / hấp:** Một phần Natri tự nhiên và gia vị nêm hòa tan bớt ra nước luộc.
- **Món canh / súp:** Natri phân bố hòa tan giữa phần nguyên liệu cái và phần nước dùng.

## Cách hệ thống Daily Mate sử dụng chỉ số

Trong hệ thống Daily Mate:
- Lượng Natri thô (`raw sodium`) được tính từ danh sách `dish_ingredients` theo `quantity_g`.
- Sau đó, hệ thống áp dụng hệ số nhân từ `cooking_methods` để tính ra `adj_sodium_total`.
- **Chỉ số `adj_sodium_total` là giá trị ước tính theo mô hình** để hệ thống so sánh với mốc tham chiếu $600\text{mg/serving}$.

## Cách diễn đạt cho người dùng

- Giải thích khoa học về sự phân bố Natri sau chế biến mà không đưa ra hướng dẫn hành động cá nhân.
- Ví dụ diễn đạt:
  - "Món ăn qua phương pháp chế biến cô đặc (như kho/rim) có nồng độ natri ước tính tập trung cao per phần ăn."
  - "Trong các món canh, natri được phân bố hòa tan giữa phần nguyên liệu và phần nước dùng."

## Giới hạn của thông tin

- Mức độ cô đặc hoặc pha loãng thực tế phụ thuộc vào lượng nước sử dụng và thời gian đun nấu riêng của từng người bếp. Giá trị điều chỉnh là ước tính mô hình, không phải phân tích phòng thí nghiệm.
- Thông tin mang tính tham khảo, không thay thế tư vấn y tế.

## Nguồn tham khảo

- Bảng thành phần thực phẩm Việt Nam - Viện Dinh dưỡng Quốc gia (NIN).
- Quyết định 5968/QĐ-BYT Hướng dẫn chẩn đoán và điều trị tăng huyết áp - Bộ Y tế.
