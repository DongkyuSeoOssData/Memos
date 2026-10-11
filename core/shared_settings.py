"""여러 기기가 함께 쓰는 설정.

환경설정 가운데 '어느 기기에서나 같아야 자연스러운 것'만 골라 드라이브의 한 파일(_settings.json)로 주고받습니다.
그 PC에만 맞는 값(메모 폴더 경로, 창 위치·크기, 자동 실행, 동기화 주소와 접근 암호 등)은 넣지 않습니다.
 - 메모 폴더 경로·창 크기는 PC마다 다르고,
 - 동기화 주소와 접근 암호는 그것이 있어야 이 파일을 받을 수 있으므로 공유할 수 없습니다.

드라이브의 파일 모양: {"updated_at": "<마지막으로 바꾼 시각>", "settings": {<공유하는 설정들>}}
더 나중에 바꾼 쪽의 설정이 이깁니다.
"""
import json
from typing import Any, Dict

# 드라이브에 올리는 파일 이름. '_'로 시작해 메모 파일({id}.json)과 구분됩니다.
SETTINGS_FILE = "_settings.json"
# 공유 설정을 마지막으로 바꾼 시각을 적어 두는 설정 키
STAMP_KEY = "settings_updated_at"

SHARED_KEYS = frozenset({
    # 화면
    "app_theme", "light_theme_mode", "dark_theme_mode", "ui_style", "folder_ui",
    # 폴더 목록과 순서
    "folders",
    # 새 메모 기본값
    "default_memo_color", "default_font_family", "default_code_font_family", "default_font_size",
    "default_code_lang", "default_code_theme", "default_is_pinned", "default_memo_opacity",
    "default_memo_width", "default_memo_height", "default_code_memo_width", "default_code_memo_height",
    "default_rolled_height", "default_gen_line_numbers", "default_gen_line_bg",
    "default_code_line_numbers", "default_code_line_bg", "default_show_line_numbers", "default_show_line_bg",
    # 동작
    "auto_eng_kor_convert", "auto_save_idle_sec", "locked_memo_relock_min", "trash_auto_delete_days",
    "reminder_quick_minutes",
    "sync_interval_index", "shortcuts",
})


# 값의 형식. 여기에 없는 공유 설정은 글자입니다. 드라이브에서 받은 값이 이 형식이 아니면 버립니다.
_BOOL_KEYS = frozenset({
    "default_is_pinned", "default_gen_line_numbers", "default_gen_line_bg", "default_code_line_numbers",
    "default_code_line_bg", "default_show_line_numbers", "default_show_line_bg", "auto_eng_kor_convert",
})
_NUMBER_KEYS = frozenset({
    "default_font_size", "default_memo_opacity", "default_memo_width", "default_memo_height",
    "default_code_memo_width", "default_code_memo_height", "default_rolled_height", "auto_save_idle_sec",
    "locked_memo_relock_min", "trash_auto_delete_days", "sync_interval_index",
})
_LIST_KEYS = frozenset({"folders", "reminder_quick_minutes"})
_DICT_KEYS = frozenset({"shortcuts"})


def well_formed(key: str, value: Any) -> bool:
    """공유 설정의 값이 그 설정에 맞는 형식인지."""
    if key in _BOOL_KEYS:
        return isinstance(value, bool)
    if key in _NUMBER_KEYS:
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if key in _LIST_KEYS:
        return isinstance(value, list)
    if key in _DICT_KEYS:
        return isinstance(value, dict)
    return isinstance(value, str)


def shared_subset(settings: Dict[str, Any]) -> Dict[str, Any]:
    return {k: settings[k] for k in sorted(SHARED_KEYS) if k in settings}


def fingerprint(settings: Dict[str, Any]) -> str:
    """공유 설정이 바뀌었는지 비교하기 위한 값."""
    return json.dumps(shared_subset(settings), ensure_ascii=False, sort_keys=True)


def from_remote(remote: Any) -> Dict[str, Any]:
    """드라이브에서 받은 내용 중 공유하기로 한 설정만 골라냅니다.

    모르는 키나 기기별 설정이 섞여 와도 무시하고, 형식이 맞지 않는 값(숫자 자리에 글자 등)도 버립니다.
    """
    settings = remote.get("settings") if isinstance(remote, dict) else None
    if not isinstance(settings, dict):
        return {}
    return {k: v for k, v in settings.items() if k in SHARED_KEYS and well_formed(k, v)}
