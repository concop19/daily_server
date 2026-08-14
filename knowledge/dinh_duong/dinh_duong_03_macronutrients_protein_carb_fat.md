---
doc_id: doc_dinh_duong_03
group: dinh_duong
topic: macronutrients_protein_carb_fat
health_conditions:
  - general_nutrition
language: vi
source_ids:
  - source_001
generated_by: antigravity
generated_at: 2026-08-12
confidence: high
---

# Các Chất Dinh Dưỡng Đại Lượng (Protein, Carbohydrate, Fat, Sugar)

## Khái niệm chính

Các chất dinh dưỡng đại lượng (Macronutrients) là các chất dinh dưỡng cơ thể cần với số lượng lớn để cung cấp năng lượng và duy trì cấu trúc cơ thể, bao gồm:

1. **Protein (Chất đạm):** Có trong thịt, cá, trứng, sữa, đậu đỗ. Giúp xây dựng cơ bắp, tế bào, enzym và nội tiết tố.
2. **Carbohydrate (Chất đường bột):** Có trong cơm, bánh mì, khoai, bún, phở, đường. Là nguồn cung cấp năng lượng chính cho hoạt động thể chất và não bộ.
3. **Sugar (Đường):** Là dạng carbohydrate đơn giản (mono/disaccharides), hấp thu nhanh vào máu.
4. **Fat / Lipid (Chất béo):** Có trong dầu ăn, mỡ động vật, bơ, hạt. Giúp hấp thu các vitamin tan trong dầu (A, D, E, K), bảo vệ nội tạng và cung cấp năng lượng dự trữ.

## Ý nghĩa đối với món ăn

Tỷ lệ giữa các chất đại lượng tạo nên đặc tính dinh dưỡng của món ăn:
- Món giàu protein và chất béo mang lại cảm giác no lâu.
- Món chứa nhiều đường và carbohydrate tinh chế dễ làm tăng nhanh đường huyết sau khi ăn.
- Lượng chất béo trong món ăn ảnh hưởng trực tiếp đến mật độ calo (1g fat = 9 kcal, trong khi 1g protein/carb = 4 kcal).

## Cách hệ thống Daily Mate sử dụng chỉ số

Trong Daily Mate:
- **Giới hạn của Dataset món ăn:** Cơ sở dữ liệu món ăn hiện tại của Daily Mate (`dishes.json`) **KHÔNG chứa các trường dữ liệu định lượng riêng biệt như `protein_density`, `fat_density`, `sugar_density`**.
- **Cách phản ánh chỉ số:** 
  - Đạm (Protein) và Chất béo (Fat) đóng góp vào tổng calo năng lượng (`dish_energy_total` / `adj_energy_total`) và chỉ số no bụng (`dish_satiety_score` / `adj_satiety_score`).
  - Carbohydrate và Đường gia vị đóng góp vào việc tính toán chỉ số Tải lượng đường huyết (`dish_glycemic_load` / `adj_glycemic_load`).
- **Quy tắc cho RAG:** Hệ thống RAG tuyệt đối **không tự bịa đặt số liệu cụ thể (như số gam hay chỉ số density)** đối với các trường dữ liệu mà dataset không cung cấp. RAG chỉ giải thích đặc tính chung từ thành phần nguyên liệu.
- RAG không tự thực hiện lọc món ăn và không tự đề xuất thay đổi công thức chế biến.

## Cách diễn đạt cho người dùng

- Cung cấp cái nhìn toàn diện về sự cân bằng dinh dưỡng dựa trên thông tin nguyên liệu thực tế, không đưa ra con số định lượng bịa đặt.
- Ví dụ diễn đạt:
  - "Món ăn này sử dụng các nguyên liệu cân đối giữa protein và carbohydrate, giúp cung cấp năng lượng ổn định."
  - "Món ăn chứa thành phần gia vị đường hoặc tinh bột, người dùng cần lưu ý chỉ số tải lượng đường huyết (GL)."

## Giới hạn của thông tin

- Giá trị dinh dưỡng điều chỉnh (Adjusted value) là giá trị ước tính qua mô hình toán học sau hệ số chế biến, không phải kết quả phân tích phòng thí nghiệm.
- Thông tin mang tính tham khảo, không thay thế tư vấn y tế.

## Nguồn tham khảo

- Bảng thành phần thực phẩm Việt Nam (Vietnamese Food Composition Table) - Viện Dinh dưỡng Quốc gia (NIN).
