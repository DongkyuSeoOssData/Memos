from ui import modern_style
from ui.check_marks import CheckMarks
from typing import List, Any
from PyQt6.QtWidgets import *
from PyQt6.QtGui import *
from PyQt6.QtCore import *
import re

class CodeHighlighter(QSyntaxHighlighter):
    """
    iOS 미니멀 흑백 & 모던 네온 하이라이터:
    - Light: Base Text #000000
    - Dark: Base Text #FFFFFF
    """
    def __init__(self, document: QTextDocument, lang: str = "JSON", theme: str = "dark") -> None:
        super().__init__(document)
        self.lang = lang.upper()
        self.theme = theme.lower()
        self.rules = []

        is_dark = (self.theme == "dark")
        kw_color = QColor("#FF7B72") if is_dark else QColor("#D73A49")
        str_color = QColor("#A5D6FF") if is_dark else QColor("#032F62")
        num_color = QColor("#79C0FF") if is_dark else QColor("#005CC5")
        cm_color = QColor("#8B949E") if is_dark else QColor("#6A737D")
        type_color = QColor("#D2A8FF") if is_dark else QColor("#6F42C1")

        kw_fmt = QTextCharFormat()
        kw_fmt.setForeground(kw_color)
        kw_fmt.setFontWeight(QFont.Weight.Bold)

        str_fmt = QTextCharFormat()
        str_fmt.setForeground(str_color)

        num_fmt = QTextCharFormat()
        num_fmt.setForeground(num_color)

        cm_fmt = QTextCharFormat()
        cm_fmt.setForeground(cm_color)
        cm_fmt.setFontItalic(True)

        type_fmt = QTextCharFormat()
        type_fmt.setForeground(type_color)

        if "JSON" in self.lang:
            self.rules.append((re.compile(r'"[^"\\]*(\\.[^"\\]*)*"\s*:'), type_fmt))
            self.rules.append((re.compile(r':\s*"[^"\\]*(\\.[^"\\]*)*"'), str_fmt))
            self.rules.append((re.compile(r'\b(true|false|null)\b'), kw_fmt))
            self.rules.append((re.compile(r'\b[-+]?\d*\.?\d+\b'), num_fmt))
        elif any(k in self.lang for k in ["C#", "VB.NET", "PYTHON", "JAVASCRIPT", "C++", "JAVA", "POWER"]):
            kw_pat = r'\b(public|private|protected|class|void|string|int|bool|if|else|for|foreach|while|return|using|namespace|dim|as|function|def|var|let|const|import)\b'
            self.rules.append((re.compile(kw_pat, re.IGNORECASE), kw_fmt))
            self.rules.append((re.compile(r'"[^"\\]*(\\.[^"\\]*)*"|\'[^\'\\]*(\\.[^\'\\]*)*\''), str_fmt))
            # 주석 기호는 언어마다 다릅니다. (작은따옴표 주석은 VB에만 해당)
            if "VB" in self.lang:
                comment_pat = r"'.*"
            elif "PYTHON" in self.lang or "POWER" in self.lang:
                comment_pat = r'#.*'
            else:
                comment_pat = r'//.*'
            self.rules.append((re.compile(comment_pat), cm_fmt))
            self.rules.append((re.compile(r'\b[A-Z][a-zA-Z0-9_]*\b'), type_fmt))
            self.rules.append((re.compile(r'\b[-+]?\d+\b'), num_fmt))
        else:
            self.rules.append((re.compile(r'"[^"\\]*(\\.[^"\\]*)*"'), str_fmt))
            self.rules.append((re.compile(r'\b[-+]?\d+\b'), num_fmt))

    def highlightBlock(self, text: str) -> None:
        base_fmt = QTextCharFormat()
        base_fmt.setForeground(QColor("#FFFFFF") if self.theme == "dark" else QColor("#000000"))
        self.setFormat(0, len(text), base_fmt)

        for pattern, fmt in self.rules:
            for match in pattern.finditer(text):
                start, end = match.span()
                self.setFormat(start, end - start, fmt)

class LineNumberArea(QWidget):
    def __init__(self, editor: 'MemoTextEdit') -> None:
        super().__init__(editor)
        self.editor = editor

    def sizeHint(self) -> QSize:
        return QSize(self.editor.line_number_area_width(), 0)

    def paintEvent(self, event: Any) -> None:
        self.editor.line_number_area_paint_event(event)

