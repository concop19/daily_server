---
doc_id: doc_ibs_01
group: ibs
topic: ibs_khai_niem_va_dinh_duong
health_conditions:
  - ibs
language: vi
source_ids:
  - source_001
  - source_007
generated_by: antigravity
generated_at: 2026-08-12
confidence: high
---

# Hội Chứng Ruột Kích Thích (IBS) và Vai Trò Dinh Dưỡng

## Khái niệm chính

**Hội chứng ruột kích thích (Irritable Bowel Syndrome - IBS)** là một rối loạn tiêu hóa chức năng phổ biến của ruột giải thích bởi các triệu chứng đau bụng, đầy hơi, chướng bụng, tiêu chảy (IBS-D), táo bón (IBS-C) hoặc xen kẽ cả hai (IBS-M), mà không có tổn thương cấu trúc hay viêm nhiễm thực thể trên xét nghiệm.

- **Vai trò của dinh dưỡng:** Chế độ ăn uống là yếu tố kích thích (trigger) hàng đầu khởi phát hoặc làm trầm trọng thêm các triệu chứng IBS.
- **Phân biệt Chất xơ trong IBS:**
  - **Chất xơ hòa tan (Soluble fiber):** Thường dễ dung nạp hơn, giúp tạo gel làm mềm phân ở người táo bón và hút bớt nước ở người tiêu chảy.
  - **Chất xơ không hòa tan (Insoluble fiber):** Có thể làm tăng kích thích cơ học ruột, dễ gây đầy hơi và quặn bụng ở một số người IBS nhạy cảm.

## Ý nghĩa đối với món ăn

Đối với món ăn tiêu thụ bởi người có triệu chứng IBS:
1. **Khẩu phần ăn (Serving size):** Ăn khẩu phần quá lớn trong một bữa làm tăng áp lực căng dãn dạ dày - ruột, kích hoạt phản xạ dạ dày - đại tràng (gastrocolic reflex) gây co thắt ruột.
2. **Hàm lượng chất béo:** Món ăn giàu mỡ (chiên, rán, xào nhiều dầu) làm chậm tốc độ rỗng dạ dày và kích thích co thắt đại tràng mạnh hơn.

## Cách hệ thống Daily Mate sử dụng chỉ số

Trong hệ thống Daily Mate:
- **Giới hạn Dataset:** Cơ sở dữ liệu món ăn (`dishes.json`) không có trường `fiber_density` hay `fat_density`. Mức độ êm dịu tiêu hóa được phản ánh qua thành phần nguyên liệu thực vật và phương pháp nấu.
- **Phân định vai trò RAG:** Hệ thống RAG **không tự quyết định lọc món ăn**. Thuật toán xếp hạng và lọc món do backend Python pipeline xử lý. RAG chỉ giải thích dữ liệu chỉ số và cung cấp kiến thức tham khảo.
- RAG tuyệt đối **không tự đề xuất cách chỉnh sửa công thức món ăn, thay thế nguyên liệu hay thay đổi cách nấu**.

## Cách diễn đạt cho người dùng

- Diễn đạt ôn hòa với tư vấn có điều kiện, hướng dẫn người dùng quan sát phản ứng của bản thân.
- Ví dụ diễn đạt:
  - "Món ăn này có phương pháp chế biến thanh nhẹ (luộc/hấp), dễ tiêu hóa và có thể phù hợp với đường ruột nhạy cảm."
  - "Món ăn có chứa thành phần chất béo và chất xơ thô; mức độ dung nạp có thể khác nhau giữa từng người."

## Giới hạn của thông tin

- Giá trị dinh dưỡng điều chỉnh (Adjusted value) là giá trị ước tính qua mô hình toán học sau hệ số chế biến, không phải kết quả phân tích phòng thí nghiệm.
- IBS có tính chất cá thể hóa rất cao; thực phẩm gây khó chịu cho người này có thể hoàn toàn bình thường đối với người khác.
- Thông tin mang tính tham khảo, không thay thế tư vấn y tế.

## Nguồn tham khảo

- ACG Clinical Guideline: Management of Irritable Bowel Syndrome - American College of Gastroenterology (2021).
- Bảng thành phần thực phẩm Việt Nam - Viện Dinh dưỡng Quốc gia (NIN).
