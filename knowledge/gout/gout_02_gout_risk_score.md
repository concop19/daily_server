---
doc_id: doc_gout_02
group: gout
topic: gout_risk_score_trong_daily_mate
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

# Chỉ Số Gout Risk Score Trong Hệ Thống Daily Mate

## Khái niệm chính

**`gout_risk_score` (Chỉ số điểm an toàn Gout)** là thước đo nội bộ của hệ thống Daily Mate dùng để đánh giá mức độ an toàn tương đối của một món ăn đối với bệnh Gout.

> [!IMPORTANT]
> **QUY ƯỚC BẮT BUỘC VỀ THANG ĐIỂM GOUT_RISK_SCORE TRONG DAILY MATE:**
> - **`gout_risk_score` CAO (gần 1.0):** Thể hiện món ăn có **điểm an toàn cao hơn** (hàm lượng purine thấp hơn).
> - **`gout_risk_score` THẤP (gần 0.0):** Thể hiện món ăn có **nguy cơ cao hơn** (hàm lượng purine cao từ thịt đỏ/hải sản/nội tạng).

Thang điểm nằm trong khoảng từ $0.0$ đến $1.0$.

## Ý nghĩa đối với món ăn

- **`gout_risk_score` $\ge 0.7$ đến $1.0$ (Mức An Toàn Cao):** Món ăn sử dụng chủ yếu nguyên liệu thực vật, trứng, sữa hoặc lượng thịt ít. Món ăn này có điểm an toàn cao hơn theo thang điểm nội bộ của Daily Mate.
- **`gout_risk_score` từ $0.3$ đến $<0.7$ (Mức An Toàn Trung Bình):** Món ăn có lượng thịt/hải sản vừa phải trong công thức.
- **`gout_risk_score` $< 0.3$ (Mức Nguy Cơ Cao):** Món ăn chứa hàm lượng purine cao từ nội tạng, thịt đỏ, hải sản đậm đặc hoặc nước hầm xương đậm đặc.

## Cách hệ thống Daily Mate sử dụng chỉ số

Trong hệ thống Daily Mate:
- **Phân định vai trò RAG:** Hệ thống RAG không tự quyết định lọc hay loại bỏ món ăn. Thuật toán loại bỏ các món có `gout_risk_score < 0.3` do mã nguồn Python backend (`pipeline.py`) thực thi. RAG chỉ giải thích chỉ số dữ liệu.
- RAG không tự đề xuất cách chỉnh sửa công thức món ăn, thay thế nguyên liệu hay thay đổi cách nấu.
- **Không tự bịa `purine_mg`:** Dataset không có trường `purine_mg`, mọi đánh giá purine đều dựa duy nhất trên chỉ số `gout_risk_score`.

## Cách diễn đạt cho người dùng

- Tuyệt đối tuân thủ đúng quy ước: **Điểm cao = An toàn hơn, Điểm thấp = Nguy cơ cao hơn**.
- Tránh các phát ngôn khẳng định y khoa tuyệt đối.
- Ví dụ diễn đạt:
  - "Món ăn này có điểm an toàn cao hơn theo thang điểm nội bộ của Daily Mate (`gout_risk_score` = 0.85). Kết quả cần được xem xét cùng khẩu phần và tình trạng cá nhân."
  - "Món ăn có chỉ số an toàn thấp hơn (`gout_risk_score` = 0.25) do chứa thành phần hải sản/thịt đỏ."

## Giới hạn của thông tin

- `gout_risk_score` là chỉ số ước tính qua mô hình toán học dựa trên nguyên liệu món ăn, không phải kết quả xét nghiệm hóa sinh hay phân tích phòng thí nghiệm. Thông tin này không phải kết luận y khoa.
- Thông tin mang tính tham khảo, không thay thế tư vấn y tế.

## Nguồn tham khảo

- Quy ước thuật toán hệ thống Daily Mate (demo_server).
- 2020 ACR Guideline for the Management of Gout - American College of Rheumatology (ACR).
