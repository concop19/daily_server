---
doc_id: doc_dinh_duong_09
group: dinh_duong
topic: raw_vs_adjusted_va_phuong_phap_nau
health_conditions:
  - general_nutrition
language: vi
source_ids:
  - source_001
generated_by: antigravity
generated_at: 2026-08-12
confidence: high
---

# Giá Trị Thô (Raw), Giá Trị Điều Chỉnh (Adjusted) và Phương Pháp Nấu

## Khái niệm chính

Trong mô hình tính toán dinh dưỡng của Daily Mate, có sự phân biệt rõ ràng giữa hai khái niệm:

1. **Giá trị thô (Raw Value):** Là tổng lượng dinh dưỡng, calo, natri, đường bột tính toán trực tiếp từ danh sách nguyên liệu chưa qua chế biến theo khối lượng (`quantity_g`), bao gồm cả nguyên liệu chính, phụ, gia vị, dầu mỡ và nước.
2. **Giá trị điều chỉnh (Adjusted Value):** Được tính bằng công thức:
   $$\text{Adjusted Value} = \text{Raw Value} \times \text{Hệ số Cooking Method}$$
   Đây là giá trị **ước tính theo mô hình Daily Mate**, **không phải kết quả xét nghiệm hoặc phân tích phòng thí nghiệm**.

Các phương pháp nấu có hệ số điều chỉnh khác nhau:
- **Luộc / Hấp:** Hệ số giữ nguyên hoặc làm thoát bớt một phần chất béo trong thịt.
- **Chiên / Rán:** Hệ số tính thêm sự hấp thụ mỡ từ dầu ăn bên ngoài vào món ăn.
- **Kho / Rim / Cô đặc:** Hệ số mô phỏng sự tập trung nồng độ gia vị khi nước bay hơi.
- **Ninh / Hầm:** Hệ số mô phỏng sự chiết xuất hòa tan purine và khoáng chất vào nước dùng.

## Ý nghĩa đối với món ăn

Việc phân biệt giữa giá trị thô và giá trị điều chỉnh giúp mô phỏng dinh dưỡng gần hơn với dạng chế biến của món ăn:
- Một món chiên có thể có nguyên liệu thô giống món hấp, nhưng giá trị điều chỉnh về năng lượng và chất béo lại cao hơn.
- Trong các món canh, natri được phân bố hòa tan giữa phần nguyên liệu và phần nước dùng.

## Cách hệ thống Daily Mate sử dụng chỉ số

Hệ thống Daily Mate triển khai hai bước tính toán:
1. **Bước 1 (Raw Calculation):** Tính tổng dinh dưỡng từ danh sách `dish_ingredients` theo `quantity_g` (gồm cờ nguyên liệu chính `is_main`).
2. **Bước 2 (Adjusted Calculation):** Nhân với hệ số từ `cooking_methods` tương ứng với món ăn đó để tính ra `adjusted energy`, `adjusted sodium`, `adjusted glycemic load`, `adjusted hydration`, `adjusted satiety`.
3. Thuật toán gợi ý backend (`pipeline.py`) sử dụng **Giá trị điều chỉnh (Adjusted Value)** để so sánh với các ngưỡng tham chiếu bệnh lý và thể trạng.

## Cách diễn đạt cho người dùng

- Giải thích minh bạch cho người dùng hiểu giá trị điều chỉnh là ước tính từ mô hình toán học dựa trên cách chế biến.
- Ví dụ diễn đạt:
  - "Món ăn này có phương pháp chế biến hấp giúp bảo tồn chất dinh dưỡng mà không làm tăng năng lượng từ dầu mỡ."
  - "Món ăn qua phương pháp chiên rán có hàm lượng chất béo điều chỉnh cao hơn so với nguyên liệu thô ban đầu."

## Giới hạn của thông tin

- Hệ số chế biến là các tham số mô hình hóa. Giá trị điều chỉnh là giá trị ước tính theo mô hình Daily Mate, không phải kết quả phân tích phòng thí nghiệm hay xét nghiệm hóa sinh.
- Thông tin mang tính tham khảo, không thay thế tư vấn y tế.

## Nguồn tham khảo

- Bảng thành phần thực phẩm Việt Nam - Viện Dinh dưỡng Quốc gia (NIN).
