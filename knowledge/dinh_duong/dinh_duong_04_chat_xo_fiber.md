---
doc_id: doc_dinh_duong_04
group: dinh_duong
topic: chat_xo_fiber
health_conditions:
  - general_nutrition
language: vi
source_ids:
  - source_001
generated_by: antigravity
generated_at: 2026-08-12
confidence: high
---

# Chất Xơ (Fiber) và Vai Trò Dinh Dưỡng

## Khái niệm chính

**Chất xơ (Dietary Fiber)** là thành phần của thực phẩm gốc thực vật mà enzym tiêu hóa của người không thể phân giải hoàn toàn. Chất xơ được chia thành hai nhóm chính:
1. **Chất xơ hòa tan (Soluble fiber):** Tan trong nước tạo thành dạng gel (có trong yến mạch, đậu, táo, cà rốt). Giúp làm chậm quá trình hấp thu đường và hỗ trợ giảm cholesterol.
2. **Chất xơ không hòa tan (Insoluble fiber):** Không tan trong nước (có trong rau xanh, ngũ cốc nguyên hạt, vỏ trái cây). Giúp tăng khối lượng phân và thúc đẩy nhu động ruột.

## Ý nghĩa đối với món ăn

Sự có mặt của chất xơ trong món ăn mang lại nhiều lợi ích:
- **Làm chậm hấp thu đường:** Giảm tốc độ tăng đường huyết sau ăn.
- **Tăng cảm giác no (`satiety`):** Giúp kiểm soát khẩu phần và cân nặng hiệu quả.
- **Hỗ trợ vi sinh đường ruột:** Là nguồn thức ăn cho các lợi khuẩn trong đại tràng.

## Cách hệ thống Daily Mate sử dụng chỉ số

Trong hệ thống Daily Mate:
- **Giới hạn của Dataset:** Cơ sở dữ liệu món ăn hiện tại (`dishes.json`) **KHÔNG chứa trường dữ liệu riêng biệt `fiber_density`**.
- **Cách phản ánh gián tiếp:** Sự đóng góp của chất xơ được phản ánh gián tiếp qua sự có mặt của các nguyên liệu thực vật (rau, củ, quả, hạt) trong `dish_ingredients`, làm tăng chỉ số no bụng (`dish_satiety_score` / `adj_satiety_score`) và hỗ trợ làm dịu chỉ số tải lượng đường huyết (`glycemic_load`).
- **Quy tắc cho RAG:** RAG không tự phát minh số liệu `fiber_density` hay số gam chất xơ cụ thể. RAG chỉ giải thích ý nghĩa chất xơ từ thành phần thực vật của món ăn mà không đưa ra hướng dẫn hành động hay đề xuất chỉnh sửa công thức.
- RAG không tự quyết định lọc món ăn và không tự đề xuất cách chỉnh sửa công thức chế biến.

## Cách diễn đạt cho người dùng

- Cung cấp thông tin dinh dưỡng khách quan về thành phần chất xơ từ thực vật.
- Ví dụ diễn đạt:
  - "Món ăn này chứa chất xơ tự nhiên từ thành phần rau củ, góp phần làm tăng chỉ số no bụng (`satiety`)."
  - "Món ăn có thành phần chủ yếu là tinh bột/đạm, có lượng chất xơ ước tính ở mức thấp hơn."

## Giới hạn của thông tin

- Giá trị dinh dưỡng điều chỉnh (Adjusted value) là giá trị ước tính qua mô hình toán học sau hệ số chế biến, không phải kết quả phân tích phòng thí nghiệm.
- Thông tin mang tính tham khảo, không phải kết luận y khoa và không thay thế tư vấn y tế.

## Nguồn tham khảo

- Bảng thành phần thực phẩm Việt Nam (Vietnamese Food Composition Table) - Viện Dinh dưỡng Quốc gia (NIN).
