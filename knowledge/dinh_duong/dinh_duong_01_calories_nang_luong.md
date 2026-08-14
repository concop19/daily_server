---
doc_id: doc_dinh_duong_01
group: dinh_duong
topic: calories_va_nang_luong
health_conditions:
  - general_nutrition
language: vi
source_ids:
  - source_001
generated_by: antigravity
generated_at: 2026-08-12
confidence: high
---

# Năng lượng và Calories trong Món ăn

## Khái niệm chính

Năng lượng trong dinh dưỡng thường được đo bằng đơn vị **Calorie** (viết tắt là `kcal`). Đây là lượng năng lượng mà thực phẩm cung cấp cho cơ thể khi được chuyển hóa. Năng lượng sinh ra từ 3 nhóm chất sinh năng lượng chính (Macronutrients):
- **Protein (Chất đạm):** Cung cấp khoảng 4 kcal cho mỗi gram.
- **Carbohydrate (Đường bột):** Cung cấp khoảng 4 kcal cho mỗi gram.
- **Lipid (Chất béo):** Cung cấp khoảng 9 kcal cho mỗi gram.

Cơ thể con người cần năng lượng để duy trì các hoạt động sống cơ bản (tỷ lệ chuyển hóa cơ bản - BMR) và các hoạt động thể chất hàng ngày (tổng năng lượng tiêu hao hàng ngày - TDEE).

## Ý nghĩa đối với món ăn

Trong một món ăn, tổng năng lượng phụ thuộc vào:
1. **Thành phần nguyên liệu:** Loại thực phẩm được sử dụng (thịt giàu mỡ hay thịt tinh, rau củ hay tinh bột).
2. **Khối lượng nguyên liệu:** Tổng trọng lượng của tất cả nguyên liệu trong món.
3. **Gia vị và dầu mỡ đi kèm:** Dầu ăn, mỡ, đường, nước mắm, sốt đều chứa calo và làm tăng năng lượng tổng thể của món ăn.

Món ăn có năng lượng được tính toán dựa trên khối lượng và đặc tính của từng nguyên liệu thành phần.

## Cách hệ thống Daily Mate sử dụng chỉ số

Trong hệ thống Daily Mate, chỉ số năng lượng (`energy`) được tính toán dựa trên quy ước:
- **Tính trên 1 serving (1 phần ăn):** Toàn bộ công thức chuẩn của một món ăn được coi là 1 serving.
- **Bao gồm tất cả nguyên liệu:** Tất cả thành phần liệt kê trong món (nguyên liệu chính, nguyên liệu phụ, nguyên liệu tùy chọn, gia vị, dầu mỡ, đường, nước) đều được tính toán.
- **Giá trị thô (Raw) và Giá trị sau chế biến (Adjusted):** 
  - Giá trị năng lượng thô (`dish_energy_total` / `energy_per_serving`) được tính từ tổng calo nguyên liệu chưa qua chế biến. 
  - Giá trị điều chỉnh (`adj_energy_total`) là giá trị **ước tính qua mô hình toán học** sau khi áp dụng hệ số nhân từ phương pháp nấu (cooking multiplier), **không phải kết quả phân tích phòng thí nghiệm hay xét nghiệm hóa sinh**.
- **Vai trò của RAG:** RAG chỉ đóng vai trò giải thích thông tin dinh dưỡng cho người dùng, không tự thực hiện thuật toán lọc hay loại bỏ món ăn (việc lọc món do hệ thống backend pipeline đảm nhiệm) và không tự đưa ra đề xuất sửa đổi cấu trúc công thức.

## Cách diễn đạt cho người dùng

Khi giải thích về năng lượng món ăn cho người dùng, hệ thống tuân thủ các nguyên tắc:
- Sử dụng ngôn ngữ trung tính, mang tính định hướng dữ liệu chỉ số.
- Ví dụ diễn đạt phù hợp:
  - "Món ăn này cung cấp năng lượng ở mức vừa phải dựa trên khối lượng 1 phần ăn tiêu chuẩn."
  - "Món ăn có hàm lượng năng lượng tương đối cao dựa trên thành phần dầu mỡ trong công thức."

## Giới hạn của thông tin

- Năng lượng tính toán là giá trị ước tính dựa trên công thức chuẩn và bảng thành phần thực phẩm.
- Lượng năng lượng thực tế có thể thay đổi tùy thuộc vào chất lượng nguyên liệu thực tế và lượng dầu mỡ sử dụng khi nấu tại gia đình.
- Thông tin mang tính tham khảo, không phải kết luận y khoa và không thay thế tư vấn y tế.

## Nguồn tham khảo

- Bảng thành phần thực phẩm Việt Nam (Vietnamese Food Composition Table) - Viện Dinh dưỡng Quốc gia (NIN), Bộ Y tế.
