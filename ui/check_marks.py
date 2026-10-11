"""체크리스트를 편집기 화면에 그리는 부분.

저장되는 내용은 줄 앞의 글자(☐/☑) 그대로 두고, 화면에서만 그 글자 자리에 네모 상자를 그립니다.
끝낸 줄은 글자를 흐리게 하고 취소선을 긋습니다. 메모 창의 편집기와 탐색기의 미리보기가 함께 씁니다.
"""
from typing import Any, Callable, Dict, Optional

from PyQt6.QtCore import QPoint, QPointF, QRect, Qt
from PyQt6.QtGui import QColor, QPainter, QPalette, QPen, QPolygonF, QTextCharFormat, QTextCursor
from PyQt6.QtWidgets import QTextEdit

from ui import checklist


class CheckMarks:
    """편집기(QTextEdit) 하나에 붙어 체크 상자를 그리고, 누르기·지우기·줄바꿈을 처리합니다.

    colors() 는 {"ink": 글자색, "fill": 채움색, "tick": 체크 표시색, "dark": 바탕이 어두운지} 를 돌려줍니다.
    on_edit() 는 체크 상태를 바꿨을 때 부릅니다. (저장 예약 등)
    """

    def __init__(self, editor: QTextEdit, colors: Callable[[], Dict[str, Any]], on_edit: Optional[Callable[[], None]] = None) -> None:
        self.editor = editor
        self.colors = colors
        self.on_edit = on_edit
        # 체크 상자를 누르기 직전에 부르는 함수. True 를 돌려주면 여기서는 글자를 바꾸지 않습니다.
        # (탐색기 미리보기가 서식이 있는 메모를 서식을 지키며 고칠 때 씀)
        self.intercept: Optional[Callable[[Any], bool]] = None
        # 본문이 바뀔 때 한 번만 훑어서 기억해 둡니다. (그릴 때와 진행 표시를 낼 때 다시 훑지 않도록)
        self.has_boxes = False
        self.done, self.total = 0, 0
        editor.textChanged.connect(self.refresh)

    # ── 위치 ─────────────────────────────────────────────────────────────────
    def box_rect(self, block: Any, index: int) -> QRect:
        """block 의 index 번째 글자(체크 상자) 자리에 그릴 네모의 위치. (편집기 안의 좌표)"""
        probe = QTextCursor(block)
        probe.setPosition(block.position() + index)
        line = self.editor.cursorRect(probe)
        side = max(9, min(24, int(line.height() * 0.64)))
        return QRect(line.left(), line.center().y() - side // 2 + 1, side, side)

    def glyph_cell(self, block: Any, index: int) -> QRect:
        """block 의 index 번째 글자(체크 상자 글자)가 차지하는 칸. (편집기 안의 좌표)"""
        probe = QTextCursor(block)
        probe.setPosition(block.position() + index)
        left = self.editor.cursorRect(probe)
        probe.setPosition(block.position() + index + 1)
        right = self.editor.cursorRect(probe)
        width = right.left() - left.left() if right.top() == left.top() and right.left() > left.left() else left.height()
        return QRect(left.left(), left.top(), width + 1, left.height())

    def _faded_ink(self) -> QColor:
        """끝낸 줄의 글자색: 글자색을 바탕 쪽으로 절반쯤 섞은 색. (반투명 색은 글자에 먹지 않아 불투명한 색으로 만듦)"""
        colors = self.colors()
        ink = QColor(colors["ink"])
        base = 0 if colors.get("dark") else 255
        return QColor(*((c + base) // 2 for c in (ink.red(), ink.green(), ink.blue())))

    # ── 화면에 보이는 모습 ───────────────────────────────────────────────────
    def refresh(self) -> None:
        """체크 상자 글자는 안 보이게 하고(그 자리에 paint 가 네모를 그림), 끝낸 줄의 글자는 흐리게 합니다."""
        selections = []
        document = self.editor.document()
        # 체크 상자 글자가 하나도 없는 메모(대부분)는 줄을 훑지 않고 끝냅니다.
        self.has_boxes = not (document.find(checklist.UNCHECKED).isNull() and document.find(checklist.CHECKED).isNull())
        self.done, self.total = 0, 0
        if self.has_boxes:
            hidden = QTextCharFormat()
            hidden.setForeground(QColor(0, 0, 0, 0))
            faded = QTextCharFormat()
            faded.setForeground(self._faded_ink())
            block = document.begin()
            while block.isValid():
                text = block.text()
                index = checklist.box_index(text)
                if index >= 0:
                    self.total += 1
                    self.done += text[index] == checklist.CHECKED
                    spans = [(index, index + 1, hidden)]
                    if text[index] == checklist.CHECKED and len(text) > index + 1:
                        spans.append((index + 1, len(text), faded))
                    for start, end, fmt in spans:
                        selection = QTextEdit.ExtraSelection()
                        selection.cursor = QTextCursor(block)
                        selection.cursor.setPosition(block.position() + start)
                        selection.cursor.setPosition(block.position() + end, QTextCursor.MoveMode.KeepAnchor)
                        selection.format = fmt
                        selections.append(selection)
                block = block.next()
        self.editor.setExtraSelections(selections)

    def paint(self) -> None:
        """보이는 줄의 체크 상자를 그립니다. 안 한 일은 빈 네모, 끝낸 일은 채운 네모에 체크 표시와 취소선."""
        editor = self.editor
        if not self.has_boxes:
            return
        colors = self.colors()
        ink, fill, tick = QColor(colors["ink"]), QColor(colors["fill"]), QColor(colors["tick"])
        outline = QColor(ink)
        outline.setAlphaF(0.72)
        strike = self._faded_ink()
        doc_layout = editor.document().documentLayout()
        scroll = QPointF(editor.horizontalScrollBar().value(), editor.verticalScrollBar().value())

        painter = QPainter(editor.viewport())
        bottom = editor.viewport().height()
        selection = editor.textCursor()
        selected_from, selected_to = (selection.selectionStart(), selection.selectionEnd()) if selection.hasSelection() else (-1, -1)
        group = QPalette.ColorGroup.Active if editor.hasFocus() else QPalette.ColorGroup.Inactive
        highlight = editor.palette().color(group, QPalette.ColorRole.Highlight)
        block = editor.cursorForPosition(QPoint(0, 0)).block()
        while block.isValid():
            text = block.text()
            index = checklist.box_index(text)
            rect = self.box_rect(block, max(index, 0))
            if rect.top() > bottom:
                break
            box_outline = outline
            if index >= 0 and selected_from <= block.position() + index < selected_to:
                box_outline = editor.palette().color(group, QPalette.ColorRole.HighlightedText)      # 선택 바탕 위에서도 보이게
                # 선택된 글자는 '선택된 글자색'으로 다시 그려져, 숨겨 둔 상자 글자(☐/☑)가 네모 위에 겹쳐 보입니다.
                # 그 글자 칸을 선택 바탕색으로 덮은 뒤 네모를 그려, 어떤 경우에도 원래 글자가 보이지 않게 합니다.
                painter.fillRect(self.glyph_cell(block, index), highlight)
            if index >= 0 and text[index] == checklist.CHECKED:
                painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
                painter.fillRect(rect, fill)
                # 취소선: 이 줄의 글자(상자 뒤부터)를 가로지르는 선. 줄이 넘어가면 넘어간 줄마다 긋습니다.
                origin = doc_layout.blockBoundingRect(block).topLeft() - scroll
                layout = block.layout()
                painter.setPen(QPen(strike, 1))
                for n in range(layout.lineCount()):
                    line = layout.lineAt(n)
                    start = origin.x() + line.x()
                    if n == 0:
                        start = max(start, rect.right() + 5)
                    end = origin.x() + line.x() + line.naturalTextWidth()
                    y = int(origin.y() + line.y() + line.height() / 2) + 1
                    if end > start:
                        painter.drawLine(int(start), y, int(end), y)
                painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
                painter.setPen(QPen(tick, max(1.5, rect.width() * 0.14), Qt.PenStyle.SolidLine,
                                    Qt.PenCapStyle.SquareCap, Qt.PenJoinStyle.MiterJoin))
                x, y, side = rect.left(), rect.top(), rect.width()
                painter.drawPolyline(QPolygonF([QPointF(x + side * 0.24, y + side * 0.53), QPointF(x + side * 0.43, y + side * 0.72),
                                                QPointF(x + side * 0.78, y + side * 0.30)]))
            elif index >= 0:
                painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
                painter.setPen(QPen(box_outline, 1))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(rect.adjusted(0, 0, -1, -1))
            block = block.next()
        painter.end()

    def progress_label(self) -> str:
        """진행 표시. 다 끝냈으면 '☑ 5/5', 남은 일이 있으면 '☐ 3/5'. 체크리스트가 없으면 ''."""
        if not self.total:
            return ""
        return f"{checklist.CHECKED if self.done == self.total else checklist.UNCHECKED} {self.done}/{self.total}"

    # ── 조작 ─────────────────────────────────────────────────────────────────
    def toggle_at(self, pos: Any) -> bool:
        """pos(편집기 안의 좌표)가 체크 상자 위면 체크 상태를 뒤집고 True 를 돌려줍니다."""
        editor = self.editor
        if editor.isReadOnly():
            return False
        block = editor.cursorForPosition(pos).block()
        index = checklist.box_index(block.text())
        if index < 0 or not self.box_rect(block, index).adjusted(-4, -4, 5, 4).contains(pos):
            return False
        if self.intercept is not None and self.intercept(block):
            return True
        edit = QTextCursor(block)
        edit.setPosition(block.position() + index)
        edit.setPosition(block.position() + index + 1, QTextCursor.MoveMode.KeepAnchor)
        edit.insertText(checklist.CHECKED if block.text()[index] == checklist.UNCHECKED else checklist.UNCHECKED)
        if self.on_edit:
            self.on_edit()
        return True

    def backspace(self) -> bool:
        """체크 상자 바로 뒤에서 Backspace: 상자와 그 뒤의 공백을 한 번에 지웁니다. (불릿·번호 목록처럼)"""
        editor = self.editor
        cursor = editor.textCursor()
        if editor.isReadOnly() or cursor.hasSelection():
            return False
        block = cursor.block()
        text = block.text()
        index = checklist.box_index(text)
        if index < 0:
            return False
        end = index + (2 if text[index + 1:index + 2] == " " else 1)       # 상자(+ 공백)가 끝나는 자리
        if not (index < cursor.positionInBlock() <= end):
            return False
        cursor.beginEditBlock()
        cursor.setPosition(block.position() + index)
        cursor.setPosition(block.position() + end, QTextCursor.MoveMode.KeepAnchor)
        cursor.removeSelectedText()
        cursor.endEditBlock()
        editor.setTextCursor(cursor)
        if self.on_edit:
            self.on_edit()
        return True

    def continue_line(self) -> bool:
        """체크리스트 줄에서 Enter: 다음 줄도 체크 상자로 시작합니다. 상자만 있는 빈 줄이면 상자를 지워 체크리스트를 끝냅니다."""
        editor = self.editor
        cursor = editor.textCursor()
        if editor.isReadOnly() or cursor.hasSelection():
            return False
        block = cursor.block()
        prefix, clear_box = checklist.continuation(block.text())
        if clear_box:
            cursor.beginEditBlock()
            cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
            cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
            cursor.insertText(checklist.without_box(block.text()).rstrip())
            cursor.endEditBlock()
            editor.setTextCursor(cursor)
            return True
        if not prefix or not cursor.atBlockEnd():
            return False
        cursor.beginEditBlock()
        cursor.insertBlock()
        cursor.insertText(prefix)
        cursor.endEditBlock()
        editor.setTextCursor(cursor)
        editor.ensureCursorVisible()
        return True


def palette_colors(widget: QTextEdit) -> Dict[str, Any]:
    """widget 에 입혀진 색(글자색·선택색)에서 체크 상자 색을 정합니다. (따로 색을 정해 주지 않는 곳에서 사용)"""
    palette = widget.palette()
    ink = palette.color(QPalette.ColorRole.Text)
    return {"ink": ink.name(), "fill": palette.color(QPalette.ColorRole.Highlight).name(), "tick": "#FFFFFF",
            "dark": ink.lightness() > 140}


class CheckEdit(QTextEdit):
    """체크 상자를 그리고 누를 수 있는 간단한 편집기. (탐색기의 미리보기)"""

    def __init__(self, colors: Optional[Callable[[], Dict[str, Any]]] = None) -> None:
        super().__init__()
        self.check_marks = CheckMarks(self, colors or (lambda: palette_colors(self)))

    def paintEvent(self, event: Any) -> None:
        super().paintEvent(event)
        self.check_marks.paint()

    def mousePressEvent(self, event: Any) -> None:
        if event.button() == Qt.MouseButton.LeftButton and not event.modifiers() and self.check_marks.toggle_at(event.pos()):
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event: Any) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.check_marks.toggle_at(event.pos()):
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def keyPressEvent(self, event: Any) -> None:
        if not event.modifiers():
            if event.key() == Qt.Key.Key_Backspace and self.check_marks.backspace():
                event.accept()
                return
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and self.check_marks.continue_line():
                event.accept()
                return
        super().keyPressEvent(event)
