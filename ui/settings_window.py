from PyQt6.QtCore import QMetaObject, pyqtSlot
from core.defaults import DEFAULT_SHORTCUTS
from core.sync_manager import is_auto_start_enabled
from ui.themes import LIGHT_THEMES, DARK_THEMES, app_palette
from ui import modern_style
from ui.wheel_guard import guard_wheel
from ui import screen_bounds
from ui.reminder_ui import DEFAULT_QUICK_MINUTES, quick_minutes

# 구글 드라이브 동기화를 준비하는 방법 (README 의 '설정 방법')
SYNC_GUIDE_URL = "https://github.com/DongkyuSeoOssData/Memos#설정-방법"
from typing import Any
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QPushButton, QLineEdit, QLabel,
    QComboBox, QCheckBox, QFileDialog, QTableWidget, QTableWidgetItem, QHeaderView, QFrame,
    QFontComboBox, QTabWidget, QKeySequenceEdit, QGroupBox, QScrollArea, QSlider, QSpinBox, QAbstractSpinBox,
    QSizeGrip, QApplication
)
from PyQt6.QtCore import Qt, QTimer, QEvent, QPoint, QUrl
from PyQt6.QtGui import QDesktopServices, QGuiApplication, QColor, QKeySequence, QFont, QFontMetrics
import threading

