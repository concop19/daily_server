"""
protein_classifier.py — Phân loại nguồn đạm chính cho món ăn Việt Nam.
Nhóm đạm:
  - 'pork':      Thịt heo / lợn (ba chỉ, sườn, thịt băm, giò heo, tai heo, chả lụa...)
  - 'poultry':   Thịt gia cầm (gà, vịt, ngan, ngỗng...)
  - 'beef':      Thịt bò (thăn bò, bắp bò, nạm bò, bò viên, gân bò...)
  - 'seafood':   Thủy hải sản (tôm, cua, mực, cá, nghêu, sò, ốc, hến, chả cá, bạch tuộc...)
  - 'egg_tofu':  Trứng & Đậu (trứng gà, trứng vịt, trứng cút, đậu phụ, tàu hũ...)
  - 'other':     Rau củ, nấm, tinh bột, canh chay, thanh đạm...
"""

import unicodedata

def _normalize_str(s: str) -> str:
    if not s:
        return ""
    # Chuyển về lowercase và chuẩn hóa NFC
    return unicodedata.normalize('NFC', s.lower())

# Từ khóa định danh có độ ưu tiên cao trong Tên món ăn (Title)
_SEAFOOD_TITLE_KEYWORDS = [
    'tôm', 'mực', 'cua', 'cá ', 'cá,', 'nghêu', 'ngao', 'sò', 'ốc', 'hến',
    'bạch tuộc', 'chả cá', 'tép', 'hàu', 'mực nang', 'mực ống', 'cua đồng',
    'cá hồi', 'cá thu', 'cá basa', 'cá diêu hồng', 'cá chép', 'cá quả', 'cá lóc'
]

_PORK_TITLE_KEYWORDS = [
    'thịt heo', 'thịt lợn', 'ba chỉ', 'sườn heo', 'sườn non', 'sườn cốt lết',
    'giò heo', 'chân giò', 'thịt kho', 'thịt luộc', 'thịt rang', 'thịt băm',
    'xá xíu', 'tai heo', 'thịt nướng', 'chả lụa', 'giò lụa', 'nem rán', 'nem cuốn',
    'sườn xào', 'thịt xào', 'heo ', 'lợn ', 'sườn '
]

_POULTRY_TITLE_KEYWORDS = [
    'gà ', 'gà,', 'thịt gà', 'cánh gà', 'đùi gà', 'ức gà', 'gà ta', 'gà rang',
    'gà luộc', 'gà kho', 'gà xào', 'gà nướng', 'vịt ', 'thịt vịt', 'vịt om',
    'ngan', 'chim bồ câu'
]

_BEEF_TITLE_KEYWORDS = [
    'thịt bò', 'bắp bò', 'nạm bò', 'gân bò', 'bò viên', 'bò xào',
    'bò kho', 'bò lúc lắc', 'bò cuốn', 'bò nhúng', 'bò né', 'bò '
]

_EGG_TOFU_TITLE_KEYWORDS = [
    'trứng ', 'trứng,', 'trứng chiên', 'trứng rán', 'trứng hấp', 'trứng cuộn',
    'trứng ốp', 'đậu phụ', 'đậu hũ', 'tàu hũ'
]

def classify_dish_protein(dish: dict) -> str:
    """
    Xác định nhóm đạm chính của món ăn.
    Trả về: 'seafood' | 'pork' | 'poultry' | 'beef' | 'egg_tofu' | 'other'
    """
    title = _normalize_str(dish.get('title') or '')
    desc = _normalize_str(dish.get('description') or '')
    
    # Loại trừ "con bò cười" (phô mai) khỏi beef
    title_clean = title.replace('bò cười', '')
    desc_clean = desc.replace('bò cười', '')
    
    # 1. Ưu tiên kiểm tra trực tiếp trên Tên món ăn (Title)
    # Kiểm tra hải sản trước để các món như "Hàu nướng..." không bị nhầm
    if any(k in title_clean for k in _SEAFOOD_TITLE_KEYWORDS):
        return 'seafood'
    if any(k in title_clean for k in _POULTRY_TITLE_KEYWORDS):
        return 'poultry'
    if any(k in title_clean for k in _BEEF_TITLE_KEYWORDS):
        return 'beef'
    if any(k in title_clean for k in _PORK_TITLE_KEYWORDS):
        return 'pork'
    if any(k in title_clean for k in _EGG_TOFU_TITLE_KEYWORDS):
        return 'egg_tofu'
        
    # Trường hợp tên chung như "Thịt rim", "Thịt xào chua ngọt" -> mặc định là pork trong ẩm thực Việt
    if 'thịt ' in title and not any(k in title for k in ['thịt bò', 'thịt gà', 'thịt vịt']):
        return 'pork'

    # 2. Nếu Title không rõ, kiểm tra Description
    full_text = f"{title} {desc}"
    if any(k in full_text for k in ['thịt gà', 'cánh gà', 'đùi gà', 'thịt vịt']):
        return 'poultry'
    if any(k in full_text for k in ['thịt bò', 'bắp bò', 'gân bò', 'bò viên']):
        return 'beef'
    if any(k in full_text for k in ['thịt heo', 'thịt lợn', 'ba chỉ', 'sườn heo', 'giò heo', 'thịt băm', 'xương heo']):
        return 'pork'
    if any(k in full_text for k in ['tôm', 'mực', 'cua', 'cá ', 'nghêu', 'sò', 'ốc', 'hến', 'bạch tuộc', 'chả cá']):
        return 'seafood'
    if any(k in full_text for k in ['trứng gà', 'trứng vịt', 'đậu phụ', 'đậu hũ', 'tàu hũ']):
        return 'egg_tofu'

    return 'other'
