# Daily Mate — Demo Server
# Project Overview

**Ngày tạo:** 2026-05-06
**Phiên bản:** Demo / MVP
**Ngôn ngữ:** Python 3.12+
**Framework:** Flask 3.x

---

## 1. Giới thiệu

**Daily Mate** là hệ thống gợi ý món ăn thông minh dành cho người dùng Việt Nam.
Server demo này là backend REST API phục vụ ứng dụng mobile/web, tự động đề xuất
món ăn phù hợp với thời tiết thực tế, thể trạng sức khỏe cá nhân,
nguyên liệu sẵn có trong tủ lạnh, và vùng miền địa lý của người dùng.

---

## 2. Mục tiêu dự án

| Mục tiêu | Mô tả |
|---|---|
| Gợi ý cá nhân hóa | Đề xuất món ăn tối ưu dựa trên dữ liệu thực của từng cá nhân |
| Hỗ trợ sức khỏe | Bộ lọc bệnh lý: tăng huyết áp, tiểu đường, gout, IBS |
| Nhận thức thời tiết | Điều chỉnh gợi ý theo điều kiện thời tiết và mùa thực tế |
| Tối ưu nguyên liệu | Ưu tiên món dùng được nguyên liệu người dùng đang có |
| Thách thức ẩm thực | "Món thử thách trong ngày" khuyến khích khám phá ẩm thực |


## 3. Tính năng chính

### 3.1 Recommendation Engine
- Gợi ý tối đa 20 món/lượt, xếp hạng theo điểm tổng hợp đa chiều
- Lọc theo ẩm thực Việt Nam, quốc tế, hoặc quốc gia cụ thể
- Phân loại món: canh/soup, món chính, hoặc tất cả
- **Basket boost**: ưu tiên món dùng được >= 40% nguyên liệu người dùng có sẵn
  (loại trừ pantry items: gia vị, dầu mỡ, sữa/trứng, ngũ cốc cơ bản)
- **Repetition decay**: giảm điểm món ăn gần đây để tránh lặp lại
  (vị trí 0 → x0.5, vị trí 1 → x0.65, vị trí 2 → x0.8)

### 3.2 Weather-Aware Scoring
- Tích hợp OpenWeatherMap API: nhiệt độ, độ ẩm, gió, AQI theo vị trí GPS
- Tính 6 chỉ số thời tiết nội bộ:
  heat_stress, dehydration_risk, cold_stress,
  oxidative_stress, infection_risk, immune_load
- Cache TTL động 15–60 phút theo mức cực đoan
  (AQI > 150, gió > 50 km/h, nhiệt > 40°C → TTL ngắn hơn)
- Fallback an toàn khi mất kết nối API ngoài

### 3.3 Health-Aware Filtering
- **Hard filter**: loại bỏ món vượt giới hạn sodium (600 mg/serving với tăng huyết áp),
  glycemic load (GL > 10 với tiểu đường), gout risk score < 0.3
- **Allergy filter**: theo ingredient ID cụ thể hoặc nhóm
  (seafood, meat, dairy, egg, nut, gluten, soy, pork, fish, shellfish, wheat)
- **Diet filter**: vegan, vegetarian, omnivore
- **Time filter**: hard ceiling = max_prep_time + 10 phút

### 3.4 Explanation Engine (Advice Engine)
- Sinh giải thích tiếng Việt tự nhiên cho mỗi gợi ý theo 7 chiều:
  headline, weather_reason, dish_match, nutrition_note,
  ingredient_note, seasonal_note, tags
- Template từ `data/advice_templates.json`, được `data_store.py` nạp vào memory
- **FitChecker**: chỉ sinh lý do khi dish score thực sự vượt ngưỡng,
  không bịa lý do khi dữ liệu không đủ điều kiện

### 3.5 Daily Challenge
- Random có trọng số theo final_score, seed cố định trong ngày
  (MD5 hash của ngày + tọa độ GPS làm tròn 0.1 độ)
