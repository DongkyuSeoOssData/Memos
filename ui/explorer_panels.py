"""메모 탐색기의 창 크기와, 옆으로 덧붙는 영역.

폴더 사이드바(왼쪽)와 환경설정 패널(오른쪽, 자리가 없으면 왼쪽)을 여닫을 때 창을 그만큼 늘리고 줄이며,
탐색기 본래 영역의 크기와 자리는 그대로 둡니다. 최소 크기, 화면 경계, 환경설정을 닫기 전에 묻는 일도 여기서 합니다.
(MemoExplorerWindow 에 섞어 쓰는 부분)
"""
from ui import themed_dialog
from ui.settings_window import SettingsWindow
from ui import screen_bounds
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QGuiApplication


class ExplorerPanelsMixin:
    """탐색기의 창 크기와 옆 패널."""

    MIN_WIDTH, MIN_HEIGHT = 580, 440     # 탐색기 본래 영역의 최소 크기 (옆에 덧붙는 영역은 따로 더함)
    DEFAULT_SIZE = (666, 961)            # 처음 열 때의 크기 (목록 10개와 미리보기가 다 보이는 크기)
    SIDEBAR_WIDTH = 176                  # 폴더 사이드바의 너비
    SIDEBAR_GAP = 12                     # 덧붙는 영역과 본래 영역 사이의 간격
    SETTINGS_WIDTH = 540                 # 환경설정 패널의 너비

    def is_size_fixed(self) -> bool:
        return bool(self.ui_manager.sync_manager.settings.get('explorer_fixed_size', False))

    def apply_size_settings(self) -> None:
        """환경설정의 탐색기 크기·고정 옵션을 창에 반영합니다."""
        geom = self.ui_manager.sync_manager.settings.get('explorer_geom')
        fixed = self.is_size_fixed()
        if fixed and self.isMaximized():
            self.showNormal()
        self._fit_table()                                # 목록 칸 높이(화면이 작으면 줄임)부터 정해야 최소 크기가 맞음
        self._apply_minimum_size()
        self.setMaximumSize(16777215, 16777215)
        if geom and len(geom) == 4 and not self.isMaximized():
            self.resize(max(580, int(geom[2])) + self._sidebar_extra + self._settings_extra, max(440, int(geom[3])))
        if fixed:
            # 모니터 간 이동(DPI 변경) 등 어떤 경우에도 크기가 변하지 않도록 고정
            self.setFixedSize(self.size())
        self.grip.setVisible(not fixed)
        self._limit_to_screen()

    def _limit_to_screen(self) -> None:
        """창이 화면보다 커지거나 화면 밖에 놓이지 않게 합니다. (크기 고정 상태에서는 크기는 그대로, 위치만)"""
        if self.isMaximized():
            return
        self._fit_table()                                # 화면이 작으면 목록 칸부터 줄여 창이 들어가게 함
        limit = screen_bounds.max_inner_size(self, inset=self.EDGE_MARGIN)
        if limit is None:
            return
        if self.is_size_fixed():
            if self.width() > limit[0] or self.height() > limit[1]:
                self.setFixedSize(min(self.width(), limit[0]), min(self.height(), limit[1]))
        else:
            self.setMaximumSize(*limit)
        screen_bounds.keep_inside(self, inset=self.EDGE_MARGIN)

    def _apply_minimum_size(self) -> None:
        """창의 최소 크기. 폴더 탭 줄처럼 화면에 놓인 것이 늘어나면 그만큼 더 필요하므로, 배치가 요구하는 크기보다 작아지지 않게 합니다."""
        # 너비는 내용에 따라 늘리지 않습니다. (긴 폴더 이름은 줄여 보여 주고, 많은 탭은 < > 로 넘겨 봄)
        self._fit_header()
        for holder in (self.bg, self):                   # 목록 칸 높이 등이 막 바뀌었으면 그것을 반영한 크기로 견줌
            if holder.layout():
                holder.layout().invalidate()
                holder.layout().activate()
        self.setMinimumSize(self.MIN_WIDTH + self._sidebar_extra + self._settings_extra,
                            max(self.MIN_HEIGHT, self.minimumSizeHint().height()))

    def _fit_header(self) -> None:
        """제목 줄의 폴더 버튼·드롭다운을 가운데의 'Memos' 와 겹치지 않는 너비로 맞춥니다.

        자리가 모자라면 창을 넓히는 대신 폴더 이름을 줄여(…) 보여 주고, 온전한 이름은 풍선 도움말로 보여 줍니다.
        드롭다운도 사이드바 방식의 폴더 버튼과 같은 너비를 씁니다.
        """
        name = self._folder_title(self.current_folder)
        button = self.btn_folder
        metrics = button.fontMetrics()
        button.setMinimumWidth(0)
        button.setMaximumWidth(16777215)
        button.setText(" " + name)
        natural = button.sizeHint().width()
        chrome = natural - metrics.horizontalAdvance(" " + name)          # 아이콘·안쪽 여백이 차지하는 너비
        # 제목 줄에서 'Memos' 왼쪽에 남는 자리 = (줄 너비 - 'Memos' 너비) / 2 에서 라이트/다크 버튼과 간격을 뺀 것
        margins = self.bg.layout().contentsMargins()
        row_width = self.content_width() - 2 * self.EDGE_MARGIN - margins.left() - margins.right()
        side = (row_width - self.title_label.sizeHint().width()) // 2 - 8
        room = max(70, side - self.btn_app_theme.width() - self._header_left.spacing())
        width = min(natural, room)
        if width < natural:
            button.setText(" " + metrics.elidedText(name, Qt.TextElideMode.ElideRight, max(10, width - chrome)))
        button.setFixedWidth(width)
        button.setToolTip(f"{name} — 폴더 목록 열기/닫기")
        self.folder_combo.setFixedWidth(max(width, min(room, 110)))
        self.folder_combo.setToolTip(f"{name} — 폴더 (고른 폴더의 메모만 보기)")
        self.folder_combo.view().setMinimumWidth(240)

    def content_x(self) -> int:
        """왼쪽에 덧붙인 영역(폴더 사이드바, 왼쪽에 붙은 환경설정 패널)을 뺀, 탐색기 본래 영역의 왼쪽 위치."""
        return self.x() + self._sidebar_extra + (self._settings_extra if self._settings_side == "left" else 0)

    def content_width(self) -> int:
        """사이드바·환경설정 패널로 덧붙인 영역을 뺀, 탐색기 본래 너비."""
        return self.width() - self._sidebar_extra - self._settings_extra

    def _grow_sideways(self, delta: int, to_left: bool, stay_on_screen: bool = False) -> None:
        """창을 옆으로 delta 만큼 늘립니다(음수면 줄임). to_left 면 왼쪽으로, 아니면 오른쪽으로.

        덧붙는 영역(폴더 사이드바·환경설정 패널)만큼만 늘리므로 탐색기 본래 영역의 위치와 크기는 그대로입니다.
        stay_on_screen 이면 늘어난 쪽이 화면 밖으로 나가지 않게 합니다.
        """
        if delta == 0 or self.isMaximized():
            return
        fixed = self.is_size_fixed()
        geom = self.geometry()
        # 덧붙는 영역을 여닫은 것이 배치에 반영된 뒤에 크기를 바꿔야, 예전 최소 너비에 걸리지 않습니다.
        for holder in (self.bg, self):
            if holder.layout():
                holder.layout().activate()
        self.setMinimumSize(0, 0)
        self.setMaximumSize(16777215, 16777215)
        left = geom.x() - delta if to_left else geom.x()
        if to_left and delta > 0 and stay_on_screen:
            screen = QGuiApplication.screenAt(geom.center()) or QGuiApplication.primaryScreen()
            if screen:
                left = max(screen.availableGeometry().left() - self.EDGE_MARGIN, left)
        self.setGeometry(left, geom.y(), geom.width() + delta, geom.height())
        self._apply_minimum_size()
        if fixed:
            self.setFixedSize(self.size())
        self._limit_to_screen()

    def _grow_down(self, delta: int) -> None:
        """창을 아래로 delta 만큼 늘립니다(음수면 줄임). 미리보기를 접고 펼 때 그만큼만 창 높이를 바꿉니다."""
        if delta == 0 or self.isMaximized():
            return
        fixed = self.is_size_fixed()
        for holder in (self.bg, self):
            if holder.layout():
                holder.layout().activate()
        self.setMinimumSize(0, 0)
        self.setMaximumSize(16777215, 16777215)
        self.resize(self.width(), self.height() + delta)
        self._apply_minimum_size()
        if fixed:
            self.setFixedSize(self.size())
            geom = self.ui_manager.sync_manager.settings.get('explorer_geom')
            if geom and len(geom) == 4:                  # 크기 고정이면 고정 크기도 그만큼 바꿔 둠
                self.ui_manager.sync_manager.settings['explorer_geom'] = [geom[0], geom[1], geom[2], self.height()]
        self._limit_to_screen()

    def _set_sidebar_extra(self, extra: int) -> None:
        """폴더 목록을 여닫을 때 창을 왼쪽으로 그만큼 늘리거나 줄입니다."""
        delta = extra - self._sidebar_extra
        self._sidebar_extra = extra            # 먼저 바꿔 두어야 resizeEvent 가 본래 너비를 그대로 봅니다.
        self._grow_sideways(delta, to_left=True, stay_on_screen=True)

    # ── 환경설정 패널 (폴더 사이드바처럼 탐색기와 한 창으로 열림) ──────────────
    def settings_open(self) -> bool:
        return self.settings_panel is not None

    def _pick_settings_side(self) -> str:
        """패널을 붙일 쪽. 오른쪽에 자리가 있으면 오른쪽, 없고 왼쪽에 있으면 왼쪽."""
        need = self.SETTINGS_WIDTH + self.SIDEBAR_GAP
        area = screen_bounds.work_area(self)
        if area is None or self.isMaximized():
            return "right"
        left = self.x() + self.EDGE_MARGIN                       # 보이는 테두리의 왼쪽
        right = self.x() + self.width() - self.EDGE_MARGIN
        if right + need <= area.left() + area.width():
            return "right"
        return "left" if left - need >= area.left() else "right"

    def open_settings_panel(self) -> None:
        if self.settings_panel is not None:
            return
        panel = SettingsWindow(self.ui_manager.sync_manager, embedded=True)
        panel.setFixedWidth(self.SETTINGS_WIDTH)
        panel.on_close = self.ask_and_close_settings_panel
        side = self._pick_settings_side()
        outer = self.bg.layout()
        if side == "left":
            outer.insertWidget(0, panel)
        else:
            outer.addWidget(panel)
        self.settings_panel = panel
        panel.show()
        self._resize_for_settings(self.SETTINGS_WIDTH + self.SIDEBAR_GAP, side)

    def settle_unsaved_settings(self) -> bool:
        """환경설정에 저장하지 않은 변경이 있으면 어떻게 할지 묻습니다. 닫아도 되면 True, 취소했으면 False.

        '저장하고 닫기'를 고르면 여기서 저장합니다. 바뀐 것이 없으면 묻지 않습니다.
        """
        panel = self.settings_panel
        if panel is None or not panel.is_dirty():
            return True
        if getattr(self, '_asking_unsaved', False):
            return False                                 # 이미 묻고 있는 중
        self._asking_unsaved = True
        try:
            choice = themed_dialog.choose(
                self, "저장하지 않은 변경이 있습니다", "환경설정에서 바꾼 내용을 저장할까요?",
                [("저장하고 닫기", "save", "primary"), ("저장 안 함", "discard", ""), ("취소", None, "")])
        finally:
            self._asking_unsaved = False
        if choice == "save":
            if self.settings_panel is not None:
                self.settings_panel.save()
            return True
        return choice == "discard"

    def ask_and_close_settings_panel(self) -> bool:
        """환경설정 패널을 닫습니다. 저장하지 않은 변경이 있으면 먼저 묻고, 취소하면 닫지 않습니다(False)."""
        if not self.settle_unsaved_settings():
            return False
        self.close_settings_panel()
        return True

    def request_hide(self) -> bool:
        """탐색기를 숨깁니다. 환경설정에 저장하지 않은 변경이 있으면 먼저 묻고, 취소하면 숨기지 않습니다(False)."""
        if not self.settle_unsaved_settings():
            return False
        self.hide()
        return True

    def close_settings_panel(self) -> None:
        """환경설정 패널을 묻지 않고 닫습니다. (저장하지 않은 변경은 버림)"""
        panel = self.settings_panel
        if panel is None:
            return
        self.settings_panel = None
        if self.ui_manager.settings_window is panel:
            self.ui_manager.settings_window = None
        self.bg.layout().removeWidget(panel)
        panel.hide()
        panel.deleteLater()
        self._resize_for_settings(0, self._settings_side)

    def _resize_for_settings(self, extra: int, side: str) -> None:
        """환경설정 패널을 여닫을 때 창을 그만큼 늘리거나 줄입니다. (side: 패널이 붙는 쪽 "left" / "right")"""
        delta = extra - self._settings_extra
        self._settings_extra, self._settings_side = extra, side
        self._grow_sideways(delta, to_left=(side == "left"))
