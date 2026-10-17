from core.defaults import DEFAULT_SHORTCUTS
from core.sync_manager import is_auto_start_enabled
from ui.themes import app_palette
from ui import modern_style
from ui.wheel_guard import guard_wheel
from ui import screen_bounds
from ui.reminder_ui import DEFAULT_POPUP_CORNER, DEFAULT_QUICK_MINUTES, quick_minutes
from typing import Any
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QPushButton, QLineEdit, QLabel, QComboBox, QCheckBox, QFileDialog, QTabWidget, QGroupBox, QSlider, QAbstractSpinBox, QSizeGrip, QApplication
from PyQt6.QtCore import Qt, QTimer, QUrl
from PyQt6.QtGui import QDesktopServices, QGuiApplication, QFont, QFontMetrics
from ui.settings_general import GeneralTabMixin
from ui.settings_sync import SyncTabMixin
from ui.settings_theme import ThemeTabMixin
from ui.settings_shortcuts import ShortcutTabMixin

# 구글 드라이브 동기화를 준비하는 방법 (README 의 '설정 방법')
SYNC_GUIDE_URL = "https://github.com/DongkyuSeoOssData/Memos#설정-방법"

class SettingsWindow(GeneralTabMixin, SyncTabMixin, ThemeTabMixin, ShortcutTabMixin, QWidget):
    """환경설정 화면.

    embedded=True 면 따로 뜨는 창이 아니라 메모 탐색기 안의 옆 패널로 들어갑니다. (폴더 사이드바처럼 탐색기와 한 창)
    이때는 창 테두리·끌어 옮기기·크기 조절이 없고, 닫기 버튼은 on_close 를 부릅니다.
    """

    def __init__(self, sm: Any, embedded: bool = False) -> None:
        super().__init__()
        self.sm = sm
        self._embedded = embedded
        self.on_close = None                # 패널로 들어갔을 때 닫기 버튼이 부를 함수 (탐색기가 넣어 줌)
        self.ui_font_pt = int(self.sm.settings.get("settings_window_font_pt", 10))
        self.colors = {
            "랜덤": "random",
            "다크그레이": "#2E3440",
            "하늘색": "#E0F2FE",
            "연두색": "#DCFCE7",
            "노란색": "#FEF9C3",
            "분홍색": "#FCE7F3",
            "흰색": "#FFFFFF"
        }
        self.init_ui()
        self.apply_theme_style()
        self.load()
        self._watch_changes()

    def _apply_initial_window_size(self) -> None:
        """저장된 창 크기가 있으면 바로 복원하고, 없으면 가장 작은 모니터 1/6 크기로 초기화합니다."""
        # 저장된 geometry 우선 복원
        saved = self.sm.settings.get('settings_window_geom')
        if saved and len(saved) == 4:
            self.setGeometry(saved[0], saved[1], saved[2], saved[3])
            return
        # 저장된 값 없으면 가장 작은 모니터 1/3×1/3
        screens = QGuiApplication.screens()
        if not screens:
            return
        smallest = min(screens, key=lambda s: s.geometry().width() * s.geometry().height())
        geom = smallest.availableGeometry()
        base_w = int(geom.width() / 3)
        base_h = int(geom.height() / 3)
        target_w = max(base_w, 580)
        target_h = max(base_h, 480)
        target_w = min(target_w, int(geom.width() * 0.8))
        target_h = min(target_h, int(geom.height() * 0.8))
        cx = geom.center().x() - target_w // 2
        cy = geom.center().y() - target_h // 2
        self.setGeometry(cx, cy, target_w, target_h)

    def _apply_font_scale(self) -> None:
        """현재 ui_font_pt 기준으로 폰트 및 행 높이를 전체 적용합니다."""
        base_font = modern_style.app_qfont(self.ui_font_pt)
        self.setFont(base_font)
        self.tabs.setFont(base_font)
        self.shortcut_table.setFont(base_font)
        self.shortcut_table.verticalHeader().setDefaultSectionSize(max(34, int(self.ui_font_pt * 3.0)))
        self.shortcut_table.horizontalHeader().setMinimumHeight(max(30, int(self.ui_font_pt * 2.6)))
        key_width = QFontMetrics(base_font).horizontalAdvance("Ctrl+Shift+Alt+W") + 44
        self.shortcut_table.setColumnWidth(1, max(160, key_width))
        self.shortcut_table.horizontalHeader().setFont(modern_style.app_qfont(max(8, self.ui_font_pt - 1)))
        # 저장 버튼 폰트도 갱신
        if hasattr(self, 'sb'):
            self.sb.setFont(modern_style.app_qfont(self.ui_font_pt + 1))

    def _calc_font_pt_from_size(self) -> int:
        """현재 창 크기를 기반으로 ui_font_pt를 동적으로 계산합니다.

        창 너비 400px 기준 9pt, 매 60px 증가마다 1pt 증가, 최대 16pt.
        """
        w = self.width()
        pt = 9 + max(0, (w - 400) // 60)
        return max(9, min(16, pt))

    def init_ui(self) -> None:
        self.setObjectName("SettingsWindow")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setWindowTitle("Memos Settings")

        # Windows 기본 제목 줄을 쓰면 끌어 옮길 때 가장자리에 붙이거나 화면 안에 묶어 두는 동작이 매끄럽지 않습니다.
        # 탐색기처럼 자체 제목 줄을 그리고 끌기·크기 조절을 직접 처리합니다.
        if not self._embedded:
            self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self._drag_start_cursor = None
        self._drag_start_pos = None

        self.setMinimumSize(580, 440)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(18, 12, 18, 18)
        main_layout.setSpacing(10)

        # 제목 줄: 가운데에 제목, 오른쪽 끝에 최소화·닫기
        self._build_title_bar(main_layout)

        # 저장 버튼 — 탭 위 상단에 배치
        self.sb = QPushButton("  설정 저장")
        self.sb.setCursor(Qt.CursorShape.PointingHandCursor)
        self.sb.setFixedHeight(40)
        self.sb.clicked.connect(self.save)
        main_layout.addWidget(self.sb)

        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)

        # --- TAB 1: 일반 설정 ---
        self._build_general_tab()

        # --- TAB 2: 구글 동기화 ---
        self._build_sync_tab()

        # --- TAB 3: 테마 & 서식 ---
        self._build_theme_tab()

        # --- TAB 4:  단축키 설정 (전체 커스텀) ---
        self._build_shortcut_tab()


        # 화면을 스크롤하다 마우스 아래에 걸린 옵션이 바뀌지 않도록, 값은 클릭으로만 바꾸게 합니다.
        for kind in (QComboBox, QAbstractSpinBox, QSlider):
            guard_wheel(self, self.findChildren(kind))

        if self._embedded:
            # 탐색기 안의 패널: 바깥 여백·최소화 버튼·크기 조절 손잡이가 필요 없고, 닫기는 패널만 닫습니다.
            main_layout.setContentsMargins(0, 0, 0, 0)
            self.btn_win_min.hide()
            self.grip.hide()
            self.btn_win_close.clicked.disconnect()
            self.btn_win_close.clicked.connect(self.request_close)
            self.btn_win_close.setToolTip("환경설정 닫기")
        else:
            self._apply_initial_window_size()

    def _build_title_bar(self, main_layout: Any) -> None:
        """제목 줄: 가운데에 제목, 왼쪽에 알림(토스트), 오른쪽 끝에 최소화·닫기."""
        title_bar = QGridLayout()
        title_bar.setContentsMargins(0, 0, 0, 0)
        title_buttons = QHBoxLayout()
        title_buttons.setSpacing(6)
        title_buttons.addStretch(1)
        self.btn_win_min = QPushButton("")
        self.btn_win_close = QPushButton("")
        for btn, tip, action in ((self.btn_win_min, "최소화", self.showMinimized), (self.btn_win_close, "닫기", self.close)):
            btn.setFixedSize(32, 28)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip(tip)
            btn.clicked.connect(action)
            title_buttons.addWidget(btn)
        title_bar.addLayout(title_buttons, 0, 0)
        self.title_label = QLabel("환경설정")
        self.title_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        title_bar.addWidget(self.title_label, 0, 0, Qt.AlignmentFlag.AlignCenter)
        # 알림(토스트)은 제목 줄 왼쪽의 빈자리에 표시합니다. (버튼이나 설정 글자를 가리지 않는 자리)
        self.toast = QLabel("")
        self.toast.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.toast.hide()
        self._toast_timer = QTimer(self)
        self._toast_timer.setSingleShot(True)
        self._toast_timer.timeout.connect(self.toast.hide)
        title_bar.addWidget(self.toast, 0, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        main_layout.addLayout(title_bar)
        self.grip = QSizeGrip(self)


    def _build_sync_help_group(self) -> Any:
        """동기화 준비 방법 안내."""
        g_help = QGroupBox("동기화 설정 방법")
        g_help_l = QVBoxLayout(g_help)
        g_help_l.setContentsMargins(18, 24, 18, 18)
        g_help_l.setSpacing(8)
        help_hint = QLabel("웹 앱 주소(GAS URL)를 만드는 방법은 GitHub 의 안내에 순서대로 적혀 있습니다. "
                           "구글 앱스 스크립트에 Code.gs 와 Index.html 을 붙여 넣고, 접근 암호를 정한 뒤, 웹 앱으로 배포하면 주소가 나옵니다.")
        help_hint.setProperty("role", "hint")
        help_hint.setWordWrap(True)
        g_help_l.addWidget(help_hint)
        help_row = QHBoxLayout()
        self.btn_sync_guide = QPushButton("설정 방법 보기 (GitHub)")
        self.btn_sync_guide.setFixedHeight(36)
        self.btn_sync_guide.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_sync_guide.setToolTip(SYNC_GUIDE_URL)
        self.btn_sync_guide.clicked.connect(self.open_sync_guide)
        help_row.addWidget(self.btn_sync_guide)
        help_row.addStretch()
        g_help_l.addLayout(help_row)
        return g_help


    def request_close(self) -> None:
        """닫기 버튼. 탐색기 안의 패널이면 패널만 닫고, 따로 뜬 창이면 창을 닫습니다."""
        if self._embedded and self.on_close:
            self.on_close()
        else:
            self.close()

    # ── 화면 밖으로 나가지 않고, 화면보다 커지지 않게 ──────────────────────────
    def _limit_to_screen(self, at: Any = None) -> None:
        if self._embedded or getattr(self, '_limiting', False) or self.isMaximized() or self.isMinimized():
            return
        self._limiting = True
        try:
            limit = screen_bounds.max_inner_size(self, at)
            if limit is not None:
                self.setMaximumSize(*limit)
            screen_bounds.keep_inside(self, at)
        finally:
            self._limiting = False

    def showEvent(self, event: Any) -> None:
        super().showEvent(event)
        self._limit_to_screen()

    # ── 끌어서 옮기기 (탐색기와 같은 방식: 가장자리에 붙고, 화면 밖으로는 나가지 않음) ──
    def mousePressEvent(self, e: Any) -> None:
        if self._embedded:
            e.ignore()                                   # 패널일 때는 탐색기가 끌기를 처리
            return
        if e.button() == Qt.MouseButton.LeftButton and not self.isMaximized():
            self._drag_start_cursor = e.globalPosition().toPoint()
            self._drag_start_pos = self.pos()

    def mouseMoveEvent(self, e: Any) -> None:
        if self._embedded:
            e.ignore()
            return
        if self._drag_start_cursor is None or self.isMaximized():
            return
        ctrl_held = bool(QApplication.keyboardModifiers() & Qt.KeyboardModifier.ControlModifier)
        x, y = screen_bounds.drag_position(self, self._drag_start_cursor, self._drag_start_pos,
                                           e.globalPosition().toPoint(), snap=not ctrl_held)
        self.move(x, y)

    def mouseReleaseEvent(self, e: Any) -> None:
        if self._embedded:
            e.ignore()
            return
        if self._drag_start_cursor is not None:
            self._drag_start_cursor = None
            self._limit_to_screen()         # 다른 모니터로 옮겼으면 그 모니터 크기에 맞춤

    def closeEvent(self, event: Any) -> None:
        """닫힘 시 현재 창 geometry를 settings에 저장하여 다음 실행 시 같은 크기로 열리도록 합니다."""
        if not self._embedded:
            self.sm.settings['settings_window_geom'] = [self.x(), self.y(), self.width(), self.height()]
            self.sm.save_settings(self.sm.settings)
        super().closeEvent(event)


    def open_sync_guide(self) -> None:
        """동기화 설정 방법(구글 앱스 스크립트에 Code.gs · Index.html 넣기, 배포)을 브라우저로 엽니다."""
        QDesktopServices.openUrl(QUrl(SYNC_GUIDE_URL))

    def show_toast(self, text: str, warn: bool = False) -> None:
        """환경설정 창 안에서 알립니다. 제목과 겹치지 않게 남는 너비 안에서만 보여 주고, 넘치면 줄입니다(…)."""
        pal, _ = app_palette(self.sm.settings)
        color = modern_style.DANGER if warn else pal['text']
        self.toast.setStyleSheet(f"color: {color}; background: transparent; font-weight: 700; font-size: {max(9.0, self.ui_font_pt - 1)}pt; "
                                 f"font-family: {modern_style.UI_FONT};")
        full = ("⚠ " if warn else "✓ ") + text
        room = max(80, (self.width() - self.title_label.sizeHint().width()) // 2 - 40)
        self.toast.ensurePolished()
        self.toast.setText(self.toast.fontMetrics().elidedText(full, Qt.TextElideMode.ElideRight, room))
        self.toast.setToolTip(full)
        self.toast.show()
        self._toast_timer.start(4500 if warn else 3000)


    def apply_theme_style(self) -> None:
        self._apply_theme_style()
        if self._embedded:
            # 탐색기와 한 창으로 보이도록 패널 둘레의 테두리를 없앱니다.
            self.setStyleSheet(self.styleSheet() + " QWidget#SettingsWindow { border: none; }")

    def _apply_theme_style(self) -> None:
        is_dark = self.sm.settings.get('app_theme', 'white') == "dark"
        if hasattr(self.sm, 'ui_manager') and hasattr(self.sm.ui_manager, 'get_theme_icon'):
            self.tabs.setTabIcon(0, self.sm.ui_manager.get_theme_icon("setting.svg", is_dark))
            self.tabs.setTabIcon(1, self.sm.ui_manager.get_theme_icon("cloude.svg", is_dark))
            self.tabs.setTabIcon(2, self.sm.ui_manager.get_theme_icon("colorpalette_89189.svg", is_dark))
            self.tabs.setTabIcon(3, self.sm.ui_manager.get_theme_icon("keyboard_119981.svg", is_dark))
            self.btn_win_min.setIcon(self.sm.ui_manager.get_theme_icon("minimize.svg", is_dark))
            self.btn_win_close.setIcon(self.sm.ui_manager.get_theme_icon("close.svg", is_dark, override_color="#FF453A"))
            self.btn_test_url.setIcon(self.sm.ui_manager.get_theme_icon("search.svg", is_dark))
            self.btn_change_path.setIcon(self.sm.ui_manager.get_theme_icon("memo.svg", is_dark))

        self._apply_font_scale()
        modern_style.apply_settings(self)

    def resizeEvent(self, event) -> None:
        """창 크기 변경 시 폰트 크기를 동적으로 재계산하여 적용합니다."""
        super().resizeEvent(event)
        self.grip.move(self.width() - 18, self.height() - 18)
        self.grip.resize(16, 16)
        new_pt = self._calc_font_pt_from_size()
        if new_pt != self.ui_font_pt:
            self.ui_font_pt = new_pt
            self.sm.settings["settings_window_font_pt"] = self.ui_font_pt
            self.apply_theme_style()

    def wheelEvent(self, event) -> None:
        if not (event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
            super().wheelEvent(event)
            return

        delta = event.angleDelta().y()
        if delta == 0:
            return

        self.ui_font_pt = max(9, min(20, self.ui_font_pt + (1 if delta > 0 else -1)))
        self.sm.settings["settings_window_font_pt"] = self.ui_font_pt
        self.apply_theme_style()
        self.sm.save_settings(self.sm.settings)
        event.accept()

    def save(self) -> None:
        # 자동 실행은 레지스트리에 먼저 반영하고, 실제로 반영된 상태를 설정값으로 저장합니다.
        want_auto_start = self.auto_start_cb.isChecked()
        auto_start_ok = self.sm.apply_auto_start(want_auto_start)
        auto_start_now = self.sm.settings.get("auto_start", False)
        self.auto_start_cb.setChecked(auto_start_now)

        self.sm.save_settings(self.collect())

        # 바뀐 설정을 열려 있는 모든 창(탐색기·메모·트레이)에 바로 반영
        self.apply_theme_style()
        ui_manager = getattr(self.sm, 'ui_manager', None)
        if ui_manager and hasattr(ui_manager, 'apply_settings_to_windows'):
            ui_manager.apply_settings_to_windows()
        self.mark_clean()

        if auto_start_ok:
            self.show_toast("설정을 저장했습니다")
        else:
            self.show_toast("저장했지만 자동 실행은 바꾸지 못했습니다", warn=True)

    # ── 저장하지 않은 변경 ───────────────────────────────────────────────────
    # 화면의 값을 모은 것(collect)을 마지막으로 불러오거나 저장했을 때의 것과 견주어, 바뀐 것이 있는지 알아냅니다.
    _NOT_COMPARED = ("settings_window_font_pt", "app_theme")      # 화면에서 고르는 값이 아닌 것

    def _comparable(self) -> dict:
        values = {k: v for k, v in self.collect().items() if k not in self._NOT_COMPARED}
        values["explorer_geom"] = values["explorer_geom"][2:]      # 위치는 탐색기를 옮기면 달라지므로 크기만 견줌
        return values

    def mark_clean(self) -> None:
        """지금 화면의 값을 '저장된 상태'로 삼습니다. (불러온 직후, 저장한 직후)"""
        self._baseline = self._comparable()
        self._refresh_dirty()

    def is_dirty(self) -> bool:
        """화면에서 바꾸고 아직 저장하지 않은 값이 있는지."""
        return getattr(self, '_baseline', None) is not None and self._comparable() != self._baseline

    def _refresh_dirty(self, *args: Any) -> None:
        """저장하지 않은 변경이 있으면 저장 버튼에 표시합니다."""
        if getattr(self, '_baseline', None) is None or getattr(self, '_loading_form', False):
            return
        self.sb.setText("  설정 저장  ●" if self.is_dirty() else "  설정 저장")
        self.sb.setToolTip("저장하지 않은 변경이 있습니다" if self.is_dirty() else "")

    def _watch_changes(self) -> None:
        """값을 바꿀 때마다 저장 버튼의 표시를 맞춥니다."""
        for box in self.findChildren(QComboBox):
            box.currentIndexChanged.connect(self._refresh_dirty)
        for box in self.findChildren(QCheckBox):
            box.toggled.connect(self._refresh_dirty)
        for box in self.findChildren(QAbstractSpinBox):
            if hasattr(box, "valueChanged"):
                box.valueChanged.connect(self._refresh_dirty)
        for box in self.findChildren(QSlider):
            box.valueChanged.connect(self._refresh_dirty)
        for box in (self.url_input, self.token_input, self.path_input):
            box.textChanged.connect(self._refresh_dirty)

    # 화면의 칸 하나가 설정값 하나와 그대로 짝지어지는 것들: (설정 키, 칸의 이름, 기본값)
    # 불러오기(_load_form)와 모으기(collect)가 이 표를 함께 쓰므로, 이런 설정을 더할 때는 칸을 만들고 여기에 한 줄만 넣습니다.
    # 읽고 쓰는 법은 칸의 종류로 정해집니다: 체크 상자 = 켬/끔, 숫자 칸 = 숫자, 글자 칸 = 글자, 고르는 칸 = 항목에 심어 둔 값.
    # 값을 바꿔서 담는 것(색, 글꼴, 휴지통 보관 기간, 탐색기 크기 등)은 표에 넣지 않고 두 함수에 따로 적습니다.
    FIELDS = (
        ("use_sync", "sync_cb", False),
        ("drive_folder_id", "url_input", ""),
        ("drive_access_token", "token_input", ""),
        ("locked_memo_relock_min", "spin_relock_min", 5),
        ("default_font_size", "default_font_size_spin", 11),
        ("auto_eng_kor_convert", "cb_auto_eng_kor", True),
        ("default_code_line_numbers", "cb_code_line_num", True),
        ("default_code_line_bg", "cb_code_line_bg", False),
        ("default_is_pinned", "cb_default_pin", False),
        ("dark_theme_mode", "dark_theme_box", "dark"),
        ("light_theme_mode", "light_theme_box", "white"),
        ("default_memo_width", "spin_memo_width", 350),
        ("default_memo_height", "spin_memo_height", 380),
        ("default_code_memo_width", "spin_code_memo_width", 500),
        ("default_code_memo_height", "spin_code_memo_height", 380),
        ("default_rolled_height", "spin_rolled_height", 53),
        ("ui_style", "ui_style_box", modern_style.DEFAULT_STYLE),
        ("auto_save_idle_sec", "auto_save_interval_box", 60),
        ("explorer_fixed_size", "cb_explorer_fixed", False),
        ("folder_ui", "folder_ui_box", "tabs"),
        ("global_hotkeys", "cb_global_hotkeys", True),
        ("error_report", "cb_error_report", True),
        ("reminder_popup_screen", "popup_screen_box", ""),
        ("reminder_popup_corner", "popup_corner_box", DEFAULT_POPUP_CORNER),
    )
    _SET_QUIETLY = ("dark_theme_box", "light_theme_box")      # 불러올 때 '바뀜' 신호를 내지 않는 칸 (미리보기가 돌지 않게)

    @staticmethod
    def _read_field(box: Any) -> Any:
        if isinstance(box, QCheckBox):
            return box.isChecked()
        if isinstance(box, QComboBox):
            return box.currentData()
        if isinstance(box, QLineEdit):
            return box.text().strip()
        return box.value()

    @staticmethod
    def _write_field(box: Any, value: Any, default: Any) -> None:
        # 설정 파일을 손으로 고쳤거나 깨져서 형식이 맞지 않는 값이 들어 있으면 기본값으로 보여 줍니다.
        if isinstance(box, QCheckBox):
            box.setChecked(bool(value))
        elif isinstance(box, QComboBox):
            index = box.findData(value)
            if index < 0:                                  # 모르는 값이 저장돼 있으면 기본값으로
                index = box.findData(default)
            if index >= 0:
                box.setCurrentIndex(index)
        elif isinstance(box, QLineEdit):
            box.setText(value if isinstance(value, str) else str(default))
        else:
            try:
                box.setValue(int(value))
            except (TypeError, ValueError):
                box.setValue(int(default))

    def collect(self) -> dict:
        """화면의 값을 설정 형식으로 모읍니다. (저장하지는 않음)"""
        auto_start_now = self.auto_start_cb.isChecked()
        shortcuts_dict = {}
        for r in range(self.shortcut_table.rowCount()):
            # 화면에 보이는 이름이 아니라 행에 심어 둔 설정 키로 찾습니다. (이름을 바꿔도 저장이 누락되지 않음)
            key = self.shortcut_table.item(r, 0).data(Qt.ItemDataRole.UserRole)
            if key:
                shortcuts_dict[key] = self.shortcut_table.cellWidget(r, 1).keySequence().toString()

        # 0: 자동 삭제 안 함, -1: 즉시 삭제, 그 외: 보관 일수
        trash_days_map = {0: 0, 1: -1, 2: 15, 3: 30}

        ns = {key: self._read_field(getattr(self, name)) for key, name, _ in self.FIELDS}
        ns.update({
            "local_memo_path": self.path_input.text().strip(),
            "sync_interval_index": self.sync_interval_combo.currentIndex(),
            "auto_start": auto_start_now,
            "reminder_quick_minutes": [spin.value() for spin in self.quick_minute_spins],
            "default_memo_color": list(self.colors.values())[self.default_color_combo.currentIndex()],
            "app_font_family": self.app_font_box.currentFont().family(),
            "default_font_family": self.default_font_box.currentFont().family(),
            "default_code_font_family": self.default_code_font_box.currentFont().family(),
            "default_code_lang": self.default_code_lang_box.currentText(),
            "default_code_theme": "dark" if self.default_code_theme_box.currentIndex() == 0 else "light",
            "default_gen_line_numbers": self.cb_gen_line_num.isChecked(),
            "default_gen_line_bg": self.cb_gen_line_bg.isChecked(),
            "default_show_line_numbers": self.cb_gen_line_num.isChecked(),
            "default_show_line_bg": self.cb_gen_line_bg.isChecked(),
            "trash_auto_delete_days": trash_days_map.get(self.trash_auto_delete_box.currentIndex(), 0),
            "app_theme": self.sm.settings.get("app_theme", "white"),
            "default_memo_opacity": round(self.opacity_slider.value() / 100.0, 2),
            "explorer_geom": self._explorer_geom_from_inputs(),
            "settings_window_font_pt": self.ui_font_pt,
            "shortcuts": shortcuts_dict,
        })
        return ns

    def sel(self) -> None:
        p = QFileDialog.getExistingDirectory(self, "선택", self.path_input.text())
        if p:
            self.path_input.setText(p)

    def load(self) -> None:
        self._loading_form = True
        try:
            self._load_form()
        finally:
            self._loading_form = False
        self.mark_clean()

    def _load_form(self) -> None:
        s = self.sm.settings
        self._fill_popup_screens(str(s.get("reminder_popup_screen", "") or ""))      # 아래 표가 값을 고르기 전에 목록부터
        self._loading_settings = True                      # 화면 스타일을 '고른' 것이 아니라 불러오는 중임을 알림
        try:
            for key, name, default in self.FIELDS:
                box = getattr(self, name)
                quiet = name in self._SET_QUIETLY
                if quiet:
                    box.blockSignals(True)
                self._write_field(box, s.get(key, default), default)
                if quiet:
                    box.blockSignals(False)
        finally:
            self._loading_settings = False
        self.path_input.setText(str(self.sm.local_path))
        self.sync_interval_combo.setCurrentIndex(s.get("sync_interval_index", 0))
        # 설정 파일이 아니라 레지스트리의 실제 등록 상태를 보여줍니다.
        self.auto_start_cb.setChecked(is_auto_start_enabled())
        for spin, minutes in zip(self.quick_minute_spins, (quick_minutes(s) + list(DEFAULT_QUICK_MINUTES))[:3]):
            spin.setValue(minutes)
        # 투명도 슬라이더 로드
        saved_opacity = s.get("default_memo_opacity", 1.0)
        self.opacity_slider.setValue(int(round(saved_opacity * 100)))


        ex_w, ex_h = self._current_explorer_size()
        self.spin_explorer_width.setValue(ex_w)
        self.spin_explorer_height.setValue(ex_h)
        # 탐색기 크기는 탐색기가 놓인 모니터의 작업 영역보다 크게 넣을 수 없습니다.
        area = screen_bounds.work_area(self._explorer_window() or self)
        if area is not None:
            self.spin_explorer_width.setMaximum(max(580, area.width()))
            self.spin_explorer_height.setMaximum(max(440, area.height()))

        self.cb_gen_line_num.setChecked(s.get("default_gen_line_numbers", s.get("default_show_line_numbers", False)))
        self.cb_gen_line_bg.setChecked(s.get("default_gen_line_bg", s.get("default_show_line_bg", False)))

        def_font = s.get("default_font_family", "D2Coding")
        def_code_font = s.get("default_code_font_family", "D2Coding")

        self.default_font_box.setCurrentFont(QFont(def_font))
        app_font = s.get("app_font_family", modern_style.DEFAULT_APP_FONT)
        self.app_font_box.setCurrentFont(QFont(app_font))
        self.app_font_note.setVisible(not modern_style.font_installed(app_font))
        self.default_code_font_box.setCurrentFont(QFont(def_code_font))

        self.default_code_lang_box.setCurrentText(s.get("default_code_lang", "JSON"))
        self.default_code_theme_box.setCurrentIndex(0 if s.get("default_code_theme", "dark") == "dark" else 1)

        curr = s.get("default_memo_color", "#FFFFFF")
        for i, (n, c) in enumerate(self.colors.items()):
            if c == curr:
                self.default_color_combo.setCurrentIndex(i)
                break

        trash_days = s.get("trash_auto_delete_days", 0)
        if trash_days < 0: self.trash_auto_delete_box.setCurrentIndex(1)
        elif trash_days == 15: self.trash_auto_delete_box.setCurrentIndex(2)
        elif trash_days == 30: self.trash_auto_delete_box.setCurrentIndex(3)
        else: self.trash_auto_delete_box.setCurrentIndex(0)

        self._fill_shortcut_table(s.get("shortcuts", {}))

    # (표시 이름, 초) — 마지막 입력 후 자동 저장까지 기다리는 시간
    AUTO_SAVE_INTERVALS = [
        ("1초", 1), ("10초", 10), ("30초", 30),
        ("1분 (기본)", 60), ("5분", 300), ("10분", 600),
    ]


    # ─── 단축키 기본값 딕셔너리 (단일 출처: core/defaults.py) ─────────────────
    DEFAULT_SHORTCUTS = DEFAULT_SHORTCUTS


