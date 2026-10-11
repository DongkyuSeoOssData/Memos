"""창 안에서 입력을 받는 가림막.

암호를 묻거나 확인을 받을 때 따로 창을 띄우지 않고, 그 창의 내용을 가린 뒤 한가운데에 입력 화면을 보여 줍니다.
 - LockOverlay    : 메모 창. 본문을 흐리게 가리고 그 위에서 묻습니다. 잠긴 메모는 평소에도 이 가림막이 본문 자리를
                    덮고 있으며, 그 위의 암호 칸에 바로 암호를 넣어 엽니다.
 - WindowOverlay  : 탐색기. 창 전체를 어둡게 가리고 가운데의 카드에서 묻습니다.
자리가 모자라면 메모는 옆에 붙는 패널(SidePanel)로, 그 밖에는 대화상자로 대신 묻습니다.
"""
from typing import Any, Callable, Dict, List, Optional, Sequence

from PyQt6.QtCore import QEvent, QObject, QPoint, QRect, Qt
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import QFrame, QGraphicsBlurEffect, QScrollArea, QVBoxLayout, QWidget

from ui import modern_style, themed_dialog


class PanelOverlay(QWidget):
    """입력 화면(panel)을 한가운데에 띄우고 답을 기다리는 가림막의 공통 부분."""

    MARGIN = 12

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.panel: Optional[QWidget] = None            # 지금 띄워 놓고 답을 기다리는 입력 화면
        self._card: Optional[QScrollArea] = None        # 그 입력 화면을 담은 카드
        outer = QVBoxLayout(self)
        outer.setContentsMargins(self.MARGIN, self.MARGIN, self.MARGIN, self.MARGIN)
        outer.addStretch(1)
        self.holder = QVBoxLayout()
        self.holder.setSpacing(8)
        outer.addLayout(self.holder)
        outer.addStretch(1)
        self.hide()

    # 아래 넷은 창마다 다르게 정합니다.
    def area(self) -> QRect:
        """가릴 영역. (부모 위젯 안의 좌표)"""
        return self.parentWidget().rect()

    def usable(self) -> bool:
        return self.parentWidget().isVisible()

    def before_run(self) -> None:
        pass

    def after_run(self) -> None:
        self.hide()

    # ── 크기 ─────────────────────────────────────────────────────────────────
    def sync_geometry(self) -> None:
        self.setGeometry(self.area())
        self._fit_card()

    def _fit_card(self) -> None:
        """카드를 내용 크기에 맞추되 창 밖으로 나가지 않게 합니다. 넘치는 내용은 카드 안에서 스크롤합니다."""
        if self._card is None:
            return
        hint = self._card.widget().sizeHint()
        room_w = max(160, self.width() - 2 * self.MARGIN)
        room_h = max(120, self.height() - 2 * self.MARGIN)
        tall = hint.height() + 2 > room_h
        width = hint.width() + 2 + (self._card.verticalScrollBar().sizeHint().width() if tall else 0)
        self._card.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded if tall else Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._card.setFixedSize(min(width, room_w), min(hint.height() + 2, room_h))

    def can_host(self, min_width: int, min_height: int) -> bool:
        """입력 화면이 이 창 안에 들어갈 만큼 자리가 있는지."""
        if not self.usable() or self.panel is not None:
            return False
        area = self.area()
        return area.width() >= min_width and area.height() >= min_height

    # ── 띄우기 ───────────────────────────────────────────────────────────────
    def run(self, panel: QWidget, card: bool = False) -> Any:
        """panel 을 한가운데에 띄우고, 확인(값)이나 취소(None)가 될 때까지 기다립니다.

        panel 은 submitted(값) / cancelled() 신호를 가진 입력 화면입니다. card=True 면 앱 색 테마의 카드에 담아
        보여 주고, 창보다 크면 카드 안에서 스크롤합니다.
        """
        self.panel = panel
        shown: QWidget = panel
        if card:
            inner = QFrame()
            inner.setObjectName("OverlayCard")
            box = QVBoxLayout(inner)
            box.setContentsMargins(16, 14, 16, 16)
            box.addWidget(panel)
            scroll = QScrollArea()
            scroll.setObjectName("OverlayCardScroll")
            scroll.setWidgetResizable(True)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            scroll.setWidget(inner)
            scroll.setStyleSheet(modern_style.dialog_qss(themed_dialog.current_settings()))
            self._card = shown = scroll
            if hasattr(panel, "layout_changed"):
                panel.layout_changed.connect(self._fit_card)
        self.holder.addWidget(shown, 0, Qt.AlignmentFlag.AlignHCenter)
        self.before_run()
        self.sync_geometry()
        self.show()
        self.raise_()
        self.window().activateWindow()
        if hasattr(panel, "focus_first"):
            panel.focus_first()

        def done() -> None:
            self.panel = None
            self._card = None
            self.holder.removeWidget(shown)
            shown.hide()
            shown.deleteLater()
            self.after_run()
            self.update()

        return themed_dialog.run_panel(panel, done)

    def cancel(self) -> None:
        """입력 중이면 취소합니다. (창을 숨기거나 닫을 때)"""
        if self.panel is not None:
            self.panel.cancelled.emit()


