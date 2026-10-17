"""메모 탐색기의 화면 만들기: 제목 줄, 폴더 탭 줄, 종류 고르기 줄, 검색 줄, 목록 표, 쪽 넘기기, 미리보기 줄, 아래쪽 버튼 줄과 아이콘.

위젯을 만들어 놓기만 합니다. 목록을 채우는 일은 explorer_list, 메모에 하는 일은 explorer_actions 에 있습니다.
(MemoExplorerWindow 에 섞어 쓰는 부분)
"""
from ui.check_marks import CheckEdit
from ui import modern_style
from ui.tab_strip import TabStrip
from typing import List, Any
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLineEdit, QLabel, QComboBox, QTableWidget, QHeaderView, QSizePolicy, QGridLayout
from PyQt6.QtCore import QEvent, QObject, Qt, QTimer
from PyQt6.QtGui import QIcon



class CornerPin(QObject):
    """widget 을 host 안의 오른쪽 위 구석에 붙여 둡니다. host 의 크기가 바뀌거나 세로 스크롤 막대가 생겨도 따라갑니다."""

    MARGIN = 6

    def __init__(self, host: Any, widget: Any) -> None:
        super().__init__(host)
        self.host, self.widget = host, widget
        host.installEventFilter(self)
        self.place()

    def place(self) -> None:
        bar = self.host.verticalScrollBar()
        right = self.host.width() - self.host.frameWidth() - (bar.width() if bar.isVisible() else 0)
        self.widget.move(right - self.widget.width() - self.MARGIN, self.host.frameWidth() + self.MARGIN)
        self.widget.raise_()

    def eventFilter(self, obj: Any, event: Any) -> bool:
        if obj is self.host and event.type() in (QEvent.Type.Resize, QEvent.Type.Show, QEvent.Type.LayoutRequest):
            self.place()
        return False


