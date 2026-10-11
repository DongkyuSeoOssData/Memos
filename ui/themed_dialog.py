"""앱 자체 모양의 대화상자.

Windows 기본 제목 줄이 달린 창 대신, 탐색기·환경설정 창처럼 자체 제목 줄과 앱 색 테마를 쓰는 창입니다.
확인 묻기(confirm), 한 줄 입력(ask_text), 암호 등 여러 칸 입력(ask_form), 색 고르기(pick_color)와
알림(toast)을 여기에서 제공합니다.
"""
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from PyQt6.QtCore import QEventLoop, QPoint, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QGuiApplication
from PyQt6.QtWidgets import (
    QDialog, QGridLayout, QHBoxLayout, QLabel, QLayout, QLineEdit, QPushButton, QVBoxLayout, QWidget,
)

from ui import modern_style, screen_bounds

# 지금 설정을 돌려주는 함수. 앱이 시작할 때 UIManager 가 넣어 줍니다. (대화상자가 앱 색 테마를 따르도록)
_settings_source: Optional[Callable[[], Dict[str, Any]]] = None


_settings_saver: Optional[Callable[[Dict[str, Any]], None]] = None


def use_settings(source: Callable[[], Dict[str, Any]], saver: Optional[Callable[[Dict[str, Any]], None]] = None) -> None:
    global _settings_source, _settings_saver
    _settings_source = source
    _settings_saver = saver


def save_settings(changes: Dict[str, Any]) -> None:
    """대화상자 안에서 바꾼 선택(예: 시간을 24시간제로 볼지)을 설정에 기억합니다."""
    if _settings_saver:
        _settings_saver(changes)


def current_settings() -> Dict[str, Any]:
    return _settings_source() if _settings_source else {}


class ThemedDialog(QDialog):
    """자체 제목 줄을 가진 대화상자. 내용은 self.body (QVBoxLayout) 에 넣습니다.

    제목 줄을 잡고 끌어 옮기며, 부모 창의 가운데에 뜨고 화면 밖으로 나가지 않습니다.
    fit_content=True 면 보이는 내용에 맞춰 창 크기가 따라갑니다.
    """

    TITLE_HEIGHT = 38

    def __init__(self, parent: Any = None, title: str = "", fit_content: bool = False) -> None:
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setWindowTitle(title)
        self.setObjectName("ThemedDialog")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(modern_style.dialog_qss(current_settings()))
        self._drag_from: Optional[QPoint] = None
        self._placed = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(1, 1, 1, 1)
        outer.setSpacing(0)
        if fit_content:
            outer.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)

        self.title_bar = QWidget()
        self.title_bar.setObjectName("DialogTitleBar")
        self.title_bar.setFixedHeight(self.TITLE_HEIGHT)
        bar = QHBoxLayout(self.title_bar)
        bar.setContentsMargins(16, 0, 6, 0)
        bar.setSpacing(6)
        self.title_label = QLabel(title)
        self.title_label.setObjectName("DialogTitle")
        bar.addWidget(self.title_label, 1)
        self.btn_close = QPushButton("✕")
        self.btn_close.setObjectName("DialogClose")
        self.btn_close.setFixedSize(30, 26)
        self.btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_close.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_close.setAutoDefault(False)
        self.btn_close.clicked.connect(self.reject)
        bar.addWidget(self.btn_close)
        outer.addWidget(self.title_bar)

        holder = QWidget()
        self.body = QVBoxLayout(holder)
        self.body.setContentsMargins(16, 12, 16, 16)
        self.body.setSpacing(10)
        outer.addWidget(holder, 1)

    # ── 버튼 줄 ──────────────────────────────────────────────────────────────
    def add_buttons(self, ok_text: str = "확인", cancel_text: Optional[str] = "취소", danger: bool = False,
                    extra: Sequence[Tuple[str, Callable[[], None]]] = ()) -> QPushButton:
        """아래쪽 버튼 줄을 붙이고 확인 버튼을 돌려줍니다. extra 는 왼쪽에 놓는 (글자, 동작) 버튼들."""
        row = QHBoxLayout()
        row.setSpacing(8)
        for text, action in extra:
            btn = QPushButton(text)
            btn.setAutoDefault(False)
            btn.clicked.connect(action)
            row.addWidget(btn)
        row.addStretch(1)
        self.ok_button = QPushButton(ok_text)
        self.ok_button.setProperty("role", "danger" if danger else "primary")
        self.ok_button.setDefault(True)
        self.ok_button.clicked.connect(self.accept)
        row.addWidget(self.ok_button)
        self.cancel_button = None
        if cancel_text:
            self.cancel_button = QPushButton(cancel_text)
            self.cancel_button.setAutoDefault(False)
            self.cancel_button.clicked.connect(self.reject)
            row.addWidget(self.cancel_button)
        self.body.addLayout(row)
        return self.ok_button

    # ── 위치 ─────────────────────────────────────────────────────────────────
    def showEvent(self, event: Any) -> None:
        super().showEvent(event)
        if self._placed:
            return
        self._placed = True
        self.adjustSize()
        anchor = self.parentWidget().window() if self.parentWidget() else None
        if anchor is not None and anchor.isVisible():
            center = anchor.frameGeometry().center()
        else:
            screen = QGuiApplication.primaryScreen()
            center = screen.availableGeometry().center() if screen else QPoint(400, 300)
        area = screen_bounds.work_area(self, center)
        x, y = center.x() - self.width() // 2, center.y() - self.height() // 2
        if area is not None:
            x = max(area.left(), min(x, area.left() + area.width() - self.width()))
            y = max(area.top(), min(y, area.top() + area.height() - self.height()))
        self.move(x, y)

    def mousePressEvent(self, event: Any) -> None:
        if event.button() == Qt.MouseButton.LeftButton and event.position().y() <= self.TITLE_HEIGHT:
            self._drag_from = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: Any) -> None:
        if self._drag_from is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_from)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: Any) -> None:
        self._drag_from = None
        super().mouseReleaseEvent(event)


