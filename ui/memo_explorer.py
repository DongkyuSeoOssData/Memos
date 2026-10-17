from ui.overlay import WindowOverlay
from ui.settings_window import SettingsWindow
from ui import modern_style
from core import folders
from ui import screen_bounds
from typing import List, Dict, Any, Optional
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QApplication, QFrame, QSizeGrip, QListWidget
from PyQt6.QtCore import Qt, QPoint, QSize, QTimer
from PyQt6.QtGui import QGuiApplication, QShortcut, QKeySequence
from ui.explorer_folders import ExplorerFoldersMixin
from ui.explorer_panels import ExplorerPanelsMixin
from ui.explorer_preview import ExplorerPreviewMixin
from ui.explorer_selection import ExplorerSelectionMixin
from ui.explorer_layout import ExplorerLayoutMixin
from ui.explorer_list import ExplorerListMixin
from ui.explorer_actions import ExplorerActionsMixin

class MemoExplorerWindow(ExplorerLayoutMixin, ExplorerListMixin, ExplorerActionsMixin, ExplorerFoldersMixin, ExplorerPanelsMixin, ExplorerPreviewMixin, ExplorerSelectionMixin, QWidget):
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
        # 검색어 입력이 멈춘 뒤에만 목록을 다시 읽습니다. (글자마다 전체 재로딩 방지)
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(300)
        self._search_timer.timeout.connect(self.on_search)
        self.init_ui()
        self.apply_theme_style()
        self.bind_global_shortcuts()
        self._fit_table()                                # 화면이 다 갖춰진 뒤의 크기로 목록 칸 높이를 다시 맞춤

    def _apply_initial_window_size(self) -> None:
        """처음 여는 탐색기: 기본 크기(DEFAULT_SIZE)로 주 모니터 가운데에 둡니다. 모니터가 작으면 그 안에 들어가게 줄입니다."""
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        geom = screen.availableGeometry()
        target_w = min(self.DEFAULT_SIZE[0], geom.width())
        target_h = min(self.DEFAULT_SIZE[1], geom.height())
        self.setGeometry(geom.center().x() - target_w // 2, geom.center().y() - target_h // 2, target_w, target_h)

    def _apply_font_scale(self) -> None:
        """현재 ui_font_pt 기준으로 창 전체의 폰트와 행 높이를 적용합니다."""
        base_font = modern_style.app_qfont(self.ui_font_pt)
        self.setFont(base_font)
        self.bg.setFont(base_font)
        self.table.setFont(base_font)
        self.pv.setFont(modern_style.app_qfont(max(9, self.ui_font_pt)))

        # 상단 제어·필터 버튼 아이콘: 폰트 1.4배
        ctrl_icon_sz = max(14, int(self.ui_font_pt * 1.4))
        for btn in [self.btn_win_pin, self.btn_win_min, self.btn_win_max, self.btn_win_close,
                    self.btn_filter_all, self.btn_filter_gen, self.btn_filter_code,
                    self.btn_arrange_rolled, self.btn_arrange_memos, self.t_btn,
                    self.p_b, self.n_b, self.btn_first_page, self.btn_last_page]:
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

    PAGE_SIZE = 10                       # 목록 한 쪽에 보이는 메모 수

    def shortcut_font_refresh(self) -> None:
        row_h = max(38, int(self.ui_font_pt * 3.2))
        self.table.verticalHeader().setDefaultSectionSize(row_h)
        for row in range(self.table.rowCount()):
            self.table.setRowHeight(row, row_h)
        self._fit_table()

    def _fit_table(self) -> None:
        row_h = self.table.verticalHeader().defaultSectionSize()
        # 목록 칸은 한 쪽의 메모 10개가 스크롤 없이 다 보이는 높이로 고정합니다. 창을 키우거나 줄이면 미리보기가 달라집니다.
        # 모니터가 작아 그 높이로는 탐색기가 화면에 들어가지 않으면, 들어가는 만큼만 보이고 목록 안에서 스크롤합니다.
        header = max(self.table.horizontalHeader().height(), self.table.horizontalHeader().sizeHint().height())
        chrome = header + 2 * self.table.frameWidth()
        rows = self.PAGE_SIZE
        limit = screen_bounds.max_inner_size(self, inset=self.EDGE_MARGIN)
        if limit is not None:
            others = self.minimumSizeHint().height() - self.table.minimumHeight()     # 목록 칸을 뺀 나머지가 차지하는 높이
            rows = max(3, min(self.PAGE_SIZE, (limit[1] - others - chrome) // row_h))
        if self.table.minimumHeight() != chrome + rows * row_h:
            self.table.setFixedHeight(chrome + rows * row_h)
            if hasattr(self, 'bg') and self.bg.layout() is not None:
                self.bg.layout().invalidate()
                if not self.is_size_fixed() and not self.isMaximized():
                    self._apply_minimum_size()           # 창의 최소 높이도 목록 칸에 맞춤

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
        # 목록에서 F2(제목 수정 단축키): 고른 메모의 제목 바꾸기. 단축키를 바꾸면 다시 걸 때 새 키로 바뀝니다.
        if getattr(self, '_rename_key', None) is None:
            self._rename_key = QShortcut(self.table)
            self._rename_key.setContext(Qt.ShortcutContext.WidgetShortcut)
            self._rename_key.activated.connect(self.rename_current)
        self._rename_key.setKey(QKeySequence(s_cfg.get("rename", "F2")))
        QShortcut(QKeySequence(s_cfg.get("toggle_memo_lock", "Ctrl+L")), self).activated.connect(
            lambda: self._lock_action_on_current("toggle_memo_lock"))
        QShortcut(QKeySequence(s_cfg.get("set_memo_password", "Ctrl+Shift+L")), self).activated.connect(
            lambda: self._lock_action_on_current("set_memo_password"))
        QShortcut(QKeySequence("Esc"), self).activated.connect(self.close)


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


    def apply_theme_style(self) -> None:
        """현재 색 테마·디자인 스타일을 창 전체에 입힙니다."""
        is_dark = self.ui_manager.sync_manager.settings.get('app_theme', 'white') == "dark"
        self.btn_app_theme.setText(" 라이트" if is_dark else " 다크")
        self.update_icons()
        self._apply_font_scale()                         # 앱 글꼴이 바뀌었을 수 있음
        modern_style.apply_explorer(self)


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
            # 창이 화면 안에서 시작할 때만 크기로 맞춥니다. 창 자체가 화면 밖에 있으면 줄일 일이 아니라 옮길 일입니다. (_limit_to_screen)
            starts_inside = self.x() < area.left() + area.width() and self.y() < area.top() + area.height()
            if starts_inside and (over_w > 0 or over_h > 0):
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
        self.stat_icon.hide()
        self.stat_label.hide()
        self.toast.show()
        self._toast_timer.start(3500)

    def hide_toast(self) -> None:
        self.toast.hide()
        self.stat_icon.show()
        self.stat_label.show()

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


    # ── 폴더 ─────────────────────────────────────────────────────────────────


    def hideEvent(self, event: Any) -> None:
        if not event.spontaneous():                      # 최소화가 아니라 숨기거나 닫을 때: 환경설정 패널도 닫음
            self.close_settings_panel()
        super().hideEvent(event)


