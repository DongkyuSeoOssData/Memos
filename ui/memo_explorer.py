from ui.dialogs import HistoryDialog
from ui.reminder_ui import ask_reminder
from core import reminders
from ui import checklist
from ui.check_marks import CheckEdit
from ui.overlay import WindowOverlay
from ui.settings_window import SettingsWindow
from ui import modern_style
from core import folders
from ui.tab_strip import TabStrip
from ui import screen_bounds
import datetime
from typing import List, Dict, Any, Optional
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLineEdit, QMenu, QApplication, QLabel, QComboBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QFrame, QSizeGrip, QSizePolicy, QListWidget, QGridLayout
)
from PyQt6.QtCore import Qt, QPoint, QSize, QTimer, pyqtSlot
from PyQt6.QtGui import QGuiApplication, QShortcut, QKeySequence, QFont, QIcon
from utils.text_utils import clean_plain_text, extract_hashtags
from ui.explorer_folders import ExplorerFoldersMixin
from ui.explorer_panels import ExplorerPanelsMixin
from ui.explorer_preview import ExplorerPreviewMixin
from ui.explorer_selection import ExplorerSelectionMixin

class MemoExplorerWindow(ExplorerFoldersMixin, ExplorerPanelsMixin, ExplorerPreviewMixin, ExplorerSelectionMixin, QWidget):
    """
    iOS 울트라 미니멀 화이트 & 블랙 탐색기:
    - 윈도우 우측 창 제어 버튼 (─, □/❐, ✕) & 100% 정상 작동하는 최대화/복원
    - 실시간 라이트 / 다크 모드 전환 지원
    """
    FAVORITE_COLOR = "#F5A623"
    # 창 둘레의 투명한 여백. 눈에 보이는 테두리는 창의 실제 크기보다 이만큼 안쪽에 있습니다.
    # 화면 끝에 붙일 때는 보이는 테두리가 끝에 닿도록 이 여백만큼 창이 화면 밖으로 나가게 합니다.
    EDGE_MARGIN = 15

    def __init__(self, ui_manager: Any) -> None:
        super().__init__()
        self.ui_manager = ui_manager
        self.ui_font_pt = int(self.ui_manager.sync_manager.settings.get("explorer_font_pt", 10))
        self.current_page: int = 1
        self.items_per_page: int = 10
        self.filtered_memos: List[Dict[str, Any]] = []
        self.filter_mode: str = "ALL"
        self.is_trash_mode: bool = False
        # 지금 보고 있는 폴더. folders.ALL(전체) / folders.UNFILED(미분류) / "업무/프로젝트A" 같은 경로
        self.current_folder: str = str(self.ui_manager.sync_manager.settings.get("explorer_folder", folders.ALL) or folders.ALL)
        # 사이드바를 열어 창 왼쪽에 덧붙인 너비. 탐색기 본래 크기(글자 크기 계산·저장되는 창 크기)에는 넣지 않습니다.
        self._sidebar_extra: int = 0
        self._checked_ids: set = set()      # 체크해 둔 메모의 id (목록을 다시 그려도 유지)
        # 환경설정 패널: 열면 탐색기 창이 그만큼 옆으로 늘어납니다. (오른쪽에 자리가 없으면 왼쪽)
        self.settings_panel: Optional[SettingsWindow] = None
        self._settings_extra: int = 0
        self._settings_side: str = "right"
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
        w = self.content_width()
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
        # 목록에서 Delete: 고른 메모들을 지웁니다. (삭제 버튼과 같음)
        if getattr(self, '_delete_key', None) is None:       # 단축키를 다시 걸 때 겹쳐서 만들지 않음
            self._delete_key = QShortcut(QKeySequence(Qt.Key.Key_Delete), self.table)
            self._delete_key.setContext(Qt.ShortcutContext.WidgetShortcut)
            # 휴지통을 보는 중에는 동작하지 않습니다. (휴지통의 메모는 복원·비우기 버튼으로 다룸)
            self._delete_key.activated.connect(lambda: None if self.is_trash_mode else self.del_checked())
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
        main_l.setContentsMargins(self.EDGE_MARGIN, self.EDGE_MARGIN, self.EDGE_MARGIN, self.EDGE_MARGIN)

        self.bg = QFrame()
        self.bg.setObjectName("ExplorerBg")
        # 사이드바 방식에서 폴더 목록을 열면 왼쪽에 목록 패널만 덧붙습니다.
        # 그 오른쪽의 탐색기 본래 화면(제목 줄·버튼·표)은 위치와 크기가 그대로입니다.
        bg_outer = QHBoxLayout(self.bg)
        bg_outer.setContentsMargins(20, 20, 20, 20)
        bg_outer.setSpacing(self.SIDEBAR_GAP)
        self.folder_list = QListWidget()
        self.folder_list.setFixedWidth(self.SIDEBAR_WIDTH)
        self.folder_list.hide()
        # 항목을 위아래로 끌어 폴더 순서를 바꿉니다.
        self.folder_list.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        self.folder_list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.folder_list.model().rowsMoved.connect(lambda *args: QTimer.singleShot(0, self._on_sidebar_reordered))
        self.folder_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.folder_list.itemClicked.connect(lambda item: self._on_folder_data(item.data(Qt.ItemDataRole.UserRole)))
        self.folder_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.folder_list.customContextMenuRequested.connect(self._show_sidebar_menu)
        bg_outer.addWidget(self.folder_list)
        bg_l = QVBoxLayout()
        bg_outer.addLayout(bg_l, 1)
        main_l.addWidget(self.bg)

        # 📌 제목 줄: 왼쪽에 [폴더][라이트/다크], 정가운데에 Memos, 오른쪽 끝에 창 버튼(고정 / ─ / □ / ✕)
        self._build_header(bg_l)

        # 탭 줄 방식일 때: 윗줄은 최상위 폴더, 아랫줄은 고른 폴더의 하위 폴더(있을 때만)
        # 자리가 모자라면 < > 로 넘겨 보고, 탭을 끌어서 순서를 바꿉니다.
        self._build_folder_tabs(bg_l)

        self._build_filter_row(bg_l)

        self._build_search_row(bg_l)

        self._build_table(bg_l)

        self._build_pager(bg_l)

        self._build_preview(bg_l)
        # 확인·이름 입력·알림 설정·암호 입력을 따로 창을 띄우지 않고 탐색기 안에서 받는 가림막
        self.inline_overlay = WindowOverlay(self, self.bg)

        # 총 n개 메모 알림 + total.svg 아이콘 적용
        self._build_status_row(bg_l)

        self.btn_box = QWidget()
        self.btn_l = QHBoxLayout(self.btn_box)
        self.btn_l.setContentsMargins(0, 10, 0, 0)
        bg_l.addWidget(self.btn_box)

        self.setup_btns()
        self.refresh()

        self.grip = QSizeGrip(self)
        self._apply_font_scale()
        self.apply_size_settings()

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

        # 알림(토스트)은 '미리보기' 제목 바로 옆에 표시합니다.
        self.toast = QLabel("")
        self.toast.hide()
        self._toast_timer = QTimer(self)
        self._toast_timer.setSingleShot(True)
        self._toast_timer.timeout.connect(self.toast.hide)

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

    def _build_preview(self, bg_l: Any) -> None:
        """미리보기: 환경설정 버튼과 알림(토스트)이 놓이는 제목 줄, 그 아래 본문 칸."""
        pv_head = QHBoxLayout()
        pv_head.setSpacing(10)
        # 환경설정 버튼: 누르면 탐색기 옆에 열리고, 열려 있을 때 다시 누르면 닫힙니다.
        self.btn_settings = QPushButton("")
        self.btn_settings.setFixedSize(28, 24)
        self.btn_settings.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_settings.setToolTip("환경설정 열기/닫기")
        self.btn_settings.clicked.connect(self.ui_manager.toggle_settings)
        pv_head.addWidget(self.btn_settings)
        pv_title = QLabel("미리보기")
        pv_title.setMinimumHeight(24)
        pv_head.addWidget(pv_title)
        pv_head.addWidget(self.toast)
        pv_head.addStretch()
        bg_l.addLayout(pv_head)
        # 미리보기에서도 체크 상자를 네모로 그리고, 눌러서 체크할 수 있습니다.
        self.pv = CheckEdit(self._preview_check_colors)
        self.pv.installEventFilter(self)                 # 미리보기에 들어올 때를 알기 위해 (_save_window_typing_first)
        self.pv.setFixedHeight(100)
        self.pv.setReadOnly(False)
        bg_l.addWidget(self.pv)
        self.pv.textChanged.connect(self.on_preview_changed)
        self.pv.check_marks.intercept = self._toggle_preview_box_keeping_format
        self.pv.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.pv.customContextMenuRequested.connect(self.show_preview_menu)

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
        stat_layout.addStretch()
        bg_l.addWidget(self.stat_box)


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
                w.apply_look()

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
        self.btn_settings.setIcon(self.ui_manager.get_theme_icon("setting.svg", is_dark))
        hover = "rgba(255,255,255,0.14)" if is_dark else "rgba(0,0,0,0.10)"
        self.btn_settings.setStyleSheet(f"QPushButton {{ border: none; background: transparent; border-radius: 0px; }} "
                                        f"QPushButton:hover {{ background: {hover}; }}")
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
        # 크기를 끌어 늘릴 때 화면 오른쪽·아래쪽 밖으로 넘어가지 않게 합니다.
        area = None if self.isMaximized() else screen_bounds.work_area(self)
        if area is not None and self.isVisible():
            area = screen_bounds.grown(area, self.EDGE_MARGIN)
            over_w = self.x() + self.width() - (area.left() + area.width())
            over_h = self.y() + self.height() - (area.top() + area.height())
            if over_w > 0 or over_h > 0:
                fit_w = max(self.minimumWidth(), self.width() - max(0, over_w))
                fit_h = max(self.minimumHeight(), self.height() - max(0, over_h))
                if (fit_w, fit_h) != (self.width(), self.height()):
                    self.resize(fit_w, fit_h)
                    return
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
        if not self.settle_unsaved_settings():           # 저장하지 않은 변경이 있는데 '취소'를 고르면 닫지 않음
            event.ignore()
            return
        self.close_settings_panel()
        # 사이드바로 덧붙인 왼쪽 영역은 빼고, 탐색기 본래 위치·크기만 기억합니다.
        geom = [self.x() + self._sidebar_extra, self.y(), self.content_width(), self.height()]
        self.ui_manager.sync_manager.settings['explorer_geom'] = geom
        self.ui_manager.sync_manager.save_settings(self.ui_manager.sync_manager.settings)
        super().closeEvent(event)

    def show_toast(self, m: str, warn: bool = False) -> None:
        self.toast.setText(("⚠ " if warn else "✓ ") + m)
        self.toast.show()
        self._toast_timer.start(3500)

    def mousePressEvent(self, e: Any) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            self._old_pos = e.globalPosition().toPoint()
            self._drag_size = self.size()
            # 끌기 시작한 지점을 기준으로 위치를 계산해야 자석처럼 붙었다가도 자연스럽게 떨어집니다.
            self._drag_start_cursor = self._old_pos
            self._drag_start_pos = self.pos()

    def mouseMoveEvent(self, e: Any) -> None:
        if self._old_pos and not self.isMaximized():
            cursor = e.globalPosition().toPoint()
            # 화면 가장자리에 가까이 가면 딱 붙고(Ctrl 을 누르고 끌면 붙지 않음), 화면 밖으로는 나가지 않습니다.
            # 보이는 테두리가 화면 끝에 닿도록, 창 둘레의 투명한 여백만큼은 화면 밖으로 나가게 둡니다.
            ctrl_held = bool(QApplication.keyboardModifiers() & Qt.KeyboardModifier.ControlModifier)
            x, y = screen_bounds.drag_position(
                self, getattr(self, '_drag_start_cursor', self._old_pos), getattr(self, '_drag_start_pos', self.pos()),
                cursor, inset=self.EDGE_MARGIN, snap=not ctrl_held)
            self.move(x, y)
            self._old_pos = cursor
            # 배율이 다른 모니터로 넘어갈 때 창이 커지는 현상 방지: 드래그 시작 시 크기를 유지
            drag_size = getattr(self, '_drag_size', None)
            if drag_size is not None and self.size() != drag_size:
                self.resize(drag_size)

    def mouseReleaseEvent(self, e: Any) -> None:
        if self._old_pos is not None:
            self._limit_to_screen()         # 다른 모니터로 옮겼으면 그 모니터 크기에 맞춤
        self._old_pos = None


    def showEvent(self, event: Any) -> None:
        super().showEvent(event)
        if not self.is_size_fixed() and not self.isMaximized():
            self._apply_minimum_size()
        self._limit_to_screen()

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
        has_reminder = bool(reminders.normalize(m.get('reminder')))
        menu.addAction("⏰ 알림 바꾸기…" if has_reminder else "⏰ 알림 설정…").triggered.connect(lambda: self.edit_reminder(m))
        menu.addAction("이전 내용 보기…").triggered.connect(lambda: self.show_history(m))
        self._add_folder_menu(menu, m)
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
        # 여러 줄을 골라 놓고(체크하거나 Ctrl·Shift 로 선택) 그중 하나에서 삭제를 누르면 고른 메모를 모두 지웁니다.
        picked = self.picked_memos()
        several = len(picked) > 1 and any(p.get('id') == m.get('id') for p in picked)
        act_del = menu.addAction(f"선택한 {len(picked)}개 삭제 (휴지통)" if several else "삭제 (휴지통)")
        if hasattr(self.ui_manager, 'get_theme_icon'):
            act_del.setIcon(self.ui_manager.get_theme_icon("trashbucket.svg", is_dark, override_color="#FF453A"))
        act_del.triggered.connect(self.del_checked if several else (lambda: self.delete_single_memo(m)))

        menu.exec(self.table.viewport().mapToGlobal(pos))

    # ── 폴더 ─────────────────────────────────────────────────────────────────


    # ── 알림 · 변경 기록 ─────────────────────────────────────────────────────
    def edit_reminder(self, memo: Dict[str, Any]) -> None:
        """메모의 알림을 걸거나 풉니다. 메모 창이 열려 있으면 그 창이 들고 있는 데이터에 반영합니다."""
        w = self.ui_manager.memo_windows.get(memo.get('id', ''))
        target = w.memo_data if w else memo
        changed, reminder = ask_reminder(self, target.get('reminder'), str(target.get('title', '')))
        if not changed:
            return
        self.ui_manager.sync_manager.set_reminder(target, reminder)
        if w:
            w.refresh_reminder_badge()
        self.show_toast("⏰ " + reminders.describe(reminder) if reminder else "알림을 해제했습니다")
        self.refresh()

    def show_history(self, memo: Dict[str, Any]) -> None:
        """메모의 이전 내용을 보여 주고, 고른 내용으로 되돌립니다."""
        memo_id = memo.get('id', '')
        sm = self.ui_manager.sync_manager
        w = self.ui_manager.memo_windows.get(memo_id)
        if w:
            w.flush_auto_save()
        self._flush_preview_save()
        dialog = HistoryDialog(self, str(memo.get('title', '')), sm.list_history(memo_id),
                               reveal=lambda index, password: sm.read_history_text(memo_id, index, password),
                               check=lambda index, password: sm.restore_problem(memo_id, index, password))
        if (dialog.exec() and dialog.chosen_index is not None
                and sm.restore_history(memo_id, dialog.chosen_index, dialog.chosen_password)):
            self.ui_manager.reload_pulled_memos([memo_id])
            self.pv.clear()
            self.show_toast("이전 내용으로 되돌렸습니다")
            self.refresh()

    def _save_memo_meta(self, memo: Dict[str, Any], **changes: Any) -> None:
        """즐겨찾기·고정·색상 같은 메모 속성을 저장합니다.

        메모 창이 열려 있으면 창이 들고 있는 데이터에도 같이 반영합니다.
        (그렇지 않으면 창이 다음에 저장할 때 예전 값으로 되돌려 버립니다)
        """
        # 수정일시(본문을 고친 시각)는 건드리지 않고, 다른 기기에 전해지도록 '속성 수정 시각'만 갱신합니다.
        changes.setdefault('meta_updated_at', datetime.datetime.now().isoformat())
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
            self.ui_manager.memo_windows[memo_id].apply_look()
        self.refresh()

    def copy_memo_text(self, memo: Dict[str, Any]) -> None:
        if memo.get('_locked') or memo.get('_unreadable'):
            self.show_toast("🔒 잠긴 메모는 복사할 수 없습니다.")
            return
        raw_cnt = memo.get('content', '')
        text = clean_plain_text(raw_cnt)
        QApplication.clipboard().setText(text)
        self.show_toast("본문 내용이 클립보드에 복사되었습니다.")


    def hideEvent(self, event: Any) -> None:
        self._flush_preview_save()
        if not event.spontaneous():                      # 최소화가 아니라 숨기거나 닫을 때: 환경설정 패널도 닫음
            self.close_settings_panel()
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


    @pyqtSlot()
    def refresh(self) -> None:
        self._flush_preview_save()
        q = self.s_in.text().lower()
        sb = self.s_type.currentIndex() == 1
        all_m = self.ui_manager.sync_manager.load_trash_memos() if self.is_trash_mode else self.ui_manager.sync_manager.load_local_memos()
        if not self.is_trash_mode:
            # 폴더를 먼저 걸러 두면 아래의 개수·해시태그·검색이 모두 그 폴더 안에서만 동작합니다.
            self._rebuild_folder_ui(all_m)
            all_m = [m for m in all_m if folders.contains(self.current_folder, folders.folder_of(m))]

        # 메모마다 본문 정리와 태그 추출은 한 번만 합니다. (아래 필터에서 다시 씀)
        # 코드 메모의 '#include', '#region' 같은 것은 태그가 아니므로 일반 메모에서만 태그를 찾습니다.
        hashtags = set()
        gen_cnt = 0
        code_cnt = 0
        digest: Dict[int, tuple] = {}
        # 본문이 그대로인 메모는 지난번에 정리해 둔 것을 씁니다. (메모가 많을 때 목록을 다시 그리는 시간을 줄임)
        # 암호 메모는 푼 내용을 여기에 남겨 두지 않도록 매번 새로 정리합니다.
        remembered = getattr(self, '_digest_cache', {})
        self._digest_cache = {}
        for m in all_m:
            content = m.get('content', '')
            is_code = bool(m.get('is_code_memo'))
            reusable = isinstance(content, str) and not m.get('is_locked')
            key = (content, is_code)
            found = remembered.get(key) if reusable else None
            if found is None:
                plain = clean_plain_text(content)
                found = (plain, [] if is_code else extract_hashtags(plain))
            if reusable:
                self._digest_cache[key] = found
            plain, tags = found
            if is_code:
                code_cnt += 1
            else:
                gen_cnt += 1
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
        # 폴더 탭 줄·글자 크기에 따라 필요한 크기가 달라지므로, 화면을 다시 채운 뒤 최소 크기를 맞춥니다.
        if not self.is_size_fixed() and not self.isMaximized():
            self._apply_minimum_size()


    def update_table(self) -> None:
        # 동기화가 끝나거나 열어 둔 메모가 저장되어 목록이 다시 그려져도, 체크해 둔 것은 그대로 둡니다.
        self._remember_checked()
        self.table.setRowCount(0)
        row_h = max(38, int(self.ui_font_pt * 3.2))
        items = self.filtered_memos[(self.current_page - 1) * 10 : self.current_page * 10]
        for m in items:
            r = self.table.rowCount()
            self.table.insertRow(r)
            self.table.setRowHeight(r, row_h)

            c = QTableWidgetItem("")
            c.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            c.setCheckState(Qt.CheckState.Checked if m.get('id') in self._checked_ids else Qt.CheckState.Unchecked)
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
            reminder_text = reminders.describe(m.get('reminder'))
            if reminder_text:
                badge_text = f"⏰ {badge_text}"
            raw_content = m.get('content', '')
            # 암호 메모는 열려 있든 잠겨 있든 진행 표시를 내지 않습니다. (잠그고 풀 때마다 나타났다 사라지지 않게, 내용도 드러나지 않게)
            if isinstance(raw_content, str) and checklist.has_boxes(raw_content) and not (m.get('is_locked') or m.get('_locked') or m.get('_unreadable')):
                progress = checklist.progress_label(clean_plain_text(raw_content))
                if progress:
                    badge_text = f"{badge_text}  {progress}"       # 남은 일이 있으면 ☐, 다 끝냈으면 ☑

            t = QTableWidgetItem(badge_text)
            if reminder_text:
                t.setToolTip("알림: " + reminder_text)
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


