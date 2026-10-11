"""메모 창의 화면 만들기: 제목 줄, 본문, 서식 줄, 글꼴 줄.

위젯을 만들어 놓기만 합니다. 메모의 내용과 모양을 입히는 일은 memo_apply 에 있습니다.
(MemoWindow 에 섞어 쓰는 부분)
"""
from ui.memo_editor import MemoTextEdit
from ui.wheel_guard import guard_wheel
from ui.overlay import LockOverlay
from typing import Any
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLineEdit, QLabel, QComboBox, QSizeGrip, QFontComboBox, QCompleter
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QIntValidator


class MemoLayoutMixin:
    """메모 창의 화면 만들기."""

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

        self._build_title_row(bg_l)

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

        self._build_search_bar(cc_layout)

        self._build_format_bar()

        self._build_font_bar()

        # 글꼴 줄은 서식 줄 위에 엽니다. 아래에 열면 서식 줄의 버튼들이 위로 밀려 올라가 자리가 바뀝니다.
        cc_layout.addWidget(self.sub_fmt_widget)
        cc_layout.addLayout(self.fmt_bar)

        self.update_toolbar_button_states()
        bg_l.addWidget(self.content_container)
        self.grip = QSizeGrip(self)

    def _build_title_row(self, bg_l: Any) -> None:
        """제목 줄: 제목 칸과 자물쇠, 코드 언어, 체크리스트 진행, 고정·접기·닫기 버튼."""
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

    def _build_format_bar(self) -> None:
        """서식 줄: 굵게·기울임·취소선, 목록·체크리스트, 코드 정렬, 알림 표시."""
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

        self.btn_toggle_sub_fmt = QPushButton("Aa ▴")
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

    def _build_font_bar(self) -> None:
        """글꼴 줄: 글꼴, 글자 크기, 글자색, 형광펜."""
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
