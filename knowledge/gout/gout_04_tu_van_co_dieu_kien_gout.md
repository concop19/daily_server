---
doc_id: doc_gout_04
group: gout
topic: tu_van_co_dieu_kien_gout
health_conditions:
  - gout
language: vi
source_ids:
  - source_006
  - source_unknown_001
generated_by: antigravity
generated_at: 2026-08-12
confidence: high
---

# Quy Tắc Diễn Đạt Có Điều Kiện Cho Bệnh Nhân Gout

## Khái niệm chính

Hệ thống RAG của Daily Mate tuân thủ nghiêm ngặt nguyên tắc **tư vấn có điều kiện (conditional framing)** đối với bệnh Gout:

- **Không khẳng định y khoa nhị phân:** Tránh các phát ngôn "Món này bùng phát gút cấp ngay" hay "Món này chữa khỏi bệnh gút".
- **Luôn diễn đạt đúng quy ước `gout_risk_score`:** 
  - `gout_risk_score` **CAO** $\rightarrow$ **AN TOÀN HƠN** (chứa ít purine).
  - `gout_risk_score` **THẤP** $\rightarrow$ **NGUY CƠ CAO HƠN** (chứa nhiều purine từ thịt đỏ/hải sản/nội tạng/nước hầm).
- Tuyệt đối không diễn giải ngược rằng điểm `gout_risk_score` cao là nguy hiểm.

## Ý nghĩa đối với món ăn

Đặc tính chỉ số của món ăn đối với bệnh Gout được giải thích dựa trên:
1. Chỉ số `gout_risk_score` của 1 serving món ăn có $\ge 0.3$ (đạt tiêu chuẩn qua lọc cứng) hay không.
2. Tỷ lệ đóng góp purine từ nguyên liệu chính và nước dùng ninh hầm.
3. Thang điểm đánh giá an toàn nội bộ của Daily Mate.

## Cách hệ thống Daily Mate sử dụng chỉ số

Khi sinh câu trả lời cho người dùng bị Gout:
- Nếu `gout_risk_score >= 0.7`: Hệ thống giải thích món ăn có điểm an toàn cao hơn theo thang điểm nội bộ của Daily Mate.
- Nếu $0.3 \le \text{gout\_risk\_score} < 0.7$: Hệ thống cho biết món ăn ở mức an toàn trung bình trong mô hình đánh giá.
- Nếu `gout_risk_score < 0.3`: Hệ thống cho biết món ăn thuộc nhóm nguy cơ cao (chỉ số an toàn thấp), bị bộ lọc cứng tự động loại bỏ.
- RAG không tự đề xuất thay thế nguyên liệu hay sửa công thức chế biến của món ăn.

## Cách diễn đạt cho người dùng

Cấu trúc câu giải thích tiêu chuẩn cho bệnh Gout:
1. **Phân tích chỉ số an toàn:** "Món ăn này có chỉ số an toàn Gout (`gout_risk_score`) là [X] trên thang điểm 1.0 (điểm cao hơn = an toàn hơn)..."
2. **Đánh giá có điều kiện:** "...mức điểm này phản ánh món ăn có điểm an toàn [cao hơn / thấp hơn] theo thang điểm nội bộ của Daily Mate. Kết quả cần được xem xét cùng khẩu phần và tình trạng cá nhân."
3. **Cảnh báo y tế bắt buộc:** "Thông tin mang tính tham khảo, không phải kết luận y khoa và không thay thế tư vấn y tế."

## Giới hạn của thông tin

- Tình trạng nồng độ axit uric máu của mỗi cá nhân là khác nhau và cần sự theo dõi điều trị của bác sĩ chuyên khoa.
- Thông tin mang tính tham khảo, không thay thế tư vấn y tế.

## Nguồn tham khảo

- Quy ước thuật toán hệ thống Daily Mate (demo_server).
- 2020 ACR Guideline for the Management of Gout - American College of Rheumatology (ACR).
