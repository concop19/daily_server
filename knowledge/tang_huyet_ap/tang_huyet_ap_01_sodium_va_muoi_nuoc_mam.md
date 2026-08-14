---
doc_id: doc_tang_huyet_ap_01
group: tang_huyet_ap
topic: sodium_va_gia_vi_muoi_nuoc_mam
health_conditions:
  - hypertension
language: vi
source_ids:
  - source_003
  - source_004
generated_by: antigravity
generated_at: 2026-08-12
confidence: high
---

# Sodium (Natri), Muối và Nước Mắm Trong Bệnh Tăng Huyết Áp

## Khái niệm chính

Đối với bệnh tăng huyết áp (huyết áp cao), **Sodium (Natri)** là chỉ số dinh dưỡng quan trọng cần theo dõi.

- **Cơ chế tác động:** Nồng độ Natri cao trong máu hút nước vào lòng mạch, làm tăng thể tích tuần hoàn và gây tăng áp lực lên thành động mạch.
- **Nguồn cung cấp chính trong món ăn Việt:** Muối ăn, nước mắm, mắm tôm, mắm nêm, hạt nêm, nước tương và các loại gia vị ướp sẵn.
- **Quy đổi:** 1g muối ăn $\approx 400\text{mg}$ Natri; 1 thìa canh nước mắm truyền thống ($15\text{ml}$) chứa khoảng $900 - 1200\text{mg}$ Natri.

## Ý nghĩa đối với món ăn

Trong một công thức món ăn:
- Gia vị mặn đóng góp phần lớn tổng lượng Natri của món ăn.
- Nguyên liệu thô (thịt, cá, rau) đóng góp một phần Natri tự nhiên.
- Natri từ gia vị hòa tan vào toàn bộ món ăn bao gồm cả phần nguyên liệu và phần nước dùng/nước sốt.

## Cách hệ thống Daily Mate sử dụng chỉ số

Trong Daily Mate:
- Tổng lượng Natri thô (`dish_sodium_total`) được tính bằng cách cộng tất cả nguồn Natri từ nguyên liệu và gia vị trong `dish_ingredients` theo khối lượng `quantity_g`.
- Natri điều chỉnh (`adj_sodium_total`) = $\text{Raw Value} \times \text{Hệ số Cooking Method}$. Đây là giá trị **ước tính theo mô hình Daily Mate, không phải kết quả xét nghiệm hoặc phân tích phòng thí nghiệm**.
- Ngưỡng tham chiếu đánh giá Natri cho 1 phần ăn trong hệ thống là **$\text{Sodium} \le 600\text{mg / serving}$**.

## Cách diễn đạt cho người dùng

- Cung cấp góc nhìn khoa học trung tính về chỉ số Natri ước tính của món ăn.
- Ví dụ diễn đạt:
  - "Món ăn này có hàm lượng natri ước tính nằm trong giới hạn tham chiếu cho 1 phần ăn ($\le 600\text{mg/serving}$)."
  - "Món ăn có hàm lượng natri ước tính cao hơn mốc tham chiếu do có sử dụng gia vị mặn trong công thức."

## Giới hạn của thông tin

- Lượng gia vị thực tế nêm nếm khi nấu ăn tại nhà có thể thay đổi so với công thức chuẩn.
- Thông tin mang tính tham khảo, không thay thế tư vấn y tế.

## Nguồn tham khảo

- Quyết định 5968/QĐ-BYT Hướng dẫn chẩn đoán và điều trị tăng huyết áp - Bộ Y tế.
- Guideline: Sodium intake for adults and children - WHO (2012).