class MemoTextEdit(QTextEdit):
    def __init__(self, memo_window: 'MemoWindow') -> None:
        super().__init__()
        self.memo_window = memo_window
        self.document().setDocumentMargin(12)
        self.document().setIndentWidth(22)
        self.extra_cursors: List[QTextCursor] = []
        self.line_number_area = LineNumberArea(self)
        self.document().documentLayout().update.connect(self.update_line_number_area)
        self.verticalScrollBar().valueChanged.connect(self.line_number_area.update)
        self.textChanged.connect(self.update_line_number_area)
        self.check_marks = CheckMarks(self, self._check_colors, on_edit=lambda: self.memo_window._mark_edited())

    # ── 체크리스트 (줄 앞의 ☐ / ☑). 그리기와 조작은 CheckMarks 가 맡습니다. ─────────────
    def _check_colors(self) -> dict:
        """체크 상자에 쓸 색. 메모 바탕 밝기와 디자인 스타일(Modern 은 강조색, Neo 는 흑백)을 따릅니다."""
        w = self.memo_window
        pal = w._memo_theme_palette()
        sm = w._sync_manager()
        neo = modern_style.is_neo(sm.settings) if sm else False
        dark = w.is_dark_bg()
        return {"ink": pal['text'], "fill": pal['text'] if neo else pal['accent'],
                "tick": "#1C1C1E" if neo and dark else "#FFFFFF", "dark": dark}

    def toggle_check_at(self, pos: Any) -> bool:
        return self.check_marks.toggle_at(pos)

    def _check_box_rect(self, block: Any, index: int) -> QRect:
        return self.check_marks.box_rect(block, index)

    def refresh_check_marks(self) -> None:
        self.check_marks.refresh()

    def continue_checklist(self) -> bool:
        return self.check_marks.continue_line()

    def _unlist_at_start(self) -> bool:
        """커서가 목록 줄의 맨 앞에 있으면 그 줄을 목록에서 빼고 들여쓰기도 없앱니다. (한 번에 보통 줄로)"""
        cursor = self.textCursor()
        if self.isReadOnly() or cursor.hasSelection() or not cursor.atBlockStart():
            return False
        block = cursor.block()
        text_list = block.textList()
        if text_list is None:
            return False
        cursor.beginEditBlock()
        text_list.remove(block)
        fmt = cursor.blockFormat()
        fmt.setIndent(0)
        fmt.setTextIndent(0)
        cursor.setBlockFormat(fmt)
        cursor.endEditBlock()
        self.setTextCursor(cursor)
        self.memo_window._mark_edited()
        return True

    def mouseDoubleClickEvent(self, e: Any) -> None:
        # 체크 상자를 빠르게 두 번 누른 경우: 글자를 선택하지 않고, 누른 만큼 체크를 뒤집습니다.
        if e.button() == Qt.MouseButton.LeftButton and self.toggle_check_at(e.pos()):
            e.accept()
            return
        super().mouseDoubleClickEvent(e)

    def mousePressEvent(self, e: Any) -> None:
        if e.button() == Qt.MouseButton.LeftButton and self.memo_window.memo_data.get('_locked'):
            # 잠긴 암호 메모: 본문을 클릭하면 암호를 묻습니다.
            self.memo_window.prompt_unlock()
            e.accept()
            return
        if e.button() == Qt.MouseButton.LeftButton and not e.modifiers() and self.toggle_check_at(e.pos()):
            # 체크 상자(☐/☑)를 누르면 체크 상태만 바꾸고 커서는 옮기지 않습니다.
            e.accept()
            return
        if e.button() == Qt.MouseButton.LeftButton and (e.modifiers() & Qt.KeyboardModifier.AltModifier):
            click_cursor = self.cursorForPosition(e.pos())
            all_positions = [c.position() for c in ([self.textCursor()] + self.extra_cursors)]
            if click_cursor.position() not in all_positions:
                self.extra_cursors.append(click_cursor)
            self.viewport().update()
            e.accept()
            return
        elif e.button() == Qt.MouseButton.LeftButton and not (e.modifiers() & Qt.KeyboardModifier.AltModifier):
            if self.extra_cursors:
                self.extra_cursors.clear()
                self.viewport().update()
        super().mousePressEvent(e)

    def shift_code_indent(self, delta: int) -> None:
        """코드 메모의 들여쓰기: 실제 공백 4칸을 넣거나 뺍니다. (복사해도 들여쓰기가 유지됨)"""
        cursor = self.textCursor()
        doc = self.document()
        if delta > 0 and not cursor.hasSelection():
            cursor.insertText("    ")
            return
        block = doc.findBlock(cursor.selectionStart())
        end = doc.findBlock(cursor.selectionEnd())
        if cursor.hasSelection() and end != block and end.position() == cursor.selectionEnd():
            end = end.previous()
        cursor.beginEditBlock()
        while block.isValid():
            line_cursor = QTextCursor(block)
            if delta > 0:
                line_cursor.insertText("    ")
            else:
                text = block.text()
                count = min(4, len(text) - len(text.lstrip(' ')))
                if count == 0 and text.startswith(chr(9)):
                    count = 1
                if count:
                    line_cursor.movePosition(QTextCursor.MoveOperation.Right, QTextCursor.MoveMode.KeepAnchor, count)
                    line_cursor.removeSelectedText()
            if block == end:
                break
            block = block.next()
        cursor.endEditBlock()

    def line_number_area_width(self) -> int:
        if not self.memo_window.memo_data.get('show_line_numbers', False):
            return 0
        digits = len(str(max(1, self.document().blockCount())))
        return 15 + self.fontMetrics().horizontalAdvance('9') * digits

    def update_line_number_area(self) -> None:
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)
        self.line_number_area.setVisible(self.memo_window.memo_data.get('show_line_numbers', False))
        cr = self.contentsRect()
        self.line_number_area.setGeometry(QRect(cr.left(), cr.top(), self.line_number_area_width(), cr.height()))
        self.line_number_area.update()

    def resizeEvent(self, e: Any) -> None:
        super().resizeEvent(e)
        cr = self.contentsRect()
        self.line_number_area.setGeometry(QRect(cr.left(), cr.top(), self.line_number_area_width(), cr.height()))

    def line_number_area_paint_event(self, event: Any) -> None:
        painter = QPainter(self.line_number_area)
        theme = self.memo_window.memo_window_get_settings().get('app_theme', 'white')
        is_dark = (theme == "dark")

        bg_color = QColor(0, 0, 0, 40) if is_dark else QColor(0, 0, 0, 15)
        text_color = QColor("#8E8E93")

        painter.fillRect(event.rect(), bg_color)
        painter.setPen(text_color)
        line_font = QFont(self.font().family(), self.memo_window.memo_data.get('font_size', 11))
        painter.setFont(line_font)

        block = self.document().begin()
        scroll_y = self.verticalScrollBar().value()
        block_number = 0

        while block.isValid():
            block_bb = self.document().documentLayout().blockBoundingRect(block)
            pos_y = block_bb.top() - scroll_y

            if pos_y <= event.rect().bottom() and pos_y + block_bb.height() >= event.rect().top():
                painter.drawText(
                    0, int(pos_y), self.line_number_area.width() - 5, self.fontMetrics().height(),
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, str(block_number + 1)
                )

            block = block.next()
            block_number += 1

    def keyPressEvent(self, e: Any) -> None:
        if e.key() == Qt.Key.Key_Escape:
            # 멀티 커서가 켜져 있으면 Esc는 커서만 해제하고, 그렇지 않을 때만 메모를 닫습니다.
            if self.extra_cursors:
                self.extra_cursors.clear()
                self.viewport().update()
            else:
                self.memo_window.close()
            e.accept()
            return

        if (e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not e.modifiers() and not self.extra_cursors
                and not self.isReadOnly() and self.continue_checklist()):
            e.accept()
            return
        # 체크 상자 바로 뒤에서 Backspace: 상자와 공백을 한 번에 지웁니다. (불릿·번호 목록처럼)
        if e.key() == Qt.Key.Key_Backspace and not e.modifiers() and not self.extra_cursors and self.check_marks.backspace():
            e.accept()
            return
        # 불릿·번호 목록의 맨 앞에서 Backspace: 목록 표시와 들여쓰기를 한 번에 없앱니다.
        if e.key() == Qt.Key.Key_Backspace and not e.modifiers() and not self.extra_cursors and self._unlist_at_start():
            e.accept()
            return

        is_code = self.memo_window.memo_data.get('is_code_memo', False)

        # VS Code 스타일 멀티 커서 복제 (Ctrl+Alt+Up/Down, Alt+Shift+Up/Down, Ctrl+Shift+Up/Down)
        has_ctrl = bool(e.modifiers() & Qt.KeyboardModifier.ControlModifier)
        has_alt = bool(e.modifiers() & Qt.KeyboardModifier.AltModifier)
        has_shift = bool(e.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        is_multi_shortcut = (has_ctrl and has_alt) or (has_alt and has_shift) or (has_ctrl and has_shift)

        if is_multi_shortcut and e.key() in (Qt.Key.Key_Up, Qt.Key.Key_Down):
            base_cursor = self.extra_cursors[-1] if self.extra_cursors else self.textCursor()
            new_cursor = QTextCursor(base_cursor)
            if e.key() == Qt.Key.Key_Down:
                moved = new_cursor.movePosition(QTextCursor.MoveOperation.Down)
            else:
                moved = new_cursor.movePosition(QTextCursor.MoveOperation.Up)

            if moved:
                self.extra_cursors.append(new_cursor)
                self.viewport().update()
            e.accept()
            return

        # 멀티 커서 활성화 시 타이핑 / 백스페이스 / Delete 동기화 처리
        if self.extra_cursors:
            all_cursors = [self.textCursor()] + self.extra_cursors
            pos_dict = {}
            for c in all_cursors:
                pos_dict[c.position()] = c
            all_cursors = list(pos_dict.values())
            all_cursors.sort(key=lambda c: c.position(), reverse=True)
            key_text = e.text()

            if e.key() == Qt.Key.Key_Backspace:
                self.textCursor().beginEditBlock()
                for c in all_cursors:
                    if c.hasSelection():
                        c.removeSelectedText()
                    else:
                        c.deletePreviousChar()
                self.textCursor().endEditBlock()
                self.setTextCursor(all_cursors[0])
                self.extra_cursors = all_cursors[1:]
                self.viewport().update()
                e.accept()
                return
            elif e.key() == Qt.Key.Key_Delete:
                self.textCursor().beginEditBlock()
                for c in all_cursors:
                    if c.hasSelection():
                        c.removeSelectedText()
                    else:
                        c.deleteChar()
                self.textCursor().endEditBlock()
                self.setTextCursor(all_cursors[0])
                self.extra_cursors = all_cursors[1:]
                self.viewport().update()
                e.accept()
                return
            elif key_text and (key_text.isprintable() or key_text in ('\r', '\n', '\t')):
                if not (has_ctrl and not (has_alt or has_shift)):
                    self.textCursor().beginEditBlock()
                    for c in all_cursors:
                        if c.hasSelection():
                            c.removeSelectedText()
                        c.insertText(key_text)
                    self.textCursor().endEditBlock()
                    self.setTextCursor(all_cursors[0])
                    self.extra_cursors = all_cursors[1:]
                    self.viewport().update()
                    e.accept()
                    return

        # VS Code 스타일 줄 상하 이동 (Alt+Up / Alt+Down)
        if (e.modifiers() == Qt.KeyboardModifier.AltModifier) and e.key() in (Qt.Key.Key_Up, Qt.Key.Key_Down):
            cursor = self.textCursor()
            block = cursor.block()
            if e.key() == Qt.Key.Key_Up and block.previous().isValid():
                cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
                cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
                line_text = cursor.selectedText()
                cursor.removeSelectedText()
                cursor.deletePreviousChar()
                cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
                cursor.insertText(line_text + "\n")
                cursor.movePosition(QTextCursor.MoveOperation.Up)
                self.setTextCursor(cursor)
            elif e.key() == Qt.Key.Key_Down and block.next().isValid():
                cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
                cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
                line_text = cursor.selectedText()
                cursor.removeSelectedText()
                cursor.deleteChar()
                cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock)
                cursor.insertText("\n" + line_text)
                self.setTextCursor(cursor)
            e.accept()
            return

        # 코드 메모 전용 IDE 고급 기능: 자동 괄호/따옴표/스마트 딜리트/지속적 스마트 들여쓰기
        if is_code:
            cursor = self.textCursor()
            key_text = e.text()

            # 1. 백스페이스(Backspace) 연결 괄호 쌍 동시 삭제
            if e.key() == Qt.Key.Key_Backspace and not cursor.hasSelection():
                pos = cursor.position()
                doc_text = self.toPlainText()
                if 0 < pos < len(doc_text):
                    prev_char = doc_text[pos - 1]
                    next_char = doc_text[pos]
                    pair_map = {'{': '}', '(': ')', '[': ']', '"': '"', "'": "'"}
                    if prev_char in pair_map and pair_map[prev_char] == next_char:
                        cursor.deletePreviousChar()
                        cursor.deleteChar()
                        self.setTextCursor(cursor)
                        e.accept()
                        return

            # 2. 닫는 괄호/따옴표 덮어쓰기 (Overtyping)
            if key_text in ('}', ')', ']', '"', "'") and not cursor.hasSelection():
                pos = cursor.position()
                doc_text = self.toPlainText()
                if pos < len(doc_text) and doc_text[pos] == key_text:
                    cursor.movePosition(QTextCursor.MoveOperation.Right)
                    self.setTextCursor(cursor)
                    e.accept()
                    return

            # 3. 여는 괄호/따옴표 자동 완성
            pair_map = {'{': '}', '(': ')', '[': ']', '"': '"', "'": "'"}
            if key_text in pair_map:
                closing = pair_map[key_text]
                if cursor.hasSelection():
                    sel = cursor.selectedText()
                    cursor.insertText(f"{key_text}{sel}{closing}")
                else:
                    cursor.insertText(f"{key_text}{closing}")
                    cursor.movePosition(QTextCursor.MoveOperation.Left)
                self.setTextCursor(cursor)
                e.accept()
                return

            # 4. 지속적인 스마트 엔터 들여쓰기 유지 (Auto-Indentation Level Maintenance)
            if e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                pos = cursor.position()
                doc_text = self.toPlainText()

                # (1) { | } 사이에서 Enter 누를 시 3줄 자동 형성 및 정밀 들여쓰기
                if 0 < pos < len(doc_text) and doc_text[pos - 1] in ('{', '[', '(') and doc_text[pos] in ('}', ']', ')'):
                    line_text = cursor.block().text()
                    indent_str = line_text[:len(line_text) - len(line_text.lstrip())]
                    cursor.insertText(f"\n{indent_str}    \n{indent_str}")
                    cursor.movePosition(QTextCursor.MoveOperation.Up)
                    cursor.movePosition(QTextCursor.MoveOperation.EndOfLine)
                    self.setTextCursor(cursor)
                    e.accept()
                    return

                # (2) 일반 엔터 누를 시 이전 줄의 들여쓰기(공백)를 지속 유지 + 여는 기호 수용
                line_text = cursor.block().text()
                indent_str = line_text[:len(line_text) - len(line_text.lstrip())]

                stripped_line = line_text[:cursor.positionInBlock()].rstrip()
                if stripped_line and stripped_line[-1] in ('{', '[', '(', ':'):
                    indent_str += "    "

                cursor.insertText(f"\n{indent_str}")
                self.setTextCursor(cursor)
                e.accept()
                return

        if e.key() == Qt.Key.Key_Backtab or (e.key() == Qt.Key.Key_Tab and e.modifiers() & Qt.KeyboardModifier.ShiftModifier):
            self.memo_window.apply_outdent()
            e.accept()
            return
        elif e.key() == Qt.Key.Key_Tab:
            self.memo_window.apply_indent()
            e.accept()
            return
        elif e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            cursor = self.textCursor()
            current_indent = cursor.blockFormat().indent()
            super().keyPressEvent(e)
            if current_indent > 0:
                new_cursor = self.textCursor()
                bf = new_cursor.blockFormat()
                bf.setIndent(current_indent)
                new_cursor.setBlockFormat(bf)
            return

        super().keyPressEvent(e)

    def paintEvent(self, event: Any) -> None:
        painter = QPainter(self.viewport())
        show_bg = self.memo_window.memo_data.get('show_line_bg', False)
        is_code = self.memo_window.memo_data.get('is_code_memo', False)

        if is_code:
            code_theme = self.memo_window.memo_data.get('code_theme', 'dark')
            is_dark_bg = (code_theme == "dark")
        else:
            bg_color = self.memo_window.memo_data.get('bg_color', '#FFFFFF')
            if bg_color == "random": bg_color = "#FFFFFF"
            is_dark_bg = True if bg_color in ['#2E3440', '#1C1C1E', '#000000'] else False
            if not is_dark_bg:
                c_obj = QColor(bg_color)
                if c_obj.isValid():
                    lum = (0.299 * c_obj.red() + 0.587 * c_obj.green() + 0.114 * c_obj.blue()) / 255.0
                    if lum < 0.5:
                        is_dark_bg = True

        grid_color = QColor(255, 255, 255, 45) if is_dark_bg else QColor(0, 0, 0, 45)
        indent_color = QColor(142, 142, 147, 100)
        scroll_y = self.verticalScrollBar().value()
        line_font = QFont(self.font().family(), self.memo_window.memo_data.get('font_size', 11))
        fm = QFontMetrics(line_font)
        line_height = fm.lineSpacing()

        if show_bg:
            painter.setPen(grid_color)
            block = self.document().begin()
            last_bottom = 0
            while block.isValid():
                block_bb = self.document().documentLayout().blockBoundingRect(block)
                pos_y = block_bb.top() - scroll_y
                line_bottom = int(pos_y + block_bb.height())
                if line_bottom > 0 and pos_y <= self.viewport().height():
                    painter.drawLine(0, line_bottom, self.viewport().width(), line_bottom)
                last_bottom = line_bottom
                block = block.next()

            y = last_bottom + line_height if last_bottom > 0 else int(line_height - (scroll_y % line_height))
            while y < self.viewport().height():
                painter.drawLine(0, y, self.viewport().width(), y)
                y += line_height


        painter.end()
        super().paintEvent(event)
        self.check_marks.paint()

    def wheelEvent(self, event: Any) -> None:
        modifiers = QApplication.keyboardModifiers()
        delta = event.angleDelta().y()
        if modifiers == Qt.KeyboardModifier.ControlModifier:
            current_size = self.memo_window.memo_data.get('font_size', 11)
            s = max(6, min(72, current_size + (1 if delta > 0 else -1)))
            f = self.font()
            f.setPointSize(s)
            self.setFont(f)
            cursor = self.textCursor()
            cursor.select(QTextCursor.SelectionType.Document)
            fmt = QTextCharFormat()
            # 크기만 바꿉니다. (글꼴 전체를 덮어쓰면 굵게·기울임·밑줄이 풀림)
            fmt.setFontPointSize(s)
            cursor.mergeCharFormat(fmt)
            self.memo_window.memo_data['font_size'] = s
            self.memo_window.apply_line_bg_style()
            self.update_line_number_area()
            # size_box에 신호 차단 후 조용히 동기화
            if hasattr(self.memo_window, 'size_box'):
                sb = self.memo_window.size_box
                sb.blockSignals(True)
                sb.setCurrentText(str(s))
                if sb.currentText() != str(s):  # 목록에 없는 값이면 직접 입력
                    sb.setEditText(str(s)) if sb.isEditable() else None
                sb.blockSignals(False)
            if hasattr(self.memo_window, '_wheel_save_timer'):
                self.memo_window._wheel_save_timer.start(1000)
            self.memo_window.show_toast(f"폰트 크기: {s}pt")
            event.accept()
            return
        elif modifiers == Qt.KeyboardModifier.ShiftModifier:
            op = max(0.3, min(1.0, self.memo_window.windowOpacity() + (0.05 if delta > 0 else -0.05)))
            self.memo_window.setWindowOpacity(op)
            self.memo_window.memo_data['opacity'] = op
            if hasattr(self.memo_window, '_wheel_save_timer'):
                self.memo_window._wheel_save_timer.start(1000)
            self.memo_window.show_toast(f"투명도: {int(op * 100)}%")
            event.accept()
            return
        super().wheelEvent(event)
