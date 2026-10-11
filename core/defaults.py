from typing import Dict

# 앱 버전. (오류 보고 메일의 제목에 들어갑니다. README 의 제목과 같이 올립니다)
APP_VERSION = "3.3.1"

# 단축키 기본값의 단일 출처. SyncManager(신규 설치 기본값)와 SettingsWindow(초기화 버튼/표시)가 함께 사용합니다.
DEFAULT_SHORTCUTS: Dict[str, str] = {
    "new_memo":            "Alt+N",       # 새 메모 생성 (전역)
    "new_code_memo":       "Alt+Shift+N", # 새 코드 메모 생성 (전역)
    "open_explorer":       "Alt+W",       # 탐색기 켜기/숨기기 (전역)
    "toggle_all_memos":    "Alt+H",       # 모든 메모 숨기기/보이기 (전역)
    "arrange_rolled_memos":"Alt+R",       # 접은 메모 정렬 (전역)
    "arrange_all_memos":   "Alt+A",       # 펼친 메모 정렬 (전역)
    "save":                "Ctrl+S",      # 메모 저장 (표준)
    "search":              "Ctrl+F",      # 검색 (표준)
    "replace":             "Ctrl+H",      # 찾아 바꾸기 (표준)
    "rename":              "F2",          # 제목 수정
    "toggle_rollup":       "Alt+M",       # 메모 창 접기/펼치기
    "toggle_pin":          "Alt+P",       # 항상 위에 고정
    "delete_memo":         "Alt+D",       # 메모 삭제
    "toggle_line_numbers": "Alt+G",       # 행번호 표시 토글
    "toggle_line_bg":      "Alt+B",       # 줄노트 배경 토글
    "toggle_fmt_bar":      "Alt+T",       # 서식 툴바 접기/열기
    "copy_all":            "Alt+C",       # 전체 내용 복사
    "eng_kor_convert":     "Alt+E",       # 한/영 오타 변환
    "format_code":         "Alt+F",       # 코드 자동 정렬
    "toggle_code_theme":   "Alt+L",       # 코드 테마 전환
    "open_all_memos":      "Alt+O",       # 전체 메모 열기
    "toggle_memo_lock":    "Ctrl+L",      # 암호 메모 잠그기 / 잠금 해제
    "set_memo_password":   "Ctrl+Shift+L",# 암호 걸기 / 암호 변경
    "quick_search":        "Alt+Q",       # 빠른 검색 창 (전역)
    "toggle_checklist":    "Alt+K",       # 체크리스트 켜기/끄기
    "set_reminder":        "Ctrl+R",      # 알림 설정
    "show_history":        "Ctrl+Shift+H",# 이전 내용 보기 / 되돌리기
}
