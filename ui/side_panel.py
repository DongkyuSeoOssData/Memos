"""메모 창 옆에 붙어서 열리는 패널.

알림 설정이나 이전 내용처럼 메모 안에 다 들어가지 않는 화면을, 메모 오른쪽에 붙여서 보여 줍니다.
메모와 같은 바탕색을 쓰고 맞닿는 쪽에는 테두리를 두지 않아 한 덩어리처럼 보이며, 크기는 메모와 따로 가집니다.
(내용이 다 보이도록 최소 크기가 있어, 메모가 작거나 접혀 있어도 잘리지 않습니다)
오른쪽에 자리가 없으면 왼쪽에 붙습니다. 메모를 옮기면 따라 움직이고, 메모를 숨기거나 닫으면 함께 닫힙니다.
"""
from typing import Any, Optional

from PyQt6.QtCore import QEvent, QObject, QPoint, Qt
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ui import modern_style, screen_bounds
from ui.input_panels import run_panel


class SidePanel(QWidget):
    def __init__(self, memo_window: Any) -> None:
        super().__init__(None)
        self.memo_window = memo_window
        self.panel: Optional[QWidget] = None
        self._on_left = False
        flags = Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
        if memo_window.windowFlags() & Qt.WindowType.WindowStaysOnTopHint:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.setObjectName("MemoSidePanel")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 10, 14, 14)
        outer.setSpacing(10)
        head = QHBoxLayout()
        head.setSpacing(6)
        self.title_label = QLabel("")
        self.title_label.setProperty("role", "title")
        head.addWidget(self.title_label, 1)
        self.btn_close = QPushButton("✕")
        self.btn_close.setObjectName("PanelClose")
        self.btn_close.setFixedSize(28, 24)
        self.btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_close.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_close.clicked.connect(self.cancel)
        head.addWidget(self.btn_close)
        outer.addLayout(head)
        self.holder = QVBoxLayout()
        outer.addLayout(self.holder, 1)
        memo_window.installEventFilter(self)

    # ── 모양·위치 ────────────────────────────────────────────────────────────
    def apply_style(self) -> None:
        """메모와 같은 바탕색. 메모와 맞닿는 쪽에는 테두리를 두지 않습니다."""
        w = self.memo_window
        colors = modern_style.memo_colors(w)
        bg_color, edge = colors["bg"], colors["edge"]
        joined = "right" if self._on_left else "left"
        self.setStyleSheet(
            f"QWidget#MemoSidePanel {{ background-color: {bg_color}; border: 1px solid {edge}; border-{joined}: none; }}"
            + modern_style.memo_form_qss(w))
        self.setWindowOpacity(w.windowOpacity())

    def place(self) -> None:
        """메모의 오른쪽(자리가 없으면 왼쪽)에 위쪽을 맞춰 붙입니다."""
        w = self.memo_window
        frame = w.bg.mapToGlobal(QPoint(0, 0))
        left, top, width = frame.x(), frame.y(), w.bg.width()
        area = screen_bounds.work_area(w)
        x = left + width - 1                                  # 메모의 오른쪽 테두리에 겹쳐 붙임
        on_left = area is not None and x + self.width() > area.left() + area.width() and left - self.width() + 1 >= area.left()
        if on_left:
            x = left - self.width() + 1
        if on_left != self._on_left:
            self._on_left = on_left
            self.apply_style()
        y = top
        if area is not None:
            y = max(area.top(), min(y, area.top() + area.height() - self.height()))
        self.move(x, y)

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if obj is self.memo_window and self.panel is not None:
            if event.type() in (QEvent.Type.Move, QEvent.Type.Resize):
                self.place()
            elif event.type() in (QEvent.Type.Hide, QEvent.Type.Close):
                self.cancel()
        return False

    # ── 띄우기 ───────────────────────────────────────────────────────────────
    def is_busy(self) -> bool:
        return self.panel is not None

    def run(self, panel: QWidget, title: str = "", min_width: int = 0, min_height: int = 0) -> Any:
        """panel(submitted·cancelled 신호를 가진 화면)을 메모 옆에 띄우고, 확인(값)이나 취소(None)가 될 때까지 기다립니다."""
        self.panel = panel
        self.title_label.setText(title)
        self.holder.addWidget(panel)
        self.setMinimumSize(0, 0)
        self.apply_style()
        self._min_size = (min_width, min_height)
        # 패널을 만든 뒤에 메모의 '항상 위'를 바꿨을 수 있으므로 열 때마다 맞춥니다.
        on_top = bool(self.memo_window.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)
        if on_top != bool(self.windowFlags() & Qt.WindowType.WindowStaysOnTopHint):
            self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, on_top)
        self._refit()
        if hasattr(panel, "layout_changed"):
            panel.layout_changed.connect(self._refit)
        self.show()
        self._refit()               # 화면에 올린 뒤 한 번 더 (줄바꿈되는 글자의 높이가 이때 정해짐)
        self.raise_()
        self.activateWindow()
        if hasattr(panel, "focus_first"):
            panel.focus_first()

        def done() -> None:
            self.panel = None
            self.holder.removeWidget(panel)
            panel.hide()
            panel.deleteLater()
            self.hide()

        return run_panel(panel, done)

    def _refit(self) -> None:
        """보이는 입력이 바뀌면 그 내용이 다 보이는 크기로 맞춥니다."""
        if self.panel is None:
            return
        min_width, min_height = getattr(self, '_min_size', (0, 0))
        self.layout().activate()
        hint = self.sizeHint()
        width = max(hint.width(), min_width)
        height = max(hint.height(), self.layout().heightForWidth(width) if self.layout().hasHeightForWidth() else 0, min_height)
        self.resize(width, height)
        self.place()

    def cancel(self) -> None:
        if self.panel is not None:
            self.panel.cancelled.emit()

    def keyPressEvent(self, event: Any) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.cancel()
            return
        super().keyPressEvent(event)
