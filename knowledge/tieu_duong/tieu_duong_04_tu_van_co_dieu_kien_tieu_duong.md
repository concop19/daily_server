---
doc_id: doc_tieu_duong_04
group: tieu_duong
topic: tu_van_co_dieu_kien_tieu_duong
health_conditions:
  - diabetes
language: vi
source_ids:
  - source_002
  - source_005
generated_by: antigravity
generated_at: 2026-08-12
confidence: high
---

# Quy Tắc Diễn Đạt Có Điều Kiện Cho Thông Tin Tiểu Đường

## Khái niệm chính

Hệ thống RAG của Daily Mate tuân thủ nghiêm ngặt nguyên tắc **tư vấn có điều kiện (conditional framing)** khi giải thích dữ liệu liên quan tới bệnh đái tháo đường:

- **Không khẳng định nhị phân hay y khoa tuyệt đối:** Không dùng các câu như "Món này an toàn tuyệt đối", "Món này phù hợp hoàn toàn cho người bệnh" hoặc "Món này chữa được tiểu đường".
- **Luôn đưa ra điều kiện gắn liền với chỉ số:** Trả lời dựa trên tải lượng đường huyết ước tính (`adj_glycemic_load`) và mốc tham chiếu $\text{GL} \le 10$.

## Ý nghĩa đối với món ăn

Một món ăn không được dán nhãn "tốt hoàn toàn" hay "xấu hoàn toàn", mà được giải thích dựa trên:
1. Chỉ số GL ước tính của 1 serving món ăn có nằm trong mốc tham chiếu ($\le 10$) hay không.
2. Mức độ đóng góp carbohydrate từ nguyên liệu chính và gia vị nêm nếm.
3. Bản chất chỉ số ước tính từ mô hình toán học.

## Cách hệ thống Daily Mate sử dụng chỉ số

Trong việc giải thích RAG:
- Nếu món ăn có $\text{GL} \le 10$: Hệ thống giải thích món ăn có tải lượng đường huyết ước tính ở mức thấp đối với 1 phần ăn tiêu chuẩn. Kết quả cần được xem xét cùng khẩu phần và tình trạng cá nhân.
- Nếu món ăn có $\text{GL} > 10$: Hệ thống giải thích món ăn có tải lượng đường huyết ước tính cao hơn mốc tham chiếu tiêu chuẩn.
- RAG không đưa ra lời khuyên hành động cá nhân hay đề xuất thay đổi công thức chế biến.

## Cách diễn đạt cho người dùng

Cấu trúc mẫu câu giải thích tiêu chuẩn:
1. **Phần phân tích chỉ số:** "Món ăn này có chỉ số tải lượng đường huyết (GL) ước tính là [X] trên 1 khẩu phần tiêu chuẩn..."
2. **Phần điều kiện & Thận trọng:** "...mức điểm này phản ánh tải lượng đường huyết [thấp / trung bình / cao] theo mô hình đánh giá của Daily Mate. Kết quả cần được xem xét cùng khẩu phần và tình trạng cá nhân."
3. **Cảnh báo y tế bắt buộc:** "Thông tin mang tính tham khảo, không phải kết luận y khoa và không thay thế tư vấn y tế."

## Giới hạn của thông tin

- Hệ thống không có thông tin về hồ sơ bệnh án chi tiết hay phác đồ điều trị cá nhân của người dùng.
- Thông tin mang tính tham khảo, không thay thế tư vấn y tế.

## Nguồn tham khảo

- Quyết định 5481/QĐ-BYT Hướng dẫn chẩn đoán và điều trị bệnh đái tháo đường týp 2 - Bộ Y tế.
- Standards of Care in Diabetes - ADA (2024).