class ExplorerLayoutMixin:
    """탐색기의 화면 만들기."""

    def _build_header(self, bg_l: Any) -> None:
        """제목 줄: 왼쪽에 폴더·색 테마 버튼, 가운데에 Memos, 오른쪽 끝에 창 버튼."""
        header = QGridLayout()
        header.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout()
        row.setSpacing(0)
        center = QHBoxLayout()          # 왼쪽 묶음
        center.setSpacing(8)
        ctrl = QHBoxLayout()            # 오른쪽 창 버튼 묶음
        ctrl.setSpacing(6)
        row.addLayout(center)
        row.addStretch(1)
        row.addLayout(ctrl)
        header.addLayout(row, 0, 0)

        # 사이드바 방식일 때: 폴더 아이콘 + 지금 고른 폴더 이름. 누르면 왼쪽 폴더 목록을 열고 닫습니다.
        self.btn_folder = QPushButton("")
        self.btn_folder.setFixedHeight(30)
        self.btn_folder.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_folder.setToolTip("폴더 목록 열기/닫기")
        self.btn_folder.clicked.connect(self.toggle_folder_sidebar)
        center.addWidget(self.btn_folder)

        # 드롭다운 방식일 때: 고른 폴더(와 그 하위 폴더)의 메모만 목록·태그·검색에 나타납니다.
        self.folder_combo = QComboBox()
        self.folder_combo.setFixedHeight(30)
        self.folder_combo.setCursor(Qt.CursorShape.PointingHandCursor)
        self.folder_combo.setToolTip("폴더 (고른 폴더의 메모만 보기)")
        self.folder_combo.activated.connect(self._on_folder_picked)
        center.addWidget(self.folder_combo)

        self.btn_app_theme = QPushButton("")
        self.btn_app_theme.setFixedSize(88, 30)
        self.btn_app_theme.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_app_theme.clicked.connect(self.toggle_app_theme)
        center.addWidget(self.btn_app_theme)

        # 알림(토스트)은 아래쪽 '총 n개 메모' 줄 자리에 잠깐 덮어 보입니다. (그 줄은 보여 주기만 하는 줄이라 잠깐 가려도 됨)
        self.toast = QLabel("")
        self.toast.hide()
        self._toast_timer = QTimer(self)
        self._toast_timer.setSingleShot(True)
        self._toast_timer.timeout.connect(self.hide_toast)

        # 윈도우 스타일 우상단 제어 버튼 (📌 고정 / ─ 최소화 / □ 최대화 / ✕ 닫기)
        self.btn_win_pin   = QPushButton("")
        self.btn_win_min   = QPushButton("")
        self.btn_win_max   = QPushButton("")
        self.btn_win_close = QPushButton("")

        for b_item, tip in [(self.btn_win_pin, "화면 고정 토글"), (self.btn_win_min, "최소화"), (self.btn_win_max, "최대화"), (self.btn_win_close, "닫기")]:
            b_item.setFixedSize(32, 28)
            b_item.setCursor(Qt.CursorShape.PointingHandCursor)
            b_item.setToolTip(tip)
            ctrl.addWidget(b_item)

        self.btn_win_pin.clicked.connect(self.toggle_explorer_pin)
        self.btn_win_min.clicked.connect(self.showMinimized)
        self.btn_win_max.clicked.connect(self.toggle_maximize)
        self.btn_win_close.clicked.connect(self.close)

        # 'Memos' 는 같은 칸에 겹쳐 놓아, 양옆 묶음의 너비와 상관없이 제목 줄의 정가운데에 둡니다.
        self.title_label = QLabel("Memos")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        header.addWidget(self.title_label, 0, 0, Qt.AlignmentFlag.AlignCenter)
        self._header_left, self._header_right = center, ctrl
        bg_l.addLayout(header)

    def _build_folder_tabs(self, bg_l: Any) -> None:
        """폴더 탭 줄 (탭 줄 방식일 때): 윗줄은 최상위 폴더, 아랫줄은 하위 폴더."""
        self.folder_tabs = QWidget()
        tabs_l = QVBoxLayout(self.folder_tabs)
        tabs_l.setContentsMargins(0, 0, 0, 0)
        tabs_l.setSpacing(4)
        self.folder_tab_strip = TabStrip()
        self.folder_subtab_strip = TabStrip()
        for strip in (self.folder_tab_strip, self.folder_subtab_strip):
            strip.moved.connect(self.move_folder)
            tabs_l.addWidget(strip)
        self.folder_tab_buttons: List[QPushButton] = []
        bg_l.addWidget(self.folder_tabs)

    def _build_filter_row(self, bg_l: Any) -> None:
        """종류 고르기 줄: 전체 / 일반 / 코드 / 즐겨찾기 등."""
        filter_layout = QHBoxLayout()
        self.btn_filter_all  = QPushButton(" 전체")
        self.btn_filter_gen  = QPushButton(" 일반")
        self.btn_filter_code = QPushButton(" 코드")

        for fb in [self.btn_filter_all, self.btn_filter_gen, self.btn_filter_code]:
            fb.setFixedHeight(34)
            fb.setCheckable(True)
            fb.setCursor(Qt.CursorShape.PointingHandCursor)
            filter_layout.addWidget(fb)

        self.btn_filter_all.clicked.connect(lambda: self.set_filter_mode("ALL"))
        self.btn_filter_gen.clicked.connect(lambda: self.set_filter_mode("GENERAL"))
        self.btn_filter_code.clicked.connect(lambda: self.set_filter_mode("CODE"))
        self.update_filter_buttons()

        filter_layout.addStretch()

        self.btn_arrange_rolled = QPushButton(" 접은 메모 정렬")
        self.btn_arrange_memos  = QPushButton(" 펼친 메모 정렬")

        for ab in [self.btn_arrange_rolled, self.btn_arrange_memos]:
            ab.setFixedHeight(34)
            ab.setCursor(Qt.CursorShape.PointingHandCursor)
            filter_layout.addWidget(ab)

        self.btn_arrange_rolled.clicked.connect(self.ui_manager.arrange_rolled_up_memos)
        self.btn_arrange_memos.clicked.connect(self.ui_manager.arrange_memos)

        bg_l.addLayout(filter_layout)

    def _build_search_row(self, bg_l: Any) -> None:
        """검색 줄: 검색 종류, 태그, 검색어, 휴지통."""
        sh_l = QHBoxLayout()
        self.s_type = QComboBox()
        self.s_type.addItems(["제목 검색", "본문 검색"])
        self.s_type.setFixedHeight(36)

        self.tag_combo = QComboBox()
        self.tag_combo.addItem("#")
        self.tag_combo.setFixedHeight(36)
        # 💡 메인 콤보박스 버튼 크기가 절대 자동으로 늘어나지 않게 고정 정책 부여
        self.tag_combo.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.tag_combo.setFixedWidth(55) # 혹은 원하는 고정 폭 (예: 50~60px)
        self.tag_combo.currentIndexChanged.connect(self.on_search)

        self.s_in = QLineEdit()
        self.s_in.setPlaceholderText("검색")
        self.s_in.setFixedHeight(36)
        self.s_in.textChanged.connect(lambda _text: self._search_timer.start())

        self.t_btn = QPushButton("휴지통 보기")
        self.t_btn.setCheckable(True)
        self.t_btn.setFixedHeight(36)
        self.t_btn.clicked.connect(self.toggle_trash)

        sh_l.addWidget(self.s_type)
        sh_l.addWidget(self.tag_combo)
        sh_l.addWidget(self.s_in)
        sh_l.addWidget(self.t_btn)
        bg_l.addLayout(sh_l)

    def _build_table(self, bg_l: Any) -> None:
        """메모 목록 표."""
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["선택", "★", "구분 / 제목", "수정일시", "잠금"])
        self.table.horizontalHeaderItem(1).setToolTip("즐겨찾기")
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.cellClicked.connect(self.on_cell_click)
        self.table.cellDoubleClicked.connect(self.on_cell_double_click)
        self.table.itemSelectionChanged.connect(self.sync_selection_and_checkboxes)
        self.table.setTextElideMode(Qt.TextElideMode.ElideRight)

        self.table.verticalHeader().setVisible(False)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_table_context_menu)
        self.table.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        h = self.table.horizontalHeader()
        h.setSectionsMovable(False)
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(0, 50)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(1, 44)
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(3, 120)
        h.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(4, 70)
        h.sectionClicked.connect(self.on_header_click)
        bg_l.addWidget(self.table)

    def _build_pager(self, bg_l: Any) -> None:
        """쪽 넘기기 줄."""
        pg_l = QHBoxLayout()
        # |< 첫 쪽 · ‹ 앞 쪽 · 쪽 번호 · 다음 쪽 › · 마지막 쪽 >|
        self.btn_first_page = QPushButton("|‹")
        self.btn_first_page.setFixedSize(30, 30)
        self.btn_first_page.setToolTip("첫 쪽")
        self.btn_first_page.clicked.connect(self.go_first)
        self.btn_last_page = QPushButton("›|")
        self.btn_last_page.setFixedSize(30, 30)
        self.btn_last_page.setToolTip("마지막 쪽")
        self.btn_last_page.clicked.connect(self.go_last)
        self.p_b = QPushButton("‹")
        self.p_b.setFixedSize(30, 30)
        self.p_b.clicked.connect(self.go_prev)

        self.p_l = QLabel("1 / 1")

        self.n_b = QPushButton("›")
        self.n_b.setFixedSize(30, 30)
        self.n_b.clicked.connect(self.go_next)

        pg_l.addStretch()
        pg_l.addWidget(self.btn_first_page)
        pg_l.addWidget(self.p_b)
        pg_l.addWidget(self.p_l)
        pg_l.addWidget(self.n_b)
        pg_l.addWidget(self.btn_last_page)
        pg_l.addStretch()
        bg_l.addLayout(pg_l)

    def _build_preview(self, bg_l: Any) -> None:
        """미리보기: 제목 줄(왼쪽 환경설정 버튼과 알림(토스트) · 가운데 제목과 접기 버튼 · 오른쪽 예약된 알림 버튼), 그 아래 본문 칸."""
        pv_head = QHBoxLayout()
        pv_head.setSpacing(10)
        # 양옆 묶음이 남는 너비를 똑같이 나눠 가져, 제목이 줄의 가운데에 옵니다.
        pv_left, pv_right = QHBoxLayout(), QHBoxLayout()
        pv_left.setSpacing(10)
        # 환경설정 버튼: 누르면 탐색기 옆에 열리고, 열려 있을 때 다시 누르면 닫힙니다.
        self.btn_settings = QPushButton("")
        self.btn_settings.setFixedSize(28, 24)
        self.btn_settings.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_settings.setToolTip("환경설정 열기/닫기")
        self.btn_settings.clicked.connect(self.ui_manager.toggle_settings)
        pv_left.addWidget(self.btn_settings)
        pv_left.addStretch()
        # 예약된 알림 버튼: 알림이 걸린 메모를 빨리 울리는 순으로 보여 주고, 거기서 미루거나 해제합니다. (옆의 숫자는 예약된 개수)
        self.btn_reminders = QPushButton("")
        self.btn_reminders.setFixedHeight(24)
        self.btn_reminders.setMinimumWidth(28)
        self.btn_reminders.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_reminders.clicked.connect(self.show_reminder_list)
        self.ui_manager.sync_manager.reminders_changed.connect(self.update_reminder_button, Qt.ConnectionType.QueuedConnection)
        self.update_reminder_button()
        pv_right.addStretch()
        pv_right.addWidget(self.btn_reminders)
        # 가운데 제목 '미리보기 ▾' 가 곧 접기·펼치기 버튼입니다. 접으면 본문 칸이 사라지고 그만큼 탐색기가 줄어듭니다. (PC마다 기억)
        self.btn_preview_fold = QPushButton("")
        self.btn_preview_fold.setFixedHeight(24)
        self.btn_preview_fold.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_preview_fold.clicked.connect(self.toggle_preview)
        pv_head.addLayout(pv_left, 1)
        pv_head.addWidget(self.btn_preview_fold)
        pv_head.addLayout(pv_right, 1)
        bg_l.addLayout(pv_head)
        # 미리보기는 읽기만 합니다. (체크 상자는 네모로 그려 보여 주기만 하고, 고치기는 메모 창에서)
        # 목록 칸의 높이는 고정이라, 창을 키우고 줄이면 미리보기 칸이 그만큼 커지고 작아집니다.
        self.pv = CheckEdit(self._preview_check_colors)
        self.pv.setMinimumHeight(self.PREVIEW_MIN_HEIGHT)
        self.pv.setReadOnly(True)
        bg_l.addWidget(self.pv, 1)
        # 미리보기를 접었을 때만 보이는 빈 칸: 창을 최대화했을 때처럼 줄일 수 없는 남는 높이를 받습니다.
        self._pv_filler = QWidget()
        self._pv_filler.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self._pv_filler.hide()
        bg_l.addWidget(self._pv_filler, 1)
        self.pv.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.pv.customContextMenuRequested.connect(self.show_preview_menu)
        # 복사 버튼: 코드 블록처럼 미리보기 칸 안의 오른쪽 위에 둡니다. 누르면 보이는 메모의 본문 전체가 클립보드로.
        self.btn_preview_copy = QPushButton("", self.pv)
        self.btn_preview_copy.setFixedSize(28, 28)
        self.btn_preview_copy.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_preview_copy.setToolTip("본문 복사")
        self.btn_preview_copy.clicked.connect(self.copy_preview)
        self._preview_corner = CornerPin(self.pv, self.btn_preview_copy)
        self._show_preview(bool(self.ui_manager.sync_manager.settings.get('explorer_preview_open', True)))

    def preview_open(self) -> bool:
        return not self.pv.isHidden()

    PREVIEW_MIN_HEIGHT = 100

    def toggle_preview(self) -> None:
        """미리보기 본문 칸을 접거나 폅니다. 접으면 그 높이만큼 창이 줄고, 펴면 다시 늘어납니다."""
        opening = not self.preview_open()
        # 접으면 미리보기 자리에 높이 0 인 빈 칸이 들어가므로, 창은 미리보기 높이만큼만 줄이고 늘립니다.
        if opening:
            delta = getattr(self, '_folded_preview_height', self.PREVIEW_MIN_HEIGHT)
        else:
            self._folded_preview_height = self.pv.height()
            delta = -self.pv.height()
        self._show_preview(opening)
        self.ui_manager.sync_manager.save_settings({'explorer_preview_open': opening})
        self._grow_down(delta)

    def _show_preview(self, opening: bool) -> None:
        self.pv.setVisible(opening)
        self._pv_filler.setVisible(not opening)
        self.btn_preview_fold.setText("미리보기 ▾" if opening else "미리보기 ▸")
        self.btn_preview_fold.setToolTip("미리보기 접기" if opening else "미리보기 펼치기")

    def _build_status_row(self, bg_l: Any) -> None:
        """메모 개수를 보여 주는 줄."""
        self.stat_box = QWidget()
        stat_layout = QHBoxLayout(self.stat_box)
        stat_layout.setContentsMargins(0, 4, 0, 0)
        stat_layout.setSpacing(6)

        self.stat_icon = QLabel()
        if hasattr(self.ui_manager, 'get_theme_icon'):
            self.stat_icon.setPixmap(self.ui_manager.get_theme_icon("total.svg", False, override_color="#8E8E93").pixmap(16, 16))

        self.stat_label = QLabel("총 0개")

        stat_layout.addWidget(self.stat_icon)
        stat_layout.addWidget(self.stat_label)
        stat_layout.addWidget(self.toast)                # 토스트가 뜨는 동안에는 개수 대신 토스트
        stat_layout.addStretch()
        bg_l.addWidget(self.stat_box)

    def setup_btns(self) -> None:
        self.b_new        = QPushButton("새 메모")
        self.b_new_code   = QPushButton("코드 메모")
        self.b_ref        = QPushButton("새로고침")
        self.b_sync       = QPushButton("동기화")
        self.b_del        = QPushButton("삭제")
        self.b_res        = QPushButton("복구")
        self.b_empty_trash = QPushButton("비우기")

        # 툴팅 설정 (악은 너비에서 아이콘만 표시될 때 유용)
        for btn, tip in [
            (self.b_new, "새 메모 생성"), (self.b_new_code, "코드 메모 생성"),
            (self.b_ref, "새로고침"), (self.b_sync, "클라우드 동기화"),
            (self.b_del, "선택 메모 삭제"), (self.b_res, "선택 메모 복구"),
            (self.b_empty_trash, "휴지통 비우기")
        ]:
            btn.setToolTip(tip)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)

        self.b_new.clicked.connect(self.ui_manager.create_empty_memo)
        self.b_new_code.clicked.connect(self.ui_manager.create_code_memo)
        self.b_ref.clicked.connect(self.refresh)
        self.b_sync.clicked.connect(self.ui_manager.sync_manager.sync_all)
        self.b_del.clicked.connect(self.del_checked)
        self.b_res.clicked.connect(self.res_checked)
        self.b_empty_trash.clicked.connect(self.empty_trash)

    def _refresh_btn_labels(self) -> None:
        """숙 너비(px)에 따라 버튼을 "아이콘+텍스트" 또는 "아이콘만" 모드로 전환합니다.

        기준: 창 너비 580px 미만 시 텍스트 숨김, 이상시 텍스트 표시.
        """
        show_text = self.content_width() >= 580
        # 하단 액션 버튼: 아이콘 앞에 공백 최소화
        labels = {
            self.b_new:         " 새 메모",
            self.b_new_code:    " 코드 메모",
            self.b_ref:         " 새로고침",
            self.b_sync:        " 동기화",
            self.b_del:         " 삭제",
            self.b_res:         " 복구",
            self.b_empty_trash: " 비우기",
        }
        for btn, text in labels.items():
            btn.setText(text if show_text else "")
        # 필터/정렬 버튼
        filter_labels = {
            self.btn_filter_all:     "전체",
            self.btn_filter_gen:     "일반",
            self.btn_filter_code:    "코드",
            self.btn_arrange_rolled: "접은정렬",
            self.btn_arrange_memos:  "펼친정렬",
        }
        for btn, text in filter_labels.items():
            btn.setText(text if show_text else "")

    def favorite_icon(self, is_fav: bool) -> Any:
        """즐겨찾기 별: 등록된 메모는 노란 별, 아니면 테두리만 있는 옅은 별."""
        if not hasattr(self.ui_manager, 'get_theme_icon'):
            return QIcon()
        is_dark = self.ui_manager.sync_manager.settings.get('app_theme', 'white') == "dark"
        if is_fav:
            return self.ui_manager.get_theme_icon("star_true.svg", is_dark, override_color=self.FAVORITE_COLOR)
        return self.ui_manager.get_theme_icon("star_false.svg", is_dark, override_color="#8E8E93")

    def update_icons(self) -> None:
        if not hasattr(self.ui_manager, 'get_theme_icon'): return
        theme = self.ui_manager.sync_manager.settings.get('app_theme', 'white')
        is_dark = (theme == 'dark')
        self.btn_win_pin.setText("")
        self.btn_win_min.setText("")
        self.btn_win_max.setText("")
        self.btn_win_close.setText("")
        self.btn_app_theme.setIcon(self.ui_manager.get_theme_icon("litemode.svg" if is_dark else "darkmod.svg", is_dark))
        self.btn_win_min.setIcon(self.ui_manager.get_theme_icon("minimize.svg", is_dark))
        self.btn_win_max.setIcon(self.ui_manager.get_theme_icon("maximize.svg", is_dark))
        self.btn_win_close.setIcon(self.ui_manager.get_theme_icon("close.svg", is_dark, override_color="#FF453A"))
        self.btn_filter_all.setIcon(self.ui_manager.get_theme_icon("total.svg", is_dark))
        self.btn_filter_gen.setIcon(self.ui_manager.get_theme_icon("memo.svg", is_dark))
        self.btn_filter_code.setIcon(self.ui_manager.get_theme_icon("codememo.svg", is_dark))
        self.btn_arrange_rolled.setIcon(self.ui_manager.get_theme_icon("정렬1.svg", is_dark))
        self.btn_arrange_memos.setIcon(self.ui_manager.get_theme_icon("정렬2.svg", is_dark))
        t_icon = "total.svg" if getattr(self, 'is_trash_mode', False) else "trashbucket.svg"
        self.t_btn.setIcon(self.ui_manager.get_theme_icon(t_icon, is_dark))
        self.p_b.setText("")
        self.n_b.setText("")
        self.p_b.setIcon(self.ui_manager.get_theme_icon("arrow left.svg", is_dark))
        self.n_b.setIcon(self.ui_manager.get_theme_icon("arrow right.svg", is_dark))
        for btn, icon in ((self.btn_first_page, "page first.svg"), (self.btn_last_page, "page last.svg")):
            btn.setText("")
            btn.setIcon(self.ui_manager.get_theme_icon(icon, is_dark))
        self.b_new_code.setIcon(self.ui_manager.get_theme_icon("codememo.svg", is_dark))
        self.b_ref.setIcon(self.ui_manager.get_theme_icon("restart-icon.svg", is_dark))
        self.b_sync.setIcon(self.ui_manager.get_theme_icon("cloude.svg", is_dark))
        self.btn_settings.setIcon(self.ui_manager.get_theme_icon("setting.svg", is_dark))
        hover = "rgba(255,255,255,0.14)" if is_dark else "rgba(0,0,0,0.10)"
        self.btn_settings.setStyleSheet(f"QPushButton {{ border: none; background: transparent; border-radius: 0px; }} "
                                        f"QPushButton:hover {{ background: {hover}; }}")
        ink = modern_style.app_palette(self.ui_manager.sync_manager.settings)[0]['text']
        self.btn_preview_copy.setIcon(self.ui_manager.get_theme_icon("copy.svg", is_dark))
        pal = modern_style.app_palette(self.ui_manager.sync_manager.settings)[0]
        # 본문 글자 위에 떠 있으므로 바탕을 칠하고 가는 테두리를 둡니다. (코드 블록의 복사 버튼처럼)
        self.btn_preview_copy.setStyleSheet(
            f"QPushButton {{ border: 1px solid {pal['border']}; background: {pal['card']}; border-radius: 0px; padding: 0; }} "
            f"QPushButton:hover {{ border-color: {ink}; }}")
        self.btn_preview_fold.setStyleSheet(
            f"QPushButton {{ border: none; background: transparent; border-radius: 0px; padding: 0 8px; color: {ink}; }} "
            f"QPushButton:hover {{ background: {hover}; }}")
        self.btn_reminders.setIcon(self.ui_manager.get_theme_icon("alarm.svg", is_dark))
        self.btn_reminders.setStyleSheet(
            f"QPushButton {{ border: none; background: transparent; border-radius: 0px; padding: 0 5px; color: {ink}; "
            f"font-family: {modern_style.UI_FONT}; font-size: 9.5pt; font-weight: 700; }} "
            f"QPushButton:hover {{ background: {hover}; }}")
        self.b_del.setIcon(self.ui_manager.get_theme_icon("minus.svg", is_dark))
        self.b_res.setIcon(self.ui_manager.get_theme_icon("restart-icon.svg", is_dark))
        self.b_empty_trash.setIcon(self.ui_manager.get_theme_icon("trashbucket.svg", is_dark))
        # 고정·새 메모 버튼의 아이콘과 창 버튼 모양은 디자인 스타일이 정합니다.
        modern_style.apply_explorer_chrome(self)
