---
doc_id: doc_tang_huyet_ap_04
group: tang_huyet_ap
topic: tu_van_co_dieu_kien_huyet_ap
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

# Quy Tắc Diễn Đạt Có Điều Kiện Cho Bệnh Nhân Tăng Huyết Áp

## Khái niệm chính

Hệ thống RAG của Daily Mate tuân thủ nguyên tắc **tư vấn có điều kiện (conditional framing)** đối với thông tin liên quan tới bệnh tăng huyết áp:

- **Không khẳng định y khoa nhị phân:** Tránh kết luận "Món này an toàn tuyệt đối" hoặc "Món này làm hạ huyết áp ngay".
- **Gắn liền với thông tin chỉ số:** Phân tích dựa trên mốc tham chiếu $600\text{mg}$ Natri/serving và sự phân bổ Natri trong món ăn.

## Ý nghĩa đối với món ăn

Một món ăn chứa lượng natri vượt ngưỡng $600\text{mg/serving}$ được đánh giá dựa trên:
1. Hàm lượng gia vị nêm nếm trong công thức tổng thể theo `quantity_g`.
2. Sự hòa tan và phân bổ Natri giữa phần cái và phần nước.
3. Kích thước phần ăn chuẩn tiêu chuẩn.

## Cách hệ thống Daily Mate sử dụng chỉ số

Khi sinh câu giải thích dữ liệu RAG:
- Nếu món ăn có $\text{Sodium} \le 600\text{mg}$: Hệ thống giải thích món ăn có chỉ số an toàn cao hơn theo thang điểm nội bộ của Daily Mate.
- Nếu món ăn có $\text{Sodium} > 600\text{mg}$: Hệ thống chỉ rõ hàm lượng natri ước tính vượt mốc tham chiếu đơn bữa ($600\text{mg}$).
- RAG không tự đưa ra lời khuyên chỉnh sửa công thức hay hướng dẫn thay đổi lối sống cá nhân.

## Cách diễn đạt cho người dùng

Cấu trúc câu giải thích tiêu chuẩn:
1. **Phân tích hàm lượng Natri:** "Món ăn này có hàm lượng natri ước tính là [X] mg trên 1 phần ăn tiêu chuẩn..."
2. **Đánh giá có điều kiện:** "...mức natri này [nằm trong / vượt quá] mốc tham chiếu đơn bữa ($600\text{mg}$). Món ăn có điểm an toàn [cao hơn / thấp hơn] theo thang điểm nội bộ của Daily Mate."
3. **Cảnh báo y tế bắt buộc:** "Thông tin mang tính tham khảo, không thay thế tư vấn y tế."

## Giới hạn của thông tin

- Hệ thống không có thông tin bệnh án cá nhân. Kết quả cần được xem xét cùng khẩu phần chuẩn và tình trạng sức khỏe thực tế.
- Thông tin mang tính tham khảo, không thay thế tư vấn y tế.

## Nguồn tham khảo

- Quyết định 5968/QĐ-BYT Hướng dẫn chẩn đoán và điều trị tăng huyết áp - Bộ Y tế.
- Guideline: Sodium intake for adults and children - WHO (2012).
