# Báo Cáo Tổng Quan Thư Viện Kiến Thức Dinh Dưỡng (Knowledge Base Report)
**Dự án:** Daily Mate — Nutrition RAG Knowledge Base  
**Cập nhật lần cuối:** 2026-08-12  
**Hệ thống thực hiện:** Antigravity AI  

---

## 📊 1. Thống Kê Tổng Quan

* **Tổng số tài liệu Markdown:** 24 tài liệu
* **Tổng số nhóm chủ đề:** 5 nhóm
  1. `dinh_duong` (Dinh dưỡng tổng quát): 9 tài liệu
  2. `tieu_duong` (Tiểu đường): 4 tài liệu
  3. `tang_huyet_ap` (Tăng huyết áp): 4 tài liệu
  4. `gout` (Bệnh Gout): 4 tài liệu
  5. `ibs` (Hội chứng ruột kích thích - IBS): 3 tài liệu
* **File danh mục nguồn:** `knowledge/sources.json` (9 nguồn chuẩn hóa)

---

## 🛠️ 2. Kết Quả Rà Soát & Hoàn Thiện Lần Cuối

1. **Chuẩn Hóa Disclaimer Y Khoa Bắt Buộc:**
   - $100\%$ các tài liệu thuộc 4 nhóm bệnh lý (`tieu_duong/`, `tang_huyet_ap/`, `gout/`, `ibs/`) đã được chỉnh sửa để chứa **chính xác 100% câu disclaimer chuẩn**:
     $$\text{“Thông tin mang tính tham khảo, không thay thế tư vấn y tế.”}$$

2. **Loại Bỏ Hoàn Toàn Lời Khuyên Hành Động & Hướng Dẫn Điều Chỉnh Món:**
   - Đã rà soát và loại bỏ các cụm từ hành động như *nếu bạn..., nên hạn chế, nên tiết chế, nên ăn kèm, nên giảm, nên tăng, nên uống ít, nên tránh, điều chỉnh cách nấu, hạn chế nước dùng/nước chấm*; các ví dụ còn lại chỉ mô tả trung lập.
   - RAG chỉ tập trung giải thích ý nghĩa chỉ số, phân tích món dựa trên dữ liệu hiện có, trả lời có điều kiện và nêu lý do phù hợp/chưa phù hợp mà không đề xuất sửa công thức, nguyên liệu, khẩu phần hay cách nấu.

3. **Chuẩn Hóa Cách Mô Tả Giá Trị Điều Chỉnh (Adjusted Values):**
   - Đã loại bỏ toàn bộ các cụm từ dễ gây hiểu nhầm như *"hàm lượng thực tế tiêu thụ"*, *"kết quả đo thực tế"*, *"nồng độ thực tế"*.
   - Mô tả chính xác theo quy ước Daily Mate:
     - `Raw Value`: Giá trị tính từ nguyên liệu theo khối lượng `quantity_g`.
     - `Adjusted Value`: $\text{Raw Value} \times \text{Hệ số Cooking Method}$.
     - `Adjusted Value` là giá trị ước tính theo mô hình Daily Mate, **không phải kết quả xét nghiệm hoặc phân tích phòng thí nghiệm**.

4. **Cập Nhật `sources.json` & Trường `needs_verification`:**
   - Giữ nguyên cấu trúc JSON chuẩn hóa và bổ sung trường cờ `"needs_verification"` cho từng nguồn.
   - Đã chỉnh sửa tiêu đề của `source_008` thành *"Glycemic Index and Glycemic Load for 100+ Foods"* để khớp chính xác với URL Harvard Health Publishing, đồng thời đánh dấu `"needs_verification": true`.

5. **Nhất Quán Quy Ước Thang Điểm Gout:**
   - $100\%$ tài liệu tuân thủ quy ước nội bộ: **`gout_risk_score` CAO = AN TOÀN HƠN** (tiệm cận $1.0$ là ít purine, tiệm cận $0.0$ là nguy cơ cao).
   - Không gọi các chỉ số nội bộ là chẩn đoán y khoa hay khẳng định món ăn "an toàn tuyệt đối".