class WindowOverlay(PanelOverlay):
    """탐색기처럼 넓은 창: 창 전체를 어둡게 가리고 가운데의 카드에서 묻습니다."""

    def __init__(self, window: QWidget, frame: QWidget) -> None:
        super().__init__(frame)
        self._frame = frame
        frame.installEventFilter(self)
        window.installEventFilter(self)

    def paintEvent(self, event: Any) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 110))
        painter.end()

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if self.panel is not None:
            if obj is self._frame and event.type() == QEvent.Type.Resize:
                self.sync_geometry()
            elif obj is not self._frame and event.type() in (QEvent.Type.Hide, QEvent.Type.Close):
                self.cancel()
        return False

    def mousePressEvent(self, event: Any) -> None:
        event.accept()                                   # 가려진 뒤쪽이 눌리지 않게


class LockOverlay(PanelOverlay):
    """메모 창의 본문 자리를 덮는 가림막."""

    PANEL_WIDTH = 300           # 암호 입력 묶음의 너비

    def __init__(self, window: Any) -> None:
        super().__init__(window.bg)
        self.memo_window = window
        self.unlock_panel: Optional[themed_dialog.FormPanel] = None      # 잠긴 메모에 늘 보이는 암호 칸
        self._blur: Optional[QGraphicsBlurEffect] = None

    # ── 모양 ─────────────────────────────────────────────────────────────────
    def apply_style(self) -> None:
        """메모 바탕 밝기에 맞춘 색. (앱 색 테마가 아니라 메모 자신의 색을 따름)"""
        w = self.memo_window
        pal = w._memo_theme_palette()
        ink = pal['text']
        sm = w._sync_manager()
        neo = modern_style.is_neo(sm.settings) if sm else False
        on_bg = ink if neo else pal['accent']
        on_text = ("#1C1C1E" if w.is_dark_bg() else "#FFFFFF") if neo else "#FFFFFF"
        field = "rgba(0,0,0,0.28)" if w.is_dark_bg() else "rgba(255,255,255,0.78)"
        self.setStyleSheet(f"""
            QLabel {{ color: {ink}; background: transparent; font-family: {modern_style.UI_FONT}; font-size: 9.5pt; }}
            QLabel[role="title"] {{ font-size: 11pt; font-weight: 700; }}
            QLabel[role="error"] {{ color: {modern_style.DANGER}; font-weight: 600; }}
            QLineEdit {{
                padding: 7px 9px; border: 1px solid {modern_style._rgba(ink, 0.35)}; border-radius: 0px; background: {field};
                color: {ink}; font-family: {modern_style.UI_FONT}; font-size: 10pt; selection-background-color: {pal['accent']};
            }}
            QLineEdit:focus {{ border-color: {on_bg}; }}
            QPushButton {{
                padding: 6px 14px; border: 1px solid {modern_style._rgba(ink, 0.35)}; border-radius: 0px; background: transparent;
                color: {ink}; font-family: {modern_style.UI_FONT}; font-size: 9.5pt; font-weight: 600;
            }}
            QPushButton:hover {{ border-color: {on_bg}; }}
            QPushButton[role="primary"] {{ background: {on_bg}; border-color: {on_bg}; color: {on_text}; }}
            QPushButton[role="danger"] {{ background: {modern_style.DANGER}; border-color: {modern_style.DANGER}; color: white; }}
        """)

    def paintEvent(self, event: Any) -> None:
        w = self.memo_window
        painter = QPainter(self)
        dark = w.is_dark_bg()
        if w.is_sealed():
            # 잠긴 메모: 본문 대신 흐릿한 줄 모양만 보여 줍니다. (실제 내용은 풀기 전에는 메모리에도 없음)
            bar = QColor(255, 255, 255, 26) if dark else QColor(0, 0, 0, 20)
            widths = (0.82, 0.64, 0.90, 0.48, 0.74, 0.58, 0.86, 0.40, 0.70, 0.52)
            y, n = 14, 0
            while y < self.height() - 14:
                painter.fillRect(QRect(14, y, int((self.width() - 28) * widths[n % len(widths)]), 9), bar)
                y += 24
                n += 1
        else:
            # 흐리게 한 본문이 비쳐 보이도록 반투명하게 덮습니다.
            painter.fillRect(self.rect(), QColor(20, 20, 22, 150) if dark else QColor(255, 255, 255, 150))
        painter.end()

    def area(self) -> QRect:
        editor = self.memo_window.text_edit
        return QRect(editor.mapTo(self.parentWidget(), QPoint(0, 0)), editor.size())

    def usable(self) -> bool:
        w = self.memo_window
        return w.isVisible() and not getattr(w, '_is_rolled_up', False)

    def sync_geometry(self) -> None:
        """본문 편집기 자리에 정확히 겹쳐 놓고, 안의 입력 화면을 그 한가운데에 맞춥니다."""
        super().sync_geometry()
        room = max(120, self.width() - 2 * self.MARGIN)
        for form in (self.unlock_panel, self.panel if self._card is None else None):
            if form is not None:
                form.setFixedWidth(min(self.PANEL_WIDTH, room))

    # ── 잠긴 메모: 늘 보이는 암호 칸 ─────────────────────────────────────────
    def refresh(self) -> None:
        """메모 상태에 맞춥니다. 잠긴 메모면 암호 칸을 띄워 두고, 아니면(입력 중이 아닐 때) 숨깁니다."""
        w = self.memo_window
        if self.panel is not None:
            return
        locked = bool(w.memo_data.get('_locked')) and not getattr(w, '_is_rolled_up', False)
        if not locked:
            self._drop_unlock_panel()
            self.hide()
            return
        if self.unlock_panel is None:
            panel = themed_dialog.FormPanel("🔒 암호 메모", "", [{"label": "암호를 입력하세요", "password": True}], "열기",
                                            cancel_text=None, validate=lambda values: w.try_unlock(values[0]))
            panel.submitted.connect(lambda values: w.finish_unlock())
            self.unlock_panel = panel
            self.holder.addWidget(panel, 0, Qt.AlignmentFlag.AlignHCenter)
        self.apply_style()
        self.sync_geometry()
        self.show()
        self.raise_()
        self.layout().activate()                         # 암호 칸을 지금 크기의 한가운데에

    def _drop_unlock_panel(self) -> None:
        if self.unlock_panel is not None:
            self.holder.removeWidget(self.unlock_panel)
            self.unlock_panel.hide()
            self.unlock_panel.deleteLater()
            self.unlock_panel = None

    def focus_inline(self) -> bool:
        """잠긴 메모의 암호 칸이 보이고 있으면 거기에 커서를 두고 True. (따로 묻지 않아도 됨)"""
        if self.panel is None and self.unlock_panel is not None and self.isVisible():
            self.memo_window.activateWindow()
            self.unlock_panel.focus_first()
            return True
        return False

    # ── 입력 화면 띄우기 ─────────────────────────────────────────────────────
    def before_run(self) -> None:
        w = self.memo_window
        if self.unlock_panel is not None:
            self.unlock_panel.hide()
        if not w.is_sealed():
            self._blur = QGraphicsBlurEffect(w.text_edit)
            self._blur.setBlurRadius(10)
            w.text_edit.setGraphicsEffect(self._blur)
        self.apply_style()

    def after_run(self) -> None:
        if self._blur is not None:
            self.memo_window.text_edit.setGraphicsEffect(None)
            self._blur = None
        if self.unlock_panel is not None:
            self.unlock_panel.show()
        self.refresh()


