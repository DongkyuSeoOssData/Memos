"""메모 창의 찾기·바꾸기 줄.

(MemoWindow 에 섞어 쓰는 부분)
"""
from typing import Any
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QLineEdit, QLabel
from PyQt6.QtGui import QColor, QTextCursor, QPalette, QTextDocument


class MemoFindMixin:
    """메모 창의 찾기·바꾸기."""

    def _build_search_bar(self, cc_layout: Any) -> None:
        """찾기·바꾸기 줄."""
        self.search_bar = QWidget()
        sl = QHBoxLayout(self.search_bar)
        sl.setContentsMargins(0, 4, 0, 4)

        self.s_in = QLineEdit()
        self.s_in.setPlaceholderText("찾을 단어")
        self.s_in.returnPressed.connect(lambda: self.do_find(backward=False))

        self.s_count = QLabel("0/0")

        self.s_prev_btn = QPushButton("▲")
        self.s_prev_btn.setFixedSize(24, 24)
        self.s_prev_btn.clicked.connect(lambda: self.do_find(backward=True))

        self.s_next_btn = QPushButton("▼")
        self.s_next_btn.setFixedSize(24, 24)
        self.s_next_btn.clicked.connect(lambda: self.do_find(backward=False))

        self.r_in = QLineEdit()
        self.r_in.setPlaceholderText("바꿀 단어")
        self.r_in.returnPressed.connect(self.do_replace)

        self.r_btn = QPushButton("바꾸기")
        self.r_btn.clicked.connect(self.do_replace)

        self.s_close = QPushButton("")
        self.s_close.setFixedSize(24, 24)
        self.s_close.setStyleSheet("border:none; background:transparent;")
        if getattr(self, 'ui_manager', None) and hasattr(self.ui_manager, 'get_theme_icon'):
            self.s_close.setIcon(self.ui_manager.get_theme_icon("close.svg", False, override_color="#FF453A"))
        self.s_close.clicked.connect(self.search_bar.hide)

        for w in [self.s_in, self.s_count, self.s_prev_btn, self.s_next_btn, self.r_in, self.r_btn, self.s_close]:
            sl.addWidget(w)

        self.search_bar.hide()
        cc_layout.addWidget(self.search_bar)

    def show_search_only(self) -> None:
        self.r_in.hide()
        self.r_btn.hide()
        self.search_bar.show()
        self.s_in.setFocus()
        self.s_in.selectAll()

    def show_search_and_replace(self) -> None:
        self.r_in.show()
        self.r_btn.show()
        self.search_bar.show()
        self.s_in.setFocus()
        self.s_in.selectAll()

    def do_find(self, backward: bool = False) -> None:
        search_text = self.s_in.text()
        if not search_text:
            self.s_count.setText("0/0")
            return

        p = self.text_edit.palette()
        p.setColor(QPalette.ColorRole.Highlight, QColor("#007AFF"))
        p.setColor(QPalette.ColorRole.HighlightedText, QColor("#FFFFFF"))
        self.text_edit.setPalette(p)

        if backward:
            found = self.text_edit.find(search_text, QTextDocument.FindFlag.FindBackward)
        else:
            found = self.text_edit.find(search_text)

        if not found:
            c = self.text_edit.textCursor()
            c.movePosition(QTextCursor.MoveOperation.End if backward else QTextCursor.MoveOperation.Start)
            self.text_edit.setTextCursor(c)
            found = self.text_edit.find(search_text, QTextDocument.FindFlag.FindBackward if backward else QTextDocument.FindFlag(0))

        if found:
            text = self.text_edit.toPlainText().lower()
            st_low = search_text.lower()
            total = text.count(st_low)
            cursor_pos = self.text_edit.textCursor().position()
            current = text[:cursor_pos].count(st_low)
            if backward and current == 0 and total > 0: current = 1
            self.s_count.setText(f"{current}/{total}")
        else:
            self.s_count.setText("0/0")

    def do_replace(self) -> None:
        c = self.text_edit.textCursor()
        if c.hasSelection() and c.selectedText().lower() == self.s_in.text().lower():
            c.insertText(self.r_in.text())
            self._mark_edited()
        self.do_find(backward=False)