- Hiển thị độ khó: easy (<=20 phút), medium (<=45 phút), hard (>45 phút)
- Kèm lý do phù hợp theo chiều thời tiết nổi bật nhất trong ngày

---

## 4. Công nghệ sử dụng

| Thành phần | Công nghệ |
|---|---|
| Web Framework | Flask 3.x + Flask-CORS |
| Data layer local | JSON DataStore — nạp toàn bộ dữ liệu vào memory khi khởi động |
| Database cloud | Supabase (PostgreSQL) — feedback, request log |
| Auth | Supabase JWT (ES256/HS256) — PyJWT + JWKS auto-cache |
| Weather API | OpenWeatherMap (current weather + air pollution) |
| Deployment | Gunicorn + Procfile (tương thích Heroku / Railway) |
| Monitoring | Supabase REST — ghi log endpoint/latency/uid mỗi request |
| Rate Limiting | In-process decorator: 10 req/60s trên /api/v1/recommend |


## 5. Phạm vi dữ liệu (JSON DataStore — thư mục `data/`)

Các dataset tĩnh được lưu dưới dạng JSON và nạp một lần vào memory khi server
khởi động. Các lookup chính dùng list/dict trong Python thay vì mở kết nối DB
cho từng request, giúp giảm đáng kể latency của recommendation pipeline.

| Bảng | Nội dung |
|---|---|
| `dishes.json` | Món ăn + chỉ số: hydration, warming, cooling, glycemic load, sodium, gout risk, cost level |
| `ingredients.json` | Nguyên liệu: danh mục, vùng phân phối, mùa vụ, source_type |
| `dish_ingredients.json` | Quan hệ món – nguyên liệu với khối lượng (g) và is_main flag |
| `cooking_methods.json` | Phương pháp nấu (nấu canh, soup...) |
| `provinces.json` | 63 tỉnh/thành: vùng ẩm thực, khí hậu, tọa độ trung tâm |
| `availability_matrix.json` | Ma trận availability theo (distribution_reach, food_region) |
| `advice_templates.json` | Mẫu giải thích theo context_type + trigger_dim + intensity |
| `device_tokens.json` | Token push và vị trí thiết bị; ghi lại sau mỗi lần upsert |

---

## 6. API Endpoints

| Method | Endpoint | Auth | Mô tả |
|---|---|---|---|
| GET | /health | Không | Health check + thống kê DB |
| GET | /api/weather | JWT | Lấy thời tiết + weather vector theo GPS |
| POST | /api/v1/recommend | JWT + Rate limit | Gợi ý món ăn (endpoint chính) |
| POST | /api/v1/feedback | JWT | Gửi phản hồi: eaten / skipped / rated |
| GET | /api/v1/challenge | Không | Món thử thách trong ngày |
| GET | /api/v1/dishes | Không | Danh sách món (pagination) |
| GET | /api/v1/dishes/<id> | Không | Chi tiết món + nguyên liệu |
| GET | /api/v1/ingredients | Không | Danh sách nguyên liệu |
| GET | /api/v1/locations | Không | Danh sách 63 tỉnh/thành |
| POST | /api/v1/weather/simulate | Không | Mô phỏng weather vector |
| POST | /api/v1/pipeline/debug | Không | Debug pipeline (dev only) |
| GET | /admin/stats | JWT + Admin | Thống kê request trong ngày |

---

## 7. Giới hạn hiện tại (Demo)

- AI polish explanation cần Groq API key riêng
  (module ai_polish.py đã thiết kế và review kỹ, chưa enable trong demo)
- Data catalog được load lại từ JSON khi restart; device tokens được persist trong `data/device_tokens.json`
- Weather cache dùng L1 in-memory và L2 Supabase, nên L1 mất khi restart nhưng L2 vẫn có thể phục hồi
- Rate limiter in-process, chưa scale ngang được (cần Redis cho production)
- Admin stats chỉ xem qua Supabase service_role key
- Chưa có cơ chế học từ feedback người dùng để cải thiện gợi ý theo thời gian