class SettingsWindow(QWidget):
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
        base_font = QFont(self.sm.settings.get("default_font_family", "D2Coding"), self.ui_font_pt)
        self.setFont(base_font)
        self.tabs.setFont(base_font)
        self.shortcut_table.setFont(base_font)
        self.shortcut_table.verticalHeader().setDefaultSectionSize(max(34, int(self.ui_font_pt * 3.0)))
        self.shortcut_table.horizontalHeader().setMinimumHeight(max(30, int(self.ui_font_pt * 2.6)))
        key_width = QFontMetrics(base_font).horizontalAdvance("Ctrl+Shift+Alt+W") + 44
        self.shortcut_table.setColumnWidth(1, max(160, key_width))
        self.shortcut_table.horizontalHeader().setFont(QFont(base_font.family(), max(8, self.ui_font_pt - 1)))
        # 저장 버튼 폰트도 갱신
        if hasattr(self, 'sb'):
            self.sb.setFont(QFont(base_font.family(), self.ui_font_pt + 1))

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

        # 저장 버튼 — 탭 위 상단에 배치
        self.sb = QPushButton("  설정 저장")
        self.sb.setCursor(Qt.CursorShape.PointingHandCursor)
        self.sb.setFixedHeight(40)
        self.sb.clicked.connect(self.save)
        main_layout.addWidget(self.sb)

        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)

        # --- TAB 1: 일반 설정 ---
        tab_general = QWidget()
        l_gen = QVBoxLayout(tab_general)
        l_gen.setContentsMargins(15, 15, 15, 15)
        l_gen.setSpacing(15)

        g_folder = QGroupBox("폴더 표시 방식")
        g_folder_l = QVBoxLayout(g_folder)
        g_folder_l.setContentsMargins(18, 24, 18, 18)
        g_folder_l.setSpacing(8)
        self.folder_ui_box = QComboBox()
        self.folder_ui_box.addItem("탭 줄 (위쪽에 폴더가 한 줄로)", "tabs")
        self.folder_ui_box.addItem("사이드바 (왼쪽에 폴더 목록)", "sidebar")
        self.folder_ui_box.addItem("드롭다운 (버튼 하나)", "dropdown")
        self.folder_ui_box.setFixedHeight(36)
        g_folder_l.addWidget(self.folder_ui_box)
        folder_hint = QLabel("탭 줄은 폴더가 몇 개 안 될 때, 사이드바는 폴더가 많거나 여러 단계일 때 편합니다. "
                             "사이드바는 탐색기 왼쪽 위의 폴더 버튼으로 열고 닫습니다.")
        folder_hint.setProperty("role", "hint")
        folder_hint.setWordWrap(True)
        g_folder_l.addWidget(folder_hint)
        l_gen.addWidget(g_folder)

        g2 = QGroupBox("암호 메모")
        g2_l = QVBoxLayout(g2)
        g2_l.setContentsMargins(18, 24, 18, 18)
        g2_l.setSpacing(8)
        relock_row = QHBoxLayout()
        relock_row.addWidget(QLabel("마지막 입력 후 자동 잠금:"))
        self.spin_relock_min = QSpinBox()
        self.spin_relock_min.setRange(0, 240)
        self.spin_relock_min.setSuffix(" 분")
        self.spin_relock_min.setSpecialValueText("자동 잠금 안 함")
        self.spin_relock_min.setFixedHeight(34)
        relock_row.addWidget(self.spin_relock_min)
        relock_row.addStretch()
        g2_l.addLayout(relock_row)
        relock_hint = QLabel("메모 창 우클릭 → '이 메모에 암호 걸기'로 원하는 메모만 암호화합니다. 암호를 잊으면 복구할 수 없습니다.")
        relock_hint.setProperty("role", "hint")
        relock_hint.setWordWrap(True)
        g2_l.addWidget(relock_hint)
        l_gen.addWidget(g2)

        g4 = QGroupBox("시스템 편의 및 실행 옵션")
        g4_l = QVBoxLayout(g4)
        g4_l.setContentsMargins(18, 24, 18, 18)
        g4_l.setSpacing(12)

        self.cb_default_pin = QCheckBox("새 메모 실행 시 화면 고정 기본 적용")
        self.cb_auto_eng_kor = QCheckBox("한/영 영타 오타 자동 변환기 사용")
        self.auto_start_cb = QCheckBox("윈도우 시작 시 자동 실행")

        self.cb_gen_line_num = QCheckBox("일반 메모: 최초 실행 시 행번호 표시")
        self.cb_gen_line_bg = QCheckBox("일반 메모: 최초 실행 시 줄노트 배경 표시")
        self.cb_code_line_num = QCheckBox("코드 메모: 최초 실행 시 행번호 표시")
        self.cb_code_line_bg = QCheckBox("코드 메모: 최초 실행 시 줄노트 배경 표시")

        for cb_item in [
            self.cb_default_pin, self.cb_auto_eng_kor, self.auto_start_cb,
            self.cb_gen_line_num, self.cb_gen_line_bg,
            self.cb_code_line_num, self.cb_code_line_bg
        ]:
            g4_l.addWidget(cb_item)

        g4_l.addWidget(QLabel("자동 저장 대기 시간 (마지막 입력 후):"))
        self.auto_save_interval_box = QComboBox()
        for label, sec in self.AUTO_SAVE_INTERVALS:
            self.auto_save_interval_box.addItem(label, sec)
        self.auto_save_interval_box.setFixedHeight(40)
        g4_l.addWidget(self.auto_save_interval_box)

        g4_l.addWidget(QLabel("휴지통 보관 기간:"))
        self.trash_auto_delete_box = QComboBox()
        self.trash_auto_delete_box.addItems(["없음 (수동 비우기)", "즉시 삭제 (0일)", "15일 경과 시 자동 삭제", "30일 경과 시 자동 삭제"])
        self.trash_auto_delete_box.setFixedHeight(40)
        g4_l.addWidget(self.trash_auto_delete_box)
        l_gen.addWidget(g4)

        g_alarm = QGroupBox("알림 설정의 빠른 선택")
        g_alarm_l = QVBoxLayout(g_alarm)
        g_alarm_l.setContentsMargins(18, 24, 18, 18)
        g_alarm_l.setSpacing(8)
        self.quick_minute_spins = []
        for n in range(3):                               # 버튼 하나에 한 줄씩
            alarm_row = QHBoxLayout()
            alarm_row.setSpacing(10)
            alarm_row.addWidget(QLabel(f"버튼 {n + 1}:"))
            spin = QSpinBox()
            spin.setRange(1, 10080)                      # 1분 ~ 7일
            spin.setSuffix(" 분 뒤")
            spin.setFixedHeight(34)
            spin.setMinimumWidth(140)
            alarm_row.addWidget(spin)
            alarm_row.addStretch()
            g_alarm_l.addLayout(alarm_row)
            self.quick_minute_spins.append(spin)
        alarm_hint = QLabel("알림 설정 화면에서 한 번에 고르는 버튼 세 개입니다. 60분은 '1시간 뒤', 1440분은 '1일 뒤'처럼 보입니다.")
        alarm_hint.setProperty("role", "hint")
        alarm_hint.setWordWrap(True)
        g_alarm_l.addWidget(alarm_hint)
        l_gen.addWidget(g_alarm)


        g_guide = QGroupBox("사용 안내")
        g_guide_l = QVBoxLayout(g_guide)
        g_guide_l.setContentsMargins(18, 24, 18, 18)
        g_guide_l.setSpacing(8)
        guide_row = QHBoxLayout()
        self.btn_make_guide = QPushButton("사용 안내 메모 만들기")
        self.btn_make_guide.setFixedHeight(36)
        self.btn_make_guide.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_make_guide.clicked.connect(self.make_guide_memos)
        guide_row.addWidget(self.btn_make_guide)
        guide_row.addStretch()
        g_guide_l.addLayout(guide_row)
        guide_hint = QLabel("메모 창 · 메모 탐색기 · 환경설정 사용법을 적은 메모 세 개를 '사용 안내' 폴더에 만듭니다. "
                            "처음 실행했을 때 만들어지는 것과 같은 메모이며, 읽은 뒤에는 지워도 됩니다.")
        guide_hint.setProperty("role", "hint")
        guide_hint.setWordWrap(True)
        g_guide_l.addWidget(guide_hint)
        l_gen.addWidget(g_guide)

        l_gen.addStretch()

        # QScrollArea로 감싸서 창이 작아져도 스크롤로 접근 가능하게 처리
        scroll_gen = QScrollArea()
        scroll_gen.setWidget(tab_general)
        scroll_gen.setWidgetResizable(True)
        scroll_gen.setFrameShape(QFrame.Shape.NoFrame)
        scroll_gen.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_gen.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.tabs.addTab(scroll_gen, "일반 설정")

        # --- TAB 2: 구글 동기화 ---
        tab_sync = QWidget()
        l_sync = QVBoxLayout(tab_sync)
        l_sync.setContentsMargins(15, 15, 15, 15)
        l_sync.setSpacing(15)

        g1 = QGroupBox("구글 드라이브 백업 및 동기화 설정")
        g1_l = QVBoxLayout(g1)
        g1_l.setContentsMargins(18, 24, 18, 18)
        g1_l.setSpacing(12)

        self.sync_cb = QCheckBox("구글 드라이브 동기화 활성화")
        self.sync_cb.setProperty("role", "value")
        g1_l.addWidget(self.sync_cb)

        g1_l.addWidget(QLabel("GAS Web App URL:"))
        url_box = QHBoxLayout()
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://script.google.com/macros/s/.../exec")
        self.url_input.setFixedHeight(40)

        self.btn_test_url = QPushButton(" 연결 테스트")
        self.btn_test_url.setFixedHeight(40)
        self.btn_test_url.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_test_url.clicked.connect(self.test_gas_url)

        url_box.addWidget(self.url_input)
        url_box.addWidget(self.btn_test_url)
        g1_l.addLayout(url_box)

        g1_l.addWidget(QLabel("동기화 접근 암호 (선택):"))
        self.token_input = QLineEdit()
        self.token_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.token_input.setPlaceholderText("스크립트 속성 ACCESS_TOKEN 에 넣은 값")
        self.token_input.setFixedHeight(40)
        g1_l.addWidget(self.token_input)
        token_hint = QLabel("스크립트에 ACCESS_TOKEN 을 설정하면 이 값을 아는 기기만 메모를 읽고 쓸 수 있습니다. "
                            "모바일 화면에서도 같은 값을 입력합니다.")
        token_hint.setProperty("role", "hint")
        token_hint.setWordWrap(True)
        g1_l.addWidget(token_hint)

        g1_l.addWidget(QLabel("로컬 메모 저장 위치:"))
        ph = QHBoxLayout()
        self.path_input = QLineEdit()
        self.path_input.setReadOnly(True)
        self.path_input.setFixedHeight(40)
        self.btn_change_path = QPushButton(" 경로 변경")
        self.btn_change_path.setFixedHeight(40)
        self.btn_change_path.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_change_path.clicked.connect(self.sel)
        ph.addWidget(self.path_input)
        ph.addWidget(self.btn_change_path)
        g1_l.addLayout(ph)

        g1_l.addWidget(QLabel("변경 후 동기화까지 기다리는 시간:"))
        self.sync_interval_combo = QComboBox()
        self.sync_interval_combo.addItems(["1분 뒤", "10분 뒤", "30분 뒤", "1시간 뒤"])
        self.sync_interval_combo.setFixedHeight(40)
        g1_l.addWidget(self.sync_interval_combo)
        sync_hint = QLabel("정해진 간격마다 무조건 동기화하지 않습니다. 메모를 고치면 이 시간만큼 기다렸다가 바뀐 메모만 올립니다. "
                           "고친 것이 없을 때는 다른 기기의 변경이 있는지 15분마다 파일 목록만 확인합니다. "
                           "탐색기의 동기화 버튼을 누르면 바로 동기화합니다.")
        sync_hint.setProperty("role", "hint")
        sync_hint.setWordWrap(True)
        g1_l.addWidget(sync_hint)
        l_sync.addWidget(g1)
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
        l_sync.addWidget(g_help)

        l_sync.addStretch()

        scroll_sync = QScrollArea()
        scroll_sync.setWidget(tab_sync)
        scroll_sync.setWidgetResizable(True)
        scroll_sync.setFrameShape(QFrame.Shape.NoFrame)
        scroll_sync.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_sync.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.tabs.addTab(scroll_sync, "구글 동기화")

        # --- TAB 3: 테마 & 서식 ---
        tab_font = QWidget()
        l_font = QVBoxLayout(tab_font)
        l_font.setContentsMargins(12, 12, 12, 12)
        l_font.setSpacing(12)

        g3 = QGroupBox("기본 서식 / 폰트 / 코드 테마")
        g3_l = QVBoxLayout(g3)
        g3_l.setContentsMargins(14, 22, 14, 14)
        g3_l.setSpacing(8)

        g3_l.addWidget(QLabel("기본 메모 폰트:"))
        self.default_font_box = QFontComboBox()
        self.default_font_box.setFixedHeight(36)
        g3_l.addWidget(self.default_font_box)

        g3_l.addWidget(QLabel("코드 메모 폰트:"))
        self.default_code_font_box = QFontComboBox()
        self.default_code_font_box.setFixedHeight(36)
        g3_l.addWidget(self.default_code_font_box)

        g3_l.addWidget(QLabel("기본 폰트 크기 (pt):"))
        self.default_font_size_spin = QSpinBox()
        self.default_font_size_spin.setRange(6, 72)
        self.default_font_size_spin.setValue(11)
        self.default_font_size_spin.setSuffix(" pt")
        self.default_font_size_spin.setFixedHeight(36)
        g3_l.addWidget(self.default_font_size_spin)

        g3_l.addWidget(QLabel("코드 기본 언어:"))
        self.default_code_lang_box = QComboBox()
        self.default_code_lang_box.addItems(["JSON", "C#", "VB.NET", "Power Automate", "PowerShell", "Batch (CMD)", "SQL", "Markdown", "Python", "JavaScript", "HTML", "CSS", "C++", "Java"])
        self.default_code_lang_box.setFixedHeight(36)
        g3_l.addWidget(self.default_code_lang_box)

        g3_l.addWidget(QLabel("코드 기본 테마:"))
        self.default_code_theme_box = QComboBox()
        self.default_code_theme_box.addItems(["Atom One Dark", "라이트 모드"])
        self.default_code_theme_box.setFixedHeight(36)
        g3_l.addWidget(self.default_code_theme_box)

        g3_l.addWidget(QLabel("다크 모드 스타일:"))
        self.dark_theme_box = QComboBox()
        for k, v in DARK_THEMES.items():
            self.dark_theme_box.addItem(v["name"], k)
        self.dark_theme_box.setFixedHeight(36)
        g3_l.addWidget(self.dark_theme_box)

        g3_l.addWidget(QLabel("라이트 모드 스타일:"))
        self.light_theme_box = QComboBox()
        for k, v in LIGHT_THEMES.items():
            self.light_theme_box.addItem(v["name"], k)
        self.light_theme_box.setFixedHeight(36)
        g3_l.addWidget(self.light_theme_box)

        def _on_theme_style_changed():
            self.sm.settings["dark_theme_mode"] = self.dark_theme_box.currentData()
            self.sm.settings["light_theme_mode"] = self.light_theme_box.currentData()
            self.apply_theme_style()
            if hasattr(self.sm, 'ui_manager') and self.sm.ui_manager:
                if self.sm.ui_manager.explorer_window and self.sm.ui_manager.explorer_window.isVisible():
                    self.sm.ui_manager.explorer_window.apply_theme_style()
                for w in self.sm.ui_manager.memo_windows.values():
                    if w.isVisible():
                        w.apply_data()
        self.dark_theme_box.currentIndexChanged.connect(lambda _: _on_theme_style_changed())
        self.light_theme_box.currentIndexChanged.connect(lambda _: _on_theme_style_changed())

        g3_l.addWidget(QLabel("일반 메모 기본 색상:"))
        self.default_color_combo = QComboBox()
        self.default_color_combo.setFixedHeight(36)
        for idx, (name, color_hex) in enumerate(self.colors.items()):
            self.default_color_combo.addItem(name)
            if color_hex != "random":
                self.default_color_combo.setItemData(idx, QColor(color_hex), Qt.ItemDataRole.BackgroundRole)
        g3_l.addWidget(self.default_color_combo)

        # 기본 투명도 설정 그룹
        g_opacity = QGroupBox("새 메모 기본 투명도 (불투명 100% 기본)")
        g_opacity_l = QVBoxLayout(g_opacity)
        g_opacity_l.setContentsMargins(14, 22, 14, 14)
        g_opacity_l.setSpacing(8)

        opa_row = QHBoxLayout()
        self.opacity_value_label = QLabel("100%  (완전 불투명 — 권장)")
        self.opacity_value_label.setProperty("role", "value")
        opa_row.addWidget(self.opacity_value_label)
        opa_row.addStretch()
        g_opacity_l.addLayout(opa_row)

        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(20, 100)
        self.opacity_slider.setValue(100)
        self.opacity_slider.setFixedHeight(30)
        def _settings_opacity_changed(val: int) -> None:
            if val == 100:
                self.opacity_value_label.setText(f"{val}%  (완전 불투명 — 권장)")
            elif val >= 80:
                self.opacity_value_label.setText(f"{val}%  (약간 투명)")
            elif val >= 60:
                self.opacity_value_label.setText(f"{val}%  (반투명)")
            else:
                self.opacity_value_label.setText(f"{val}%  (많이 투명)")
        self.opacity_slider.valueChanged.connect(_settings_opacity_changed)
        g_opacity_l.addWidget(self.opacity_slider)

        opa_hint = QLabel("※ 개별 메모 우클릭 메뉴에서도 개별 조절 가능합니다.")
        opa_hint.setProperty("role", "hint")
        opa_hint.setWordWrap(True)
        g_opacity_l.addWidget(opa_hint)

        # 메모 기본 실행 크기 설정 그룹 — 2열 그리드
        g_size = QGroupBox("메모 기본 실행 크기 (일반 & 코드)")
        g_size_l = QGridLayout(g_size)
        g_size_l.setContentsMargins(14, 22, 14, 14)
        g_size_l.setSpacing(8)

        self.spin_memo_width = QSpinBox()
        self.spin_memo_width.setRange(200, 1920)
        self.spin_memo_width.setSuffix(" px")
        self.spin_memo_width.setFixedHeight(34)

        self.spin_memo_height = QSpinBox()
        self.spin_memo_height.setRange(150, 1080)
        self.spin_memo_height.setSuffix(" px")
        self.spin_memo_height.setFixedHeight(34)

        self.spin_code_memo_width = QSpinBox()
        self.spin_code_memo_width.setRange(200, 1920)
        self.spin_code_memo_width.setSuffix(" px")
        self.spin_code_memo_width.setFixedHeight(34)

        self.spin_code_memo_height = QSpinBox()
        self.spin_code_memo_height.setRange(150, 1080)
        self.spin_code_memo_height.setSuffix(" px")
        self.spin_code_memo_height.setFixedHeight(34)

        # 일반 메모: 레이블-스핀박스 2열 배치
        g_size_l.addWidget(QLabel("일반 가로:"), 0, 0)
        g_size_l.addWidget(self.spin_memo_width, 0, 1)
        g_size_l.addWidget(QLabel("일반 세로:"), 1, 0)
        g_size_l.addWidget(self.spin_memo_height, 1, 1)
        g_size_l.addWidget(QLabel("코드 가로:"), 2, 0)
        g_size_l.addWidget(self.spin_code_memo_width, 2, 1)
        g_size_l.addWidget(QLabel("코드 세로:"), 3, 0)
        g_size_l.addWidget(self.spin_code_memo_height, 3, 1)
        g_size_l.setColumnStretch(1, 1)

        # 접힌 메모 크기 설정 그룹
        g_rolled = QGroupBox("메모 접힌(—) 상태 높이 설정")
        g_rolled_l = QVBoxLayout(g_rolled)
        g_rolled_l.setContentsMargins(14, 22, 14, 14)
        g_rolled_l.setSpacing(8)

        rolled_row = QHBoxLayout()
        rolled_row.addWidget(QLabel("접힌 높이:"))
        self.spin_rolled_height = QSpinBox()
        self.spin_rolled_height.setRange(36, 120)   # 최소 36px(아이콘+제목 보이는 최소치), 최대 120px
        self.spin_rolled_height.setValue(53)
        self.spin_rolled_height.setSuffix(" px")
        self.spin_rolled_height.setFixedHeight(34)
        self.spin_rolled_height.setToolTip("메모를 접었을 때의 창 높이입니다. (36~120px)")
        rolled_row.addWidget(self.spin_rolled_height)
        rolled_row.addStretch()
        g_rolled_l.addLayout(rolled_row)

        rolled_hint = QLabel("✖ 제목줄·아이콘 크기가 높이에 비례하여 자동 조정됩니다. (\uc5ec백 최소: 36px 권장)")
        rolled_hint.setProperty("role", "hint")
        rolled_hint.setWordWrap(True)
        g_rolled_l.addWidget(rolled_hint)

        # 디자인 스타일 (Modern ↔ Neo 전환)
        g_style = QGroupBox("디자인 스타일")
        g_style_l = QVBoxLayout(g_style)
        g_style_l.setContentsMargins(14, 22, 14, 14)
        g_style_l.setSpacing(8)
        self.ui_style_box = QComboBox()
        self.ui_style_box.addItem("Modern (기본)", "modern")
        self.ui_style_box.addItem("Neo (미니멀 · 선 중심)", "neo")
        self.ui_style_box.setFixedHeight(36)

        def _on_ui_style_picked() -> None:
            # Neo 디자인을 고르면 어울리는 Mono 색 테마를 함께 골라 줍니다. (저장 전에 다시 바꿀 수 있음)
            if self.ui_style_box.currentData() != "neo" or getattr(self, "_loading_settings", False):
                return
            for box in (self.dark_theme_box, self.light_theme_box):
                idx = box.findData("mono")
                if idx >= 0:
                    box.setCurrentIndex(idx)
        self.ui_style_box.currentIndexChanged.connect(lambda _: _on_ui_style_picked())

        g_style_l.addWidget(self.ui_style_box)
        style_hint = QLabel("탐색기·환경설정·메모 창의 모양을 바꿉니다. 저장하면 바로 적용됩니다. "
                            "Neo는 아래 색 테마의 'Mono Paper / Mono Graphite'와 가장 잘 어울립니다.")
        style_hint.setProperty("role", "hint")
        style_hint.setWordWrap(True)
        g_style_l.addWidget(style_hint)
        l_font.addWidget(g_style)

        l_font.addWidget(g3)
        l_font.addWidget(g_opacity)
        l_font.addWidget(g_size)
        l_font.addWidget(g_rolled)

        # 메모 탐색기 크기 설정 그룹
        g_explorer = QGroupBox("메모 탐색기 크기")
        g_explorer_l = QGridLayout(g_explorer)
        g_explorer_l.setContentsMargins(14, 22, 14, 14)
        g_explorer_l.setSpacing(8)

        self.spin_explorer_width = QSpinBox()
        self.spin_explorer_width.setRange(580, 3840)
        self.spin_explorer_width.setSuffix(" px")
        self.spin_explorer_width.setFixedHeight(34)

        self.spin_explorer_height = QSpinBox()
        self.spin_explorer_height.setRange(440, 2160)
        self.spin_explorer_height.setSuffix(" px")
        self.spin_explorer_height.setFixedHeight(34)

        self.cb_explorer_fixed = QCheckBox("탐색기 크기 고정 (화면 이동·모니터 변경 시에도 크기 유지)")

        g_explorer_l.addWidget(QLabel("탐색기 가로:"), 0, 0)
        g_explorer_l.addWidget(self.spin_explorer_width, 0, 1)
        g_explorer_l.addWidget(QLabel("탐색기 세로:"), 1, 0)
        g_explorer_l.addWidget(self.spin_explorer_height, 1, 1)
        g_explorer_l.addWidget(self.cb_explorer_fixed, 2, 0, 1, 2)
        g_explorer_l.setColumnStretch(1, 1)
        l_font.addWidget(g_explorer)

        l_font.addStretch()

        scroll_font = QScrollArea()
        scroll_font.setWidget(tab_font)
        scroll_font.setWidgetResizable(True)
        scroll_font.setFrameShape(QFrame.Shape.NoFrame)
        scroll_font.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_font.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.tabs.addTab(scroll_font, "테마 & 서식")

        # --- TAB 4:  단축키 설정 (전체 커스텀) ---
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

    def make_guide_memos(self) -> None:
        ui_manager = getattr(self.sm, 'ui_manager', None)
        if ui_manager is None:
            return
        ui_manager.remake_guide_memos()
        self.show_toast("사용 안내 메모를 만들었습니다")

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

    def test_gas_url(self) -> None:
        url = self.url_input.text().strip()
        if not url or not url.startswith("http"):
            self.show_toast("http(s):// 로 시작하는 주소를 입력하세요", warn=True)
            return

        self.sm.drive_api.set_web_app_url(url)
        self.sm.drive_api.set_access_token(self.token_input.text())
        self.show_toast("연결 테스트 중…")

        def _async_ping():
            try:
                res = self.sm.drive_api.ping_web_app()
                if res:
                    QMetaObject.invokeMethod(self, "_on_ping_success", Qt.ConnectionType.QueuedConnection)
                else:
                    QMetaObject.invokeMethod(self, "_on_ping_failed", Qt.ConnectionType.QueuedConnection)
            except Exception:
                QMetaObject.invokeMethod(self, "_on_ping_failed", Qt.ConnectionType.QueuedConnection)

        threading.Thread(target=_async_ping, daemon=True).start()

    @pyqtSlot()
    def _on_ping_success(self) -> None:
        self.sync_cb.setChecked(True)
        self.show_toast("연결 성공 (동기화 켬)")

    @pyqtSlot()
    def _on_ping_failed(self) -> None:
        self.show_toast("연결 실패 (주소·접근 암호 확인)", warn=True)

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

        ns = {
            "use_sync": self.sync_cb.isChecked(),
            "drive_folder_id": self.url_input.text().strip(),
            "drive_access_token": self.token_input.text().strip(),
            "local_memo_path": self.path_input.text().strip(),
            "sync_interval_index": self.sync_interval_combo.currentIndex(),
            "auto_start": auto_start_now,
            "locked_memo_relock_min": self.spin_relock_min.value(),
            "reminder_quick_minutes": [spin.value() for spin in self.quick_minute_spins],
            "default_memo_color": list(self.colors.values())[self.default_color_combo.currentIndex()],
            "default_font_family": self.default_font_box.currentFont().family(),
            "default_code_font_family": self.default_code_font_box.currentFont().family(),
            "default_font_size": self.default_font_size_spin.value(),
            "default_code_lang": self.default_code_lang_box.currentText(),
            "default_code_theme": "dark" if self.default_code_theme_box.currentIndex() == 0 else "light",
            "auto_eng_kor_convert": self.cb_auto_eng_kor.isChecked(),
            "default_gen_line_numbers": self.cb_gen_line_num.isChecked(),
            "default_gen_line_bg": self.cb_gen_line_bg.isChecked(),
            "default_code_line_numbers": self.cb_code_line_num.isChecked(),
            "default_code_line_bg": self.cb_code_line_bg.isChecked(),
            "default_show_line_numbers": self.cb_gen_line_num.isChecked(),
            "default_show_line_bg": self.cb_gen_line_bg.isChecked(),
            "default_is_pinned": self.cb_default_pin.isChecked(),
            "trash_auto_delete_days": trash_days_map.get(self.trash_auto_delete_box.currentIndex(), 0),
            "app_theme": self.sm.settings.get("app_theme", "white"),
            "dark_theme_mode": self.dark_theme_box.currentData(),
            "light_theme_mode": self.light_theme_box.currentData(),
            "default_memo_opacity": round(self.opacity_slider.value() / 100.0, 2),
            "default_memo_width": self.spin_memo_width.value(),
            "default_memo_height": self.spin_memo_height.value(),
            "default_code_memo_width": self.spin_code_memo_width.value(),
            "default_code_memo_height": self.spin_code_memo_height.value(),
            "default_rolled_height": self.spin_rolled_height.value(),
            "ui_style": self.ui_style_box.currentData(),
            "auto_save_idle_sec": self.auto_save_interval_box.currentData(),
            "explorer_fixed_size": self.cb_explorer_fixed.isChecked(),
            "folder_ui": self.folder_ui_box.currentData(),
            "explorer_geom": self._explorer_geom_from_inputs(),
            "settings_window_font_pt": self.ui_font_pt,
            "shortcuts": shortcuts_dict,
            "global_hotkeys": self.cb_global_hotkeys.isChecked(),
        }
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
        self.sync_cb.setChecked(s.get("use_sync", False))
        self.url_input.setText(s.get("drive_folder_id",""))
        self.token_input.setText(s.get("drive_access_token", ""))
        self.path_input.setText(str(self.sm.local_path))
        self.sync_interval_combo.setCurrentIndex(s.get("sync_interval_index", 0))
        # 설정 파일이 아니라 레지스트리의 실제 등록 상태를 보여줍니다.
        self.auto_start_cb.setChecked(is_auto_start_enabled())
        self.spin_relock_min.setValue(int(s.get("locked_memo_relock_min", 5)))
        for spin, minutes in zip(self.quick_minute_spins, (quick_minutes(s) + list(DEFAULT_QUICK_MINUTES))[:3]):
            spin.setValue(minutes)
        self.cb_default_pin.setChecked(s.get("default_is_pinned", False))
        self.cb_auto_eng_kor.setChecked(s.get("auto_eng_kor_convert", True))
        # 투명도 슬라이더 로드
        saved_opacity = s.get("default_memo_opacity", 1.0)
        self.opacity_slider.setValue(int(round(saved_opacity * 100)))

        self.spin_memo_width.setValue(s.get("default_memo_width", 350))
        self.spin_memo_height.setValue(s.get("default_memo_height", 380))
        self.spin_code_memo_width.setValue(s.get("default_code_memo_width", 500))
        self.spin_code_memo_height.setValue(s.get("default_code_memo_height", 380))
        self.spin_rolled_height.setValue(s.get("default_rolled_height", 53))
        style_idx = self.ui_style_box.findData(s.get("ui_style", modern_style.DEFAULT_STYLE))
        self._loading_settings = True
        self.ui_style_box.setCurrentIndex(style_idx if style_idx >= 0 else self.ui_style_box.findData("modern"))
        self._loading_settings = False

        idx = self.auto_save_interval_box.findData(s.get("auto_save_idle_sec", 60))
        self.auto_save_interval_box.setCurrentIndex(idx if idx >= 0 else self.auto_save_interval_box.findData(60))

        ex_w, ex_h = self._current_explorer_size()
        self.spin_explorer_width.setValue(ex_w)
        self.spin_explorer_height.setValue(ex_h)
        self.cb_explorer_fixed.setChecked(s.get("explorer_fixed_size", False))
        # 탐색기 크기는 탐색기가 놓인 모니터의 작업 영역보다 크게 넣을 수 없습니다.
        area = screen_bounds.work_area(self._explorer_window() or self)
        if area is not None:
            self.spin_explorer_width.setMaximum(max(580, area.width()))
            self.spin_explorer_height.setMaximum(max(440, area.height()))
        self.folder_ui_box.setCurrentIndex(max(0, self.folder_ui_box.findData(s.get("folder_ui", "tabs"))))

        self.cb_gen_line_num.setChecked(s.get("default_gen_line_numbers", s.get("default_show_line_numbers", False)))
        self.cb_gen_line_bg.setChecked(s.get("default_gen_line_bg", s.get("default_show_line_bg", False)))
        self.cb_code_line_num.setChecked(s.get("default_code_line_numbers", True))
        self.cb_code_line_bg.setChecked(s.get("default_code_line_bg", False))

        def_font = s.get("default_font_family", "D2Coding")
        def_code_font = s.get("default_code_font_family", "D2Coding")

        self.default_font_box.setCurrentFont(QFont(def_font))
        self.default_code_font_box.setCurrentFont(QFont(def_code_font))
        self.default_font_size_spin.setValue(s.get("default_font_size", 11))

        self.default_code_lang_box.setCurrentText(s.get("default_code_lang", "JSON"))
        self.default_code_theme_box.setCurrentIndex(0 if s.get("default_code_theme", "dark") == "dark" else 1)

        dark_mode_val = s.get("dark_theme_mode", "dark")
        self.dark_theme_box.blockSignals(True)
        for i in range(self.dark_theme_box.count()):
            if self.dark_theme_box.itemData(i) == dark_mode_val:
                self.dark_theme_box.setCurrentIndex(i)
                break
        self.dark_theme_box.blockSignals(False)

        light_mode_val = s.get("light_theme_mode", "white")
        self.light_theme_box.blockSignals(True)
        for i in range(self.light_theme_box.count()):
            if self.light_theme_box.itemData(i) == light_mode_val:
                self.light_theme_box.setCurrentIndex(i)
                break
        self.light_theme_box.blockSignals(False)

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
        self.cb_global_hotkeys.setChecked(bool(s.get("global_hotkeys", True)))

    # (표시 이름, 초) — 마지막 입력 후 자동 저장까지 기다리는 시간
    AUTO_SAVE_INTERVALS = [
        ("1초", 1), ("10초", 10), ("30초", 30),
        ("1분 (기본)", 60), ("5분", 300), ("10분", 600),
    ]

    def _explorer_window(self) -> Any:
        return getattr(getattr(self.sm, 'ui_manager', None), 'explorer_window', None)

    def _current_explorer_size(self) -> tuple:
        explorer = self._explorer_window()
        if explorer and not explorer.isMaximized():
            return explorer.content_width(), explorer.height()
        geom = self.sm.settings.get("explorer_geom")
        if geom and len(geom) == 4:
            return int(geom[2]), int(geom[3])
        return 620, 480

    def _explorer_geom_from_inputs(self) -> list:
        """입력한 가로·세로에 현재 탐색기 위치를 합쳐 explorer_geom 형식으로 돌려줍니다."""
        explorer = self._explorer_window()
        geom = self.sm.settings.get("explorer_geom")
        if explorer:
            x, y = explorer.content_x(), explorer.y()     # 왼쪽에 붙은 사이드바·패널은 탐색기 위치에 넣지 않음
        elif geom and len(geom) == 4:
            x, y = int(geom[0]), int(geom[1])
        else:
            x, y = 100, 100
        return [x, y, self.spin_explorer_width.value(), self.spin_explorer_height.value()]

    # ─── 단축키 기본값 딕셔너리 (단일 출처: core/defaults.py) ─────────────────
    DEFAULT_SHORTCUTS = DEFAULT_SHORTCUTS

    def _reset_shortcuts_to_default(self) -> None:
        """단축키 테이블을 DEFAULT_SHORTCUTS 기본값으로 초기화합니다.

        이 메서드는 UI만 변경하며, 실제 적용은 저장 버튼을 눌러야 합니다.
        """
        self._fill_shortcut_table(self.DEFAULT_SHORTCUTS)
        self._refresh_dirty()
        self.show_toast("기본값으로 되돌림 · 저장해야 적용")

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
        ("화면 항상 고정(Pin) 토글",   "toggle_pin",           "다른 창 위에 항상 표시"),
        ("현재 메모 삭제",            "delete_memo",          "현재 포커스된 메모 삭제"),
        ("행번호 표시 토글",           "toggle_line_numbers",  "행 번호 영역 켜기/끄기"),
        ("줄노트 배경 토글",           "toggle_line_bg",       "줄노트 줄무늬 배경 켜기/끄기"),
        ("서식 툴바 접기/열기",        "toggle_fmt_bar",       "하단 서식 도구모음 토글"),
        ("전체 메모 내용 복사",        "copy_all",             "메모 전체 내용을 클립보드로"),
        ("한/영 영타 오타 변환",       "eng_kor_convert",      "영어로 입력된 한글 오타 변환"),
        ("코드 자동 정렬 (Prettify)",  "format_code",          "코드 메모 전용"),
        ("코드 테마 전환",             "toggle_code_theme",    "코드 메모 다크/라이트 전환"),
        ("전체 메모 열기",            "open_all_memos",       "저장된 모든 메모 표시"),
        # ── 암호 메모 (메모 창 / 탐색기에서 선택한 메모) ─────────────────────
        ("암호 메모 잠그기/잠금 해제",  "toggle_memo_lock",     "열려 있으면 잠그고, 잠겨 있으면 암호 입력"),
        ("메모 암호 걸기/변경",        "set_memo_password",    "일반 메모에 암호 설정, 암호 메모는 암호 변경"),
        # ── 체크리스트 · 알림 · 변경 기록 ─────────────────────────────────────
        ("체크리스트 켜기/끄기",       "toggle_checklist",     "선택한 줄 앞에 체크 상자(☐)를 붙이거나 뗌"),
        ("알림 설정",                 "set_reminder",         "날짜·시간·반복(크론식)을 정해 알림을 겁니다"),
        ("이전 내용 보기",            "show_history",         "저장되기 전의 내용을 보고 되돌립니다"),
    ]

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
