---
doc_id: doc_dinh_duong_07
group: dinh_duong
topic: purine_va_chiet_xuat
health_conditions:
  - general_nutrition
  - gout
language: vi
source_ids:
  - source_001
  - source_006
generated_by: antigravity
generated_at: 2026-08-12
confidence: high
---

# Purine trong Dinh Dưỡng Thực Phẩm

## Khái niệm chính

**Purine** là một hợp chất tự nhiên chứa nitơ có trong tế bào của tất cả các sinh vật sống. Trong cơ thể người, purine được phân giải thành **Axit Uric**. 

- **Nguồn purine:** Purine đến từ quá trình chuyển hóa nội sinh trong cơ thể và purine ngoại sinh nạp từ thực phẩm.
- **Thực phẩm giàu purine:** Thịt đỏ (bò, dê, cừu), nội tạng động vật (gan, thận, lòng), hải sản (tôm, cua, mực, cá mòi, sò), nước ninh xương đặc.
- **Thực phẩm ít purine:** Ngũ cốc, rau củ quả, sữa và các sản phẩm từ sữa, trứng.

## Ý nghĩa đối với món ăn

Hàm lượng purine trong món ăn chịu ảnh hưởng bởi:
1. **Chủng loại nguyên liệu:** Loại thịt/hải sản và khối lượng nguyên liệu chính được dùng trong công thức.
2. **Phương pháp chế biến:** Purine là chất tan trong nước. Khi ninh/hầm thịt hoặc hải sản trong thời gian dài, một lượng lớn purine chiết xuất từ thịt sẽ hòa tan vào nước dùng/nước canh.

## Cách hệ thống Daily Mate sử dụng chỉ số

Trong Daily Mate:
- **Giới hạn của Dataset:** Cơ sở dữ liệu món ăn (`dishes.json`) **KHÔNG chứa trường dữ liệu hàm lượng purine tuyệt đối `purine_mg`**.
- **Chỉ số chuẩn hóa (`gout_risk_score`):** Mức độ an toàn purine của món ăn được quy đổi duy nhất qua chỉ số **`gout_risk_score`** ($0.0 - 1.0$). 
  - Quy ước bắt buộc: **`gout_risk_score` CAO $\rightarrow$ AN TOÀN HƠN**; **THẤP $\rightarrow$ NGUY CƠ CAO HƠN**.
- **Quy tắc cho RAG:** RAG không tự bịa đặt số miligram purine (`purine_mg`) cho món ăn khi dataset không cung cấp. RAG chỉ giải thích mức độ an toàn purine từ chỉ số `gout_risk_score` và đặc tính nguyên liệu.
- RAG không tự quyết định lọc món ăn và không tự đề xuất cách chỉnh sửa công thức chế biến.

## Cách diễn đạt cho người dùng

- Cung cấp thông tin khách quan về đặc tính purine của món ăn dựa trên nguyên liệu và điểm `gout_risk_score`.
- Ví dụ diễn đạt:
  - "Món ăn này sử dụng nguyên liệu thực vật, có chỉ số an toàn Gout cao (`gout_risk_score` cao)."
  - "Món ăn có chứa nguyên liệu thịt đỏ/hải sản, thuộc nhóm cần lưu ý đối với người có axit uric cao (`gout_risk_score` thấp)."

## Giới hạn của thông tin

- `gout_risk_score` là chỉ số ước tính qua mô hình toán học từ dữ liệu nguyên liệu, không phải kết quả phân tích hay xét nghiệm hóa sinh phòng thí nghiệm.
- Thông tin mang tính tham khảo, không thay thế tư vấn y tế.

## Nguồn tham khảo

- Bảng thành phần thực phẩm Việt Nam - Viện Dinh dưỡng Quốc gia (NIN).
- 2020 ACR Guideline for the Management of Gout - American College of Rheumatology.
