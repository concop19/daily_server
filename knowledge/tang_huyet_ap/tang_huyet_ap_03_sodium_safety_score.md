---
doc_id: doc_tang_huyet_ap_03
group: tang_huyet_ap
topic: sodium_safety_score
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

# Ý Nghĩa Chỉ Số Sodium Safety Score trong Daily Mate

## Khái niệm chính

**`sodium_safety_score` (Điểm an toàn Natri)** là chỉ số chuẩn hóa trong hệ thống Daily Mate nhằm đánh giá mức độ an toàn của hàm lượng Natri trong 1 serving món ăn đối với sức khỏe hệ tim mạch.

- Điểm số được tính toán dựa trên khoảng cách giữa hàm lượng Natri điều chỉnh (`adj_sodium_total`) của món ăn và ngưỡng an toàn tham chiếu.
- Ngưỡng tham chiếu chuẩn trong hệ thống là **$600\text{mg}$ Natri / serving**.

## Ý nghĩa đối với món ăn

- **Món ăn có Natri $\le 600\text{mg}$:** Có chỉ số an toàn natri cao hơn theo thang điểm nội bộ của Daily Mate.
- **Món ăn có Natri $> 600\text{mg}$:** Vượt mốc tham chiếu đơn bữa, làm giảm chỉ số `sodium_safety_score` trong mô hình đánh giá.

## Cách hệ thống Daily Mate sử dụng chỉ số

Trong Daily Mate:
- `adj_sodium_total` là giá trị **ước tính theo mô hình toán học** ($\text{Raw Value} \times \text{Hệ số Cooking Method}$), **không phải kết quả xét nghiệm hoặc phân tích phòng thí nghiệm**.
- **Phân định vai trò RAG:** Hệ thống RAG không tự quyết định lọc hay loại bỏ món ăn (việc lọc món do mã nguồn Python backend `pipeline.py` đảm nhiệm). RAG chỉ giải thích dữ liệu chỉ số cho người dùng.
- RAG không tự đề xuất cách chỉnh sửa công thức chế biến, thay thế nguyên liệu hay đưa ra lời khuyên hành động cá nhân.

## Cách diễn đạt cho người dùng

- Giải thích khoa học về chỉ số Natri dựa trên mốc tham chiếu nội bộ.
- Ví dụ diễn đạt:
  - "Món ăn có hàm lượng natri ước tính nằm trong mốc tham chiếu cho 1 phần ăn, có chỉ số an toàn cao hơn theo thang điểm nội bộ của Daily Mate."
  - "Món ăn này có hàm lượng natri ước tính vượt mốc $600\text{mg/serving}$, có chỉ số an toàn natri thấp hơn."

## Giới hạn của thông tin

- Chỉ số an toàn natri được thiết kế theo mô hình tham chiếu tổng quát. Kết quả cần được xem xét cùng khẩu phần chuẩn và tình trạng sức khỏe thực tế.
- Thông tin mang tính tham khảo, không thay thế tư vấn y tế.

## Nguồn tham khảo

- Quyết định 5968/QĐ-BYT Hướng dẫn chẩn đoán và điều trị tăng huyết áp - Bộ Y tế.
- Guideline: Sodium intake for adults and children - WHO (2012).