# ── 알림 (토스트) ──────────────────────────────────────────────────────────────
def toast(widget: Any, text: str, warn: bool = False) -> None:
    """widget 이 속한 창(메모·탐색기·환경설정)의 토스트로 알립니다. 따로 창을 띄우지 않습니다."""
    window = widget.window() if widget is not None else None
    show = getattr(window, "show_toast", None)
    if show is None:
        return
    try:
        show(text, warn=warn)
    except TypeError:
        show(text)


# ── 확인 묻기 ──────────────────────────────────────────────────────────────────
# 창 안에 띄울 곳이 없다는 표시. (이때는 대화상자로 묻습니다)
NO_HOST = object()


def _inline(parent: Any, panel: QWidget, title: str, need_width: int, need_height: int) -> Any:
    """panel 을 parent 가 속한 창(메모·탐색기) 안에서 띄워 답을 받습니다. 띄울 곳이 없으면 NO_HOST."""
    from ui import lock_overlay                       # 서로 불러 쓰므로 여기서 가져옵니다.
    return lock_overlay.host_panel(parent, panel, title, need_width, need_height)


def confirm(parent: Any, title: str, text: str, ok_text: str = "확인", cancel_text: str = "취소", danger: bool = False) -> bool:
    """예/아니오를 묻습니다. 부른 창(메모·탐색기) 안에서 묻고, 그럴 수 없을 때만 대화상자를 띄웁니다."""
    panel = FormPanel(title, text, [], ok_text, cancel_text, danger=danger)
    panel.setMinimumWidth(300)
    answer = _inline(parent, panel, "", 260, 130)
    if answer is not NO_HOST:
        return answer is not None
    panel.deleteLater()
    dialog = ThemedDialog(parent, title, fit_content=True)
    label = QLabel(text)
    label.setWordWrap(True)
    label.setMinimumWidth(320)
    label.setMaximumWidth(460)
    dialog.body.addWidget(label)
    dialog.add_buttons(ok_text, cancel_text, danger=danger)
    return dialog.exec() == QDialog.DialogCode.Accepted


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


