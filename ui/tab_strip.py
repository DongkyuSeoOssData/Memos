"""한 줄짜리 탭 묶음. 자리가 모자라면 < > 로 넘겨 보고, 탭을 끌어서 순서를 바꿉니다."""
from typing import Any, List, Optional

from PyQt6.QtCore import QEvent, QSize, Qt, pyqtSignal
from PyQt6.QtWidgets import QApplication, QHBoxLayout, QLayout, QPushButton, QWidget


class TabStrip(QWidget):
    """탭 버튼들을 한 줄에 놓습니다.

    - 버튼은 글자가 잘리지 않게 항상 온전한 크기로만 보입니다. 줄에 다 들어가지 않으면 들어가는 만큼만 보이고,
      양 끝의 < > 버튼으로 나머지를 넘겨 봅니다.
    - 끌 수 있는 탭(set_tabs 의 draggable)은 좌우로 끌어 순서를 바꿀 수 있습니다. 놓으면 moved 신호를 보냅니다.
    """

    # (옮긴 탭의 키, 그 탭이 놓일 자리 바로 뒤 탭의 키 또는 None=맨 뒤)
    moved = pyqtSignal(object, object)

    SPACING = 4

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(self.SPACING)
        self._layout.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        self.btn_prev = QPushButton("<")
        self.btn_next = QPushButton(">")
        for btn, step in ((self.btn_prev, -1), (self.btn_next, 1)):
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.setToolTip("이전 폴더 보기" if step < 0 else "다음 폴더 보기")
            btn.clicked.connect(lambda checked, s=step: self.page(s))
        self.tabs: List[QPushButton] = []
        self._keys: dict = {}
        self._draggable: set = set()
        self._first = 0             # 지금 보이는 첫 탭의 번호
        self._last = -1             # 지금 보이는 마지막 탭의 번호
        self._press_x: Optional[float] = None
        self._dragging: Optional[QPushButton] = None
        self._rebuild_layout()

    # ── 내용 채우기 ──────────────────────────────────────────────────────────
    def set_tabs(self, tabs: List[QPushButton], keys: List[Any], draggable: List[Any], keep_visible: Any = None) -> None:
        """탭을 새로 채웁니다. keys 는 탭마다의 식별값, draggable 은 끌어서 옮길 수 있는 키들, keep_visible 은 꼭 보여야 할 키."""
        for old in self.tabs:
            old.removeEventFilter(self)
            old.setParent(None)
            old.deleteLater()
        self.tabs = list(tabs)
        self._keys = {btn: key for btn, key in zip(tabs, keys)}
        self._draggable = set(draggable)
        height = max([btn.maximumHeight() for btn in tabs if btn.maximumHeight() < 1000] or [30])
        for nav in (self.btn_prev, self.btn_next):
            nav.setFixedSize(26, height)
        for btn in tabs:
            btn.installEventFilter(self)
        self._first = min(self._first, max(0, len(tabs) - 1))
        self._rebuild_layout()
        self.relayout(keep_visible)

    def _rebuild_layout(self) -> None:
        while self._layout.count():
            self._layout.takeAt(0)
        self._layout.addWidget(self.btn_prev)
        for btn in self.tabs:
            self._layout.addWidget(btn)
        self._layout.addStretch(1)
        self._layout.addWidget(self.btn_next)

    # ── 넘겨 보기 ────────────────────────────────────────────────────────────
    def _width_of(self, btn: QPushButton) -> int:
        btn.ensurePolished()
        return btn.sizeHint().width()

    def relayout(self, keep_visible: Any = None) -> None:
        """지금 너비에 온전히 들어가는 탭만 보이게 합니다."""
        n = len(self.tabs)
        widths = [self._width_of(btn) for btn in self.tabs]
        avail = self.width()
        total = sum(widths) + self.SPACING * max(0, n - 1)
        if n == 0 or avail <= 0 or total <= avail:
            self._first, self._last = 0, n - 1
            for btn in self.tabs:
                btn.show()
            self.btn_prev.hide()
            self.btn_next.hide()
            return

        room = avail - 2 * (self.btn_prev.width() + self.SPACING)       # < > 자리를 뺀 너비

        def last_from(first: int) -> int:
            used, last = 0, first - 1
            for i in range(first, n):
                need = widths[i] + (self.SPACING if i > first else 0)
                if used + need > room and i > first:      # 한 개도 안 들어가는 좁은 창이면 한 개는 보여 줌
                    break
                used += need
                last = i
            return last

        first = max(0, min(self._first, n - 1))
        target = next((i for i, btn in enumerate(self.tabs) if self._keys.get(btn) == keep_visible), None) \
            if keep_visible is not None else None
        if target is not None:
            if target < first:
                first = target
            while last_from(first) < target and first < target:
                first += 1
        # 뒤쪽에 빈자리가 남으면 앞의 탭을 더 당겨 채웁니다.
        while first > 0 and last_from(first - 1) == n - 1:
            first -= 1
        last = last_from(first)
        self._first, self._last = first, last
        for i, btn in enumerate(self.tabs):
            btn.setVisible(first <= i <= last)
        self.btn_prev.show()
        self.btn_next.show()
        self.btn_prev.setEnabled(first > 0)
        self.btn_next.setEnabled(last < n - 1)

    def page(self, step: int) -> None:
        """> 는 지금 보이는 마지막 탭 다음부터, < 는 그만큼 앞으로 넘깁니다."""
        if not self.tabs:
            return
        if step > 0:
            self._first = min(len(self.tabs) - 1, self._last + 1)
        else:
            shown = max(1, self._last - self._first + 1)
            self._first = max(0, self._first - shown)
        self.relayout()

    def minimumSizeHint(self) -> QSize:
        # 들어가지 않는 탭은 < > 로 넘겨 보므로, 탭이 아무리 많아도 창을 넓히라고 요구하지 않습니다.
        return QSize(90, super().minimumSizeHint().height())

    def visible_keys(self) -> List[Any]:
        return [self._keys[btn] for btn in self.tabs if not btn.isHidden()]

    def resizeEvent(self, event: Any) -> None:
        super().resizeEvent(event)
        self.relayout()

    # ── 끌어서 순서 바꾸기 ───────────────────────────────────────────────────
    def drop_target(self, dragged: Any, global_x: float) -> Any:
        """global_x 에 놓았을 때 dragged 가 들어갈 자리 바로 뒤의 키. 맨 뒤면 None."""
        for btn in self.tabs:
            key = self._keys[btn]
            if btn.isHidden() or key not in self._draggable or key == dragged:
                continue
            center = btn.mapToGlobal(btn.rect().center()).x()
            if global_x < center:
                return key
        return None

    def eventFilter(self, obj: Any, event: Any) -> bool:
        key = self._keys.get(obj)
        if key is None or key not in self._draggable:
            return False
        kind = event.type()
        if kind == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
            self._press_x = event.globalPosition().x()
            self._dragging = None
        elif kind == QEvent.Type.MouseMove and self._press_x is not None:
            if self._dragging is None and abs(event.globalPosition().x() - self._press_x) >= QApplication.startDragDistance():
                self._dragging = obj
                obj.setCursor(Qt.CursorShape.ClosedHandCursor)
            if self._dragging is not None:
                return True
        elif kind == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
            dragging, self._dragging, self._press_x = self._dragging, None, None
            if dragging is not None:
                dragging.setCursor(Qt.CursorShape.PointingHandCursor)
                dragging.setDown(False)
                self.moved.emit(key, self.drop_target(key, event.globalPosition().x()))
                return True         # 끌어 옮긴 것은 클릭으로 치지 않음
        return False
