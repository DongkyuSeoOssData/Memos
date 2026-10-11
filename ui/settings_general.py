"""환경설정의 '일반 설정' 탭: 폴더 보기 방식, 암호 메모, 시스템, 알림, 사용 안내.

(SettingsWindow 에 섞어 쓰는 부분. 입력 칸을 만들기만 하고, 값을 읽고 쓰는 일은 SettingsWindow 의 FIELDS 표가 합니다)
"""
from ui.reminder_ui import POPUP_CORNERS, ReminderPopup
from typing import Any
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QComboBox, QCheckBox, QFrame, QGroupBox, QScrollArea, QSpinBox
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QGuiApplication


class GeneralTabMixin:
    """환경설정의 일반 설정 탭."""

    def _build_general_tab(self) -> None:
        """'일반 설정' 탭: 폴더 표시 방식, 암호 메모, 시스템·편의 옵션, 알림 빠른 선택, 사용 안내."""
        tab_general = QWidget()
        l_gen = QVBoxLayout(tab_general)
        l_gen.setContentsMargins(15, 15, 15, 15)
        l_gen.setSpacing(15)

        g_folder = self._build_folder_ui_group()
        l_gen.addWidget(g_folder)

        g2 = self._build_locked_memo_group()
        l_gen.addWidget(g2)

        g4 = self._build_system_group()
        l_gen.addWidget(g4)

        g_alarm = self._build_reminder_group()
        l_gen.addWidget(g_alarm)


        g_guide = self._build_guide_group()
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

    def _build_folder_ui_group(self) -> Any:
        """폴더 표시 방식."""
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
        return g_folder

    def _build_locked_memo_group(self) -> Any:
        """암호 메모를 다시 잠그는 시간."""
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
        return g2

    def _build_system_group(self) -> Any:
        """자동 실행, 자동 저장, 휴지통, 새 메모의 기본 옵션."""
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

        self.cb_error_report = QCheckBox("오류가 나면 보고 메일 보내기")
        g4_l.addWidget(self.cb_error_report)
        report_hint = QLabel("동기화 스크립트가 메일을 보냅니다. 받는 주소는 스크립트 속성 ERROR_MAIL_TO 이고, 없으면 스크립트 주인의 "
                             "구글 계정입니다. 스크립트에 접근 암호(ACCESS_TOKEN)를 넣어 둔 경우에만 보냅니다. "
                             "오류의 종류와 발생 위치만 보내며 메모의 제목·본문은 보내지 않습니다.")
        report_hint.setProperty("role", "hint")
        report_hint.setWordWrap(True)
        g4_l.addWidget(report_hint)

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
        return g4

    def _build_reminder_group(self) -> Any:
        """알림: 알림 설정 화면의 빠른 선택 세 가지, 알림 창을 띄울 모니터와 모서리."""
        g_alarm = QGroupBox("알림")
        g_alarm_l = QVBoxLayout(g_alarm)
        g_alarm_l.setContentsMargins(18, 24, 18, 18)
        g_alarm_l.setSpacing(8)
        g_alarm_l.addWidget(QLabel("알림 설정의 빠른 선택"))
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

        g_alarm_l.addSpacing(6)
        g_alarm_l.addWidget(QLabel("알림 창을 띄울 자리"))
        place_row = QHBoxLayout()
        place_row.setSpacing(10)
        self.popup_screen_box = QComboBox()
        self.popup_screen_box.setFixedHeight(40)
        self.popup_screen_box.setToolTip("모니터가 여러 대일 때 알림 창을 띄울 모니터")
        place_row.addWidget(self.popup_screen_box, 2)
        self.popup_corner_box = QComboBox()
        self.popup_corner_box.setFixedHeight(40)
        for key, label in POPUP_CORNERS:
            self.popup_corner_box.addItem(label, key)
        place_row.addWidget(self.popup_corner_box, 1)
        self.btn_popup_sample = QPushButton("자리 확인")
        self.btn_popup_sample.setFixedHeight(40)
        self.btn_popup_sample.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_popup_sample.setToolTip("지금 고른 모니터와 모서리에 알림 창을 한 번 띄워 봅니다 (저장하기 전에도 됨)")
        self.btn_popup_sample.clicked.connect(self.show_popup_sample)
        place_row.addWidget(self.btn_popup_sample)
        g_alarm_l.addLayout(place_row)
        place_hint = QLabel("'자리 확인'을 누르면 지금 고른 자리에 알림 창을 띄워 봅니다. 고른 값은 '설정 저장'을 눌러야 적용됩니다. "
                            "고른 모니터가 연결돼 있지 않으면 주 모니터에 띄웁니다. 알림이 여럿이면 그 모서리에서부터 쌓입니다.")
        place_hint.setProperty("role", "hint")
        place_hint.setWordWrap(True)
        g_alarm_l.addWidget(place_hint)
        return g_alarm

    def show_popup_sample(self) -> None:
        """지금 화면에서 고른 모니터와 모서리에 알림 창을 한 번 띄워 봅니다. (저장하지 않은 값으로도)"""
        old = getattr(self, '_popup_sample', None)
        if old is not None:
            try:
                old.close()
            except RuntimeError:                # 이미 닫혀서 지워진 창
                pass
        settings = {**self.sm.settings, "reminder_popup_screen": self.popup_screen_box.currentData() or "",
                    "reminder_popup_corner": self.popup_corner_box.currentData()}
        self._popup_sample = ReminderPopup(settings, "", "알림 창 자리 확인", "알림이 울리면 여기에 뜹니다.",
                                           lambda memo_id: None, lambda memo_id, minutes: None)
        self._popup_sample.show()

    def _fill_popup_screens(self, saved: str) -> None:
        """알림 창을 띄울 모니터 목록을 지금 연결된 모니터로 채웁니다.

        설정에는 모니터 이름을 적어 둡니다. 골라 둔 모니터가 지금 연결돼 있지 않아도 목록에 남겨,
        다른 설정을 저장할 때 그 선택이 사라지지 않게 합니다.
        """
        box = self.popup_screen_box
        box.blockSignals(True)
        box.clear()
        # 주 모니터는 한 줄로만 둡니다. (값은 빈 글자: 주 모니터가 바뀌면 바뀐 쪽을 따라감) 나머지 모니터만 따로 늘어놓습니다.
        primary = QGuiApplication.primaryScreen()
        size = primary.geometry() if primary else None
        box.addItem(f"주 모니터 ({size.width()}×{size.height()})" if size else "주 모니터", "")
        names = [primary.name()] if primary else []
        for n, screen in enumerate(QGuiApplication.screens(), start=1):
            if screen is primary:
                continue
            size = screen.geometry()
            box.addItem(f"모니터 {n} ({size.width()}×{size.height()})", screen.name())
            names.append(screen.name())
        if saved and saved not in names:
            box.addItem(f"연결되지 않은 모니터 ({saved})", saved)
        box.blockSignals(False)

    def _build_guide_group(self) -> Any:
        """사용 안내 메모 다시 만들기."""
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
        return g_guide

    def make_guide_memos(self) -> None:
        ui_manager = getattr(self.sm, 'ui_manager', None)
        if ui_manager is None:
            return
        ui_manager.remake_guide_memos()
        self.show_toast("사용 안내 메모를 만들었습니다")
