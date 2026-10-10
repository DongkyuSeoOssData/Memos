from ui.dialogs import ConflictDialog
from ui import modern_style
import datetime
from typing import List, Dict, Any, Optional
from PyQt6.QtWidgets import (
    QWidget, QTextEdit, QVBoxLayout, QHBoxLayout, QPushButton, QLineEdit, QMenu, QApplication,
    QMessageBox, QLabel, QComboBox, QTableWidget, QTableWidgetItem, QHeaderView, QDialog, QFrame,
    QSizeGrip, QSizePolicy
)
from PyQt6.QtCore import Qt, QPoint, QSize, QTimer, pyqtSlot
from PyQt6.QtGui import QGuiApplication, QShortcut, QKeySequence, QFont, QIcon
from utils.text_utils import clean_plain_text, extract_hashtags

class MemoExplorerWindow(QWidget):
    """
    iOS 울트라 미니멀 화이트 & 블랙 탐색기:
    - 윈도우 우측 창 제어 버튼 (─, □/❐, ✕) & 100% 정상 작동하는 최대화/복원
    - 실시간 라이트 / 다크 모드 전환 지원
    """
    FAVORITE_COLOR = "#F5A623"

    def __init__(self, ui_manager: Any) -> None:
        super().__init__()
        self.ui_manager = ui_manager
        self.ui_font_pt = int(self.ui_manager.sync_manager.settings.get("explorer_font_pt", 10))
        self.current_page: int = 1
        self.items_per_page: int = 10
        self.filtered_memos: List[Dict[str, Any]] = []
        self.filter_mode: str = "ALL"
        self.is_trash_mode: bool = False
        self._old_pos: Optional[QPoint] = None
        self._is_loading_preview: bool = False
        # 검색어 입력이 멈춘 뒤에만 목록을 다시 읽습니다. (글자마다 전체 재로딩 방지)
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(300)
        self._search_timer.timeout.connect(self.on_search)
        # 미리보기 편집도 입력이 멈춘 뒤 한 번만 암호화·저장합니다.
        self._pending_preview_memo: Optional[Dict[str, Any]] = None
        self._preview_save_timer = QTimer(self)
        self._preview_save_timer.setSingleShot(True)
        self._preview_save_timer.setInterval(500)
        self._preview_save_timer.timeout.connect(self._flush_preview_save)
        self.init_ui()
        self.apply_theme_style()
        self.bind_global_shortcuts()

    def _apply_initial_window_size(self) -> None:
        """멀티모니터 환경에서 가장 작은 모니터 해상도의 1/6 크기로 창을 초기화합니다."""
        screens = QGuiApplication.screens()
        if not screens:
            return
        # 가장 작은 모니터 탐색 (너비 × 높이 면적 기준)
        smallest = min(screens, key=lambda s: s.geometry().width() * s.geometry().height())
        geom = smallest.availableGeometry()
        # 1/6 크기 = 가로 1/3, 세로 1/3
        base_w = int(geom.width() / 3)
        base_h = int(geom.height() / 3)
        target_w = max(base_w, 620)
        target_h = max(base_h, 480)
        target_w = min(target_w, int(geom.width() * 0.8))
        target_h = min(target_h, int(geom.height() * 0.8))
        cx = geom.center().x() - target_w // 2
        cy = geom.center().y() - target_h // 2
        self.setGeometry(cx, cy, target_w, target_h)

    def _apply_font_scale(self) -> None:
        """현재 ui_font_pt 기준으로 창 전체의 폰트와 행 높이를 적용합니다."""
        base_font = QFont("D2Coding", self.ui_font_pt)
        self.setFont(base_font)
        self.bg.setFont(base_font)
        self.table.setFont(base_font)
        self.pv.setFont(QFont("D2Coding", max(9, self.ui_font_pt)))

        # 상단 제어·필터 버튼 아이콘: 폰트 1.4배
        ctrl_icon_sz = max(14, int(self.ui_font_pt * 1.4))
        for btn in [self.btn_win_pin, self.btn_win_min, self.btn_win_max, self.btn_win_close,
                    self.btn_filter_all, self.btn_filter_gen, self.btn_filter_code,
                    self.btn_arrange_rolled, self.btn_arrange_memos, self.t_btn,
                    self.p_b, self.n_b]:
            btn.setIconSize(QSize(ctrl_icon_sz, ctrl_icon_sz))

        # 하단 액션 버튼 아이콘: 폰트와 동일 크기 (텍스트와 나란히 보이도록 작게)
        act_icon_sz = max(12, int(self.ui_font_pt * 1.1))
        if hasattr(self, 'b_new'):
            btn_h = max(30, int(self.ui_font_pt * 2.6))
            for btn in [self.b_new, self.b_new_code, self.b_ref, self.b_sync,
                        self.b_del, self.b_res, self.b_empty_trash]:
                btn.setIconSize(QSize(act_icon_sz, act_icon_sz))
                btn.setFixedHeight(btn_h)
        self.shortcut_font_refresh()

    def _calc_font_pt_from_size(self) -> int:
        """현재 창 너비를 기반으로 ui_font_pt를 동적으로 계산합니다.

        창 너비 440px 기준 9pt, 매 60px 증가마다 1pt 증가, 최대 16pt.
        """
        w = self.width()
        pt = 9 + max(0, (w - 440) // 60)
        return max(9, min(16, pt))

    def shortcut_font_refresh(self) -> None:
        row_h = max(38, int(self.ui_font_pt * 3.2))
        self.table.verticalHeader().setDefaultSectionSize(row_h)
        for row in range(self.table.rowCount()):
            self.table.setRowHeight(row, row_h)

    def bind_global_shortcuts(self) -> None:
        s_cfg = self.ui_manager.sync_manager.settings.get("shortcuts", {})
        # 글로벌 단축키와 중복을 막기 위해 전역 훅 단축키는 QShortcut에서 제외
        QShortcut(QKeySequence(s_cfg.get("open_all_memos", "Alt+O")), self).activated.connect(self.ui_manager.open_all_memos)
        QShortcut(QKeySequence(s_cfg.get("toggle_memo_lock", "Ctrl+L")), self).activated.connect(
            lambda: self._lock_action_on_current("toggle_memo_lock"))
        QShortcut(QKeySequence(s_cfg.get("set_memo_password", "Ctrl+Shift+L")), self).activated.connect(
            lambda: self._lock_action_on_current("set_memo_password"))
        QShortcut(QKeySequence("Esc"), self).activated.connect(self.close)

    # ── 암호 메모 관리 ───────────────────────────────────────────────────────
    def _lock_action(self, memo: Dict[str, Any], action: str) -> None:
        """선택한 메모에 암호 관련 동작을 수행합니다. (메모 창의 기능을 그대로 사용, 창은 띄우지 않음)"""
        memo_id = memo.get('id', '')
        if not memo_id or self.is_trash_mode:
            return
        self._flush_preview_save()
        w = self.ui_manager.memo_windows.get(memo_id)
        if w is None:
            fresh = next((x for x in self.ui_manager.sync_manager.load_local_memos() if x.get('id') == memo_id), None)
            if not fresh:
                return
            self.ui_manager.create_new_memo(fresh, show_on_create=False)
            w = self.ui_manager.memo_windows.get(memo_id)
        if w is None:
            return
        w._dialog_parent = self
        try:
            getattr(w, action)()
        finally:
            w._dialog_parent = None
        self.pv.clear()
        self.refresh()

    def _lock_action_on_current(self, action: str) -> None:
        r = self.table.currentRow()
        item = self.table.item(r, 2) if r >= 0 else None
        memo = item.data(Qt.ItemDataRole.UserRole) if item else None
        if memo:
            self._lock_action(memo, action)
        else:
            self.show_toast("먼저 목록에서 메모를 선택하세요.")

    def _add_lock_menu(self, menu: Any, m: Dict[str, Any]) -> None:
        if m.get('_unreadable'):
            return
        sc = self.ui_manager.sync_manager.settings.get("shortcuts", {})
        def _label(text: str, key: str) -> str:
            return f"{text} ({sc[key]})" if sc.get(key) else text

        menu.addSeparator()
        if m.get('_locked'):
            menu.addAction(_label("🔓 잠금 해제 (암호 입력)", "toggle_memo_lock")).triggered.connect(
                lambda: self._lock_action(m, "prompt_unlock"))
            if self.ui_manager.sync_manager.memo_has_master_recovery(m.get('id', '')):
                menu.addAction("관리자 키로 복구…").triggered.connect(
                    lambda: self._lock_action(m, "recover_with_master_key"))
        elif m.get('is_locked'):
            menu.addAction(_label("🔒 지금 잠그기", "toggle_memo_lock")).triggered.connect(
                lambda: self._lock_action(m, "lock_now"))
            menu.addAction(_label("암호 변경", "set_memo_password")).triggered.connect(
                lambda: self._lock_action(m, "set_memo_password"))
            menu.addAction("암호 제거 (일반 메모로)").triggered.connect(
                lambda: self._lock_action(m, "remove_memo_password"))
        else:
            menu.addAction(_label("🔒 이 메모에 암호 걸기", "set_memo_password")).triggered.connect(
                lambda: self._lock_action(m, "set_memo_password"))

    def keyPressEvent(self, e: Any) -> None:
        if e.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.del_checked()
            e.accept()
            return
        super().keyPressEvent(e)

    def init_ui(self) -> None:
        self.setWindowTitle("Memos Explorer")
        geom = self.ui_manager.sync_manager.settings.get('explorer_geom')
        if geom and len(geom) == 4:
            self.setGeometry(geom[0], geom[1], geom[2], geom[3])
        else:
            self._apply_initial_window_size()
        self.setMinimumSize(580, 440)

        self.is_pinned = self.ui_manager.sync_manager.settings.get('explorer_is_pinned', True)
        f = Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowSystemMenuHint | Qt.WindowType.WindowMinimizeButtonHint
        if self.is_pinned:
            f = f | Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(f)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        main_l = QVBoxLayout(self)
        main_l.setContentsMargins(15, 15, 15, 15)

        self.bg = QFrame()
        self.bg.setObjectName("ExplorerBg")
        bg_l = QVBoxLayout(self.bg)
        bg_l.setContentsMargins(20, 20, 20, 20)
        main_l.addWidget(self.bg)

        # 📌 상단 헤더: 좌측 제목 & 우측 윈도우 스타일 컨트롤 버튼 (─, □, ✕)
        ctrl = QHBoxLayout()

        self.title_label = QLabel("Memos")
        ctrl.addWidget(self.title_label)

        self.btn_app_theme = QPushButton("")
        self.btn_app_theme.setFixedSize(100, 30)
        self.btn_app_theme.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_app_theme.clicked.connect(self.toggle_app_theme)

        # 알림(토스트)은 '미리보기' 제목 바로 옆에 표시합니다.
        self.toast = QLabel("")
        self.toast.hide()
        self._toast_timer = QTimer(self)
        self._toast_timer.setSingleShot(True)
        self._toast_timer.timeout.connect(self.toast.hide)

        ctrl.addWidget(self.btn_app_theme)
        ctrl.addStretch()

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

        bg_l.addLayout(ctrl)

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

        pg_l = QHBoxLayout()
        self.p_b = QPushButton("‹")
        self.p_b.setFixedSize(30, 30)
        self.p_b.clicked.connect(self.go_prev)

        self.p_l = QLabel("1 / 1")

        self.n_b = QPushButton("›")
        self.n_b.setFixedSize(30, 30)
        self.n_b.clicked.connect(self.go_next)

        pg_l.addStretch()
        pg_l.addWidget(self.p_b)
        pg_l.addWidget(self.p_l)
        pg_l.addWidget(self.n_b)
        pg_l.addStretch()
        bg_l.addLayout(pg_l)

        pv_head = QHBoxLayout()
        pv_head.setSpacing(10)
        pv_title = QLabel("미리보기")
        pv_title.setMinimumHeight(24)
        pv_head.addWidget(pv_title)
        pv_head.addWidget(self.toast)
        pv_head.addStretch()
        bg_l.addLayout(pv_head)
        self.pv = QTextEdit()
        self.pv.setFixedHeight(100)
        self.pv.setReadOnly(False)
        bg_l.addWidget(self.pv)
        self.pv.textChanged.connect(self.on_preview_changed)

        # 총 n개 메모 알림 + total.svg 아이콘 적용
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
        stat_layout.addStretch()
        bg_l.addWidget(self.stat_box)

        self.btn_box = QWidget()
        self.btn_l = QHBoxLayout(self.btn_box)
        self.btn_l.setContentsMargins(0, 10, 0, 0)
        bg_l.addWidget(self.btn_box)

        self.setup_btns()
        self.refresh()

        self.grip = QSizeGrip(self)
        self._apply_font_scale()
        self.apply_size_settings()

    def is_size_fixed(self) -> bool:
        return bool(self.ui_manager.sync_manager.settings.get('explorer_fixed_size', False))

    def apply_size_settings(self) -> None:
        """환경설정의 탐색기 크기·고정 옵션을 창에 반영합니다."""
        geom = self.ui_manager.sync_manager.settings.get('explorer_geom')
        fixed = self.is_size_fixed()
        if fixed and self.isMaximized():
            self.showNormal()
        self.setMinimumSize(580, 440)
        self.setMaximumSize(16777215, 16777215)
        if geom and len(geom) == 4 and not self.isMaximized():
            self.resize(max(580, int(geom[2])), max(440, int(geom[3])))
        if fixed:
            # 모니터 간 이동(DPI 변경) 등 어떤 경우에도 크기가 변하지 않도록 고정
            self.setFixedSize(self.size())
        self.grip.setVisible(not fixed)

    def toggle_maximize(self) -> None:
        """100% 정상 작동하는 윈도우 최대화/복원 기능"""
        if self.is_size_fixed():
            return
        if self.isMaximized():
            self.showNormal()
            self.btn_win_max.setText("")
            self.btn_win_max.setToolTip("최대화")
        else:
            self.showMaximized()
            self.btn_win_max.setText("")
            self.btn_win_max.setToolTip("복원")

    def toggle_app_theme(self) -> None:
        cur = self.ui_manager.sync_manager.settings.get('app_theme', 'white')
        new_theme = "dark" if cur == "white" else "white"
        self.ui_manager.sync_manager.settings['app_theme'] = new_theme
        self.ui_manager.sync_manager.save_settings(self.ui_manager.sync_manager.settings)

        self.apply_theme_style()
        self.update_filter_buttons()
        self.update_table()

        # 열려있는 모든 메모 창에도 테마 변경 브로드캐스팅
        for w in self.ui_manager.memo_windows.values():
            if w.isVisible():
                w.apply_data()

        if self.ui_manager.settings_window and self.ui_manager.settings_window.isVisible():
            self.ui_manager.settings_window.apply_theme_style()

    def toggle_explorer_pin(self) -> None:
        self.is_pinned = not getattr(self, 'is_pinned', False)
        self.ui_manager.sync_manager.settings['explorer_is_pinned'] = self.is_pinned
        self.ui_manager.sync_manager.save_settings(self.ui_manager.sync_manager.settings)
        f = self.windowFlags()

        was_visible = self.isVisible()

        if self.is_pinned:
            self.setWindowFlags(f | Qt.WindowType.WindowStaysOnTopHint)
            self.show_toast("화면 고정 켜짐")
        else:
            self.setWindowFlags(f & ~Qt.WindowType.WindowStaysOnTopHint)
            self.show_toast("화면 고정 해제됨")

        if was_visible:
            self.show()

        self.update_icons()

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
        self.b_new_code.setIcon(self.ui_manager.get_theme_icon("codememo.svg", is_dark))
        self.b_ref.setIcon(self.ui_manager.get_theme_icon("restart-icon.svg", is_dark))
        self.b_sync.setIcon(self.ui_manager.get_theme_icon("cloude.svg", is_dark))
        self.b_del.setIcon(self.ui_manager.get_theme_icon("minus.svg", is_dark))
        self.b_res.setIcon(self.ui_manager.get_theme_icon("restart-icon.svg", is_dark))
        self.b_empty_trash.setIcon(self.ui_manager.get_theme_icon("trashbucket.svg", is_dark))
        # 고정·새 메모 버튼의 아이콘과 창 버튼 모양은 디자인 스타일이 정합니다.
        modern_style.apply_explorer_chrome(self)

    def apply_theme_style(self) -> None:
        """현재 색 테마·디자인 스타일을 창 전체에 입힙니다."""
        is_dark = self.ui_manager.sync_manager.settings.get('app_theme', 'white') == "dark"
        self.btn_app_theme.setText(" 라이트" if is_dark else " 다크")
        self.update_icons()
        modern_style.apply_explorer(self)

    def sync_selection_and_checkboxes(self) -> None:
        selected_rows = set(index.row() for index in self.table.selectedIndexes())
        for r in range(self.table.rowCount()):
            item_cb = self.table.item(r, 0)
            if item_cb:
                if r in selected_rows:
                    item_cb.setCheckState(Qt.CheckState.Checked)
                else:
                    item_cb.setCheckState(Qt.CheckState.Unchecked)

    def set_filter_mode(self, mode: str) -> None:
        self.filter_mode = mode
        self.update_filter_buttons()
        self.current_page = 1
        self.refresh()

    def update_filter_buttons(self) -> None:
        modern_style.apply_explorer_filters(self)

    def wheelEvent(self, event: Any) -> None:
        if not (event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
            super().wheelEvent(event)
            return

        delta = event.angleDelta().y()
        if delta == 0:
            return

        self.ui_font_pt = max(9, min(20, self.ui_font_pt + (1 if delta > 0 else -1)))
        self.ui_manager.sync_manager.settings["explorer_font_pt"] = self.ui_font_pt
        self.apply_theme_style()
        self.ui_manager.sync_manager.save_settings(self.ui_manager.sync_manager.settings)
        event.accept()

    def resizeEvent(self, event: Any) -> None:
        """창 크기 변경 시 폰트와 아이콘 크기를 동적으로 재계산하여 적용하고,
        버튼 텍스트 표시를 너비에 맞게 전환합니다.
        """
        super().resizeEvent(event)
        self.grip.move(self.width() - 35, self.height() - 35)
        self.grip.resize(16, 16)
        # 창 너비 변화 시 폰트 자동 스케일
        new_pt = self._calc_font_pt_from_size()
        if new_pt != self.ui_font_pt:
            self.ui_font_pt = new_pt
            self.ui_manager.sync_manager.settings["explorer_font_pt"] = self.ui_font_pt
            self.apply_theme_style()
        # 좌우 너비에 따라 버튼 텍스트 표시 전환
        if hasattr(self, 'b_new'):
            self._refresh_btn_labels()

    def closeEvent(self, event: Any) -> None:
        geom = [self.x(), self.y(), self.width(), self.height()]
        self.ui_manager.sync_manager.settings['explorer_geom'] = geom
        self.ui_manager.sync_manager.save_settings(self.ui_manager.sync_manager.settings)
        super().closeEvent(event)

    def show_toast(self, m: str) -> None:
        self.toast.setText(f"✓ {m}")
        self.toast.show()
        self._toast_timer.start(3500)

    def mousePressEvent(self, e: Any) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self._old_pos = e.globalPosition().toPoint()
            self._drag_size = self.size()

    def mouseMoveEvent(self, e: Any) -> None:
        if self._old_pos and not self.isMaximized():
            d = e.globalPosition().toPoint() - self._old_pos
            self.move(self.x() + d.x(), self.y() + d.y())
            self._old_pos = e.globalPosition().toPoint()
            # 배율이 다른 모니터로 넘어갈 때 창이 커지는 현상 방지: 드래그 시작 시 크기를 유지
            drag_size = getattr(self, '_drag_size', None)
            if drag_size is not None and self.size() != drag_size:
                self.resize(drag_size)

    def mouseReleaseEvent(self, e: Any) -> None:
        self._old_pos = None

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
        show_text = self.width() >= 580
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

    def empty_trash(self) -> None:
        if QMessageBox.question(self, "휴지통 비우기", "휴지통의 모든 메모를 영구 삭제할까요? (복구 불가)", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            cnt = self.ui_manager.sync_manager.empty_trash_locally()
            self.pv.clear()
            self.refresh()
            self.show_toast(f"🧹 휴지통의 메모 {cnt}개가 영구 삭제되었습니다.")

    def show_table_context_menu(self, pos: QPoint) -> None:
        item = self.table.itemAt(pos)
        if not item: return
        r = item.row()
        m_item = self.table.item(r, 2)
        if not m_item: return
        m = m_item.data(Qt.ItemDataRole.UserRole)
        if not m: return

        theme = self.ui_manager.sync_manager.settings.get('app_theme', 'white')
        is_dark = (theme == "dark")
        menu = QMenu(self)
        menu.setStyleSheet(modern_style.menu_qss(self.ui_manager.sync_manager.settings))

        act_open = menu.addAction("메모 열기")
        if hasattr(self.ui_manager, 'get_theme_icon'):
            act_open.setIcon(self.ui_manager.get_theme_icon("memo.svg", is_dark))
        act_open.triggered.connect(lambda: self.ui_manager.show_specific_memo(m.get('id')))

        act_open_all = menu.addAction("모든 메모 켜기 (Ctrl+Shift+O)")
        if hasattr(self.ui_manager, 'get_theme_icon'):
            act_open_all.setIcon(self.ui_manager.get_theme_icon("memo.svg", is_dark))
        act_open_all.triggered.connect(self.ui_manager.open_all_memos)

        fav_text = "즐겨찾기 해제" if m.get('is_favorite') else "즐겨찾기 등록"
        act_fav = menu.addAction(fav_text)
        if hasattr(self.ui_manager, 'get_theme_icon'):
            act_fav.setIcon(self.favorite_icon(bool(m.get('is_favorite'))))
        act_fav.triggered.connect(lambda: self.toggle_fav(m))

        prot_text = "삭제 방지 해제" if m.get('is_protected') else "삭제 방지 설정"
        act_prot = menu.addAction(prot_text)
        if hasattr(self.ui_manager, 'get_theme_icon'):
            act_prot.setIcon(self.ui_manager.get_theme_icon("lock_open.svg" if m.get('is_protected') else "lock_close.svg", is_dark))
        act_prot.triggered.connect(lambda: self.toggle_protect(m))
        self._add_lock_menu(menu, m)

        menu.addSeparator()
        cm = menu.addMenu("메모 색상 변경")
        if hasattr(self.ui_manager, 'get_theme_icon'):
            cm.setIcon(self.ui_manager.get_theme_icon("colorpalette_89189.svg", is_dark))
        for n, c in {"다크그레이": "#2E3440", "하늘색": "#E0F2FE", "연두색": "#DCFCE7", "노란색": "#FEF9C3", "분홍색": "#FCE7F3", "흰색": "#FFFFFF"}.items():
            cm.addAction(n).triggered.connect(lambda checked, memo=m, code=c: self.change_memo_color(memo, code))

        act_copy = menu.addAction("본문 내용 복사")
        if hasattr(self.ui_manager, 'get_theme_icon'):
            act_copy.setIcon(self.ui_manager.get_theme_icon("font.svg", is_dark))
        act_copy.triggered.connect(lambda: self.copy_memo_text(m))

        menu.addSeparator()
        act_del = menu.addAction("삭제 (휴지통)")
        if hasattr(self.ui_manager, 'get_theme_icon'):
            act_del.setIcon(self.ui_manager.get_theme_icon("trashbucket.svg", is_dark, override_color="#FF453A"))
        act_del.triggered.connect(lambda: self.delete_single_memo(m))

        menu.exec(self.table.viewport().mapToGlobal(pos))

    def _save_memo_meta(self, memo: Dict[str, Any], **changes: Any) -> None:
        """즐겨찾기·고정·색상 같은 메모 속성을 저장합니다.

        메모 창이 열려 있으면 창이 들고 있는 데이터에도 같이 반영합니다.
        (그렇지 않으면 창이 다음에 저장할 때 예전 값으로 되돌려 버립니다)
        """
        memo.update(changes)
        w = self.ui_manager.memo_windows.get(memo.get('id', ''))
        if w:
            w.memo_data.update(changes)
            self.ui_manager.sync_manager.save_memo_locally(w.memo_data)
        else:
            self.ui_manager.sync_manager.save_memo_locally(memo)

    def toggle_protect(self, memo: Dict[str, Any]) -> None:
        self._save_memo_meta(memo, is_protected=not memo.get('is_protected', False))
        self.show_toast(f"{'🔒 삭제 방지 설정됨' if memo['is_protected'] else '🔓 삭제 방지 해제됨'}")
        self.refresh()

    def change_memo_color(self, memo: Dict[str, Any], color_hex: str) -> None:
        self._save_memo_meta(memo, bg_color=color_hex)
        memo_id = memo.get('id')
        if memo_id and memo_id in self.ui_manager.memo_windows:
            self.ui_manager.memo_windows[memo_id].apply_data()
        self.refresh()

    def copy_memo_text(self, memo: Dict[str, Any]) -> None:
        if memo.get('_locked') or memo.get('_unreadable'):
            self.show_toast("🔒 잠긴 메모는 복사할 수 없습니다.")
            return
        raw_cnt = memo.get('content', '')
        text = clean_plain_text(raw_cnt)
        QApplication.clipboard().setText(text)
        self.show_toast("본문 내용이 클립보드에 복사되었습니다.")

    def delete_single_memo(self, memo: Dict[str, Any]) -> None:
        if memo.get('is_protected'):
            self.show_toast("🔒 삭제 방지 설정된 메모입니다.")
            return
        memo_id = memo.get('id')
        if memo_id and QMessageBox.question(self, "삭제", f"'{memo.get('title','')}' 메모를 휴지통으로 이동할까요?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            self.ui_manager.close_memo_window_by_id(memo_id, is_deleting=True)
            self.ui_manager.sync_manager.delete_memo_locally(memo_id, title=memo.get('title'))
            self.ui_manager.sync_manager.delete_memos_cloud([memo_id])
            self.pv.clear()
            self.refresh()

    def on_cell_click(self, r: int, c: int) -> None:
        """셀 클릭 시 미리보기 업데이트 — 코드 메모는 D2Coding 폰트 적용."""
        m_item = self.table.item(r, 2)
        if m_item:
            m = m_item.data(Qt.ItemDataRole.UserRole)
            if m:
                self._flush_preview_save()
                self._is_loading_preview = True
                sealed = bool(m.get('_locked') or m.get('_unreadable'))
                # 창에 아직 저장되지 않은 입력이 있으면 먼저 저장하고 그 내용을 보여줍니다.
                w = self.ui_manager.memo_windows.get(m.get('id', ''))
                if w and not sealed and not w.is_sealed():
                    w.flush_auto_save()
                    m['content'] = w.memo_data.get('content', m.get('content', ''))
                content = m.get('content', '')
                if m.get('_locked'):
                    clean_text = "🔒 암호 메모입니다. 메모를 열어 암호를 입력하면 볼 수 있습니다."
                elif m.get('_unreadable'):
                    clean_text = "⚠ 본문을 복호화할 수 없는 메모입니다."
                else:
                    clean_text = clean_plain_text(content)
                self.pv.setReadOnly(self.is_trash_mode or sealed)
                self.pv.setPlainText(clean_text)
                self._is_loading_preview = False

    def on_preview_changed(self) -> None:
        if self._is_loading_preview or self.is_trash_mode:
            return
        r = self.table.currentRow()
        if r < 0:
            return
        m_item = self.table.item(r, 2)
        if m_item:
            m = m_item.data(Qt.ItemDataRole.UserRole)
            if not m: return
            if m.get('_locked') or m.get('_unreadable') or self.pv.isReadOnly():
                return
            memo_id = m.get('id', '')
            new_content = self.pv.toPlainText()
            m['content'] = new_content
            m['updated_at'] = datetime.datetime.now().isoformat()

            if self._pending_preview_memo is not None and self._pending_preview_memo is not m:
                self._flush_preview_save()
            self._pending_preview_memo = m
            self._preview_save_timer.start()

            if memo_id in self.ui_manager.memo_windows:
                w = self.ui_manager.memo_windows[memo_id]
                w._is_updating_from_explorer = True
                w.text_edit.setPlainText(new_content)
                w._is_updating_from_explorer = False
                # 창이 들고 있는 데이터도 맞춰 두어야, 창이 나중에 저장할 때 미리보기 편집을 되돌리지 않습니다.
                w.memo_data['content'] = new_content
                w.memo_data['updated_at'] = m['updated_at']
                # 미리보기에서의 입력도 '마지막 입력'으로 보고 자동 잠금 시간을 다시 셉니다.
                w.restart_relock_timer()

            if self.table.item(r, 3):
                self.table.item(r, 3).setText(datetime.datetime.now().strftime("%y%m%d.%H%M"))

    def _flush_preview_save(self) -> None:
        self._preview_save_timer.stop()
        m = self._pending_preview_memo
        self._pending_preview_memo = None
        if m is not None:
            self.ui_manager.sync_manager.save_memo_locally(m)

    def hideEvent(self, event: Any) -> None:
        self._flush_preview_save()
        super().hideEvent(event)

    def on_cell_double_click(self, r: int, c: int) -> None:
        if not self.is_trash_mode:
            m_item = self.table.item(r, 2)
            if m_item:
                m = m_item.data(Qt.ItemDataRole.UserRole)
                if m:
                    memo_id = m.get('id')
                    if memo_id:
                        # id가 있으면 반드시 id로만 열기 (title 폴백 없음)
                        self.ui_manager.show_specific_memo(memo_id)
                    else:
                        self.ui_manager.show_specific_memo(m.get('title', ''))


    def update_btns_visibility(self) -> None:
        while self.btn_l.count():
            wi = self.btn_l.takeAt(0).widget()
            if wi:
                wi.setParent(None)
        if not self.is_trash_mode:
            self.btn_l.addWidget(self.b_new)
            self.btn_l.addWidget(self.b_new_code)
            self.btn_l.addWidget(self.b_ref)
            self.btn_l.addWidget(self.b_sync)
            self.btn_l.addStretch()
            self.btn_l.addWidget(self.b_del)
        else:
            self.btn_l.addWidget(self.b_ref)
            self.btn_l.addWidget(self.b_res)
            self.btn_l.addWidget(self.b_empty_trash)
            self.btn_l.addStretch()
        # 레이아웃 후 다시 텍스트/아이콘 상태 원상 복원
        self._refresh_btn_labels()

    def toggle_trash(self) -> None:
        self.is_trash_mode = self.t_btn.isChecked()
        self.t_btn.setText("목록으로 돌아가기" if self.is_trash_mode else "휴지통 보기")
        is_dark = self.ui_manager.sync_manager.settings.get('app_theme', 'white') == "dark"
        icon_name = "total.svg" if self.is_trash_mode else "trashbucket.svg"
        self.t_btn.setIcon(self.ui_manager.get_theme_icon(icon_name, is_dark))
        self.pv.setReadOnly(self.is_trash_mode)
        self.pv.clear()
        self.current_page = 1
        self.refresh()

    def on_search(self) -> None:
        self.current_page = 1
        self.refresh()

    def go_prev(self) -> None:
        if self.current_page > 1:
            self.current_page -= 1
            self.update_table()

    def go_next(self) -> None:
        total_pages = max(1, (len(self.filtered_memos) + 9) // 10)
        if self.current_page < total_pages:
            self.current_page += 1
            self.update_table()

    def on_header_click(self, idx: int) -> None:
        if idx == 0:
            all_c = all(self.table.item(r, 0).checkState() == Qt.CheckState.Checked for r in range(self.table.rowCount()))
            ns = Qt.CheckState.Unchecked if all_c else Qt.CheckState.Checked
            for r in range(self.table.rowCount()):
                self.table.item(r, 0).setCheckState(ns)

    @pyqtSlot()
    def refresh(self) -> None:
        self._flush_preview_save()
        q = self.s_in.text().lower()
        sb = self.s_type.currentIndex() == 1
        all_m = self.ui_manager.sync_manager.load_trash_memos() if self.is_trash_mode else self.ui_manager.sync_manager.load_local_memos()

        # 메모마다 본문 정리와 태그 추출은 한 번만 합니다. (아래 필터에서 다시 씀)
        # 코드 메모의 '#include', '#region' 같은 것은 태그가 아니므로 일반 메모에서만 태그를 찾습니다.
        hashtags = set()
        gen_cnt = 0
        code_cnt = 0
        digest: Dict[int, tuple] = {}
        for m in all_m:
            plain = clean_plain_text(m.get('content', ''))
            if m.get('is_code_memo'):
                code_cnt += 1
                tags: List[str] = []
            else:
                gen_cnt += 1
                tags = extract_hashtags(plain)
            digest[id(m)] = (plain, tags)
            hashtags.update(tags)

        self.stat_label.setText(f"총 {len(all_m)}개 메모 (일반: {gen_cnt}개 | 코드: {code_cnt}개)")
        if hasattr(self.ui_manager, 'get_theme_icon'):
            self.stat_icon.setPixmap(self.ui_manager.get_theme_icon("total.svg", False, override_color="#8E8E93").pixmap(16, 16))

        cur_tag = self.tag_combo.currentText()
        self.tag_combo.blockSignals(True)
        self.tag_combo.clear()
        self.tag_combo.addItem("#")

        max_len = 1  # 기본 '#' 기준 최소 길이
        for tag in sorted(hashtags):
            tag_str = f"#{tag}"
            self.tag_combo.addItem(tag_str)
            if len(tag_str) > max_len:
                max_len = len(tag_str)

        self.tag_combo.setCurrentText(cur_tag if cur_tag in [self.tag_combo.itemText(i) for i in range(self.tag_combo.count())] else "#")

        # 💡 동적 너비 계산 로직 추가: 폰트 사이즈(pt) 기준 대략적인 픽셀 계산 + 최소 너비 보장 (예: 기본 100px, 글자당 8px 추가)
        dynamic_width = max(100, max_len * 9 + 30)

        view = self.tag_combo.view()
        if view:
            # 드롭다운 리스트 내부는 유동적으로 너비가 넓어지게 하되, 메인 버튼은 위에서 고정함
            view.setMinimumWidth(dynamic_width)

        self.tag_combo.blockSignals(False)

        selected_tag = self.tag_combo.currentText()
        tag_filter = "" if selected_tag == "#" else selected_tag

        all_m.sort(key=lambda x: (x.get('is_favorite', False), x.get('updated_at', '')), reverse=True)

        filtered = []
        for m in all_m:
            is_code = m.get('is_code_memo', False)
            if self.filter_mode == "GENERAL" and is_code: continue
            if self.filter_mode == "CODE" and not is_code: continue

            plain_cnt, tags = digest[id(m)]
            if tag_filter and tag_filter[1:] not in tags:
                continue
            if q:
                if sb and q not in plain_cnt.lower(): continue
                if not sb and q not in m.get('title','').lower(): continue
            filtered.append(m)

        self.filtered_memos = filtered
        self.update_table()
        self.update_btns_visibility()

    def update_table(self) -> None:
        self.table.setRowCount(0)
        row_h = max(38, int(self.ui_font_pt * 3.2))
        items = self.filtered_memos[(self.current_page - 1) * 10 : self.current_page * 10]
        for m in items:
            r = self.table.rowCount()
            self.table.insertRow(r)
            self.table.setRowHeight(r, row_h)

            c = QTableWidgetItem("")
            c.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            c.setCheckState(Qt.CheckState.Unchecked)
            self.table.setItem(r, 0, c)

            if not self.is_trash_mode:
                is_fav = m.get('is_favorite', False)
                fb = QPushButton()
                fb.setFixedSize(30, 30)
                fb.setCursor(Qt.CursorShape.PointingHandCursor)
                fb.setToolTip("즐겨찾기 해제" if is_fav else "즐겨찾기 등록")
                fb.setIcon(self.favorite_icon(is_fav))
                fb.setIconSize(QSize(20, 20))
                fb.setStyleSheet("border: none; background: transparent;")
                fb.clicked.connect(lambda checked, memo=m: self.toggle_fav(memo))
                cell_w = QWidget()
                cell_l = QHBoxLayout(cell_w)
                cell_l.addWidget(fb)
                cell_l.setAlignment(Qt.AlignmentFlag.AlignCenter)
                cell_l.setContentsMargins(0, 0, 0, 0)
                self.table.setCellWidget(r, 1, cell_w)
            else:
                self.table.setCellWidget(r, 1, QWidget())

            is_code = m.get('is_code_memo', False)
            title_text = m.get('title', '').strip()
            theme = self.ui_manager.sync_manager.settings.get('app_theme', 'white')
            is_dark = (theme == "dark")

            is_pinned = m.get('is_pinned', False)

            if is_code:
                lang = m.get('code_lang', 'JSON')
                badge_text = f"[{lang}] {title_text}"
            else:
                badge_text = f"{title_text}"
            if m.get('is_locked'):
                badge_text = f"🔒 {badge_text}"

            t = QTableWidgetItem(badge_text)
            if hasattr(self.ui_manager, 'get_theme_icon'):
                if is_pinned:
                    t.setIcon(self.ui_manager.get_theme_icon("pin_icon_True.svg", is_dark))
                else:
                    t.setIcon(self.ui_manager.get_theme_icon("codememo.svg" if is_code else "memo.svg", is_dark))
            t.setData(Qt.ItemDataRole.UserRole, m)
            t.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)

            if is_code:
                t.setFont(QFont("D2Coding", 10, QFont.Weight.Bold))

            self.table.setItem(r, 2, t)

            up = m.get('updated_at', '')
            try:
                ds = datetime.datetime.fromisoformat(up).strftime("%y%m%d.%H%M") if up else ""
            except (TypeError, ValueError):
                # 수정시각이 깨진 메모 하나 때문에 목록 전체가 멈추지 않도록 함
                ds = ""
            dt = QTableWidgetItem(ds)
            dt.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
            self.table.setItem(r, 3, dt)

            is_prot = m.get('is_protected', False)
            prot_btn = QPushButton("잠김" if is_prot else "해제")
            if hasattr(self.ui_manager, 'get_theme_icon'):
                prot_btn.setIcon(self.ui_manager.get_theme_icon("lock_close.svg" if is_prot else "lock_open.svg", is_dark))
            prot_btn.setFixedSize(50, 28)
            prot_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            prot_btn.clicked.connect(lambda checked, memo=m: self.toggle_protect(memo))

            cell_p_w = QWidget()
            cell_p_l = QHBoxLayout(cell_p_w)
            cell_p_l.addWidget(prot_btn)
            cell_p_l.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cell_p_l.setContentsMargins(0, 0, 0, 0)
            self.table.setCellWidget(r, 4, cell_p_w)

        self.p_l.setText(f"{self.current_page} / {max(1, (len(self.filtered_memos) + 9) // 10)}")
        self.shortcut_font_refresh()
        modern_style.apply_explorer_table(self)

    def toggle_fav(self, memo: Dict[str, Any]) -> None:
        self._save_memo_meta(memo, is_favorite=not memo.get('is_favorite', False))
        self.refresh()

    def del_checked(self) -> None:
        checked_memos = []
        for r in range(self.table.rowCount()):
            item_cb = self.table.item(r, 0)
            if item_cb and item_cb.checkState() == Qt.CheckState.Checked:
                m = self.table.item(r, 2).data(Qt.ItemDataRole.UserRole)
                if m and m not in checked_memos:
                    checked_memos.append(m)

        if not checked_memos:
            for r in set(index.row() for index in self.table.selectedIndexes()):
                m = self.table.item(r, 2).data(Qt.ItemDataRole.UserRole)
                if m and m not in checked_memos:
                    checked_memos.append(m)

        protected_memos = [m for m in checked_memos if m.get('is_protected')]
        if protected_memos:
            self.show_toast(f"🔒 {len(protected_memos)}개 메모가 삭제 방지 상태입니다.")
            checked_memos = [m for m in checked_memos if not m.get('is_protected')]

        if checked_memos and QMessageBox.question(self, "일괄 삭제", f"선택한 {len(checked_memos)}개 메모를 휴지통으로 이동할까요?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            deleted_ids = []
            for m in checked_memos:
                memo_id = m.get('id')
                if memo_id:
                    self.ui_manager.close_memo_window_by_id(memo_id, is_deleting=True)
                    self.ui_manager.sync_manager.delete_memo_locally(memo_id, title=m.get('title'))
                    deleted_ids.append(memo_id)
            self.ui_manager.sync_manager.delete_memos_cloud(deleted_ids)
            self.pv.clear()
            self.refresh()

    def res_checked(self) -> None:
        for r in range(self.table.rowCount()):
            if self.table.item(r, 0).checkState() == Qt.CheckState.Checked:
                m = self.table.item(r, 2).data(Qt.ItemDataRole.UserRole)
                memo_id = m.get('id')
                title = m.get('title', '')
                if memo_id:
                    ex = next((x for x in self.ui_manager.sync_manager.load_local_memos() if x.get('id') == memo_id), None)
                    if not ex or ConflictDialog(title, ex.get('content', ''), m.get('content', '')).exec() == QDialog.DialogCode.Accepted:
                        self.ui_manager.sync_manager.restore_memo_locally(memo_id)
        self.pv.clear()
        self.refresh()