---

## 📁 3. Danh Sách Chi Tiết Tài Liệu Theo Nhóm

### 3.1 Nhóm Dinh Dưỡng Tổng Quát (`dinh_duong/`)
| STT | Tên file | Chủ đề chính | Nguồn tham chiếu |
|---|---|---|---|
| 1 | [dinh_duong_01_calories_nang_luong.md](file:///d:/dream_project/daily_mate_code/demo_server/knowledge/dinh_duong/dinh_duong_01_calories_nang_luong.md) | Calorie, TDEE, năng lượng thô vs sau chế biến (ước tính mô hình) | `source_001` |
| 2 | [dinh_duong_02_khau_phan_serving.md](file:///d:/dream_project/daily_mate_code/demo_server/knowledge/dinh_duong/dinh_duong_02_khau_phan_serving.md) | Quy ước 1 công thức = 1 serving, bao gồm toàn bộ gia vị & nước | `source_001` |
| 3 | [dinh_duong_03_macronutrients_protein_carb_fat.md](file:///d:/dream_project/daily_mate_code/demo_server/knowledge/dinh_duong/dinh_duong_03_macronutrients_protein_carb_fat.md) | Đạm (Protein), Đường bột (Carb), Đường (Sugar), Chất béo (Fat) (giới hạn dataset) | `source_001` |
| 4 | [dinh_duong_04_chat_xo_fiber.md](file:///d:/dream_project/daily_mate_code/demo_server/knowledge/dinh_duong/dinh_duong_04_chat_xo_fiber.md) | Chất xơ hòa tan & không hòa tan, vai trò trong cảm giác no | `source_001` |
| 5 | [dinh_duong_05_sodium_natri.md](file:///d:/dream_project/daily_mate_code/demo_server/knowledge/dinh_duong/dinh_duong_05_sodium_natri.md) | Sodium/Natri, nguồn từ gia vị, khuyến nghị WHO | `source_001`, `source_003`, `source_004` |
| 6 | [dinh_duong_06_gi_va_gl.md](file:///d:/dream_project/daily_mate_code/demo_server/knowledge/dinh_duong/dinh_duong_06_gi_va_gl.md) | Chỉ số đường huyết (GI) và Tải lượng đường huyết (GL) | `source_005`, `source_008` |
| 7 | [dinh_duong_07_purine.md](file:///d:/dream_project/daily_mate_code/demo_server/knowledge/dinh_duong/dinh_duong_07_purine.md) | Purine trong thực phẩm, quy đổi duy nhất qua `gout_risk_score` | `source_001`, `source_006` |
| 8 | [dinh_duong_08_hydration_satiety.md](file:///d:/dream_project/daily_mate_code/demo_server/knowledge/dinh_duong/dinh_duong_08_hydration_satiety.md) | Chỉ số cấp nước (`hydration`) và no bụng (`satiety`) | `source_001` |
| 9 | [dinh_duong_09_raw_vs_adjusted_dieu_chinh_phuong_phap_nau.md](file:///d:/dream_project/daily_mate_code/demo_server/knowledge/dinh_duong/dinh_duong_09_raw_vs_adjusted_dieu_chinh_phuong_phap_nau.md) | Giá trị thô (Raw) vs sau nấu (Adjusted), tác động phương pháp nấu | `source_001` |

### 3.2 Nhóm Tiểu Đường (`tieu_duong/`)
| STT | Tên file | Chủ đề chính | Nguồn tham chiếu |
|---|---|---|---|
| 10 | [tieu_duong_01_carbohydrate_va_duong.md](file:///d:/dream_project/daily_mate_code/demo_server/knowledge/tieu_duong/tieu_duong_01_carbohydrate_va_duong.md) | Carb phức hợp vs carb đơn giản, đường nêm nếm trong gia vị | `source_002`, `source_005` |
| 11 | [tieu_duong_02_gi_gl_trong_mon_an.md](file:///d:/dream_project/daily_mate_code/demo_server/knowledge/tieu_duong/tieu_duong_02_gi_gl_trong_mon_an.md) | Đọc chỉ số GL, mốc GL $\le 10$ cho 1 serving trong Daily Mate | `source_002`, `source_005`, `source_008` |
| 12 | [tieu_duong_03_khau_phan_tieu_duong.md](file:///d:/dream_project/daily_mate_code/demo_server/knowledge/tieu_duong/tieu_duong_03_khau_phan_tieu_duong.md) | Vai trò khẩu phần đối với chỉ số tải lượng đường huyết | `source_002`, `source_005` |
| 13 | [tieu_duong_04_tu_van_co_dieu_kien_tieu_duong.md](file:///d:/dream_project/daily_mate_code/demo_server/knowledge/tieu_duong/tieu_duong_04_tu_van_co_dieu_kien_tieu_duong.md) | Quy tắc diễn đạt có điều kiện cho thông tin tiểu đường | `source_002`, `source_005` |

### 3.3 Nhóm Tăng Huyết Áp (`tang_huyet_ap/`)
| STT | Tên file | Chủ đề chính | Nguồn tham chiếu |
|---|---|---|---|
| 14 | [tang_huyet_ap_01_sodium_va_muoi_nuoc_mam.md](file:///d:/dream_project/daily_mate_code/demo_server/knowledge/tang_huyet_ap/tang_huyet_ap_01_sodium_va_muoi_nuoc_mam.md) | Natri trong muối, nước mắm, gia vị mặn và nước dùng | `source_003`, `source_004` |
| 15 | [tang_huyet_ap_02_raw_adjusted_sodium.md](file:///d:/dream_project/daily_mate_code/demo_server/knowledge/tang_huyet_ap/tang_huyet_ap_02_raw_adjusted_sodium.md) | Natri thô vs Natri điều chỉnh theo cách nấu (kho cô đặc vs luộc/canh) | `source_001`, `source_003` |
| 16 | [tang_huyet_ap_03_sodium_safety_score.md](file:///d:/dream_project/daily_mate_code/demo_server/knowledge/tang_huyet_ap/tang_huyet_ap_03_sodium_safety_score.md) | Ý nghĩa `sodium_safety_score`, mốc tham chiếu $600\text{mg/serving}$ | `source_003`, `source_004` |
| 17 | [tang_huyet_ap_04_tu_van_co_dieu_kien_huyet_ap.md](file:///d:/dream_project/daily_mate_code/demo_server/knowledge/tang_huyet_ap/tang_huyet_ap_04_tu_van_co_dieu_kien_huyet_ap.md) | Quy tắc diễn đạt có điều kiện cho bệnh nhân tăng huyết áp | `source_003`, `source_004` |

### 3.4 Nhóm Bệnh Gout (`gout/`)
| STT | Tên file | Chủ đề chính | Nguồn tham chiếu |
|---|---|---|---|
| 18 | [gout_01_purine_khai_niem_va_tinh_toan.md](file:///d:/dream_project/daily_mate_code/demo_server/knowledge/gout/gout_01_purine_khai_niem_va_tinh_toan.md) | Khái niệm Purine, Axit Uric, quy đổi duy nhất qua `gout_risk_score` | `source_001`, `source_006` |
| 19 | [gout_02_gout_risk_score.md](file:///d:/dream_project/daily_mate_code/demo_server/knowledge/gout/gout_02_gout_risk_score.md) | `gout_risk_score` trong Daily Mate (Quy ước: **CAO = AN TOÀN HƠN**) | `source_006`, `source_unknown_001` |
| 20 | [gout_03_nguyen_lieu_phuong_phap_nau_gout.md](file:///d:/dream_project/daily_mate_code/demo_server/knowledge/gout/gout_03_nguyen_lieu_phuong_phap_nau_gout.md) | Ảnh hưởng nguyên liệu chính, nước ninh hầm, Condiment penalty (mắm) | `source_001`, `source_006` |
| 21 | [gout_04_tu_van_co_dieu_kien_gout.md](file:///d:/dream_project/daily_mate_code/demo_server/knowledge/gout/gout_04_tu_van_co_dieu_kien_gout.md) | Quy tắc diễn đạt có điều kiện cho bệnh nhân Gout | `source_006`, `source_unknown_001` |

### 3.5 Nhóm IBS (`ibs/`)
| STT | Tên file | Chủ đề chính | Nguồn tham chiếu |
|---|---|---|---|
| 22 | [ibs_01_khai_niem_va_dinh_duong.md](file:///d:/dream_project/daily_mate_code/demo_server/knowledge/ibs/ibs_01_khai_niem_va_dinh_duong.md) | IBS là gì, vai trò khẩu phần, chất xơ hòa tan vs không hòa tan | `source_001`, `source_007` |
| 23 | [ibs_02_gia_vi_nguyen_lieu_kich_thich.md](file:///d:/dream_project/daily_mate_code/demo_server/knowledge/ibs/ibs_02_gia_vi_nguyen_lieu_kich_thich.md) | Các gia vị kích thích (ớt, tiêu, hành, tỏi, mỡ cao, đồ chiên) | `source_007` |
| 24 | [ibs_03_tu_van_co_dieu_kien_ibs.md](file:///d:/dream_project/daily_mate_code/demo_server/knowledge/ibs/ibs_03_tu_van_co_dieu_kien_ibs.md) | Quy tắc diễn đạt thận trọng & có điều kiện cho IBS | `source_007` |

---

## 📚 4. Danh Sách Nguồn & Trạng Thái Xác Minh (`sources.json`)

| Source ID | Tên tài liệu / Tổ chức | Trạng thái `needs_verification` | Ghi chú thẩm định |
|---|---|---|---|
| `source_001` | Bảng thành phần thực phẩm Việt Nam (NIN) | `true` | Cần chuyên gia đối chiếu bản in 2017 thủ công |
| `source_002` | Quyết định 5481/QĐ-BYT (Đái tháo đường týp 2 - Bộ Y tế) | `false` | Đã xác minh văn bản pháp quy y tế Việt Nam |
| `source_003` | Quyết định 5968/QĐ-BYT (Tăng huyết áp - Bộ Y tế) | `false` | Đã xác minh văn bản pháp quy y tế Việt Nam |
| `source_004` | Guideline: Sodium intake (WHO) | `false` | Đã xác minh văn bản chính thức của WHO |
| `source_005` | Standards of Care in Diabetes—2024 (ADA) | `true` | Cần đối chiếu thủ công các bản cập nhật ADA mới nhất |
| `source_006` | 2020 ACR Guideline for Management of Gout (ACR) | `false` | Đã xác minh hướng dẫn lâm sàng của ACR |
| `source_007` | ACG Clinical Guideline: Management of IBS (ACG) | `false` | Đã xác minh hướng dẫn lâm sàng của ACG |
| `source_008` | Glycemic Index and GL for 100+ Foods (Harvard Health) | `true` | Đã chỉnh sửa tiêu đề cho khớp URL. Cần kiểm tra thủ công đối chiếu bài báo của ĐH Sydney |
| `source_unknown_001` | Nguồn chưa xác định (Quy ước nội bộ Daily Mate) | `true` | Dành cho các giả định thuật toán nội bộ. Cần chuyên gia xác minh thủ công |

---

## 🔍 5. Các Mục Cần Con Người Kiểm Tra Thủ Công (Manual Audit List)

1. **`source_001` (NIN Food Table):** Cần chuyên gia dinh dưỡng đối chiếu thủ công bản in Bảng thành phần thực phẩm Việt Nam (2017) với danh mục nguyên liệu thô của hệ thống.
2. **`source_005` (ADA 2024) & `source_008` (Harvard Health):** Cần người kiểm tra đối chiếu bảng tra cứu GI/GL quốc tế để thống nhất giá trị tham chiếu giữa Harvard Medical School và công trình của Đại học Sydney.
3. **`source_unknown_001` (Quy ước thuật toán nội bộ):** Cần đội ngũ y khoa/kỹ thuật Daily Mate rà soát lại các giả định quy đổi thang điểm `gout_risk_score` ($0.0 - 1.0$) và `sodium_safety_score` trước khi triển khai hệ thống RAG lên môi trường Production.
