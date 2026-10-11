"""입력 화면: 답을 받는 작은 화면 묶음.

 - FormPanel   : 제목·설명·입력 칸 몇 개·확인/취소 (확인 묻기, 한 줄 입력, 암호 입력)
 - ChoicePanel : 안내 글과 버튼 몇 개 중 하나 고르기
 - ColorPanel  : 색 고르기
모두 submitted(값) / cancelled() 신호로 답을 알립니다. 어디에 띄울지는 모릅니다: 창 안의 가림막(overlay),
메모 옆 패널(side_panel), 대화상자(themed_dialog)가 이 화면을 받아 띄우고, run_panel 로 답을 기다립니다.
"""
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from PyQt6.QtCore import QEventLoop, Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget


class FormPanel(QWidget):
    """제목·설명·입력 칸 몇 개·확인/취소로 이루어진 입력 묶음.

    대화상자 안에도, 창 안의 가림막(암호 입력 등) 안에도 똑같이 들어갑니다.
    validate(값들) 가 오류 문구를 돌려주면 닫지 않고 그 문구를 칸 아래에 보여 줍니다.
    """

    submitted = pyqtSignal(list)
    cancelled = pyqtSignal()

    def __init__(self, title: str, text: str, fields: Sequence[Dict[str, Any]], ok_text: str = "확인",
                 cancel_text: Optional[str] = "취소", validate: Optional[Callable[[List[str]], Optional[str]]] = None,
                 danger: bool = False, show_title: bool = True) -> None:
        super().__init__()
        self._validate = validate
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        if show_title and title:
            head = QLabel(title)
            head.setProperty("role", "title")
            layout.addWidget(head)
        if text:
            note = QLabel(text)
            note.setWordWrap(True)
            layout.addWidget(note)
        self.inputs: List[QLineEdit] = []
        for field in fields:
            box = QLineEdit(str(field.get("text", "")))
            box.setPlaceholderText(str(field.get("label", "")))
            if field.get("password"):
                box.setEchoMode(QLineEdit.EchoMode.Password)
            box.returnPressed.connect(self._enter_pressed)
            layout.addWidget(box)
            self.inputs.append(box)
        self.error = QLabel("")
        self.error.setProperty("role", "error")
        self.error.setWordWrap(True)
        self.error.hide()
        layout.addWidget(self.error)

        row = QHBoxLayout()
        row.setSpacing(8)
        row.addStretch(1)
        self.ok_button = QPushButton(ok_text)
        self.ok_button.setProperty("role", "danger" if danger else "primary")
        self.ok_button.clicked.connect(self.submit)
        row.addWidget(self.ok_button)
        self.cancel_button = None
        if cancel_text:
            self.cancel_button = QPushButton(cancel_text)
            self.cancel_button.clicked.connect(self.cancelled.emit)
            row.addWidget(self.cancel_button)
        layout.addLayout(row)

    def values(self) -> List[str]:
        return [box.text() for box in self.inputs]

    def focus_first(self) -> None:
        (self.inputs[0] if self.inputs else self.ok_button).setFocus()

    def _enter_pressed(self) -> None:
        """Enter: 다음 빈 칸으로 넘어가고, 마지막 칸이면 확인."""
        index = self.inputs.index(self.sender())
        if index + 1 < len(self.inputs):
            self.inputs[index + 1].setFocus()
        else:
            self.submit()

    def show_error(self, message: str) -> None:
        self.error.setText("⚠ " + message)
        self.error.show()

    def submit(self) -> None:
        values = self.values()
        message = self._validate(values) if self._validate else None
        if message:
            self.show_error(message)
            target = self.inputs[-1] if self.inputs else None
            if target is not None:
                target.selectAll()
                target.setFocus()
            return
        self.submitted.emit(values)

    def keyPressEvent(self, event: Any) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.cancelled.emit()
            return
        super().keyPressEvent(event)


def run_panel(panel: Any, on_done: Callable[[], None]) -> Any:
    """panel(submitted·cancelled 신호를 가진 입력 화면)이 확인되거나 취소될 때까지 기다렸다가 값(취소면 None)을 돌려줍니다.
    끝나면 on_done 을 부릅니다."""
    result: Dict[str, Any] = {"values": None}
    loop = QEventLoop()

    def finish(values: Any = None) -> None:
        result["values"] = values
        loop.quit()

    panel.submitted.connect(finish)
    panel.cancelled.connect(lambda: finish(None))
    panel.destroyed.connect(loop.quit)
    loop.exec()
    on_done()
    return result["values"]


