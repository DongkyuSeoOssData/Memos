from ui.memo_editor import MemoTextEdit, CodeHighlighter
from ui.themes import memo_palette
from ui import modern_style
from ui.wheel_guard import guard_wheel
from ui import screen_bounds
from core import reminders
from ui import checklist, memo_geometry
from ui.reminder_ui import ask_reminder
from ui.dialogs import pick_history
from ui.side_panel import SidePanel
from ui.lock_overlay import LockOverlay
from ui.memo_lock import MemoLockMixin
from ui.memo_format import MemoFormatMixin
import re
import datetime
import json
from typing import Dict, Any, Optional
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLineEdit, QMenu, QApplication,
    QLabel, QComboBox, QSizeGrip, QFontComboBox, QSlider, QCompleter,
    QWidgetAction
)
from PyQt6.QtCore import Qt, QPoint, QRect, QTimer, QEvent
from PyQt6.QtGui import (
    QColor, QShortcut, QKeySequence, QFont, QTextCursor, QTextCharFormat, QIntValidator,
    QPalette, QTextDocument, QCursor
)
from utils.text_utils import convert_eng_kor_smart
from utils.text_utils import clean_plain_text, is_html_content

class MemoWindow(MemoLockMixin, MemoFormatMixin, QWidget):
    """
    개별 메모장 창 클래스:
    - 옵션 2: 애플 모던 사이버/네온 핀 뱃지 (📍 / 📌)
    - 윈도우 스타일 우상단 제어 버튼 (─ 최소화 / □ 최대화 / ✕ 닫기)
    - 100% 정상 작동하는 최대화/복원 (toggle_maximize)
    - 기본 100% 불투명 솔리드 상태 (opacity: 1.0)
    """
    def __init__(self, m: Dict[str, Any], sc: Any, dc: Any, rc: Any, cc: Any) -> None:
        super().__init__()
        self.memo_data = m
        self.save_callback = sc
        self.delete_callback = dc
        self.rename_callback = rc
        self.close_callback = cc
        self.ui_manager = getattr(cc, '__self__', None)
        self._old_pos: Optional[QPoint] = None
        self._is_updating_from_explorer: bool = False
        self._is_rolled_up: bool = m.get('is_rolled_up', False)
        self._normal_height: int = m.get('height', 400)

        self._auto_save_timer = QTimer(self)
        self._auto_save_timer.setSingleShot(True)
        self._auto_save_timer.timeout.connect(self.execute_auto_save)
        self._dirty_since: Optional[float] = None

        # 암호 메모: 마지막 입력 후 일정 시간이 지나면 다시 잠급니다.
        self._relock_timer = QTimer(self)
        self._relock_timer.setSingleShot(True)
        self._relock_timer.timeout.connect(self.lock_now)

        self.highlighter: Optional[CodeHighlighter] = None

        self.toast_label = QLabel(self)
        self.toast_label.hide()
        self.toast_timer = QTimer(self)
        self.toast_timer.setSingleShot(True)
        self.toast_timer.timeout.connect(self.toast_label.hide)

        self.setup_ui()
        self.apply_data()
        self.bind_shortcuts()

        self.setMouseTracking(True)
        self.text_edit.setMouseTracking(True)
        self.text_edit.cursorPositionChanged.connect(self.update_toolbar_button_states)

        self._is_deleting = False
        self._title_save_timer = QTimer(self)
        self._title_save_timer.setSingleShot(True)
        self._title_save_timer.timeout.connect(self._do_title_save)

        self._wheel_save_timer = QTimer(self)
        self._wheel_save_timer.setSingleShot(True)
        self._wheel_save_timer.timeout.connect(lambda: self.save_callback(self.memo_data))

    def bind_shortcuts(self) -> None:
        # 기존 QShortcut 키를 비워 무력화 (rebind 시 중복 등록 방지)
        for _sc in self.findChildren(QShortcut):
            _sc.setEnabled(False)
            _sc.setKey(QKeySequence())
            _sc.deleteLater()

        s_cfg = self.memo_window_get_settings().get("shortcuts", {})

        QShortcut(QKeySequence(s_cfg.get("save", "Ctrl+S")), self).activated.connect(self.manual_save)
        QShortcut(QKeySequence(s_cfg.get("search", "Ctrl+F")), self).activated.connect(self.show_search_only)
        QShortcut(QKeySequence(s_cfg.get("replace", "Ctrl+H")), self).activated.connect(self.show_search_and_replace)
        QShortcut(QKeySequence(s_cfg.get("rename", "F2")), self).activated.connect(self.enable_rename)
        QShortcut(QKeySequence(s_cfg.get("eng_kor_convert", "Alt+E")), self).activated.connect(self.convert_selected_eng_kor)
        QShortcut(QKeySequence(s_cfg.get("toggle_fmt_bar", "Alt+T")), self).activated.connect(self.toggle_sub_fmt_panel)
        QShortcut(QKeySequence(s_cfg.get("copy_all", "Alt+C")), self).activated.connect(self.copy_all_content)
        QShortcut(QKeySequence(s_cfg.get("format_code", "Alt+F")), self).activated.connect(self.prettify_code)

        QShortcut(QKeySequence(s_cfg.get("toggle_pin", "Alt+P")), self).activated.connect(self.toggle_pin)
        QShortcut(QKeySequence(s_cfg.get("toggle_rollup", "Alt+M")), self).activated.connect(self.toggle_rollup)
        QShortcut(QKeySequence(s_cfg.get("delete_memo", "Alt+D")), self).activated.connect(lambda: self.delete_callback(self))
        QShortcut(QKeySequence(s_cfg.get("toggle_code_theme", "Alt+L")), self).activated.connect(self.toggle_code_theme)
        QShortcut(QKeySequence(s_cfg.get("toggle_line_numbers", "Alt+G")), self).activated.connect(self.toggle_line_numbers)
        QShortcut(QKeySequence(s_cfg.get("toggle_line_bg",      "Alt+B")), self).activated.connect(self.toggle_line_bg)

        if getattr(self, 'ui_manager', None):
            # 글로벌 단축키(keyboard 훅)와 중복 방지를 위해 로컬 QShortcut에서는 제외함
            # open_all_memos는 전역 단축키가 아니므로 로컬로 유지
            QShortcut(QKeySequence(s_cfg.get("open_all_memos", "Alt+O")), self).activated.connect(self.ui_manager.open_all_memos)

        QShortcut(QKeySequence(s_cfg.get("toggle_memo_lock", "Ctrl+L")), self).activated.connect(self.toggle_memo_lock)
        QShortcut(QKeySequence(s_cfg.get("set_memo_password", "Ctrl+Shift+L")), self).activated.connect(self.set_memo_password)
        QShortcut(QKeySequence(s_cfg.get("toggle_checklist", "Alt+K")), self).activated.connect(self.toggle_checklist)
        QShortcut(QKeySequence(s_cfg.get("set_reminder", "Ctrl+R")), self).activated.connect(self.edit_reminder)
        QShortcut(QKeySequence(s_cfg.get("show_history", "Ctrl+Shift+H")), self).activated.connect(self.show_history)

        QShortcut(QKeySequence("Esc"), self).activated.connect(self.close)

    def rebind_shortcuts(self) -> None:
        """설정 변경 후 단축키를 새 설정으로 재등록합니다."""
        self.bind_shortcuts()

    def memo_window_get_settings(self) -> Dict[str, Any]:
        return self.ui_manager.sync_manager.settings if getattr(self, 'ui_manager', None) else {}

    def memo_bg_color(self) -> str:
        """일반 메모의 바탕색."""
        bg_color = self.memo_data.get('bg_color', '#FFFFFF')
        return '#FFFFFF' if bg_color == 'random' else bg_color

    def is_dark_bg(self) -> bool:
        """메모 바탕이 어두운지 여부. (글자·아이콘을 밝게 그려야 하는지)"""
        if self.memo_data.get('is_code_memo', False):
            return self.memo_data.get('code_theme', 'dark') == 'dark'
        color = QColor(self.memo_bg_color())
        if not color.isValid():
            return False
        return (0.299 * color.red() + 0.587 * color.green() + 0.114 * color.blue()) / 255.0 < 0.5

    def _memo_theme_palette(self) -> Dict[str, Any]:
        return memo_palette(self.is_dark_bg())

    def show_toast(self, text: str, warn: bool = False) -> None:
        self.toast_label.setText(("⚠ " + text) if warn else text)
        self.toast_label.adjustSize()
        x = self.width() - self.toast_label.width() - 15
        y = self.height() - (self.fmt_bar.geometry().height() if hasattr(self, 'fmt_bar') else 35) - self.toast_label.height() - 20
        self.toast_label.move(max(10, x), max(10, y))
        self.toast_label.show()
        self.toast_label.raise_()
        self.toast_timer.start(3000 if warn else 1500)

    def toggle_line_numbers(self) -> None:
        self.memo_data['show_line_numbers'] = not self.memo_data.get('show_line_numbers', False)
        self.text_edit.update_line_number_area()
        self.save_callback(self.memo_data)

    def toggle_line_bg(self) -> None:
        self.memo_data['show_line_bg'] = not self.memo_data.get('show_line_bg', False)
        self.text_edit.viewport().update()
        self.save_callback(self.memo_data)

    def apply_line_bg_style(self) -> None:
        """본문 편집기의 글자색·글꼴·스크롤바."""
        is_dark_bg = self.is_dark_bg()
        text_color = "#F2F2F7" if is_dark_bg else "#1C1C1E"
        font_fam = "'D2Coding'" if self.memo_data.get('is_code_memo', False) else modern_style.MONO_FONT
        self.text_edit.setStyleSheet(
            f"QTextEdit {{ border:none; background: transparent; color:{text_color}; "
            f"font-family: {font_fam}; font-size: {self.memo_data.get('font_size', 11)}pt; }}"
            + modern_style.scrollbars(is_dark_bg)
        )

    def setup_ui(self) -> None:
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.window_layout = QVBoxLayout(self)
        self.window_layout.setContentsMargins(6, 6, 6, 6)

        self.bg = QWidget()
        self.bg.setObjectName("MemoBackground")
        self.bg_layout = QVBoxLayout(self.bg)
        bg_l = self.bg_layout
        self.bg_layout.setContentsMargins(14, 10, 14, 14)
        self.window_layout.addWidget(self.bg)

        ctrl = QHBoxLayout()
        ctrl.setSpacing(6)

        # 📌 제목 레이블 (압정 영역 직전까지 확장)
        self.title_edit = QLineEdit()
        self.title_edit.setReadOnly(True)
        self.title_edit.editingFinished.connect(self.handle_rename)
        self.title_edit.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.title_edit.customContextMenuRequested.connect(self.show_menu)
        self.title_edit.installEventFilter(self)
        # 다른 칸이 닫히며 포커스가 넘어와 제목 전체가 선택된 것처럼 보이지 않도록, 직접 눌렀을 때만 포커스를 받습니다.
        self.title_edit.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        ctrl.addWidget(self.title_edit, 1)

        # 접어 둔 암호 메모임을 알리는 자물쇠. 제목 칸 안의 왼쪽 끝에 얹어, 한눈에 구분되게 합니다.
        # (접힌 상태에서는 본문 자리의 암호 칸이 보이지 않으므로)
        # 제목 줄의 배치에 끼워 넣지 않는 이유: 끼워 넣으면 제목 줄에 필요한 최소 너비가 늘어나, 좁게 접어 둔 메모가
        # 암호를 거는 순간 옆으로 늘어납니다. 제목 칸의 최소 너비도 지금 값으로 고정해, 자물쇠 자리를 비워도 늘지 않게 합니다.
        self.title_edit.setMinimumWidth(self.title_edit.minimumSizeHint().width())
        self.lbl_lock = QLabel("🔒", self.title_edit)
        self.lbl_lock.setToolTip("암호 메모")
        self.lbl_lock.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.lbl_lock.hide()

        self.btn_code_theme = QPushButton("")
        self.btn_code_theme.setFixedSize(90, 24)

        self.btn_code_theme.clicked.connect(self.toggle_code_theme)
        self.btn_code_theme.hide()

        self.code_lang_box = QComboBox()
        self.code_lang_box.addItems(["JSON", "C#", "VB.NET", "Power Automate", "PowerShell", "Batch (CMD)", "SQL", "Markdown", "Python", "JavaScript", "HTML", "CSS", "C++", "Java", "Plain Text"])
        self.code_lang_box.setFixedHeight(24)
        self.code_lang_box.currentTextChanged.connect(self.on_code_lang_changed)
        self.code_lang_box.hide()

        # 언어 선택 아이콘 버튼 (language.svg) - 콤보박스와 함께 표시
        self.btn_lang_icon = QPushButton("")
        self.btn_lang_icon.setFixedSize(24, 24)
        self.btn_lang_icon.setEnabled(False)  # 클릭 불가, 아이콘 표시 전용
        self.btn_lang_icon.setStyleSheet("QPushButton { background: transparent; border: none; }")
        self.btn_lang_icon.hide()

        ctrl.addWidget(self.btn_code_theme)
        ctrl.addWidget(self.btn_lang_icon)
        ctrl.addWidget(self.code_lang_box)
        ctrl.addStretch()

        # 체크리스트 진행 표시 (끝낸 일/전체). 접어 둔 메모에서도 남은 일이 보입니다.
        self.lbl_progress = QLabel("")
        self.lbl_progress.setToolTip("체크리스트: 끝낸 일 / 전체")
        self.lbl_progress.hide()
        ctrl.addWidget(self.lbl_progress)

        # 핀 버튼
        self.btn_pin = QPushButton("")
        self.btn_pin.setFixedSize(28, 26)
        self.btn_pin.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_pin.setToolTip("화면 고정 토글 (Ctrl+P)")
        self.btn_pin.clicked.connect(self.toggle_pin)
        ctrl.addWidget(self.btn_pin)

        self.btn_min   = QPushButton("")
        self.btn_max   = QPushButton("")
        self.btn_close = QPushButton("")

        for b_item, tip in [(self.btn_min, "최소화/접기 (Ctrl+M)"), (self.btn_max, "최대화"), (self.btn_close, "닫기 (Esc)")]:
            b_item.setFixedSize(28, 26)
            b_item.setCursor(Qt.CursorShape.PointingHandCursor)
            b_item.setToolTip(tip)
            ctrl.addWidget(b_item)

        self.btn_min.clicked.connect(self.toggle_rollup)
        self.btn_max.clicked.connect(self.toggle_maximize)
        self.btn_close.clicked.connect(self.close)

        bg_l.addLayout(ctrl)

        self.content_container = QWidget()
        cc_layout = QVBoxLayout(self.content_container)
        cc_layout.setContentsMargins(0, 0, 0, 0)

        self.text_edit = MemoTextEdit(self)
        self.text_edit.setStyleSheet("border:none; background:transparent;")
        self.text_edit.textChanged.connect(self.update_content)
        # 암호를 물을 때 본문을 가리고 그 위에 입력 칸을 보여 주는 가림막 (잠긴 메모는 평소에도 덮여 있음)
        self.lock_overlay = LockOverlay(self)
        self.text_edit.textChanged.connect(self.refresh_progress)
        self.text_edit.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.text_edit.customContextMenuRequested.connect(self.show_menu)
        self.text_edit.installEventFilter(self)

        self.toast = QLabel("")
        self.toast.setStyleSheet("color: #0A84FF; font-weight: bold; font-size: 10pt;")
        self.toast.hide()

        cc_layout.addWidget(self.toast, alignment=Qt.AlignmentFlag.AlignCenter)
        cc_layout.addWidget(self.text_edit)

        self.search_bar = QWidget()
        sl = QHBoxLayout(self.search_bar)
        sl.setContentsMargins(0, 4, 0, 4)

        self.s_in = QLineEdit()
        self.s_in.setPlaceholderText("찾을 단어")
        self.s_in.returnPressed.connect(lambda: self.do_find(backward=False))

        self.s_count = QLabel("0/0")

        self.s_prev_btn = QPushButton("▲")
        self.s_prev_btn.setFixedSize(24, 24)
        self.s_prev_btn.clicked.connect(lambda: self.do_find(backward=True))

        self.s_next_btn = QPushButton("▼")
        self.s_next_btn.setFixedSize(24, 24)
        self.s_next_btn.clicked.connect(lambda: self.do_find(backward=False))

        self.r_in = QLineEdit()
        self.r_in.setPlaceholderText("바꿀 단어")
        self.r_in.returnPressed.connect(self.do_replace)

        self.r_btn = QPushButton("바꾸기")
        self.r_btn.clicked.connect(self.do_replace)

        self.s_close = QPushButton("")
        self.s_close.setFixedSize(24, 24)
        self.s_close.setStyleSheet("border:none; background:transparent;")
        if getattr(self, 'ui_manager', None) and hasattr(self.ui_manager, 'get_theme_icon'):
            self.s_close.setIcon(self.ui_manager.get_theme_icon("close.svg", False, override_color="#FF453A"))
        self.s_close.clicked.connect(self.search_bar.hide)

        for w in [self.s_in, self.s_count, self.s_prev_btn, self.s_next_btn, self.r_in, self.r_btn, self.s_close]:
            sl.addWidget(w)

        self.search_bar.hide()
        cc_layout.addWidget(self.search_bar)

        self.fmt_bar = QHBoxLayout()
        self.fmt_bar.setContentsMargins(0, 4, 0, 0)
        self.fmt_bar.setSpacing(4)

        self.btn_bullet = QPushButton("")
        self.btn_num = QPushButton("")
        self.btn_check = QPushButton("")                # 아이콘은 apply_data 에서 본문의 체크 상자와 같은 모양으로 그려 넣습니다.
        self.btn_check.setToolTip("체크리스트 (선택한 줄에 체크 상자 붙이기/떼기)")
        self.btn_indent = QPushButton("")
        self.btn_outdent = QPushButton("")

        self.btn_bold = QPushButton("B")
        self.btn_italic = QPushButton("I")
        self.btn_underline = QPushButton("U")
        self.btn_strike = QPushButton("S")
        self.btn_strike.setToolTip("취소선 (선택한 글자에 줄 긋기/지우기)")

        for b in [self.btn_bullet, self.btn_num, self.btn_check, self.btn_indent, self.btn_outdent, self.btn_bold, self.btn_italic, self.btn_underline, self.btn_strike]:
            b.setFixedSize(24, 24)
            # 굵게·기울임·밑줄·취소선만 '켜짐/꺼짐'이 표시됩니다. 목록·들여쓰기는 누를 때 동작만 하는 버튼입니다.
            b.setCheckable(b in (self.btn_bold, self.btn_italic, self.btn_underline, self.btn_strike))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            # 버튼을 눌러도 본문의 입력 포커스가 넘어가지 않게 합니다.
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            self.fmt_bar.addWidget(b)

        self.btn_bullet.clicked.connect(self.apply_bullet)
        self.btn_num.clicked.connect(self.apply_number)
        self.btn_check.clicked.connect(self.toggle_checklist)
        self.btn_indent.clicked.connect(self.apply_indent)
        self.btn_outdent.clicked.connect(self.apply_outdent)
        self.btn_bold.clicked.connect(self.toggle_bold)
        self.btn_italic.clicked.connect(self.toggle_italic)
        self.btn_underline.clicked.connect(self.toggle_underline)
        self.btn_strike.clicked.connect(self.toggle_strike)

        self.btn_format_code = QPushButton("{} 정렬")
        self.btn_format_code.setFixedHeight(24)
        self.btn_format_code.clicked.connect(self.prettify_code)
        self.btn_format_code.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_format_code.hide()
        self.fmt_bar.addWidget(self.btn_format_code)

        self.btn_toggle_sub_fmt = QPushButton("Aa ▾")
        self.btn_toggle_sub_fmt.setFixedHeight(24)
        self.btn_toggle_sub_fmt.clicked.connect(self.toggle_sub_fmt_panel)
        self.btn_toggle_sub_fmt.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.fmt_bar.addWidget(self.btn_toggle_sub_fmt)

        self.fmt_bar.addStretch()

        # 알림이 걸려 있으면 그 시각을 보여 줍니다. 누르면 알림 설정 창이 열립니다.
        self.btn_reminder = QPushButton("")
        self.btn_reminder.setFixedHeight(24)
        self.btn_reminder.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_reminder.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_reminder.clicked.connect(self.edit_reminder)
        self.btn_reminder.hide()
        self.fmt_bar.addWidget(self.btn_reminder)

        self.sub_fmt_widget = QWidget()
        sub_l = QHBoxLayout(self.sub_fmt_widget)
        sub_l.setContentsMargins(0, 2, 0, 0)
        sub_l.setSpacing(4)

        # 글꼴: 목록에서 고르거나, 이름의 일부를 적어 찾습니다. (적는 동안에는 바뀌지 않고, 고르거나 Enter 를 쳐야 적용)
        self.font_box = QFontComboBox()
        self.font_box.setEditable(True)
        self.font_box.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.font_box.setMaximumWidth(140)
        self.font_box.setFixedHeight(24)
        self.font_box.setToolTip("글꼴 (이름을 적어 검색)")
        self.font_box.setCurrentFont(QFont(self.memo_data.get('font_family') or 'D2Coding'))
        finder = self.font_box.completer()
        finder.setFilterMode(Qt.MatchFlag.MatchContains)
        finder.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        finder.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        finder.activated[str].connect(self.pick_font_family)
        self.font_box.activated.connect(lambda index: self.pick_font_family(self.font_box.itemText(index)))
        self.font_box.lineEdit().editingFinished.connect(lambda: self.pick_font_family(self.font_box.currentText()))
        self.btn_font_drop = self._drop_button(self.font_box, "글꼴 목록 열기")
        sub_l.addLayout(self._joined(self.font_box, self.btn_font_drop))

        # 크기: 목록에서 고르거나 숫자를 직접 적습니다. (6~72)
        self.size_box = QComboBox()
        self.size_box.setEditable(True)
        self.size_box.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.size_box.setValidator(QIntValidator(1, 99, self.size_box))
        self.size_box.setToolTip("글자 크기 (숫자를 적어도 됨)")
        size_finder = self.size_box.completer()
        size_finder.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        size_finder.activated[str].connect(self.pick_font_size)
        self.size_box.setFixedSize(54, 24)
        for sz in [8, 9, 10, 11, 12, 14, 16, 18, 20, 24, 28, 32, 36, 48, 72]:
            self.size_box.addItem(str(sz))
        self.size_box.setCurrentText(str(self.memo_data.get('font_size', 11)))
        self.size_box.activated.connect(lambda index: self.pick_font_size(self.size_box.itemText(index)))
        self.size_box.lineEdit().editingFinished.connect(lambda: self.pick_font_size(self.size_box.currentText()))
        self.btn_size_drop = self._drop_button(self.size_box, "크기 목록 열기")
        sub_l.addLayout(self._joined(self.size_box, self.btn_size_drop))
        # 지나가던 휠에 글꼴·크기·언어가 바뀌지 않게 합니다. (클릭해서 고름)
        guard_wheel(self, (self.font_box, self.size_box, self.code_lang_box))

        self.btn_fg_color = QPushButton("A")
        self.btn_fg_color.setFixedSize(24, 24)
        self.btn_fg_color.setToolTip("글씨색 선택 (RGB)")
        self.btn_fg_color.clicked.connect(self.choose_fg_color)
        self.btn_fg_color.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        sub_l.addWidget(self.btn_fg_color)

        self.btn_bg_color = QPushButton("▣")
        self.btn_bg_color.setFixedSize(24, 24)
        self.btn_bg_color.setToolTip("글씨 배경색 / 형광펜")
        self.btn_bg_color.clicked.connect(self.show_bg_color_menu)
        self.btn_bg_color.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        sub_l.addWidget(self.btn_bg_color)
        sub_l.addStretch()

        self.sub_fmt_widget.hide()

        cc_layout.addLayout(self.fmt_bar)
        cc_layout.addWidget(self.sub_fmt_widget)

        self.update_toolbar_button_states()
        bg_l.addWidget(self.content_container)
        self.grip = QSizeGrip(self)

    def _drop_button(self, box: Any, tip: str) -> QPushButton:
        """글꼴·크기 칸 옆의 '목록 열기' 버튼. 칸에는 적어서 찾고, 이 버튼으로는 목록을 펼칩니다."""
        button = QPushButton("▾")
        button.setFixedSize(20, 24)
        button.setToolTip(tip)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        button.clicked.connect(lambda checked=False: self.open_choice_list(box))
        return button

    def open_choice_list(self, box: Any) -> None:
        """글꼴·크기 목록을 칸 아래에 펼칩니다. 목록이 떠 있는 채로 칸에 적으면 그 글자가 들어간 것만 남습니다."""
        edit = box.lineEdit()
        edit.setFocus()
        edit.selectAll()                                # 바로 적으면 지금 글자를 대신함
        finder = box.completer()
        finder.setCompletionPrefix("")                  # 처음에는 전부 보여 줌
        finder.popup().setMinimumWidth(max(box.width() + 20, 120))
        finder.complete()

    @staticmethod
    def _joined(box: Any, button: QPushButton) -> QHBoxLayout:
        pair = QHBoxLayout()
        pair.setContentsMargins(0, 0, 0, 0)
        pair.setSpacing(0)
        pair.addWidget(box)
        pair.addWidget(button)
        return pair

    LOCK_BADGE_WIDTH = 20

    def refresh_lock_badge(self) -> None:
        """접어 둔 암호 메모의 제목 왼쪽에 자물쇠를 보입니다. (제목 글자는 그만큼 오른쪽에서 시작)"""
        show = bool(self.memo_data.get('is_locked')) and self._is_rolled_up
        self.title_edit.setTextMargins(self.LOCK_BADGE_WIDTH if show else 0, 0, 0, 0)
        if show:
            self.lbl_lock.setFont(self.title_edit.font())
            self.lbl_lock.setGeometry(0, 0, self.LOCK_BADGE_WIDTH, self.title_edit.height())
        self.lbl_lock.setVisible(show)

    def side_panel(self) -> SidePanel:
        """이 메모 옆에 붙는 패널. (알림 설정·이전 내용처럼 메모 안에 다 들어가지 않는 화면을 띄우는 곳)"""
        if getattr(self, '_side_panel', None) is None:
            self._side_panel = SidePanel(self)
        return self._side_panel

    # ── 체크리스트 진행 표시 ──────────────────────────────────────────────────
    def refresh_progress(self) -> None:
        """제목 줄의 진행 표시('☐ 3/5', 다 끝내면 '☑ 5/5')를 지금 본문에 맞춥니다. 체크리스트가 없거나 잠긴 메모면 숨깁니다."""
        text = "" if self.is_sealed() else self.text_edit.check_marks.progress_label()
        if text != self.lbl_progress.text() or self.lbl_progress.isHidden() == bool(text):
            ink = self._memo_theme_palette()['text']
            self.lbl_progress.setStyleSheet(
                f"color: {ink}; background: {modern_style.rgba(ink, 0.10)}; padding: 1px 6px; font-size: 8.5pt; "
                f"font-weight: 700; font-family: {modern_style.UI_FONT};")
            self.lbl_progress.setText(text)
            self.lbl_progress.setVisible(bool(text))

    # ── 알림 ─────────────────────────────────────────────────────────────────
    def refresh_reminder_badge(self) -> None:
        """서식 줄 오른쪽의 알림 표시를 지금 알림에 맞춥니다."""
        text = reminders.describe(self.memo_data.get('reminder'))
        self.btn_reminder.setToolTip("알림: " + text + " (눌러서 바꾸기)" if text else "")
        self.btn_reminder.setVisible(bool(text) and not self._is_rolled_up)
        if not text:
            self.btn_reminder.setText("")
            return
        # 메모 폭에 들어가는 가장 자세한 표기를 고릅니다. (좁은 메모에서는 시계만)
        due = reminders.due_at(self.memo_data.get('reminder'))
        used = sum(item.widget().width() + self.fmt_bar.spacing() for item in map(self.fmt_bar.itemAt, range(self.fmt_bar.count()))
                   if item.widget() and item.widget() is not self.btn_reminder and not item.widget().isHidden())
        room = self.bg.width() - used - 36
        metrics = self.btn_reminder.fontMetrics()
        choices = ("⏰ " + text, f"⏰ {due.month}.{due.day:02d} {due.hour:02d}:{due.minute:02d}", f"⏰ {due.month}.{due.day:02d}", "⏰")
        label = next((c for c in choices if metrics.horizontalAdvance(c) + 18 <= room), choices[-1])
        self.btn_reminder.setText(label)
        self.btn_reminder.setFixedWidth(metrics.horizontalAdvance(label) + 18)

    def edit_reminder(self) -> None:
        """알림 설정 창을 띄워 이 메모의 알림을 걸거나 풉니다."""
        sm = self._sync_manager()
        if not sm:
            return
        changed, reminder = ask_reminder(self._dlg_parent(), self.memo_data.get('reminder'), str(self.memo_data.get('title', '')))
        if not changed:
            return
        sm.set_reminder(self.memo_data, reminder)
        self.refresh_reminder_badge()
        self._refresh_explorer()
        self.show_toast("⏰ " + reminders.describe(reminder) if reminder else "알림을 해제했습니다")

    # ── 변경 기록 ────────────────────────────────────────────────────────────
    def show_history(self) -> None:
        """이전 내용을 보여 주고, 고른 내용으로 되돌립니다."""
        sm = self._sync_manager()
        memo_id = self.memo_data.get('id', '')
        if not sm or not memo_id:
            return
        self.flush_auto_save()                  # 지금 치던 내용도 기록에 남도록 먼저 저장
        chosen = pick_history(self._dlg_parent(), str(self.memo_data.get('title', '')), sm.list_history(memo_id),
                              reveal=lambda index, password: sm.read_history_text(memo_id, index, password),
                              check=lambda index, password: sm.restore_problem(memo_id, index, password))
        if chosen is not None and sm.restore_history(memo_id, chosen[0], chosen[1]):
            self.ui_manager.reload_pulled_memos([memo_id])
            self._refresh_explorer()
            self.show_toast("이전 내용으로 되돌렸습니다")

    def toggle_maximize(self) -> None:
        """100% 정상 작동하는 최대화/복원 토글"""
        if self.isMaximized():
            self.showNormal()
            self.btn_max.setText("")
            self.btn_max.setToolTip("최대화")
        else:
            self.showMaximized()
            self.btn_max.setText("")
            self.btn_max.setToolTip("복원")

    def toggle_code_theme(self) -> None:
        """코드 테마 사용자 수동 전환"""
        self.memo_data['content'] = self.current_content()
        cur = self.memo_data.get('code_theme',
              'dark' if self.memo_window_get_settings().get('app_theme', 'white') == 'dark' else 'light')
        new_theme = "light" if cur == "dark" else "dark"
        self.memo_data['code_theme'] = new_theme
        self.memo_data['code_theme_user_set'] = True
        self.apply_data()
        self.update()
        self.repaint()
        self.text_edit.viewport().update()
        self._mark_edited()

    def toggle_sub_fmt_panel(self) -> None:
        is_vis = self.sub_fmt_widget.isVisible()
        self.sub_fmt_widget.setVisible(not is_vis)
        self.btn_toggle_sub_fmt.setText("Aa ▴" if not is_vis else "Aa ▾")
        if is_vis:
            self.title_edit.deselect()
            self.text_edit.setFocus()                   # 닫으면 본문으로 돌아감

    def on_code_lang_changed(self, lang: str) -> None:
        self.memo_data['code_lang'] = lang
        theme = self.memo_data.get('code_theme', 'dark')
        self.highlighter = CodeHighlighter(self.text_edit.document(), lang, theme)
        self._mark_edited()

    def prettify_code(self) -> None:
        """JSON / 기타 코드 자동 정렬 — 정렬 후 하이라이터 및 글씨색 강제 재적용."""
        raw_code = self.text_edit.toPlainText().strip()
        if not raw_code:
            return
        lang = self.memo_data.get('code_lang', 'JSON').upper()
        code_theme = self.memo_data.get('code_theme', 'dark')
        code_text = "#F2F2F7" if code_theme == "dark" else "#1C1C1E"

        def _apply_after_format(formatted: str) -> None:
            """setPlainText 적용 후 하이라이터 및 글씨색 복원."""
            self.text_edit.setPlainText(formatted)
            self.text_edit.document().setModified(True)      # 본문을 바꾼 것이므로 '고침'으로 표시
            # 하이라이터 재적용
            self.highlighter = CodeHighlighter(self.text_edit.document(), lang, code_theme)
            # 전체 글씨새 재적용
            cursor = self.text_edit.textCursor()
            cursor.select(QTextCursor.SelectionType.Document)
            base_fmt = QTextCharFormat()
            base_fmt.setForeground(QColor(code_text))
            cursor.mergeCharFormat(base_fmt)
            self._mark_edited()

        if "JSON" in lang:
            try:
                parsed = json.loads(raw_code)
                formatted = json.dumps(parsed, indent=2, ensure_ascii=False)
                _apply_after_format(formatted)
                self.show_toast("✨ JSON 코드 자동 정렬 완료")
                return
            except Exception:
                self.show_toast("⚠️ JSON 구문 오류 (정렬 안 됨)")
                return

        lines = raw_code.splitlines()
        formatted_lines: list = []
        indent = 0
        for line in lines:
            stripped = line.strip()
            if stripped.startswith('}') or stripped.startswith(']'):
                indent = max(0, indent - 1)
            formatted_lines.append("  " * indent + stripped)
            if stripped.endswith('{') or stripped.endswith('['):
                indent += 1

        _apply_after_format("\n".join(formatted_lines))
        self.show_toast("✨ 코드 인덴트 정렬 완료")

    def mouseDoubleClickEvent(self, e: Any) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            if self._is_rolled_up or e.position().y() <= 53:
                self.toggle_rollup()
                e.accept()
                return
        super().mouseDoubleClickEvent(e)

    def eventFilter(self, obj: Any, event: Any) -> bool:
        if hasattr(self, 'title_edit') and obj == self.title_edit:
            if event.type() == QEvent.Type.MouseButtonDblClick and event.button() == Qt.MouseButton.LeftButton:
                self.toggle_rollup()
                return True

            if not self.title_edit.isReadOnly():
                if event.type() == QEvent.Type.FocusOut:
                    self.handle_rename()
            else:
                if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                    self.mousePressEvent(event)
                    return True
                elif event.type() == QEvent.Type.MouseMove:
                    self.mouseMoveEvent(event)
                    return True
                elif event.type() == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
                    self.mouseReleaseEvent(event)
                    return True

        return super().eventFilter(obj, event)

    def find_snap_target_memo(self) -> Optional['MemoWindow']:
        if not getattr(self, 'ui_manager', None):
            return None

        memos_below = []
        memos_above = []

        for other_id, other_win in self.ui_manager.memo_windows.items():
            if other_win is self or not other_win.isVisible() or not other_win._is_rolled_up:
                continue

            # 📌 수직 15px 이내 직접 맞닿아 있고 가로 영역이 겹칠 때만(붙어있을 때만) 탐색
            touch_below = abs(other_win.y() - (self.y() + self.height())) <= 15
            touch_above = abs((other_win.y() + other_win.height()) - self.y()) <= 15
            horiz_overlap = (self.x() < other_win.x() + other_win.width()) and (self.x() + self.width() > other_win.x())

            if (touch_below or touch_above) and horiz_overlap:
                dy = other_win.y() - self.y()
                if dy > 0:
                    memos_below.append((dy, other_win))
                elif dy < 0:
                    memos_above.append((abs(dy), other_win))

        if memos_below:
            memos_below.sort(key=lambda item: item[0])
            return memos_below[0][1]
        if memos_above:
            memos_above.sort(key=lambda item: item[0])
            return memos_above[0][1]

        return None

    def resizeEvent(self, event: Any) -> None:
        super().resizeEvent(event)
        if hasattr(self, 'lock_overlay'):
            self.lock_overlay.refresh()                    # 접거나 펼 때 보이기/숨기기
            self.refresh_lock_badge()
            if not self.lock_overlay.isHidden():
                self.lock_overlay.sync_geometry()
        if hasattr(self, 'btn_reminder') and not self.btn_reminder.isHidden():
            self.refresh_reminder_badge()
        if hasattr(self, 'grip'):
            # 📌 접힌 메모와 동일하게 메모 안쪽에 딱 알맞게 안착 (삐져나옴 방지)
            if self._is_rolled_up:
                self.grip.move(self.width() - 18, self.height() - 18)
            else:
                self.grip.move(self.width() - 20, self.height() - 20)
            self.grip.resize(12, 12)

        # 📌 접힌 상태에서 맞닿아 있을 때만 12px 스냅 멈춤 & 15px 이상 끌면 이탈하여 가로 자유 조절
        applying = getattr(self, '_applying_geometry', False)
        if self._is_rolled_up:
            if not applying:
                self.memo_data['rolled_width'] = self.width()
            rolled_h = self._get_rolled_height()
            if self.height() != rolled_h:
                self.resize(self.width(), rolled_h)
                return  # resize()가 또 resizeEvent를 발생시키므로 이번 이벤트는 여기서 종료
            # 접힌 상태이면 버튼·타이틀 크기를 항상 재보정 (외부 resize/스케일 변경 대응)
            self._apply_rolled_ui(rolled_h)
            target_win = self.find_snap_target_memo()
            if target_win:
                target_w = target_win.width()
                mouse_x = QCursor.pos().x()

                if getattr(self, '_sticky_snap_origin', None):
                    start_mouse_x, snap_w = self._sticky_snap_origin
                    if abs(mouse_x - start_mouse_x) > 15:
                        self._sticky_snap_origin = None  # 15px 이상 당기면 자석 이탈!
                    else:
                        self.resize(snap_w, rolled_h)
                        return

                if not getattr(self, '_sticky_snap_origin', None):
                    if abs(self.width() - target_w) <= 12:
                        self.resize(target_w, rolled_h)
                        self._sticky_snap_origin = (mouse_x, target_w)
            else:
                self._sticky_snap_origin = None
        elif not applying and not self.is_locked_compact():
            self.memo_data['unrolled_width'] = self.width()
            self.memo_data['unrolled_height'] = self.height()
            self.memo_data['width'] = self.width()
            self.memo_data['height'] = self.height()

    def show_menu(self, pos: QPoint) -> None:
        menu = QMenu(self)
        menu.setStyleSheet(modern_style.menu_qss(self.memo_window_get_settings()))

        s = self.memo_window_get_settings()
        sc = s.get("shortcuts", {})
        def _fmt_sc(title: str, key: str, default: str) -> str:
            val = sc.get(key, default)
            return f"{title} ({val})" if val else title

        sender_widget = self.sender()
        if hasattr(sender_widget, 'copy'):
            menu.addAction("복사 (Ctrl+C)").triggered.connect(sender_widget.copy)
            menu.addAction("잘라내기 (Ctrl+X)").triggered.connect(sender_widget.cut)
            menu.addAction("붙여넣기 (Ctrl+V)").triggered.connect(sender_widget.paste)
            menu.addAction("모두 선택 (Ctrl+A)").triggered.connect(sender_widget.selectAll)
            menu.addSeparator()

        is_code = self.memo_data.get('is_code_memo', False)
        if is_code:
            menu.addAction(_fmt_sc("코드 자동 정렬", "format_code", "Ctrl+Shift+F")).triggered.connect(self.prettify_code)
            menu.addAction("코드만 클립보드 복사").triggered.connect(self.copy_all_content)
            menu.addAction(_fmt_sc("코드 테마 전환", "toggle_code_theme", "Ctrl+Shift+L")).triggered.connect(self.toggle_code_theme)
        else:
            menu.addAction(_fmt_sc("전체 메모 내용 복사 (클립보드)", "copy_all", "Ctrl+Shift+C")).triggered.connect(self.copy_all_content)

        menu.addAction(_fmt_sc("한/영 영타 오타 변환", "eng_kor_convert", "Ctrl+Alt+E")).triggered.connect(self.convert_selected_eng_kor)

        menu.addSeparator()

        is_auto_convert = s.get("auto_eng_kor_convert", True)
        auto_convert_action = menu.addAction(f"한/영 자동 변환기 [{ 'ON' if is_auto_convert else 'OFF' }]")
        auto_convert_action.setCheckable(True)
        auto_convert_action.setChecked(is_auto_convert)
        auto_convert_action.triggered.connect(self.toggle_auto_eng_kor_setting)

        menu.addSeparator()
        menu.addAction(_fmt_sc("메모 탐색기 열기", "open_explorer", "Ctrl+E")).triggered.connect(self.ui_manager.open_memo_explorer)
        menu.addAction(_fmt_sc("저장", "save", "Ctrl+S")).triggered.connect(self.manual_save)
        menu.addAction(_fmt_sc("검색", "search", "Ctrl+F")).triggered.connect(self.show_search_only)
        menu.addAction(_fmt_sc("바꾸기", "replace", "Ctrl+H")).triggered.connect(self.show_search_and_replace)
        menu.addAction(_fmt_sc("화면 고정 토글", "toggle_pin", "Ctrl+P")).triggered.connect(self.toggle_pin)
        menu.addAction(_fmt_sc("메모 창 접기", "toggle_rollup", "Ctrl+M")).triggered.connect(self.toggle_rollup)

        ln_action = menu.addAction("행번호 표시")
        ln_action.setCheckable(True)
        ln_action.setChecked(self.memo_data.get('show_line_numbers', False))
        ln_action.triggered.connect(self.toggle_line_numbers)

        bg_action = menu.addAction("줄노트 배경")
        bg_action.setCheckable(True)
        bg_action.setChecked(self.memo_data.get('show_line_bg', False))
        bg_action.triggered.connect(self.toggle_line_bg)

        if not is_code:
            menu.addSeparator()
            cm = menu.addMenu("창 배경색 변경")
            for n, c in {"다크그레이": "#2E3440", "하늘색": "#E0F2FE", "연두색": "#DCFCE7", "노란색": "#FEF9C3", "분홍색": "#FCE7F3", "흰색": "#FFFFFF"}.items():
                cm.addAction(n).triggered.connect(lambda checked, code=c: self.change_color(code))

        menu.addSeparator()
        menu.addAction(_fmt_sc("체크리스트 켜기/끄기", "toggle_checklist", "Alt+K")).triggered.connect(self.toggle_checklist)
        has_reminder = bool(reminders.normalize(self.memo_data.get('reminder')))
        menu.addAction(_fmt_sc("⏰ 알림 바꾸기…" if has_reminder else "⏰ 알림 설정…", "set_reminder", "Ctrl+R")).triggered.connect(self.edit_reminder)
        menu.addAction(_fmt_sc("이전 내용 보기…", "show_history", "Ctrl+Shift+H")).triggered.connect(self.show_history)

        menu.addSeparator()
        if self.memo_data.get('_locked'):
            menu.addAction("🔓 잠금 해제 (암호 입력)").triggered.connect(self.prompt_unlock)
            sm_lock = self._sync_manager()
            if sm_lock and sm_lock.memo_has_master_recovery(self.memo_data.get('id', '')):
                menu.addAction("관리자 키로 복구…").triggered.connect(self.recover_with_master_key)
        elif self.memo_data.get('is_locked'):
            menu.addAction("🔒 지금 잠그기").triggered.connect(self.lock_now)
            menu.addAction("암호 변경").triggered.connect(self.set_memo_password)
            menu.addAction("암호 제거 (일반 메모로)").triggered.connect(self.remove_memo_password)
        elif not self.memo_data.get('_unreadable'):
            menu.addAction("🔒 이 메모에 암호 걸기").triggered.connect(self.set_memo_password)

        menu.addSeparator()
        # 🔆 투명도 슬라이더 서브메뉴
        opacity_menu = menu.addMenu("창 투명도 조절")
        opacity_widget = QWidget()
        opacity_layout = QHBoxLayout(opacity_widget)
        opacity_layout.setContentsMargins(12, 6, 12, 6)
        opacity_layout.setSpacing(8)
        cur_opacity_pct = int(round(float(self.memo_data.get('opacity', 1.0)) * 100))
        opa_label = QLabel(f"불투명도: {cur_opacity_pct}%")
        opa_label.setStyleSheet("color: #007AFF; font-weight: bold; font-size: 9pt; min-width: 90px;")
        opa_slider = QSlider(Qt.Orientation.Horizontal)
        opa_slider.setRange(20, 100)
        opa_slider.setValue(cur_opacity_pct)
        opa_slider.setFixedWidth(160)
        opa_slider.setStyleSheet("""
            QSlider::groove:horizontal { height: 4px; background: #C7C7CC; }
            QSlider::handle:horizontal { width: 12px; height: 18px; margin: -7px 0; background: #007AFF; }
            QSlider::sub-page:horizontal { background: #007AFF; }
        """)
        def _update_opacity(val: int) -> None:
            opa_label.setText(f"불투명도: {val}%")
            self.memo_data['opacity'] = round(val / 100.0, 2)
            self.setWindowOpacity(self.memo_data['opacity'])
            self._schedule_auto_save()
        opa_slider.valueChanged.connect(_update_opacity)
        opacity_layout.addWidget(opa_label)
        opacity_layout.addWidget(opa_slider)
        opa_action = QWidgetAction(opacity_menu)
        opa_action.setDefaultWidget(opacity_widget)
        opacity_menu.addAction(opa_action)
        opacity_menu.addSeparator()
        opacity_menu.addAction("100% (완전 불투명)").triggered.connect(lambda: opa_slider.setValue(100))
        opacity_menu.addAction("80% (약간 투명)").triggered.connect(lambda: opa_slider.setValue(80))
        opacity_menu.addAction("60% (반투명)").triggered.connect(lambda: opa_slider.setValue(60))
        opacity_menu.addAction("40% (많이 투명)").triggered.connect(lambda: opa_slider.setValue(40))

        menu.addSeparator()
        menu.addAction(_fmt_sc("메모 삭제", "delete_memo", "Ctrl+D")).triggered.connect(lambda: self.delete_callback(self))
        menu.exec(self.sender().mapToGlobal(pos))

    def toggle_auto_eng_kor_setting(self) -> None:
        sm = getattr(self.close_callback, '__self__', None).sync_manager
        cur = sm.settings.get("auto_eng_kor_convert", True)
        sm.settings["auto_eng_kor_convert"] = not cur
        sm.save_settings(sm.settings)
        self.show_toast(f"🔤 한/영 자동 변환기: {'ON' if not cur else 'OFF'}")

    def convert_selected_eng_kor(self) -> None:
        cursor = self.text_edit.textCursor()
        if cursor.hasSelection():
            txt = cursor.selectedText()
            converted = convert_eng_kor_smart(txt)
            cursor.insertText(converted)
        else:
            txt = self.text_edit.toPlainText()
            converted = convert_eng_kor_smart(txt)
            self.text_edit.setPlainText(converted)
            self.text_edit.document().setModified(True)      # 본문을 바꾼 것이므로 '고침'으로 표시
        self._mark_edited()
        self.show_toast("🔤 한/영 영타 변환 완료")

    def copy_all_content(self) -> None:
        if self.memo_data.get('is_code_memo', False):
            plain_text = self.text_edit.toPlainText()
        else:
            plain_text = clean_plain_text(self.text_edit.toHtml())
        cb = QApplication.clipboard()
        cb.setText(plain_text)
        self.show_toast("📋 클립보드에 복사되었습니다.")

    def show_search_only(self) -> None:
        self.r_in.hide()
        self.r_btn.hide()
        self.search_bar.show()
        self.s_in.setFocus()
        self.s_in.selectAll()

    def show_search_and_replace(self) -> None:
        self.r_in.show()
        self.r_btn.show()
        self.search_bar.show()
        self.s_in.setFocus()
        self.s_in.selectAll()

    def do_find(self, backward: bool = False) -> None:
        search_text = self.s_in.text()
        if not search_text:
            self.s_count.setText("0/0")
            return

        p = self.text_edit.palette()
        p.setColor(QPalette.ColorRole.Highlight, QColor("#007AFF"))
        p.setColor(QPalette.ColorRole.HighlightedText, QColor("#FFFFFF"))
        self.text_edit.setPalette(p)

        if backward:
            found = self.text_edit.find(search_text, QTextDocument.FindFlag.FindBackward)
        else:
            found = self.text_edit.find(search_text)

        if not found:
            c = self.text_edit.textCursor()
            c.movePosition(QTextCursor.MoveOperation.End if backward else QTextCursor.MoveOperation.Start)
            self.text_edit.setTextCursor(c)
            found = self.text_edit.find(search_text, QTextDocument.FindFlag.FindBackward if backward else QTextDocument.FindFlag(0))

        if found:
            text = self.text_edit.toPlainText().lower()
            st_low = search_text.lower()
            total = text.count(st_low)
            cursor_pos = self.text_edit.textCursor().position()
            current = text[:cursor_pos].count(st_low)
            if backward and current == 0 and total > 0: current = 1
            self.s_count.setText(f"{current}/{total}")
        else:
            self.s_count.setText("0/0")

    def do_replace(self) -> None:
        c = self.text_edit.textCursor()
        if c.hasSelection() and c.selectedText().lower() == self.s_in.text().lower():
            c.insertText(self.r_in.text())
            self._mark_edited()
        self.do_find(backward=False)

    def _mark_edited(self) -> None:
        """서식 변경 등으로 본문이 바뀌었음을 표시합니다. 저장은 자동 저장(마지막 입력 후 대기)에 맡깁니다."""
        if self.is_sealed():
            return
        # 본문 글자가 아니라 메모 속성(코드 테마, 기본 글꼴 등)만 바뀐 경우를 위해 표시해 둡니다.
        self._meta_dirty = True
        self._schedule_auto_save()
        self.restart_relock_timer()

    def _get_rolled_height(self) -> int:
        """settings의 default_rolled_height 값을 우선 읽고, 없으면 53을 반환합니다."""
        if getattr(self, 'ui_manager', None):
            h = self.ui_manager.sync_manager.settings.get('default_rolled_height', 53)
        else:
            h = 53
        return max(36, int(h))

    def _title_color_stylesheet(self, font_size_pt: float = 12.0) -> str:
        """현재 메모 테마 팔레트 기준으로 title_edit에 적용할 stylesheet를 반환합니다.

        코드 메모는 accent 색상, 일반 메모는 text 색상을 사용합니다.
        """
        pal = self._memo_theme_palette()
        title_color = pal['accent'] if self.memo_data.get('is_code_memo', False) else pal['text']
        return (
            f"border:none; background:transparent; color:{title_color}; "
            f"font-weight:bold; font-size:{font_size_pt}pt; font-family:{modern_style.UI_FONT};"
        )

    def _apply_rolled_ui(self, rolled_h: int) -> None:
        """접힌 상태일 때 타이틀바 높이·버튼 크기·폰트를 rolled_h에 비례하여 동적 조절합니다.

        제목 색상은 메모 테마 팔레트를 따르며 하드코딩 없이 통일됩니다.
        """
        # 버튼 크기: rolled_h 기준 비율 계산 (최소 18, 최대 32)
        btn_h = max(18, min(32, int(rolled_h * 0.55)))
        for btn in [self.btn_pin, self.btn_min, self.btn_close]:
            btn.setFixedSize(btn_h + 2, btn_h)
        # 타이틀 폰트 크기: rolled_h 기준 비율 계산 (최소 8pt, 최대 13pt)
        title_pt = max(8.0, min(13.0, rolled_h * 0.22))
        # 제목 색상 → 메모 테마 팔레트 색상으로 통일 (하드코딩 없음)
        self.title_edit.setStyleSheet(self._title_color_stylesheet(title_pt))
        # 타이틀바 여백 최소화
        if hasattr(self, 'bg_layout'):
            margin_v = max(2, int((rolled_h - btn_h) / 2) - 1)
            self.bg_layout.setContentsMargins(10, margin_v, 10, margin_v)

    def _restore_normal_ui(self) -> None:
        """펼친 상태로 복원 시 타이틀바/버튼 크기를 기본값으로 되돌리고
        제목 색상도 테마 팔레트로 통일합니다.
        """
        for btn in [self.btn_pin, self.btn_min, self.btn_close]:
            btn.setFixedSize(28, 26)
        if hasattr(self, 'btn_max'):
            self.btn_max.setFixedSize(28, 26)
        # 제목 색상 → 메모 테마 팔레트 색상으로 통일 (하드코딩 없음)
        self.title_edit.setStyleSheet(self._title_color_stylesheet(12.0))
        if hasattr(self, 'bg_layout'):
            self.bg_layout.setContentsMargins(14, 10, 14, 14)

    @staticmethod
    def _clamp_to_screen(scr_geom: Any, x: int, y: int, w: int, h: int) -> tuple:
        """창이 화면 작업 영역 밖으로 나가지 않도록 좌표를 당깁니다."""
        return memo_geometry.clamp(scr_geom, x, y, w, h)

    def _screen_area_for(self, x: int, y: int, w: int, h: int) -> Any:
        """(x, y, w, h) 자리에 놓을 창이 속할 모니터의 작업 영역.

        그 자리가 어느 모니터에도 없으면(모니터를 뗀 경우 등) 지금 창이 있는 모니터, 그것도 없으면 주 모니터입니다.
        기억해 둔 자리가 다른 모니터에 있어도 지금 모니터 안으로 끌려오지 않게 하려고 씁니다.
        """
        screen = (QApplication.screenAt(QRect(x, y, w, h).center()) or QApplication.screenAt(self.geometry().center())
                  or QApplication.primaryScreen())
        return screen.availableGeometry()

    def _apply_fold_state(self, rolled: bool, x: int, y: int, w: int, h: int) -> None:
        """접힘/펼침 상태로 바꾸고 창 크기·내용 영역·제목 줄 버튼을 그 상태에 맞춥니다."""
        self._is_rolled_up = rolled
        self.memo_data['is_rolled_up'] = rolled
        # 아래에서 창 크기를 바꾸는 동안 지나가는 크기를 '사용자가 정한 크기'로 기억하지 않게 합니다.
        # (예: 잠긴 메모를 폈다 접을 때 암호 입력용 크기가 접은 메모의 너비로 남지 않도록)
        self._applying_geometry = True
        try:
            if rolled:
                self.content_container.hide()      # 내용을 먼저 숨겨야 창을 제목 줄 높이까지 줄일 수 있습니다.
            self.window_layout.setContentsMargins(0, 0, 0, 0)
            self.setMinimumSize(0, 0) if rolled else self.setMinimumSize(200, 150)
            self.setMaximumSize(16777215, 16777215)
            self.setGeometry(x, y, w, h)
            if rolled:
                self.setMinimumHeight(h)
                self.setMaximumHeight(h)
                self._apply_rolled_ui(h)
            else:
                self.content_container.show()
                self._restore_normal_ui()
            if self.width() != w or (not rolled and self.height() != h):
                self.setGeometry(x, y, w, h)       # 내용을 다시 보이는 동안 크기가 달라졌으면 바로잡음
        finally:
            self._applying_geometry = False
        self.remember_geometry()
        # 본문 영역이 제자리를 잡은 뒤에 가림막(잠긴 메모의 암호 칸)을 그 위에 맞춥니다.
        for holder in (self.bg, self):
            if holder.layout():
                holder.layout().activate()
        if hasattr(self, 'lock_overlay'):
            self.lock_overlay.refresh()
            QTimer.singleShot(0, self.lock_overlay.refresh)
        self.btn_min.setToolTip("펼치기 (Ctrl+M)" if rolled else "접기 (Ctrl+M)")
        self.btn_max.setVisible(not rolled)
        show_code_controls = not rolled and bool(self.memo_data.get('is_code_memo', False))
        for control in (self.btn_code_theme, self.code_lang_box, self.btn_format_code, self.btn_lang_icon):
            control.setVisible(show_code_controls)
        if hasattr(self, 'btn_reminder'):
            self.refresh_reminder_badge()

    # ── 위치와 크기 기억 ─────────────────────────────────────────────────────
    # 어디에 어떤 크기로 놓을지의 규칙은 ui/memo_geometry.py 에 있습니다. (창 없이 숫자만으로 따질 수 있게 따로 둠)
    # 여기서는 지금 창의 상태를 넘겨주고, 돌려받은 자리에 창을 놓습니다.
    LOCKED_SIZE = memo_geometry.LOCKED_SIZE

    def _box(self) -> tuple:
        return self.x(), self.y(), self.width(), self.height()

    def is_locked_compact(self) -> bool:
        """잠겨 있어서 암호 입력용 작은 크기로 떠 있는지. (이때의 크기는 메모의 크기로 기억하지 않음)"""
        return memo_geometry.is_locked_compact(self.memo_data, self._is_rolled_up)

    def remember_geometry(self) -> None:
        """지금 상태(접힘/펼침)의 위치와 크기를 그 상태의 것으로 기억합니다."""
        memo_geometry.remember(self.memo_data, self._is_rolled_up, self._box())

    def _saved_unrolled_size(self) -> tuple:
        """기억해 둔 펼친 크기. (잠겨 있든 아니든 메모 본래의 크기)"""
        return memo_geometry.saved_unrolled_size(self.memo_data, getattr(self, '_normal_height', 300))

    def _unrolled_size(self) -> tuple:
        """펼쳤을 때의 크기. 잠긴 메모는 암호를 풀기 전까지 암호 입력용 작은 크기로 뜹니다."""
        return memo_geometry.unrolled_size(self.memo_data, getattr(self, '_normal_height', 300))

    def _covers_rolled_memo(self, rect: QRect) -> bool:
        """rect 에 펼치면 다른 접은 메모를 가리게 되는지."""
        manager = getattr(self, 'ui_manager', None)
        if not manager:
            return False
        return any(other is not self and other.isVisible() and other._is_rolled_up and rect.intersects(other.geometry())
                   for other in manager.memo_windows.values())

    def _rolled_stack_span(self) -> Optional[tuple]:
        """이 접은 메모가 다른 접은 메모들과 한 줄로 쌓여 있으면 그 줄의 (왼쪽 끝, 오른쪽 끝)을, 아니면 None 을 돌려줍니다."""
        manager = getattr(self, 'ui_manager', None)
        if not manager:
            return None
        left, right, found = self.x(), self.x() + self.width(), False
        for other in manager.memo_windows.values():
            if other is self or not other.isVisible() or not other._is_rolled_up:
                continue
            overlap = min(right, other.x() + other.width()) - max(left, other.x())
            if overlap >= min(self.width(), other.width()) / 2:      # 가로로 절반 넘게 겹치면 같은 줄
                left, right, found = min(left, other.x()), max(right, other.x() + other.width()), True
        return (left, right) if found else None

    def toggle_rollup(self) -> None:
        """접거나 폅니다. 접힌 상태와 펼친 상태는 저마다 기억해 둔 위치와 크기로 돌아갑니다."""
        screen = QApplication.screenAt(self.geometry().center()) or QApplication.primaryScreen()
        scr_geom = screen.availableGeometry()
        data = self.memo_data
        default_height = getattr(self, '_normal_height', 300)
        self.remember_geometry()                      # 떠나는 상태의 위치·크기를 먼저 기억

        if not self._is_rolled_up:
            self._normal_height = memo_geometry.own_size(data, False, self._box(), default_height)[1]
            data['rolled_height'] = self._get_rolled_height()
            new_left_x, new_top_y, target_w, target_h = memo_geometry.fold_target(
                data, self._box(), data['rolled_height'], scr_geom, default_height)
        else:
            new_left_x, new_top_y, target_w, target_h = memo_geometry.unfold_target(
                data, self._box(), scr_geom,
                area_for=lambda box: self._screen_area_for(*box),
                stack=self._rolled_stack_span(),
                covers=lambda box: self._covers_rolled_memo(QRect(*box)),
                default_height=default_height)
        new_left_x, new_top_y = self._clamp_to_screen(
            self._screen_area_for(new_left_x, new_top_y, target_w, target_h), new_left_x, new_top_y, target_w, target_h)
        self._apply_fold_state(not self._is_rolled_up, new_left_x, new_top_y, target_w, target_h)

        if getattr(self, 'ui_manager', None) and hasattr(self.ui_manager, 'get_theme_icon'):
            is_dark_bg = self.is_dark_bg()
            icon_name = "maximize.svg" if self._is_rolled_up else "rollup.svg"
            self.btn_min.setIcon(self.ui_manager.get_theme_icon(
                icon_name, is_dark_bg, override_color="#FFFFFF" if is_dark_bg else "#1C1C1E"))

        self.btn_min.style().unpolish(self.btn_min)
        self.btn_min.style().polish(self.btn_min)
        self.btn_min.update()
        self.btn_min.repaint()
        if hasattr(self, 'bg'):
            self.bg.update()
            self.bg.repaint()
        QApplication.processEvents()

        self.save_callback(self.memo_data)

    def update_content(self) -> None:
        if getattr(self, '_is_updating_from_explorer', False) or getattr(self, '_is_applying_data', False): return
        if self.is_sealed(): return
        self._schedule_auto_save()
        self.restart_relock_timer()

    # 쉬지 않고 계속 입력하는 동안에도 최소한 이 간격으로는 저장합니다.
    MAX_UNSAVED_SEC = 600

    def _schedule_auto_save(self) -> None:
        """마지막 입력 후 환경설정의 대기 시간이 지나면 저장하도록 예약합니다.

        입력이 이어지면 예약을 뒤로 미루되, 첫 미저장 입력 후 MAX_UNSAVED_SEC를 넘기지는 않습니다.
        """
        import time
        try:
            idle = int(self.memo_window_get_settings().get("auto_save_idle_sec", 60))
        except (TypeError, ValueError):
            idle = 60
        now = time.monotonic()
        if self._dirty_since is None or not self._auto_save_timer.isActive():
            self._dirty_since = now
        remaining_cap = self.MAX_UNSAVED_SEC - (now - self._dirty_since)
        delay = max(0.0, min(float(max(1, idle)), remaining_cap))
        self._auto_save_timer.start(int(delay * 1000))

    def flush_auto_save(self) -> None:
        """예약된 자동 저장이 남아 있으면 지금 바로 저장합니다. (닫기·숨기기·앱 종료 시)"""
        if self._auto_save_timer.isActive():
            self._auto_save_timer.stop()
            self.execute_auto_save()

    def hideEvent(self, e: Any) -> None:
        if hasattr(self, 'lock_overlay'):
            self.lock_overlay.cancel()                     # 암호를 묻던 중이면 취소
        if not getattr(self, '_is_deleting', False):
            self.flush_auto_save()
        super().hideEvent(e)

    def execute_auto_save(self) -> None:
        self._dirty_since = None
        if self.is_sealed():
            # 잠긴 상태의 빈 편집기를 본문으로 저장하면 안 됩니다.
            return
        self.memo_data['content'] = self.current_content()
        # 수정일시는 본문을 실제로 고쳤을 때만 바꿉니다. (고친 것 없이 저장만 한 경우에는 그대로)
        # 본문은 그대로이고 속성만 바뀐 경우에는 다른 기기에 전해지도록 '속성 수정 시각'만 갱신합니다.
        document = self.text_edit.document()
        now = datetime.datetime.now().isoformat()
        if document.isModified():
            self.memo_data['updated_at'] = now
        elif getattr(self, '_meta_dirty', False):
            self.memo_data['meta_updated_at'] = now
        document.setModified(False)
        self._meta_dirty = False

        plain = clean_plain_text(self.memo_data['content'])

        if self.memo_data.get('is_draft'):
            if plain:
                self.memo_data['is_draft'] = False
                self.save_callback(self.memo_data)
                self.show_toast("✓ 저장됨")
        else:
            self.save_callback(self.memo_data)
            self.show_toast("✓ 저장됨")

    def manual_save(self) -> None:
        plain = clean_plain_text(self.text_edit.toHtml())
        if plain:
            self.memo_data['is_manually_saved'] = True
            self.memo_data['is_draft'] = False
            self._auto_save_timer.stop()
            self.execute_auto_save()
        else:
            # 내용이 없으면 draft 상태 유지, 저장은 수행하되 목록에는 추가 안되게 처리
            self._auto_save_timer.stop()
            self.execute_auto_save()

    def apply_data(self) -> None:
        if getattr(self, '_is_applying_data', False):
            return
        self._is_applying_data = True
        try:
            # 아래에서 memo_data['content']로 편집기를 다시 채우므로, 자동 저장 대기 중인 입력을 먼저 반영해 둡니다.
            was_modified = hasattr(self, 'text_edit') and self._auto_save_timer.isActive() \
                and self.text_edit.document().isModified()
            if self._auto_save_timer.isActive() and hasattr(self, 'text_edit'):
                self.memo_data['content'] = self.current_content()
            self._apply_data_internal()
            modern_style.apply_memo(self)
            # 화면을 다시 채우는 것은 수정이 아닙니다. 저장을 기다리던 입력이 있었을 때만 '고침' 표시를 유지합니다.
            self.text_edit.document().setModified(bool(was_modified))
        finally:
            self._is_applying_data = False

    def _apply_data_internal(self) -> None:
        target_flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool
        is_pinned = self.memo_data.get('is_pinned', False)
        if is_pinned:
            target_flags |= Qt.WindowType.WindowStaysOnTopHint

        current_flags = self.windowFlags()
        if (current_flags & (Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)) != target_flags:
            was_visible = self.isVisible()
            self.setWindowFlags(target_flags)
            if was_visible:
                self.show()

        is_code_memo = self.memo_data.get('is_code_memo', False)
        is_dark = self.is_dark_bg()
        rolled = self._is_rolled_up

        # 아이콘 (바탕 밝기에 맞춘 색). 버튼·바탕의 모양은 apply_data() 끝에서 디자인 스타일이 입힙니다.
        if getattr(self, 'ui_manager', None) and hasattr(self.ui_manager, 'get_theme_icon'):
            icon = self.ui_manager.get_theme_icon
            ink = "#FFFFFF" if is_dark else "#1C1C1E"
            self.btn_pin.setIcon(icon("pin_icon_True.svg" if is_pinned else "pin_icon_False.svg", is_dark, override_color=ink))
            self.btn_min.setIcon(icon("maximize.svg" if rolled else "rollup.svg", is_dark, override_color=ink))
            self.btn_max.setIcon(icon("maximize.svg", is_dark, override_color=ink))
            self.btn_close.setIcon(icon("close.svg", is_dark, override_color="#FF453A"))
            self.s_prev_btn.setIcon(icon("arrow left.svg", is_dark, override_color=ink))
            self.s_next_btn.setIcon(icon("arrow right.svg", is_dark, override_color=ink))
            self.btn_format_code.setIcon(icon("restart-icon.svg", is_dark))
            self.btn_bullet.setIcon(icon("bullet_icon_177745.svg", is_dark))
            self.btn_num.setIcon(icon("list_numbers_icon_172368.svg", is_dark))
            self.btn_indent.setIcon(icon("들여쓰기.svg", is_dark))
            self.btn_check.setIcon(modern_style.checkbox_icon(ink))
            self.btn_outdent.setIcon(icon("내어쓰기.svg", is_dark))
            if is_code_memo:
                code_is_dark = self.memo_data.get('code_theme', 'dark') == "dark"
                self.btn_code_theme.setIcon(icon("litemode.svg" if code_is_dark else "darkmod.svg", is_dark))
                self.btn_lang_icon.setIcon(icon("language.svg", is_dark, override_color="#FFFFFF" if is_dark else "#000000"))

        self.btn_min.setToolTip("펼치기 (Ctrl+M)" if rolled else "접기 (Ctrl+M)")
        self.btn_max.setVisible(not rolled)
        for code_only in (self.btn_format_code, self.btn_code_theme, self.code_lang_box, self.btn_lang_icon):
            code_only.setVisible(is_code_memo and not rolled)
        self.title_edit.setStyleSheet(self._title_color_stylesheet(12.0))

        if is_code_memo:
            code_theme = self.memo_data.get('code_theme', 'dark')
            lang = self.memo_data.get('code_lang', 'JSON')
            self.btn_code_theme.setText(" 라이트" if code_theme == "dark" else " 다크")
            self.code_lang_box.blockSignals(True)
            self.code_lang_box.setCurrentText(lang)
            self.code_lang_box.blockSignals(False)
            self.highlighter = CodeHighlighter(self.text_edit.document(), lang, code_theme)
            self.highlighter.rehighlight()
        else:
            # 바탕 밝기가 바뀌면 기본 글자색으로 쓴 글자만 새 기본색으로 바꿉니다. (직접 고른 색은 유지)
            text_c = self._memo_theme_palette()['text']
            old_colors = ["#000000", "#1C1C1E", "#333333"] if is_dark else ["#FFFFFF", "#F2F2F7", "#CCCCCC"]
            doc = self.text_edit.document()
            for i in range(doc.blockCount()):
                block = doc.findBlockByNumber(i)
                it = block.begin()
                while not it.atEnd():
                    frag = it.fragment()
                    fmt = frag.charFormat()
                    if fmt.foreground().color().name().upper() in old_colors:
                        fmt.setForeground(QColor(text_c))
                        cursor = QTextCursor(block)
                        cursor.setPosition(frag.position())
                        cursor.setPosition(frag.position() + frag.length(), QTextCursor.MoveMode.KeepAnchor)
                        cursor.mergeCharFormat(fmt)
                    it += 1

        font_family = self.memo_data.get(
            'font_family',
            self.memo_window_get_settings().get('default_font_family', 'D2Coding')
        )
        font = QFont(font_family, self.memo_data.get('font_size', 11))
        self.text_edit.setFont(font)

        self.title_edit.setText(self.memo_data.get('title',''))
        self.title_edit.setCursorPosition(0)
        self.title_edit.deselect()
        self.refresh_reminder_badge()
        self.refresh_progress()
        self.text_edit.refresh_check_marks()

        self._is_updating_from_explorer = True
        cnt = str(self.memo_data.get('content',''))
        self.text_edit.setHtml(cnt) if is_html_content(cnt) else self.text_edit.setPlainText(cnt)

        # 📌 불투명도 100% 기본값 적용 (사용자가 변경한 opacity 설정 유지)
        target_opacity = float(self.memo_data.get('opacity', 1.0))
        self.setWindowOpacity(target_opacity)

        self.apply_line_bg_style()
        self.text_edit.update_line_number_area()

        # 잠긴(또는 읽을 수 없는) 메모는 편집을 막고 안내 문구를 보여줍니다.
        self.text_edit.setReadOnly(self.is_sealed())
        if self.memo_data.get('_locked'):
            self.text_edit.setPlaceholderText("")          # 잠긴 메모는 가림막이 본문 자리를 덮고 안내합니다.
        elif self.memo_data.get('_unreadable'):
            self.text_edit.setPlaceholderText("⚠ 본문을 복호화할 수 없는 메모입니다. (원본은 그대로 보존됩니다)")
        else:
            self.text_edit.setPlaceholderText("")
        self.lock_overlay.refresh()
        self.refresh_lock_badge()

        self._is_updating_from_explorer = False
        is_rolled = getattr(self, '_is_rolled_up', False) or self.memo_data.get('is_rolled_up', False)
        was_rolled = getattr(self, '_is_rolled_up', False)
        rolled_h = self._get_rolled_height()            # settings의 default_rolled_height를 우선 적용
        if is_rolled:
            self.memo_data['rolled_height'] = rolled_h
        # 이미 보이는 창은 지금 자리를 지키고, 숨어 있던 창은 기억해 둔 자리로 갑니다. (잠긴 메모는 암호 입력용 크기로)
        x, y, target_w, target_h = memo_geometry.show_target(
            self.memo_data, is_rolled, was_rolled, self.isVisible(), (self.x(), self.y()), rolled_h,
            getattr(self, '_normal_height', 300))
        x, y = self._clamp_to_screen(self._screen_area_for(x, y, target_w, target_h), x, y, target_w, target_h)
        self._apply_fold_state(is_rolled, x, y, target_w, target_h)

    def closeEvent(self, e: Any) -> None:
        panel = getattr(self, '_side_panel', None)
        if panel is not None:                               # 옆에 붙여 연 패널(알림 설정·이전 내용)도 함께 정리
            self._side_panel = None
            panel.cancel()
            panel.hide()
            panel.deleteLater()
        if getattr(self, '_is_deleting', False):
            self._auto_save_timer.stop()
        else:
            # 아직 저장되지 않은 입력을 닫기 전에 반영
            self.flush_auto_save()
        if hasattr(self, '_title_save_timer'):
            self._title_save_timer.stop()

        if getattr(self, '_is_deleting', False):
            super().closeEvent(e)
            return

        if self.memo_data.get('is_code_memo', False):
            plain_text = self.text_edit.toPlainText().strip()
        else:
            plain_text = clean_plain_text(self.text_edit.toHtml()).strip()

        is_empty_draft = (
            (not plain_text)
            and (not self.memo_data.get('is_manually_saved', False))
            and not self.memo_data.get('is_locked')
            and not self.is_sealed()
        )

        if is_empty_draft:
            self.delete_callback(self)
        else:
            if plain_text and self.memo_data.get('is_draft'):
                self.memo_data['is_draft'] = False
                self.save_callback(self.memo_data)

            self.remember_geometry()
            self.memo_data['is_rolled_up'] = self._is_rolled_up

            self.memo_data['is_visible'] = False
            self.save_callback(self.memo_data)
            self.close_callback(self)
            # 창을 닫으면 암호 메모의 키도 메모리에서 지웁니다.
            self._relock_timer.stop()
            sm = self._sync_manager()
            if sm and self.memo_data.get('is_locked'):
                sm.relock_memo(self.memo_data.get('id', ''))
        super().closeEvent(e)

    def enable_rename(self) -> None:
        self.title_edit.setReadOnly(False)
        pal = self._memo_theme_palette()
        is_rolled = getattr(self, '_is_rolled_up', False)
        rolled_h = self._get_rolled_height()
        title_pt = max(8.0, min(13.0, rolled_h * 0.22)) if is_rolled else 12.0
        self.title_edit.setStyleSheet(f"border:1px solid {pal['accent']}; background:transparent; color:{pal['text']}; font-weight:bold; font-size:{title_pt}pt; border-radius:0px; font-family: {modern_style.UI_FONT};")
        self.title_edit.setFocus()
        self.title_edit.setCursorPosition(len(self.title_edit.text()))

    def handle_rename(self) -> None:
        self.title_edit.setReadOnly(True)
        self._do_title_save()

    def _do_title_save(self) -> None:
        nt = re.sub(r'[\\/*?:"<>|]', "", self.title_edit.text().strip())
        ot = self.memo_data.get('title','')
        if not nt or nt == ot:
            self.title_edit.setText(ot)
        else:
            if self.rename_callback(ot, nt, self.memo_data):
                self.memo_data['title'] = nt
                self.memo_data['updated_at'] = datetime.datetime.now().isoformat()     # 제목을 고친 것도 수정
                self.save_callback(self.memo_data)
            else:
                self.show_toast(f"'{nt}' 제목의 메모가 이미 있습니다.", warn=True)
                self.title_edit.setText(ot)

        is_rolled = getattr(self, '_is_rolled_up', False)
        rolled_h = self._get_rolled_height()
        title_pt = max(8.0, min(13.0, rolled_h * 0.22)) if is_rolled else 12.0
        self.title_edit.setStyleSheet(self._title_color_stylesheet(title_pt))
        self.title_edit.setCursorPosition(0)
        self.title_edit.deselect()
        if getattr(self, 'ui_manager', None) and self.ui_manager.explorer_window and self.ui_manager.explorer_window.isVisible():
            self.ui_manager.explorer_window.update_table()

    def toggle_pin(self) -> None:
        self.memo_data['is_pinned'] = not self.memo_data.get('is_pinned', False)
        self.apply_data()
        self.save_callback(self.memo_data)

    def change_color(self, c: str) -> None:
        self.memo_data['bg_color'] = c
        self.apply_data()
        self.show()
        if hasattr(self, 'bg'):
            self.bg.style().unpolish(self.bg)
            self.bg.style().polish(self.bg)
            self.bg.update()
            self.bg.repaint()
        self.update()
        self.repaint()
        self.text_edit.viewport().update()
        self.text_edit.viewport().repaint()
        self.save_callback(self.memo_data)
        if getattr(self, 'ui_manager', None) and self.ui_manager.explorer_window and self.ui_manager.explorer_window.isVisible():
            self.ui_manager.explorer_window.update_table()
    def mousePressEvent(self, e: Any) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            if hasattr(self, 'title_edit') and not self.title_edit.isReadOnly():
                pos_in_title = self.title_edit.mapFromGlobal(e.globalPosition().toPoint())
                if not self.title_edit.rect().contains(pos_in_title):
                    self.handle_rename()

            self._old_pos = e.globalPosition().toPoint()
            self._press_geom = self.geometry()
            self._drag_start_pos = e.globalPosition().toPoint()
            self._drag_start_win_pos = self.pos()
            self._snap_lock_origin = None
            pos_in_title = self.title_edit.mapFromGlobal(e.globalPosition().toPoint())
            self._drag_from_title = self.title_edit.rect().contains(pos_in_title)

    def mouseMoveEvent(self, e: Any) -> None:
        if getattr(self, '_old_pos', None) and not self.isMaximized():
            curr_global = e.globalPosition().toPoint()

            # 📌 1) 마우스 시작점 기준 1:1 직결 절대 목표 좌표 계산 (딜레이/느림 100% 방지)
            mouse_delta = curr_global - self._drag_start_pos
            target_x = self._drag_start_win_pos.x() + mouse_delta.x()
            target_y = self._drag_start_win_pos.y() + mouse_delta.y()

            screen = QApplication.screenAt(curr_global) or QApplication.primaryScreen()
            scr_geom = screen.availableGeometry()

            is_title_drag = getattr(self, '_drag_from_title', False)
            ctrl_held = bool(QApplication.keyboardModifiers() & Qt.KeyboardModifier.ControlModifier)

            # 📌 2) 제목 드래그 시 위아래 15px 이내 Y축 고정 (좌우 슬라이딩)
            if self._is_rolled_up and is_title_drag and not ctrl_held:
                dy = abs(curr_global.y() - self._drag_start_pos.y())
                if dy <= 15:
                    target_y = self._drag_start_win_pos.y()

            new_x = target_x
            new_y = target_y

            # 📌 3) 15px 이내 실시간 부드러운 0px 레고 블록 스냅 (멈춤 현상 완전 해소)
            if self._is_rolled_up and not ctrl_held and getattr(self, 'ui_manager', None):
                snap_in = 15
                for other_id, other_win in self.ui_manager.memo_windows.items():
                    if other_win is self or not other_win.isVisible() or not other_win._is_rolled_up:
                        continue

                    # 수직 스냅 (상하단 0px 및 상단 맞춤)
                    if abs(target_y - (other_win.y() + other_win.height())) < snap_in:
                        new_y = other_win.y() + other_win.height()
                    elif abs((target_y + self.height()) - other_win.y()) < snap_in:
                        new_y = other_win.y() - self.height()
                    elif abs(target_y - other_win.y()) < snap_in:
                        new_y = other_win.y()

                    # 수평 스냅 (좌우 경계 0px 맞춤)
                    if abs(target_x - other_win.x()) < snap_in:
                        new_x = other_win.x()
                    elif abs((target_x + self.width()) - (other_win.x() + other_win.width())) < snap_in:
                        new_x = other_win.x() + other_win.width() - self.width()
                    elif abs(target_x - (other_win.x() + other_win.width())) < snap_in:
                        new_x = other_win.x() + other_win.width()
                    elif abs((target_x + self.width()) - other_win.x()) < snap_in:
                        new_x = other_win.x() - self.width()

                # 화면 좌측 모서리 0px 스냅
                if abs(target_x - scr_geom.left()) < snap_in:
                    new_x = scr_geom.left()

            # 화면 가장자리에 가까이 가면 딱 붙입니다. 접은 메모뿐 아니라 모든 메모에 적용합니다. (Ctrl 을 누르고 끌면 붙지 않음)
            if not ctrl_held:
                new_x, new_y = screen_bounds.snap_to_edges(scr_geom, new_x, new_y, self.width(), self.height())
            new_x, new_y = screen_bounds.clamp_position(scr_geom, new_x, new_y, self.width(), self.height())

            self.move(new_x, new_y)
            self._old_pos = curr_global

    def mouseReleaseEvent(self, e: Any) -> None:
        self._old_pos = None
        self._drag_from_title = False
        self._snap_lock_origin = None

        # 창을 옮기지도 크기를 바꾸지도 않은 단순 클릭이면 저장하지 않습니다.
        press_geom = getattr(self, '_press_geom', None)
        self._press_geom = None
        if press_geom is not None and press_geom == self.geometry():
            return

        self.remember_geometry()
        self.save_callback(self.memo_data)