def host_panel(parent: Any, panel: QWidget, title: str, need_width: int, need_height: int) -> Any:
    """panel 을 parent 가 속한 창 안에서 띄워 답을 받습니다. 띄울 곳이 없으면 themed_dialog.NO_HOST 를 돌려줍니다.

    - 메모 창: 본문 위(자리가 있을 때) → 없으면 메모 옆에 붙는 패널
    - 탐색기: 창 가운데의 카드
    """
    window = parent.window() if parent is not None else None
    overlay = getattr(window, 'lock_overlay', None)
    if overlay is not None:                              # 메모 창
        if overlay.can_host(need_width, need_height):
            return overlay.run(panel)
        side = window.side_panel()
        if window.isVisible() and not side.is_busy():
            return side.run(panel, title)
        return themed_dialog.NO_HOST
    overlay = getattr(window, 'inline_overlay', None)
    if overlay is not None and overlay.can_host(need_width + 40, need_height + 40):      # 탐색기
        return overlay.run(panel, card=True)
    return themed_dialog.NO_HOST


def ask(window: Any, title: str, text: str, fields: Sequence[Dict[str, Any]], ok_text: str = "확인",
        validate: Optional[Callable[[List[str]], Optional[str]]] = None, danger: bool = False) -> Optional[List[str]]:
    """암호 등을 창 안에서 입력받습니다. (메모에서 불렀으면 그 메모 안에서, 탐색기에서 불렀으면 탐색기 안에서)"""
    return themed_dialog.ask_form(window._dlg_parent(), title, text, fields, ok_text, validate, danger)
