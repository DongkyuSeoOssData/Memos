"""빠른 검색 창. 전역 단축키로 띄워 글자를 치는 대로 메모를 찾고, Enter 로 바로 엽니다."""
from typing import Any, Dict, List

from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtGui import QCursor, QGuiApplication
from PyQt6.QtWidgets import QLabel, QLineEdit, QListWidget, QListWidgetItem, QVBoxLayout, QWidget

from core import folders, reminders
from ui import modern_style
from utils.text_utils import clean_plain_text


class QuickSearch(QWidget):
    MAX_RESULTS = 30

    def __init__(self, ui_manager: Any) -> None:
        super().__init__()
        self.ui_manager = ui_manager
        self._memos: List[Dict[str, Any]] = []
        self._texts: Dict[str, str] = {}
        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setObjectName("QuickSearch")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedWidth(560)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 12)
        layout.setSpacing(8)
        self.input = QLineEdit()
        self.input.setPlaceholderText("메모 찾기 — 제목이나 내용의 일부를 입력하세요")
        self.input.textChanged.connect(self.refresh_results)
        self.input.installEventFilter(self)
        layout.addWidget(self.input)
        self.results = QListWidget()
        self.results.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.results.itemActivated.connect(lambda item: self.open_item(item))
        self.results.itemClicked.connect(lambda item: self.open_item(item))
        layout.addWidget(self.results)
        self.hint = QLabel("↑↓ 고르기 · Enter 열기 · Esc 닫기")
        layout.addWidget(self.hint)

    # ── 띄우기 ───────────────────────────────────────────────────────────────
    def toggle(self) -> None:
        if self.isVisible():
            self.hide()
        else:
            self.popup()

    def popup(self) -> None:
        """메모를 한 번 읽어 두고, 마우스가 있는 화면의 위쪽 가운데에 띄웁니다."""
        sm = self.ui_manager.sync_manager
        self._memos = sm.load_local_memos()
        self._texts = {}
        self.setStyleSheet(modern_style.popup_qss(sm.settings))
        self.input.clear()
        self.refresh_results()
        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        if screen:
            area = screen.availableGeometry()
            self.move(area.left() + (area.width() - self.width()) // 2, area.top() + area.height() // 5)
        self.show()
        self.raise_()
        self.activateWindow()
        self.input.setFocus()

    # ── 찾기 ─────────────────────────────────────────────────────────────────
    def _text_of(self, memo: Dict[str, Any]) -> str:
        memo_id = memo.get("id", "")
        if memo_id not in self._texts:
            sealed = memo.get("_locked") or memo.get("_unreadable")
            self._texts[memo_id] = "" if sealed else clean_plain_text(memo.get("content", ""))
        return self._texts[memo_id]

    def search(self, query: str) -> List[Dict[str, Any]]:
        """제목이 맞는 메모를 먼저, 그다음 내용이 맞는 메모를 최근 수정 순으로 돌려줍니다. 낱말을 띄어 쓰면 모두 들어 있어야 합니다."""
        words = [w for w in query.lower().split() if w]
        recent = sorted(self._memos, key=lambda m: str(m.get("updated_at", "")), reverse=True)
        if not words:
            return recent[:self.MAX_RESULTS]
        in_title, in_body = [], []
        for memo in recent:
            title = str(memo.get("title", "")).lower()
            body = self._text_of(memo).lower()
            folder = folders.folder_of(memo).lower()
            if all(w in title for w in words):
                in_title.append(memo)
            elif all(w in title or w in body or w in folder for w in words):
                in_body.append(memo)
        return (in_title + in_body)[:self.MAX_RESULTS]

    def _snippet(self, memo: Dict[str, Any], query: str) -> str:
        if memo.get("_locked"):
            return "🔒 암호 메모"
        text = " ".join(self._text_of(memo).split())
        words = [w for w in query.lower().split() if w]
        at = min([text.lower().find(w) for w in words if w in text.lower()] or [0])
        start = max(0, at - 20)
        return ("…" if start else "") + text[start:start + 90]

    def refresh_results(self) -> None:
        query = self.input.text()
        self.results.clear()
        for memo in self.search(query):
            details = [p for p in (
                "📁 " + folders.folder_of(memo) if folders.folder_of(memo) else "",
                "⏰ " + reminders.describe(memo.get("reminder")) if memo.get("reminder") else "",
                self._snippet(memo, query),
            ) if p]
            mark = "{ } " if memo.get("is_code_memo") else ""
            item = QListWidgetItem(mark + (str(memo.get("title", "")) or "(제목 없음)") + "\n" + "  ·  ".join(details))
            item.setData(Qt.ItemDataRole.UserRole, memo.get("id"))
            self.results.addItem(item)
        if self.results.count():
            self.results.setCurrentRow(0)
        rows = min(self.results.count(), 7)
        self.results.setFixedHeight(max(1, rows) * 52 + 6)
        self.results.setVisible(self.results.count() > 0)
        self.hint.setText("↑↓ 고르기 · Enter 열기 · Esc 닫기" if self.results.count() else "맞는 메모가 없습니다")
        self.adjustSize()

    # ── 고르기 ───────────────────────────────────────────────────────────────
    def open_item(self, item: Any = None) -> None:
        item = item or self.results.currentItem()
        if item is None:
            return
        memo_id = item.data(Qt.ItemDataRole.UserRole)
        self.hide()
        if memo_id:
            self.ui_manager.show_specific_memo(memo_id)

    def move_selection(self, step: int) -> None:
        if self.results.count():
            self.results.setCurrentRow((self.results.currentRow() + step) % self.results.count())

    def eventFilter(self, obj: Any, event: Any) -> bool:
        if obj is self.input and event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if key in (Qt.Key.Key_Down, Qt.Key.Key_Up):
                self.move_selection(1 if key == Qt.Key.Key_Down else -1)
                return True
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self.open_item()
                return True
            if key == Qt.Key.Key_Escape:
                self.hide()
                return True
        return False

    def changeEvent(self, event: Any) -> None:
        # 다른 창을 누르면 닫습니다.
        if event.type() == QEvent.Type.ActivationChange and self.isVisible() and not self.isActiveWindow():
            self.hide()
        super().changeEvent(event)
