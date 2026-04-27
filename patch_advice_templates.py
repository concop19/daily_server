"""
patch_advice_templates.py
=========================
Bổ sung templates còn thiếu vào DB thực tế.

Vấn đề phát hiện qua audit:
1. headline: gout/sodium/glycemic/ibs_control_need hoàn toàn thiếu
2. headline: cooling/warming/hydration chỉ có 2 variant, cần thêm P3
3. weather: nhiều trigger_dim không match engine (dinner_meal, lunch_meal...) → vô dụng
4. weather: electrolyte_need hoàn toàn thiếu (engine dùng nhưng DB không có)
5. season: autumn/dry_season/north_winter/south_dry/rainy_season/tet_preparation thiếu P2/P3
6. tag: mỗi dim chỉ 1 template → random.choices không có effect
7. ingredient: boost_medium/high cần thêm variant để đa dạng
"""

import sqlite3, sys
sys.stdout.reconfigure(encoding='utf-8')

DB = r'D:\dream_project\daily_mate_code\daily_mate_all\database\recipe.db'

NEW_TEMPLATES = [

    # ─────────────────────────────────────────────────────────────
    # HEADLINE — bổ sung các dimension bệnh còn thiếu hoàn toàn
    # ─────────────────────────────────────────────────────────────
    ('headline','gout_control_need',       0.65,1.00,'{dish_name} — purine thấp, an toàn tuyệt đối cho người bị gout',1,'vi',None),
    ('headline','gout_control_need',       0.35,0.65,'{dish_name} — ít purine, nhẹ nhàng cho khớp và thận',2,'vi',None),
    ('headline','gout_control_need',       0.00,0.35,'{dish_name} — lựa chọn thân thiện, hạn chế nguy cơ gout tái phát',3,'vi',None),

    ('headline','sodium_control_need',     0.65,1.00,'{dish_name} — sodium siêu thấp, lý tưởng kiểm soát huyết áp',1,'vi',None),
    ('headline','sodium_control_need',     0.35,0.65,'{dish_name} — nhạt muối đúng cách, tốt cho tim và huyết áp',2,'vi',None),
    ('headline','sodium_control_need',     0.00,0.35,'{dish_name} — ít mặn, phù hợp người cần theo dõi huyết áp',3,'vi',None),

    ('headline','glycemic_control_need',   0.65,1.00,'{dish_name} — GL thấp, giúp đường huyết ổn định cả buổi',1,'vi',None),
    ('headline','glycemic_control_need',   0.35,0.65,'{dish_name} — hấp thụ chậm, không gây đột biến đường huyết',2,'vi',None),
    ('headline','glycemic_control_need',   0.00,0.35,'{dish_name} — chỉ số đường huyết an toàn cho người tiểu đường',3,'vi',None),

    ('headline','ibs_control_need',        0.65,1.00,'{dish_name} — dịu nhẹ, lý tưởng cho đường ruột nhạy cảm',1,'vi',None),
    ('headline','ibs_control_need',        0.35,0.65,'{dish_name} — dễ tiêu hoá, không kích thích ruột',2,'vi',None),
    ('headline','ibs_control_need',        0.00,0.35,'{dish_name} — thân thiện đường ruột, ăn thoải mái không lo khó chịu',3,'vi',None),

    ('headline','electrolyte_need',        0.65,1.00,'{dish_name} — bổ sung kali, natri và magie sau khi mất mồ hôi nhiều',1,'vi',None),
    ('headline','electrolyte_need',        0.35,0.65,'{dish_name} — cân bằng điện giải tự nhiên, phục hồi sức khoẻ nhanh',2,'vi',None),

    ('headline','cold_stress_index',       0.65,1.00,'{dish_name} — năng lượng dày dặn, giữ ấm cơ thể trong giá lạnh',1,'vi',None),
    ('headline','cold_stress_index',       0.35,0.65,'{dish_name} — ấm từ trong ra ngoài, chống chọi gió rét hiệu quả',2,'vi',None),

    ('headline','infection_risk',          0.35,0.55,'{dish_name} — tăng đề kháng tự nhiên, bảo vệ cơ thể lúc giao mùa',2,'vi',None),
    ('headline','infection_risk',          0.00,0.35,'{dish_name} — giàu vi chất giúp cơ thể khoẻ mạnh mỗi ngày',3,'vi',None),

    # Thêm P3 cho các dim đã có 2 variant
    ('headline','cooling_food_need',       0.00,0.35,'{dish_name} — thanh mát nhẹ nhàng, giúp cơ thể dễ chịu hơn',3,'vi',None),
    ('headline','warming_food_need',       0.00,0.35,'{dish_name} — bữa ăn ấm nóng, đúng điệu ngày se lạnh',3,'vi',None),
    ('headline','hydration_need',          0.00,0.35,'{dish_name} — giữ độ ẩm cơ thể, bổ sung nước qua từng bữa ăn',3,'vi',None),

    # ─────────────────────────────────────────────────────────────
    # WEATHER — bổ sung electrolyte_need (engine dùng nhưng thiếu hoàn toàn)
    # ─────────────────────────────────────────────────────────────
    ('weather','electrolyte_need',0.70,1.00,'Nhiệt độ {temperature}°C, đổ mồ hôi nhiều — cơ thể đang mất kali và natri nhanh, cần bổ sung điện giải gấp.',1,'vi',None),
    ('weather','electrolyte_need',0.45,0.70,'Trời {temperature}°C, hoạt động nhiều là mất điện giải — ưu tiên món giàu khoáng chất để phục hồi.',2,'vi',None),
    ('weather','electrolyte_need',0.20,0.45,'Hôm nay {temperature}°C — nhắc nhở bổ sung khoáng chất qua bữa ăn, đặc biệt nếu bạn vận động.',3,'vi',None),

    # Thêm variant cho các dim ít template
    ('weather','cold_stress_index',0.30,0.65,'Hôm nay se lạnh — bổ sung bữa ăn ấm và nhiều protein để cơ thể giữ nhiệt hiệu quả hơn.',3,'vi',None),
    ('weather','comfortable',     0.00,0.30,'Nhiệt độ {temperature}°C dễ chịu — ngày đẹp trời hợp để nấu bất cứ món nào bạn thích.',3,'vi',None),
    ('weather','rainy',           0.00,0.30,'Trời lất phất mưa — món ăn nóng hổi luôn là lựa chọn tuyệt vời cho ngày ẩm ướt.',3,'vi',None),

    ('weather','hydration_need',  0.00,0.20,'Dù hôm nay không quá nóng, cơ thể vẫn cần đủ nước — món ăn nhiều rau củ là cách bổ sung thông minh.',5,'vi',None),
    ('weather','cooling_food_need',0.20,0.35,'Hơi ấm hôm nay — chọn món thanh đạm giúp cơ thể không bị tích nhiệt.',4,'vi',None),
    ('weather','warming_food_need',0.20,0.30,'Se lạnh nhẹ — món ăn ấm giúp duy trì nhiệt độ cơ thể ổn định suốt ngày.',4,'vi',None),

    # ─────────────────────────────────────────────────────────────
    # SEASON — thêm P2/P3 cho các dim ít variant
    # ─────────────────────────────────────────────────────────────
    ('season','dry_season',   0.30,0.60,'{dish_name} phù hợp mùa khô — nguyên liệu dễ tìm, dễ bảo quản và vẫn ngon trong tiết hanh.',2,'vi',None),
    ('season','dry_season',   0.00,0.30,'{dish_name} giúp bù đắp độ ẩm trong mùa khô, nhất là khi ăn kèm nhiều nước hoặc canh.',3,'vi',None),

    ('season','north_winter', 0.35,0.60,'{dish_name} ấm bụng — đúng loại món miền Bắc hay nấu trong những ngày đông lạnh giá.',2,'vi',None),
    ('season','north_winter', 0.00,0.35,'{dish_name} đơn giản mà đủ chất, giúp trụ vững qua những ngày đông kéo dài ở miền Bắc.',3,'vi',None),

    ('season','south_dry',    0.35,0.60,'{dish_name} thanh mát, phù hợp khẩu vị nhẹ nhàng của người miền Nam trong mùa khô nóng.',2,'vi',None),
    ('season','south_dry',    0.00,0.35,'{dish_name} đơn giản và tươi mát — lựa chọn quen thuộc của người miền Nam khi nắng nóng.',3,'vi',None),

    ('season','tet_preparation',0.30,0.50,'{dish_name} thanh đạm — cân bằng lại sau những ngày Tết nhiều đạm và dầu mỡ.',3,'vi',None),

    ('season','autumn',        0.00,0.40,'{dish_name} nhẹ nhàng — hợp với tiết thu se lạnh, ăn không ngán khi trời bắt đầu vào đông.',3,'vi',None),

    # ─────────────────────────────────────────────────────────────
    # TAG — thêm variant 2 cho các dim chỉ có 1 (quan trọng nhất)
    # ─────────────────────────────────────────────────────────────
    ('tag','hydration_high',  0.65,1.00,'#GiàuNước',2,'vi',None),
    ('tag','hydration_high',  0.65,1.00,'#BổSungNước',3,'vi',None),
    ('tag','hydration_mid',   0.35,0.65,'#DưỡngẨm',2,'vi',None),

    ('tag','cooling_high',    0.65,1.00,'#ThanhNhiệt',2,'vi',None),
    ('tag','cooling_high',    0.65,1.00,'#HạNhiệt',3,'vi',None),
    ('tag','cooling_mid',     0.35,0.65,'#MátLành',2,'vi',None),

    ('tag','warming_high',    0.65,1.00,'#NóngHổi',2,'vi',None),
    ('tag','warming_high',    0.65,1.00,'#SưởiẤm',3,'vi',None),
    ('tag','warming_mid',     0.35,0.65,'#ẤmÁp',2,'vi',None),

    ('tag','immunity',        0.50,1.00,'#TăngCườngMiễnDịch',2,'vi',None),
    ('tag','immunity',        0.50,1.00,'#ChốngOxyHoá',3,'vi',None),

    ('tag','season_match',    0.65,1.00,'#ĐúngMùa',2,'vi',None),
    ('tag','season_match',    0.65,1.00,'#VàoMùa',3,'vi',None),

    ('tag','high_boost',      0.65,1.00,'#NấuNgay',2,'vi',None),
    ('tag','high_boost',      0.65,1.00,'#CóSẵnNguyênLiệu',3,'vi',None),

    ('tag','quick_cook',      0.00,1.00,'#Dưới20Phút',2,'vi',None),
    ('tag','quick_cook',      0.00,1.00,'#NấuLẹ',3,'vi',None),

    ('tag','low_sodium',      0.00,1.00,'#NhạtMuối',2,'vi',None),
    ('tag','low_sodium',      0.00,1.00,'#TốtHuyếtÁp',3,'vi',None),

    ('tag','low_gl',          0.00,1.00,'#GlucoseThấp',2,'vi',None),
    ('tag','low_gl',          0.00,1.00,'#AnToànĐườngHuyết',3,'vi',None),

    ('tag','vegan_tag',       0.00,1.00,'#ThuầnChay',2,'vi',None),
    ('tag','vegetarian_tag',  0.00,1.00,'#MonChay',2,'vi',None),

    ('tag','peak_season',     0.75,1.00,'#TươiNgon',2,'vi',None),
    ('tag','comfortable_weather',0.50,1.00,'#HômNayĐẹpTrời',2,'vi',None),
    ('tag','rainy_day',       0.50,1.00,'#MưaLàBếp',2,'vi',None),

    # ─────────────────────────────────────────────────────────────
    # INGREDIENT — thêm variant
    # ─────────────────────────────────────────────────────────────
    ('ingredient','boost_high',  0.80,1.00,'{ingredient_names} — đã có đủ! Chỉ cần mở tủ lạnh là xong.',3,'vi',None),
    ('ingredient','boost_medium',0.40,0.60,'{ingredient_names} đang trong tủ — bổ sung vài thứ nữa là nấu được ngay.',3,'vi',None),
    ('ingredient','boost_low',   0.10,0.20,'{ingredient_names} trong giỏ hàng có thể dùng được — tận dụng thay vì mua mới.',2,'vi',None),
]

