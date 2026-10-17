"""환경설정의 '단축키' 탭: 단축키 표, 기본값으로 되돌리기, 겹치는 단축키 정리.

(SettingsWindow 에 섞어 쓰는 부분)
"""
from typing import Any
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QCheckBox, QTableWidget, QTableWidgetItem, QHeaderView, QKeySequenceEdit
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QKeySequence


class ShortcutTabMixin:
    """환경설정의 단축키 탭."""

    # (기능명, settings key, 설명/비고)
    SHORTCUT_ROWS = [
        # ── 전역 단축키 (기본: 어디서나 작동. 환경설정에서 '이 앱의 창이 앞에 있을 때만'으로 바꿀 수 있음) ──
        ("새 메모 생성",               "new_memo",             "어디서나 작동하는 전역 단축키"),
        ("새 코드 메모 생성",           "new_code_memo",        "어디서나 작동하는 전역 단축키"),
        ("메모 탐색기 켜기/숨기기",     "open_explorer",        "탐색기가 보이면 숨기고, 숨어있으면 열기"),
        ("모든 메모 숨기기/보이기",     "toggle_all_memos",     "어디서나 작동하는 전역 단축키"),
        ("접은 메모 정렬",             "arrange_rolled_memos", "접힌 메모 전부 화면 아래 정렬"),
        ("메모 전체 정렬",             "arrange_all_memos",    "펼친 메모 전부 계단식 정렬"),
        ("빠른 검색 창",               "quick_search",         "어디서나 검색 창을 띄워 메모를 찾아 엽니다"),
        # ── 메모 창 내 단축키 (포커스 필요) ─────────────────────────────────
        ("메모 저장",                 "save",                 "수동 저장 (표준 Ctrl+S 유지 권장)"),
        ("검색",                      "search",               "메모 내용 검색 (표준 Ctrl+F 유지 권장)"),
        ("찾아 바꾸기",               "replace",              "찾아 바꾸기 창 열기 (표준 Ctrl+H)"),
        ("제목 수정",                 "rename",               "제목 편집 모드 진입 (F2)"),
        ("메모 창 접기/펼치기",        "toggle_rollup",        "현재 메모를 접거나 펼침"),
        ("위치 고정/풀기",             "pin_position",         "접은 메모는 접은 위치, 펼친 메모는 펼친 위치를 고정"),
        ("화면 항상 고정(Pin) 토글",   "toggle_pin",           "다른 창 위에 항상 표시"),
        ("현재 메모 삭제",            "delete_memo",          "현재 포커스된 메모 삭제"),
        ("행번호 표시 토글",           "toggle_line_numbers",  "행 번호 영역 켜기/끄기"),
        ("줄노트 배경 토글",           "toggle_line_bg",       "줄노트 줄무늬 배경 켜기/끄기"),
        ("서식 툴바 접기/열기",        "toggle_fmt_bar",       "하단 서식 도구모음 토글"),
        ("전체 메모 내용 복사",        "copy_all",             "메모 전체 내용을 클립보드로"),
        ("한/영 영타 오타 변환",       "eng_kor_convert",      "영어로 입력된 한글 오타 변환"),
        ("코드 자동 정렬 (Prettify)",  "format_code",          "코드 메모 전용"),
        ("코드 테마 전환",             "toggle_code_theme",    "코드 메모 다크/라이트 전환"),
        ("메모 열기 (폴더 골라서)",    "open_all_memos",       "폴더를 골라 그 폴더의 메모를 엶 (전체 가능, 한 번에 100개까지)"),
        # ── 암호 메모 (메모 창 / 탐색기에서 선택한 메모) ─────────────────────
        ("암호 메모 잠그기/잠금 해제",  "toggle_memo_lock",     "열려 있으면 잠그고, 잠겨 있으면 암호 입력"),
        ("메모 암호 걸기/변경",        "set_memo_password",    "일반 메모에 암호 설정, 암호 메모는 암호 변경"),
        # ── 체크리스트 · 알림 · 변경 기록 ─────────────────────────────────────
        ("체크리스트 켜기/끄기",       "toggle_checklist",     "선택한 줄 앞에 체크 상자(☐)를 붙이거나 뗌"),
        ("알림 설정",                 "set_reminder",         "날짜·시간·반복(크론식)을 정해 알림을 겁니다"),
        ("이전 내용 보기",            "show_history",         "저장되기 전의 내용을 보고 되돌립니다"),
    ]

    def _build_shortcut_tab(self) -> None:
        """'단축키 설정' 탭: 전역 단축키 범위와 단축키 표."""
        tab_shortcuts = QWidget()
        l_sc = QVBoxLayout(tab_shortcuts)
        l_sc.setContentsMargins(15, 15, 15, 15)
        l_sc.setSpacing(8)

        # 헤더 설명 + 초기화 버튼 한 줄 배치
        sc_header_row = QHBoxLayout()
        sc_header_label = QLabel(
            "<b>단축키 설정</b><br/>"
            "<span style='font-size:8.5pt; color:#8E8E93;'>"
            "원하는 기능을 클릭하여 단축키를 즉시 조합 변경하세요. "
            "충돌 방지를 위해 기본값은 Alt 조합입니다."
            "</span>"
        )
        sc_header_label.setWordWrap(True)
        sc_header_row.addWidget(sc_header_label, 1)

        # 단축키 초기화 버튼: 클릭하면 모든 단축키를 기본 Alt 조합으로 복원
        self.btn_reset_shortcuts = QPushButton("  단축키 초기화")
        self.btn_reset_shortcuts.setFixedHeight(36)
        self.btn_reset_shortcuts.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_reset_shortcuts.setToolTip(
            "모든 단축키를 기본 Alt 조합값으로 초기화합니다.\n"
            "저장 버튼을 눌러야 실제로 적용됩니다."
        )
        self.btn_reset_shortcuts.clicked.connect(self._reset_shortcuts_to_default)
        sc_header_row.addWidget(self.btn_reset_shortcuts)
        l_sc.addLayout(sc_header_row)

        # 위쪽 여섯 개(새 메모·탐색기 등)를 다른 프로그램을 쓰는 중에도 받을지
        self.cb_global_hotkeys = QCheckBox("다른 프로그램을 쓰는 중에도 단축키 받기 (전역 단축키)")
        self.cb_global_hotkeys.setToolTip("새 메모 · 탐색기 열기 · 모두 숨기기 · 정렬 · 빠른 검색 단축키에 적용됩니다")
        l_sc.addWidget(self.cb_global_hotkeys)
        global_hint = QLabel("켜면 어디서나 동작하지만, 그 조합은 이 앱만 받아 다른 프로그램에서는 쓸 수 없습니다. "
                             "끄면 메모 탐색기나 메모 창이 앞에 있을 때만 동작하고, 다른 프로그램은 그 조합을 그대로 씁니다.")
        global_hint.setProperty("role", "hint")
        global_hint.setWordWrap(True)
        l_sc.addWidget(global_hint)

        # 3열: 기능 / 단축키 / 설명
        self.shortcut_table = QTableWidget(0, 3)
        self.shortcut_table.setHorizontalHeaderLabels(["기능", "단축키", "설명 / 비고"])
        h = self.shortcut_table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.shortcut_table.setColumnWidth(1, 160)
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        l_sc.addWidget(self.shortcut_table)

        # 단축키 탭은 테이블 자체가 스크롤을 지원하므로 탭 위젯에 직접 추가
        self.tabs.addTab(tab_shortcuts, "단축키 설정")

    def _reset_shortcuts_to_default(self) -> None:
        """단축키 테이블을 DEFAULT_SHORTCUTS 기본값으로 초기화합니다.

        이 메서드는 UI만 변경하며, 실제 적용은 저장 버튼을 눌러야 합니다.
        """
        self._fill_shortcut_table(self.DEFAULT_SHORTCUTS)
        self._refresh_dirty()
        self.show_toast("기본값으로 되돌림 · 저장해야 적용")

    def _resolve_shortcut_conflict(self, edited: Any) -> list:
        """방금 정한 단축키를 다른 기능이 쓰고 있었으면 그쪽을 비우고 알립니다. (같은 단축키를 두 기능에 걸 수 없음)

        비운 기능의 이름들을 돌려줍니다.
        """
        sequence = edited.keySequence().toString()
        if not sequence:
            return []
        cleared = []
        for r in range(self.shortcut_table.rowCount()):
            other = self.shortcut_table.cellWidget(r, 1)
            if other is not None and other is not edited and other.keySequence().toString().lower() == sequence.lower():
                other.clear()
                cleared.append(str(other.property("shortcut_label")))
        if cleared:
            self.show_toast(f"'{sequence}' 겹침 → '{', '.join(cleared)}' 단축키를 비웠습니다", warn=True)
        return cleared

    def _fill_shortcut_table(self, sc_map: dict) -> None:
        """단축키 테이블을 sc_map 기반으로 채웁니다. DEFAULT_SHORTCUTS를 fallback으로 사용합니다."""
        self.shortcut_table.setRowCount(0)
        for label_text, key, desc_text in self.SHORTCUT_ROWS:
            r = self.shortcut_table.rowCount()
            self.shortcut_table.insertRow(r)

            name_item = QTableWidgetItem(label_text)
            name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            name_item.setData(Qt.ItemDataRole.UserRole, key)
            self.shortcut_table.setItem(r, 0, name_item)

            k_edit = QKeySequenceEdit(QKeySequence(sc_map.get(key, self.DEFAULT_SHORTCUTS[key])))
            k_edit.setProperty("shortcut_key", key)
            k_edit.setProperty("shortcut_label", label_text)
            k_edit.editingFinished.connect(lambda edit=k_edit: self._resolve_shortcut_conflict(edit))
            k_edit.keySequenceChanged.connect(self._refresh_dirty)
            self.shortcut_table.setCellWidget(r, 1, k_edit)

            desc_item = QTableWidgetItem(desc_text)
            desc_item.setFlags(desc_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            desc_item.setForeground(QColor("#8E8E93"))
            self.shortcut_table.setItem(r, 2, desc_item)
