"""앱 자체 모양의 대화상자와, 묻는 함수들.

ThemedDialog 는 Windows 기본 제목 줄이 달린 창 대신, 탐색기·환경설정 창처럼 자체 제목 줄과 앱 색 테마를 쓰는 창입니다.
확인 묻기(confirm), 버튼 고르기(choose), 한 줄 입력(ask_text), 암호 등 여러 칸 입력(ask_form), 색 고르기(pick_color)는
먼저 부른 창(메모·탐색기) 안에서 묻고(overlay.host_panel), 그럴 수 없을 때만 대화상자를 띄웁니다.
알림(toast)도 여기에서 제공합니다.
"""
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtGui import QColor, QGuiApplication
from PyQt6.QtWidgets import QDialog, QHBoxLayout, QLabel, QLayout, QPushButton, QVBoxLayout, QWidget

from ui import live_settings, modern_style, overlay, screen_bounds
from ui.input_panels import ChoicePanel, ColorPanel, FormPanel


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
        self.setStyleSheet(modern_style.dialog_qss(live_settings.current()))
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


# ── 묻기 ──────────────────────────────────────────────────────────────────────
def confirm(parent: Any, title: str, text: str, ok_text: str = "확인", cancel_text: str = "취소", danger: bool = False) -> bool:
    """예/아니오를 묻습니다. 부른 창(메모·탐색기) 안에서 묻고, 그럴 수 없을 때만 대화상자를 띄웁니다."""
    panel = FormPanel(title, text, [], ok_text, cancel_text, danger=danger)
    panel.setMinimumWidth(300)
    answer = overlay.host_panel(parent, panel, "", 260, 130)
    if answer is not overlay.NO_HOST:
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


def choose(parent: Any, title: str, text: str, options: Sequence[Tuple[str, Any, str]]) -> Any:
    """버튼 여러 개 중 하나를 고르게 합니다. → 고른 버튼의 값 (취소·닫기는 None)

    부른 창(메모·탐색기) 안에서 묻고, 그럴 수 없을 때만 대화상자를 띄웁니다.
    """
    panel = ChoicePanel(title, text, options)
    panel.setMinimumWidth(340)
    answer = overlay.host_panel(parent, panel, "", 300, 140)
    if answer is not overlay.NO_HOST:
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


def ask_form(parent: Any, title: str, text: str, fields: Sequence[Dict[str, Any]], ok_text: str = "확인",
             validate: Optional[Callable[[List[str]], Optional[str]]] = None, danger: bool = False) -> Optional[List[str]]:
    """입력 칸 여러 개를 받습니다. 확인하면 값들을, 취소하면 None 을 돌려줍니다.

    부른 창(메모·탐색기) 안에서 묻고, 그럴 수 없을 때만 대화상자를 띄웁니다.
    """
    panel = FormPanel(title, text, fields, ok_text, validate=validate, danger=danger)
    panel.setMinimumWidth(240)
    answer = overlay.host_panel(parent, panel, "", 230, 96 + 40 * len(fields) + (44 if text else 0))
    if answer is not overlay.NO_HOST:
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
    answer = overlay.host_panel(parent, panel, "", 300, 270)
    if answer is not overlay.NO_HOST:
        return answer
    panel.deleteLater()
    dialog = ColorDialog(parent, title, initial)
    return dialog.color() if dialog.exec() == QDialog.DialogCode.Accepted else None