class ChoicePanel(QWidget):
    """안내 글과 버튼 몇 개. 누른 버튼의 값을 submitted(값) 으로, 닫으면 cancelled 를 보냅니다.

    options: [(버튼 글자, 값, 모양)] — 모양은 "primary" / "danger" / "" 이고, 값이 None 인 버튼은 취소입니다.
    """

    submitted = pyqtSignal(object)
    cancelled = pyqtSignal()

    def __init__(self, title: str, text: str, options: Sequence[Tuple[str, Any, str]]) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        if title:
            head = QLabel(title)
            head.setProperty("role", "title")
            layout.addWidget(head)
        note = QLabel(text)
        note.setWordWrap(True)
        layout.addWidget(note)
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addStretch(1)
        self.buttons: Dict[Any, QPushButton] = {}
        for label, value, role in options:
            button = QPushButton(label)
            if role:
                button.setProperty("role", role)
            if value is None:
                button.clicked.connect(self.cancelled.emit)
            else:
                button.clicked.connect(lambda checked=False, v=value: self.submitted.emit(v))
            row.addWidget(button)
            self.buttons[value] = button
        layout.addLayout(row)

    def focus_first(self) -> None:
        next(iter(self.buttons.values())).setFocus()

    def keyPressEvent(self, event: Any) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.cancelled.emit()
            return
        super().keyPressEvent(event)


# ── 색 고르기 ──────────────────────────────────────────────────────────────────
COLOR_CHOICES = (
    "#000000", "#434343", "#666666", "#999999", "#B7B7B7", "#D9D9D9", "#EFEFEF", "#FFFFFF",
    "#980000", "#FF0000", "#FF9900", "#FFD600", "#00B050", "#00B0F0", "#1F5FFF", "#9900FF",
    "#E6B8AF", "#F4CCCC", "#FCE5CD", "#FFF2CC", "#D9EAD3", "#D0E0E3", "#CFE2F3", "#D9D2E9",
    "#CC4125", "#E06666", "#F6B26B", "#FFD966", "#93C47D", "#76A5AF", "#6FA8DC", "#8E7CC3",
    "#85200C", "#990000", "#B45F06", "#BF9000", "#38761D", "#134F5C", "#0B5394", "#351C75",
)


class ColorPanel(QWidget):
    """색 고르기 화면. 색 칸을 누르거나 #RRGGBB 를 직접 적습니다. 확인하면 submitted(QColor) 를 보냅니다."""

    submitted = pyqtSignal(object)
    cancelled = pyqtSignal()

    def __init__(self, title: str = "", initial: Any = None) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        if title:
            head = QLabel(title)
            head.setProperty("role", "title")
            layout.addWidget(head)
        grid = QGridLayout()
        grid.setSpacing(4)
        self.swatches: List[QPushButton] = []
        for n, code in enumerate(COLOR_CHOICES):
            btn = QPushButton("")
            btn.setFixedSize(30, 26)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setAutoDefault(False)
            btn.setToolTip(code)
            btn.setStyleSheet(f"QPushButton {{ background: {code}; border: 1px solid rgba(128,128,128,0.55); border-radius: 0px; padding: 0; }}"
                              f"QPushButton:hover {{ border: 2px solid #007AFF; }}")
            btn.clicked.connect(lambda checked, c=code: self.code.setText(c))
            grid.addWidget(btn, n // 8, n % 8)
            self.swatches.append(btn)
        layout.addLayout(grid)

        row = QHBoxLayout()
        row.setSpacing(8)
        self.preview = QLabel("")
        self.preview.setFixedSize(40, 32)
        row.addWidget(self.preview)
        self.code = QLineEdit()
        self.code.setPlaceholderText("#RRGGBB")
        self.code.setMaxLength(7)
        self.code.textChanged.connect(self._refresh)
        self.code.returnPressed.connect(self.submit)
        row.addWidget(self.code, 1)
        layout.addLayout(row)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        buttons.addStretch(1)
        self.ok_button = QPushButton("이 색으로")
        self.ok_button.setProperty("role", "primary")
        self.ok_button.clicked.connect(self.submit)
        buttons.addWidget(self.ok_button)
        self.cancel_button = QPushButton("취소")
        self.cancel_button.clicked.connect(self.cancelled.emit)
        buttons.addWidget(self.cancel_button)
        layout.addLayout(buttons)

        start = QColor(initial) if initial is not None else QColor("#000000")
        self.code.setText((start if start.isValid() and start.alpha() > 0 else QColor("#000000")).name().upper())

    def color(self) -> Optional[QColor]:
        text = self.code.text().strip()
        if len(text) != 7 or not text.startswith("#"):
            return None
        color = QColor(text)
        return color if color.isValid() else None

    def focus_first(self) -> None:
        self.code.setFocus()
        self.code.selectAll()

    def submit(self) -> None:
        color = self.color()
        if color is not None:
            self.submitted.emit(color)

    def _refresh(self) -> None:
        color = self.color()
        self.ok_button.setEnabled(color is not None)
        fill = color.name() if color else "transparent"
        self.preview.setStyleSheet(f"background: {fill}; border: 1px solid rgba(128,128,128,0.55);")

    def keyPressEvent(self, event: Any) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.cancelled.emit()
            return
        super().keyPressEvent(event)
