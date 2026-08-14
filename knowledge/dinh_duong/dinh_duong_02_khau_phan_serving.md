---
doc_id: doc_dinh_duong_02
group: dinh_duong
topic: khau_phan_va_quy_uoc_serving
health_conditions:
  - general_nutrition
language: vi
source_ids:
  - source_001
generated_by: antigravity
generated_at: 2026-08-12
confidence: high
---

# Khẩu phần và Quy ước Serving trong Daily Mate

## Khái niệm chính

**Khẩu phần (Serving size)** là lượng thực phẩm chuẩn được quy định cho một lần ăn. Trong phân tích dinh dưỡng, việc xác định khẩu phần là căn cứ bắt buộc để tính toán tổng hàm lượng chất dinh dưỡng, calo, natri và tải lượng đường huyết.

## Ý nghĩa đối với món ăn

Mỗi món ăn có thể bao gồm nhiều nguyên liệu kết hợp với nhau. Khẩu phần quyết định:
- Tổng dung lượng calo nạp vào cơ thể.
- Tổng lượng natri, đường, chất béo và chất xơ nạp vào theo ước tính.
- Mức độ ảnh hưởng đến đường huyết và chỉ số purine.

Nếu kích thước phần ăn tăng gấp đôi, tất cả các giá trị dinh dưỡng nạp vào cũng tăng gấp đôi tương ứng.

## Cách hệ thống Daily Mate sử dụng chỉ số

Trong Daily Mate, quy ước khẩu phần được chuẩn hóa nghiêm ngặt để phục vụ tính toán RAG và Recommendation Pipeline:
1. **Quy ước 1 Serving:** Toàn bộ công thức chi tiết của một món ăn được xem là đúng **1 serving** (một phần ăn chuẩn).
2. **Tính toán toàn bộ nguyên liệu:** Tất cả thành phần có trong `dish_ingredients` đều được cộng gộp vào chỉ số của serving đó dựa trên khối lượng nguyên liệu (`quantity_g`), bao gồm:
   - Nguyên liệu chính (`is_main = true`) và nguyên liệu phụ.
   - Nguyên liệu tùy chọn (optional ingredients).
   - Tất cả các loại gia vị: muối, nước mắm, hạt nêm, đường.
   - Dầu, mỡ, bơ và nước dùng/nước lọc trong món.
3. **Giá trị thô và Giá trị điều chỉnh:** 
   - **Raw value:** Giá trị tính toán từ nguyên liệu chưa qua chế biến theo `quantity_g`.
   - **Adjusted value:** $\text{Raw Value} \times \text{Hệ số Cooking Method}$. Đây là giá trị ước tính theo mô hình Daily Mate, **không phải kết quả xét nghiệm hoặc phân tích phòng thí nghiệm**.
4. **Phân định vai trò RAG:** RAG chỉ đóng vai trò giải thích thông tin dữ liệu cho người dùng, không tự thực hiện việc lọc món ăn (việc lọc món do hệ thống backend pipeline xử lý) và không tự đề xuất thay đổi công thức chế biến hay thay thế nguyên liệu.

## Cách diễn đạt cho người dùng

Khi tương tác với người dùng về khẩu phần:
- Giải thích rõ rằng giá trị dinh dưỡng hiển thị áp dụng cho 1 phần ăn tiêu chuẩn theo công thức món.
- Ví dụ diễn đạt:
  - "Giá trị dinh dưỡng của món ăn này được tính toán cho 1 phần ăn tiêu chuẩn bao gồm đầy đủ các nguyên liệu và gia vị theo công thức."
  - "Khi ăn khẩu phần lớn hơn hoặc nhỏ hơn phần tiêu chuẩn, lượng dinh dưỡng ước tính nạp vào sẽ thay đổi tương ứng."

## Giới hạn của thông tin

- Quy ước 1 công thức = 1 serving dựa trên thiết kế chuẩn của cơ sở dữ liệu món ăn.
- Trong thực tế, sức ăn và cách chia phần của từng cá nhân hoặc gia đình có thể khác với phần ăn chuẩn.
- Thông tin mang tính tham khảo, không thay thế tư vấn y tế.

## Nguồn tham khảo

- Bảng thành phần thực phẩm Việt Nam (Vietnamese Food Composition Table) - Viện Dinh dưỡng Quốc gia (NIN).