def run():
    db = sqlite3.connect(DB)

    # Kiểm tra duplicate trước khi insert
    existing = set()
    for r in db.execute("SELECT context_type, trigger_dim, template_text FROM advice_templates").fetchall():
        existing.add((r[0], r[1], r[2][:60]))

    inserted = 0
    skipped  = 0
    for row in NEW_TEMPLATES:
        ctx, dim, imin, imax, text, pri, lang, notes = row
        key = (ctx, dim, text[:60])
        if key in existing:
            skipped += 1
            continue
        db.execute(
            "INSERT INTO advice_templates "
            "(context_type,trigger_dim,intensity_min,intensity_max,template_text,priority,lang,notes) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (ctx, dim, imin, imax, text, pri, lang, notes)
        )
        inserted += 1

    db.commit()

    # Báo cáo kết quả
    print(f"\n✅ Inserted: {inserted} | Skipped (duplicate): {skipped}")
    print("\n=== Summary sau khi patch ===")
    for r in db.execute(
        "SELECT context_type, trigger_dim, COUNT(*) as cnt "
        "FROM advice_templates "
        "GROUP BY context_type, trigger_dim "
        "ORDER BY context_type, trigger_dim"
    ).fetchall():
        flag = "⚠️ " if r[2] < 2 else ("✅ " if r[2] >= 3 else "🟡 ")
        print(f"  {flag}{r[0]:12} / {r[1]:30} → {r[2]} templates")

    total = db.execute("SELECT COUNT(*) FROM advice_templates").fetchone()[0]
    print(f"\nTOTAL: {total} templates")
    db.close()

if __name__ == '__main__':
    run()
