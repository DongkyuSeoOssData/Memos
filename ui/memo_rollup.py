"""메모 창의 접기·펴기와 자리 잡기.

접힌 모습과 펼친 모습 바꾸기, 그때의 위치와 크기 기억하기, 위치 고정, 화면 밖으로 나가지 않게 하기를 맡습니다.
어디에 놓을지의 규칙(계산)은 ui/memo_geometry.py 에 있고, 여기서는 지금 창의 상태를 넘겨 돌려받은 자리에 창을 놓습니다.
(MemoWindow 에 섞어 쓰는 부분)
"""
from ui import memo_geometry
from typing import Any, Optional
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QRect, QTimer


class MemoRollupMixin:
    """메모 창의 접기·펴기."""

    def _get_rolled_height(self) -> int:
        """settings의 default_rolled_height 값을 우선 읽고, 없으면 53을 반환합니다."""
        if getattr(self, 'ui_manager', None):
            h = self.ui_manager.sync_manager.settings.get('default_rolled_height', 53)
        else:
            h = 53
        return max(36, int(h))

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

    def _box(self) -> tuple:
        return self.x(), self.y(), self.width(), self.height()

    def is_locked_compact(self) -> bool:
        """잠겨 있어서 암호 입력용 작은 크기로 떠 있는지. (이때의 크기는 메모의 크기로 기억하지 않음)"""
        return memo_geometry.is_locked_compact(self.memo_data, self._is_rolled_up)

    def remember_geometry(self) -> None:
        """지금 상태(접힘/펼침)의 위치와 크기를 그 상태의 것으로 기억합니다."""
        memo_geometry.remember(self.memo_data, self._is_rolled_up, self._box())

    # ── 위치 고정 ────────────────────────────────────────────────────────────
    @staticmethod
    def _screen_layout() -> list:
        """지금 연결된 모니터들의 (x, y, 너비, 높이). 고정해 둔 자리를 아직 쓸 수 있는지 견줄 때 씁니다."""
        return [screen.geometry().getRect() for screen in QApplication.screens()]

    def _pinned(self, rolled: bool) -> Optional[tuple]:
        return memo_geometry.pinned_spot(self.memo_data, rolled, self._screen_layout())

    def has_position_pin(self) -> bool:
        """지금 상태(접힘/펼침)의 위치를 고정해 두었는지."""
        return memo_geometry.has_pin(self.memo_data, self._is_rolled_up)

    def pin_position(self) -> None:
        """지금 상태의 자리를 고정합니다. 앞으로 이 상태로 바뀔 때마다 이 자리로 갑니다."""
        screen = QApplication.screenAt(self.geometry().center()) or QApplication.primaryScreen()
        memo_geometry.set_pin(self.memo_data, self._is_rolled_up, (self.x(), self.y()), screen.geometry().getRect())
        self.save_callback(self.memo_data)
        self.show_toast(f"📌 {'접은' if self._is_rolled_up else '펼친'} 위치를 고정했습니다")

    def unpin_position(self) -> None:
        memo_geometry.clear_pin(self.memo_data, self._is_rolled_up)
        self.save_callback(self.memo_data)
        self.show_toast(f"{'접은' if self._is_rolled_up else '펼친'} 위치 고정을 풀었습니다")

    def toggle_position_pin(self) -> None:
        """단축키: 지금 상태의 위치를 고정하거나, 고정해 두었으면 풉니다."""
        self.unpin_position() if self.has_position_pin() else self.pin_position()

    def toggle_rollup(self) -> None:
        """접거나 폅니다.

        바뀔 상태의 위치를 고정해 두었으면 그 자리로, 아니면 왼쪽 아래 모서리를 고정점으로 접히고 펼쳐집니다. (memo_geometry)
        """
        screen = QApplication.screenAt(self.geometry().center()) or QApplication.primaryScreen()
        scr_geom = screen.availableGeometry()
        data = self.memo_data
        default_height = getattr(self, '_normal_height', 300)
        self.remember_geometry()                      # 떠나는 상태의 위치·크기를 먼저 기억

        if not self._is_rolled_up:
            self._normal_height = memo_geometry.own_size(data, False, self._box(), default_height)[1]
            data['rolled_height'] = self._get_rolled_height()
            new_left_x, new_top_y, target_w, target_h = memo_geometry.fold_target(
                data, self._box(), data['rolled_height'], scr_geom, self._pinned(True), default_height)
        else:
            new_left_x, new_top_y, target_w, target_h = memo_geometry.unfold_target(
                data, self._box(), scr_geom, self._pinned(False), default_height)
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
