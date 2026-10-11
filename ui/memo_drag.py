"""메모 창을 끌어 옮기기: 제목 줄을 잡고 끌기, 화면 가장자리와 다른 메모에 붙이기.

(MemoWindow 에 섞어 쓰는 부분)
"""
from ui import screen_bounds
from typing import Any, Optional
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt


class MemoDragMixin:
    """메모 창 끌어 옮기기."""

    def find_snap_target_memo(self) -> Optional['MemoWindow']:
        if not getattr(self, 'ui_manager', None):
            return None

        memos_below = []
        memos_above = []

        for other_id, other_win in self.ui_manager.memo_windows.items():
            if other_win is self or not other_win.isVisible() or not other_win._is_rolled_up:
                continue

            # 📌 수직 15px 이내 직접 맞닿아 있고 가로 영역이 겹칠 때만(붙어있을 때만) 탐색
            touch_below = abs(other_win.y() - (self.y() + self.height())) <= 15
            touch_above = abs((other_win.y() + other_win.height()) - self.y()) <= 15
            horiz_overlap = (self.x() < other_win.x() + other_win.width()) and (self.x() + self.width() > other_win.x())

            if (touch_below or touch_above) and horiz_overlap:
                dy = other_win.y() - self.y()
                if dy > 0:
                    memos_below.append((dy, other_win))
                elif dy < 0:
                    memos_above.append((abs(dy), other_win))

        if memos_below:
            memos_below.sort(key=lambda item: item[0])
            return memos_below[0][1]
        if memos_above:
            memos_above.sort(key=lambda item: item[0])
            return memos_above[0][1]

        return None

    def mousePressEvent(self, e: Any) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            if hasattr(self, 'title_edit') and not self.title_edit.isReadOnly():
                pos_in_title = self.title_edit.mapFromGlobal(e.globalPosition().toPoint())
                if not self.title_edit.rect().contains(pos_in_title):
                    self.handle_rename()

            self._old_pos = e.globalPosition().toPoint()
            self._press_geom = self.geometry()
            self._drag_start_pos = e.globalPosition().toPoint()
            self._drag_start_win_pos = self.pos()
            self._snap_lock_origin = None
            pos_in_title = self.title_edit.mapFromGlobal(e.globalPosition().toPoint())
            self._drag_from_title = self.title_edit.rect().contains(pos_in_title)

    def mouseMoveEvent(self, e: Any) -> None:
        if getattr(self, '_old_pos', None) and not self.isMaximized():
            curr_global = e.globalPosition().toPoint()

            # 📌 1) 마우스 시작점 기준 1:1 직결 절대 목표 좌표 계산 (딜레이/느림 100% 방지)
            mouse_delta = curr_global - self._drag_start_pos
            target_x = self._drag_start_win_pos.x() + mouse_delta.x()
            target_y = self._drag_start_win_pos.y() + mouse_delta.y()

            screen = QApplication.screenAt(curr_global) or QApplication.primaryScreen()
            scr_geom = screen.availableGeometry()

            is_title_drag = getattr(self, '_drag_from_title', False)
            ctrl_held = bool(QApplication.keyboardModifiers() & Qt.KeyboardModifier.ControlModifier)

            # 📌 2) 제목 드래그 시 위아래 15px 이내 Y축 고정 (좌우 슬라이딩)
            if self._is_rolled_up and is_title_drag and not ctrl_held:
                dy = abs(curr_global.y() - self._drag_start_pos.y())
                if dy <= 15:
                    target_y = self._drag_start_win_pos.y()

            new_x = target_x
            new_y = target_y

            # 📌 3) 15px 이내 실시간 부드러운 0px 레고 블록 스냅 (멈춤 현상 완전 해소)
            if self._is_rolled_up and not ctrl_held and getattr(self, 'ui_manager', None):
                snap_in = 15
                for other_id, other_win in self.ui_manager.memo_windows.items():
                    if other_win is self or not other_win.isVisible() or not other_win._is_rolled_up:
                        continue

                    # 수직 스냅 (상하단 0px 및 상단 맞춤)
                    if abs(target_y - (other_win.y() + other_win.height())) < snap_in:
                        new_y = other_win.y() + other_win.height()
                    elif abs((target_y + self.height()) - other_win.y()) < snap_in:
                        new_y = other_win.y() - self.height()
                    elif abs(target_y - other_win.y()) < snap_in:
                        new_y = other_win.y()

                    # 수평 스냅 (좌우 경계 0px 맞춤)
                    if abs(target_x - other_win.x()) < snap_in:
                        new_x = other_win.x()
                    elif abs((target_x + self.width()) - (other_win.x() + other_win.width())) < snap_in:
                        new_x = other_win.x() + other_win.width() - self.width()
                    elif abs(target_x - (other_win.x() + other_win.width())) < snap_in:
                        new_x = other_win.x() + other_win.width()
                    elif abs((target_x + self.width()) - other_win.x()) < snap_in:
                        new_x = other_win.x() - self.width()

                # 화면 좌측 모서리 0px 스냅
                if abs(target_x - scr_geom.left()) < snap_in:
                    new_x = scr_geom.left()

            # 화면 가장자리에 가까이 가면 딱 붙입니다. 접은 메모뿐 아니라 모든 메모에 적용합니다. (Ctrl 을 누르고 끌면 붙지 않음)
            if not ctrl_held:
                new_x, new_y = screen_bounds.snap_to_edges(scr_geom, new_x, new_y, self.width(), self.height())
            new_x, new_y = screen_bounds.clamp_position(scr_geom, new_x, new_y, self.width(), self.height())

            self.move(new_x, new_y)
            self._old_pos = curr_global

    def mouseReleaseEvent(self, e: Any) -> None:
        self._old_pos = None
        self._drag_from_title = False
        self._snap_lock_origin = None

        # 창을 옮기지도 크기를 바꾸지도 않은 단순 클릭이면 저장하지 않습니다.
        press_geom = getattr(self, '_press_geom', None)
        self._press_geom = None
        if press_geom is not None and press_geom == self.geometry():
            return

        self.remember_geometry()
        self.save_callback(self.memo_data)
