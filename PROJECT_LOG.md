
## [2026-04-28 - ai_polish.py review & rewrite] - Cải thiện chất lượng AI explanation - Ảnh hưởng đến /api/v1/recommend top-3 dishes

### Vấn đề phát hiện:
1. _build_prompt bỏ qua 3/7 trường từ advice_engine (headline, ingredient_note, seasonal_note)
2. Task description sai: "mô tả món ăn" thay vì "tổng hợp lý do gợi ý"
3. Giới hạn 40 từ + max_tokens=100 quá chặt → explanation bị cụt
4. Không có system prompt → AI thiếu context về vai trò
5. Model llama-3.1-8b-instant yếu cho tiếng Việt tự nhiên
6. Cache key dùng tuple()[:3] → không ổn định
7. Fallback chỉ lấy headline → thiếu thông tin

### Thay đổi trong ai_polish.py:
- MODEL: llama-3.1-8b-instant → llama-3.3-70b-versatile
- _build_prompt: dùng đủ 7 trường (thêm headline, ingredient_note, seasonal_note)
- System prompt: thêm role "trợ lý dinh dưỡng thân thiện" + constraints rõ ràng
- Task: đổi từ "mô tả" sang "tổng hợp lý do gợi ý" với 3-phần cấu trúc (thời tiết → điểm nổi bật → lời khuyên)
- Giới hạn: 40 từ → 70 từ; max_tokens: 100 → 180
- temperature: 0.7 → 0.55 (giảm hallucination)
- Cache key: tuple()[:3] → MD5 hash ổn định từ demand + disease_flags
- Fallback: thêm _build_fallback() tổng hợp từ tất cả trường thay vì chỉ headline
- Thêm validation: reject output < 20 chars

### Thay đổi trong app.py:
- Thêm import logging + logger = logging.getLogger(__name__)
- Thay print(dish_result["explanation"]) → logger.info với ai_source và summary_len

### Ghi chú cho tương lai:
- Nếu latency Groq tăng lên >3s: xem xét chạy polish_explanation async song song cho cả 3 dishes (asyncio.gather)
- Nếu muốn fallback tốt hơn khi không có key: có thể dùng llama.cpp local model
- Cache hiện tại là in-memory — restart server sẽ mất cache. Cân nhắc persist vào SQLite nếu cần

## [2026-04-28 - ai_polish.py fix generic output] - Fix explanation giống template - Ảnh hưởng: ai_summary trong /api/v1/recommend

### Vấn đề phát hiện (từ screenshot log):
- 3 món khác nhau nhưng ai_summary gần như giống nhau ("Hôm nay trời nóng...", "...phù hợp với người bị gout...")
- AI đang paraphrase lại weather_reason + dish_match vốn đã là template sentence từ advice_engine
- Cả 3 món cùng context (nóng + gout) → AI không có lý do để viết khác

### Root cause:
1. Prompt cũ dùng cấu trúc "Câu đầu: thời tiết → Câu giữa: điểm nổi bật" → AI luôn mở bằng thời tiết
2. Không có cơ chế tìm điểm khác biệt giữa các món
3. System prompt không cấm filler phrases

### Fix:
1. Thêm _extract_unique_angle(): tìm điểm độc đáo nhất của từng món
   - Ưu tiên: ingredient_note > seasonal_note > số liệu cụ thể trong dish_match > weather
   - Dùng regex r'\d+[\.,]?\d*\s*(?:%|mg|GL|kcal)' để extract số liệu
2. Rewrite system prompt: cấm explicit "lựa chọn hoàn hảo", "hãy thưởng thức", "cảm nhận sự", "rất phù hợp"
3. Prompt mới: [QUAN TRỌNG NHẤT] tag để AI biết bắt đầu từ đâu
4. Đổi cấu trúc: không còn "câu đầu = thời tiết" cứng nhắc
5. Fix: import re từ trong function ra top-level

### Ghi chú:
- Trong test case hiện tại, cả 3 món đều có ingredient_note=None và seasonal_note giống nhau
  → _extract_unique_angle() sẽ fallback về dish_match với % score
  → Cá rô đồng (81%), Rau củ (92%), Thịt nhồi (91%) → 3 câu mở khác nhau
- Nếu muốn differentiation tốt hơn: cần advice_engine thêm trường "unique_trait" per dish

## [2026-04-28 - ai_polish.py fix v2 - output vẫn giống nhau] - Fix differentiation thật sự

### Vấn đề:
Fix v1 vẫn ra output giống nhau vì:
1. seasonal_note ở priority #2 nhưng tất cả món cùng mùa có cùng seasonal_note template
   → Cả 3 mở bằng "Mùa xuân mát mẻ và đầy sinh khí..."
2. dish_match cũng là template: "[Tên món] có hàm lượng purine thấp (điểm: X%)"
   → Cấu trúc giống nhau, chỉ khác số %
3. AI không có dữ liệu thật sự khác nhau giữa 3 món

### Fix v2:
1. _extract_unique_angle(): đổi priority
   - CŨ: ingredient → seasonal → score → weather  
   - MỚI: ingredient → score → cook_time → seasonal → weather
2. Thêm _parse_taste(): chuyển taste_profile JSON thành "vị ngọt nhẹ, chua dịu"
   → Mỗi món có vị khác nhau → đây là data THẬT khác nhau
3. Rewrite _build_prompt() hoàn toàn:
   - Tách rõ "ĐẶC ĐIỂM RIÊNG" (vị, điểm số, cook_time, nation) vs "BỐI CẢNH NGƯỜI DÙNG"
   - Bảo AI "BỐI CẢNH NGƯỜI DÙNG đã biết, không lặp rập khuôn"
   - Cấm KHÔNG bắt đầu bằng "Mùa xuân", "Hôm nay trời", "Đây là"
4. Regex score extraction cải thiện: bắt được "điểm an toàn: 92%", "90%", "mg", "GL X"

### Kỳ vọng sau fix:
- Món Rau cần nước muối chua (vị chua dịu, 15 phút): mở bằng vị chua
- Món Rau câu múi cam và trứng muối (vị ngọt nhẹ, 98% gout): mở bằng vị ngọt + score
- Món Rau giá trộn lá kim (vị thanh mát): mở bằng tính thanh mát