def choose(parent: Any, title: str, text: str, options: Sequence[Tuple[str, Any, str]]) -> Any:
    """버튼 여러 개 중 하나를 고르게 합니다. → 고른 버튼의 값 (취소·닫기는 None)

    부른 창(메모·탐색기) 안에서 묻고, 그럴 수 없을 때만 대화상자를 띄웁니다.
    """
    panel = ChoicePanel(title, text, options)
    panel.setMinimumWidth(340)
    answer = _inline(parent, panel, "", 300, 140)
    if answer is not NO_HOST:
        return answer
    panel.deleteLater()
    dialog = ThemedDialog(parent, title, fit_content=True)
    panel = ChoicePanel("", text, options)
    panel.setMinimumWidth(360)
    dialog.body.addWidget(panel)
    result: Dict[str, Any] = {"value": None}

    def done(value: Any) -> None:
        result["value"] = value
        dialog.accept()

    panel.submitted.connect(done)
    panel.cancelled.connect(dialog.reject)
    dialog.exec()
    return result["value"]


# ── 여러 칸 입력 (암호 등) ─────────────────────────────────────────────────────
class FormPanel(QWidget):
    """제목·설명·입력 칸 몇 개·확인/취소로 이루어진 입력 묶음.

    대화상자 안에도, 메모 창 위의 가림막(암호 입력) 안에도 똑같이 들어갑니다.
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


def ask_form(parent: Any, title: str, text: str, fields: Sequence[Dict[str, Any]], ok_text: str = "확인",
             validate: Optional[Callable[[List[str]], Optional[str]]] = None, danger: bool = False) -> Optional[List[str]]:
    """입력 칸 여러 개를 받습니다. 확인하면 값들을, 취소하면 None 을 돌려줍니다.

    부른 창(메모·탐색기) 안에서 묻고, 그럴 수 없을 때만 대화상자를 띄웁니다.
    """
    panel = FormPanel(title, text, fields, ok_text, validate=validate, danger=danger)
    panel.setMinimumWidth(240)
    answer = _inline(parent, panel, "", 230, 96 + 40 * len(fields) + (44 if text else 0))
    if answer is not NO_HOST:
        return answer
    panel.deleteLater()

    dialog = ThemedDialog(parent, title, fit_content=True)
    panel = FormPanel(title, text, fields, ok_text, validate=validate, danger=danger, show_title=False)
    panel.setMinimumWidth(340)
    dialog.body.addWidget(panel)
    result: Dict[str, Any] = {"values": None}

    def done(values: List[str]) -> None:
        result["values"] = values
        dialog.accept()

    panel.submitted.connect(done)
    panel.cancelled.connect(dialog.reject)
    panel.focus_first()
    dialog.exec()
    return result["values"]


def ask_text(parent: Any, title: str, label: str, text: str = "", password: bool = False, hint: str = "") -> Tuple[str, bool]:
    """한 줄 입력. → (입력한 글자, 확인했는지)"""
    values = ask_form(parent, title, hint, [{"label": label, "text": text, "password": password}])
    return (values[0], True) if values is not None else ("", False)


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


class ColorDialog(ThemedDialog):
    """색 고르기 화면을 담은 대화상자. (창 안에 띄울 수 없을 때)"""

    def __init__(self, parent: Any, title: str, initial: Any = None) -> None:
        super().__init__(parent, title, fit_content=True)
        self.panel = ColorPanel("", initial)
        self.body.addWidget(self.panel)
        self.panel.submitted.connect(lambda color: self.accept())
        self.panel.cancelled.connect(self.reject)
        self.swatches, self.code, self.ok_button = self.panel.swatches, self.panel.code, self.panel.ok_button

    def color(self) -> Optional[QColor]:
        return self.panel.color()


def pick_color(parent: Any, title: str, initial: Any = None) -> Optional[QColor]:
    """색을 고릅니다. 부른 창 안에서 고르고, 그럴 수 없을 때만 대화상자를 띄웁니다. 취소하면 None."""
    panel = ColorPanel(title, initial)
    answer = _inline(parent, panel, "", 300, 270)
    if answer is not NO_HOST:
        return answer
    panel.deleteLater()
    dialog = ColorDialog(parent, title, initial)
    return dialog.color() if dialog.exec() == QDialog.DialogCode.Accepted else None
