import ast
import re
import json
import html
from typing import Any

# ── 한/영 키보드 매핑 (crypto_utils에 원본이 있음, 여기서는 직접 사용) ──────────
KOR_CHO  = ['ㄱ','ㄲ','ㄴ','ㄷ','ㄸ','ㄹ','ㅁ','ㅂ','ㅃ','ㅅ','ㅆ','ㅇ','ㅈ','ㅉ','ㅊ','ㅋ','ㅌ','ㅍ','ㅎ']
KOR_JUNG = ['ㅏ','ㅐ','ㅑ','ㅒ','ㅓ','ㅔ','ㅕ','ㅖ','ㅗ','ㅘ','ㅙ','ㅚ','ㅛ','ㅜ','ㅝ','ㅞ','ㅟ','ㅠ','ㅡ','ㅢ','ㅣ']
KOR_JONG = ['','ㄱ','ㄲ','ㄳ','ㄴ','ㄵ','ㄶ','ㄷ','ㄹ','ㄺ','ㄻ','ㄼ','ㄽ','ㄾ','ㄿ','ㅀ','ㅁ','ㅂ','ㅄ','ㅅ','ㅆ','ㅇ','ㅈ','ㅊ','ㅋ','ㅌ','ㅍ','ㅎ']

ENG_KEY_MAP = {
    'q':'ㅂ','Q':'ㅃ','w':'ㅈ','W':'ㅉ','e':'ㄷ','E':'ㄸ','r':'ㄱ','R':'ㄲ','t':'ㅅ','T':'ㅆ',
    'y':'ㅛ','u':'ㅕ','i':'ㅑ','o':'ㅐ','O':'ㅒ','p':'ㅔ','P':'ㅖ','a':'ㅁ','s':'ㄴ','d':'ㅇ',
    'f':'ㄹ','g':'ㅎ','h':'ㅗ','j':'ㅓ','k':'ㅏ','l':'ㅣ','z':'ㅋ','x':'ㅌ','c':'ㅊ','v':'ㅍ',
    'b':'ㅠ','n':'ㅜ','m':'ㅡ'
}
KOR_KEY_MAP = {v: k for k, v in ENG_KEY_MAP.items()}


def eng_to_kor(text: str) -> str:
    """영타로 잘못 친 텍스트(예: dkssudgktpdy)를 한글(안녕하세요)로 조합 변환합니다."""
    res = []
    i = 0
    n = len(text)
    while i < n:
        c1 = text[i]
        if c1 not in ENG_KEY_MAP:
            res.append(c1)
            i += 1
            continue
        cho_char = ENG_KEY_MAP.get(c1, '')
        if cho_char in KOR_CHO and i + 1 < n and text[i+1] in ENG_KEY_MAP:
            jung_char = ENG_KEY_MAP.get(text[i+1], '')
            if jung_char in KOR_JUNG:
                cho_idx  = KOR_CHO.index(cho_char)
                jung_idx = KOR_JUNG.index(jung_char)
                jong_idx = 0
                advance  = 2
                if i + 2 < n and text[i+2] in ENG_KEY_MAP:
                    jong_char1 = ENG_KEY_MAP.get(text[i+2], '')
                    if i + 3 < n and text[i+3] in ENG_KEY_MAP and ENG_KEY_MAP.get(text[i+3], '') in KOR_JUNG:
                        jong_idx = 0
                    elif jong_char1 in KOR_JONG:
                        jong_idx = KOR_JONG.index(jong_char1)
                        advance  = 3
                syllable = chr(0xAC00 + (cho_idx * 588) + (jung_idx * 28) + jong_idx)
                res.append(syllable)
                i += advance
                continue
        res.append(cho_char)
        i += 1
    return "".join(res)


def kor_to_eng(text: str) -> str:
    """한글 텍스트(예: 믐믐믐)를 영타(aaa)로 역변환합니다."""
    res = []
    for ch in text:
        code = ord(ch)
        if 0xAC00 <= code <= 0xD7A3:
            s_idx    = code - 0xAC00
            cho_idx  = s_idx // 588
            jung_idx = (s_idx % 588) // 28
            jong_idx = s_idx % 28
            res.append(KOR_KEY_MAP.get(KOR_CHO[cho_idx], ''))
            res.append(KOR_KEY_MAP.get(KOR_JUNG[jung_idx], ''))
            if jong_idx > 0:
                res.append(KOR_KEY_MAP.get(KOR_JONG[jong_idx], ''))
        elif ch in KOR_KEY_MAP:
            res.append(KOR_KEY_MAP[ch])
        else:
            res.append(ch)
    return "".join(res)


def convert_eng_kor_smart(text: str) -> str:
    """한글/영문 비율을 분석하여 자동으로 변환 방향을 결정합니다."""
    if not text:
        return ""
    kor_count = len(re.findall(r'[\uac00-\ud7a3]', text))
    eng_count = len(re.findall(r'[a-zA-Z]', text))
    return eng_to_kor(text) if eng_count >= kor_count else kor_to_eng(text)


def clean_plain_text(content: Any) -> str:
    """HTML 및 Qt 내부 <style>...</style> 태그, 딕셔너리 래퍼를 완전히 제거하고 순수 본문 텍스트만 추출합니다."""
    if not content:
        return ""
    if isinstance(content, dict):
        content = content.get('content', '')
    content_str = str(content)
    if content_str.startswith("{") and "'is_encrypted'" in content_str:
        try:
            d = ast.literal_eval(content_str)
            if isinstance(d, dict) and 'content' in d:
                content_str = str(d['content'])
        except Exception:
            pass
    elif content_str.startswith("{") and '"is_encrypted"' in content_str:
        try:
            d = json.loads(content_str)
            if isinstance(d, dict) and 'content' in d:
                content_str = str(d['content'])
        except Exception:
            pass

    no_style  = re.sub(r'<style[^>]*>.*?</style>', '', content_str, flags=re.DOTALL | re.IGNORECASE)
    no_script = re.sub(r'<script[^>]*>.*?</script>', '', no_style, flags=re.DOTALL | re.IGNORECASE)
    plain     = re.sub(r'<[^>]+>', '', no_script).strip()
    return html.unescape(plain)