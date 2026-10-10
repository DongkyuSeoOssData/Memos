"""메모 창의 서식 기능 (굵게·글꼴·색, 목록·들여쓰기, 저장할 본문 형식)."""
from typing import Any

from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtGui import QColor, QFont, QTextCharFormat, QTextCursor, QTextListFormat
from PyQt6.QtWidgets import QColorDialog, QMenu

from ui import checklist, modern_style


class MemoFormatMixin:
    """MemoWindow 에 섞어 쓰는 서식 기능. (memo_data, text_edit, 서식 버튼 등은 MemoWindow 의 것)"""

    MAX_INDENT = 8

    def update_toolbar_button_states(self) -> None:
        fmt = self.text_edit.currentCharFormat()
        self.btn_bold.setChecked(fmt.fontWeight() == QFont.Weight.Bold)
        self.btn_italic.setChecked(fmt.fontItalic())
        self.btn_underline.setChecked(fmt.fontUnderline())
        modern_style.apply_memo_toolbar(self)

    def show_bg_color_menu(self) -> None:
        menu = QMenu(self)
        menu.setStyleSheet(modern_style.menu_qss(self.memo_window_get_settings()))

        menu.addAction("❌ 배경색 없음 (투명)").triggered.connect(lambda: self.set_text_bg_color(QColor(0, 0, 0, 0)))
        menu.addSeparator()

        highlights = {
            "🟡 노란색 형광펜": "#FEF08A",
            "🟢 연두색 형광펜": "#BBF7D0",
            "🔵 하늘색 형광펜": "#BAE6FD",
            "🩷 분홍색 형광펜": "#FBCFE8"
        }
        for name, hex_code in highlights.items():
            menu.addAction(name).triggered.connect(lambda checked, c=hex_code: self.set_text_bg_color(QColor(c)))

        menu.addSeparator()
        menu.addAction("사용자 지정 RGB 색상...").triggered.connect(self.choose_bg_color)
        menu.exec(self.btn_bg_color.mapToGlobal(QPoint(0, self.btn_bg_color.height())))

    def set_text_bg_color(self, color: QColor) -> None:
        fmt = self.text_edit.currentCharFormat()
        fmt.setBackground(color)
        self.text_edit.mergeCurrentCharFormat(fmt)
        self._mark_edited()

    def toggle_bold(self) -> None:
        fmt = self.text_edit.currentCharFormat()
        is_bold = fmt.fontWeight() == QFont.Weight.Bold
        fmt.setFontWeight(QFont.Weight.Normal if is_bold else QFont.Weight.Bold)
        self.text_edit.mergeCurrentCharFormat(fmt)
        self.update_toolbar_button_states()
        self._mark_edited()

    def toggle_italic(self) -> None:
        fmt = self.text_edit.currentCharFormat()
        fmt.setFontItalic(not fmt.fontItalic())
        self.text_edit.mergeCurrentCharFormat(fmt)
        self.update_toolbar_button_states()
        self._mark_edited()

    def toggle_underline(self) -> None:
        fmt = self.text_edit.currentCharFormat()
        fmt.setFontUnderline(not fmt.fontUnderline())
        self.text_edit.mergeCurrentCharFormat(fmt)
        self.update_toolbar_button_states()
        self._mark_edited()

    def change_font_family(self, font: QFont) -> None:
        cursor = self.text_edit.textCursor()
        whole_memo = not cursor.hasSelection()
        if whole_memo:
            cursor.select(QTextCursor.SelectionType.Document)
        fmt = QTextCharFormat()
        fmt.setFontFamilies([font.family()])
        cursor.mergeCharFormat(fmt)
        self.text_edit.mergeCurrentCharFormat(fmt)
        if whole_memo:
            # 선택 없이 바꾼 경우에만 이 메모의 기본 글꼴로 기억합니다.
            self.text_edit.setFont(font)
            self.memo_data['font_family'] = font.family()
        self._mark_edited()

    def change_font_size(self, size_str: str) -> None:
        if not size_str.isdigit(): return
        sz = int(size_str)
        # 전체 문서에 폰트 크기 적용
        font_family = self.memo_data.get('font_family', 'D2Coding')
        f = QFont(font_family, sz)
        self.text_edit.setFont(f)
        cursor = self.text_edit.textCursor()
        cursor.select(QTextCursor.SelectionType.Document)
        fmt = QTextCharFormat()
        # 크기만 바꿉니다. (글꼴 전체를 덮어쓰면 굵게·기울임·밑줄이 풀림)
        fmt.setFontPointSize(sz)
        cursor.mergeCharFormat(fmt)
        self.memo_data['font_size'] = sz
        # 스타일시트·행번호 동기화
        self.apply_line_bg_style()
        self.text_edit.update_line_number_area()
        self._schedule_auto_save()

    def choose_fg_color(self) -> None:
        color = QColorDialog.getColor(Qt.GlobalColor.black, self, "글씨색 선택")
        if color.isValid():
            cursor = self.text_edit.textCursor()
            fmt = QTextCharFormat()
            fmt.setForeground(color)
            if cursor.hasSelection():
                cursor.mergeCharFormat(fmt)
            else:
                self.text_edit.mergeCurrentCharFormat(fmt)

            self._mark_edited()

    def choose_bg_color(self) -> None:
        colors = ["#FFFF00", "#00FF00", "#00FFFF", "#FF00FF", "transparent"]
        cur = getattr(self, '_current_bg_idx', -1)
        cur = (cur + 1) % len(colors)
        self._current_bg_idx = cur
        if colors[cur] == "transparent":
            color = QColor(0, 0, 0, 0)
        else:
            color = QColor(colors[cur])
        self.set_text_bg_color(color)

    def current_content(self) -> str:
        """저장할 본문. 코드 메모와 서식 없는 메모는 순수 텍스트, 서식이 있는 메모만 HTML 입니다."""
        if self.memo_data.get('is_code_memo', False):
            # 예전 방식(문단 들여쓰기)으로 들여 쓴 줄은 공백 4칸으로 풀어서 저장
            lines = []
            block = self.text_edit.document().begin()
            while block.isValid():
                lines.append("    " * block.blockFormat().indent() + block.text())
                block = block.next()
            return chr(10).join(lines)
        return self.text_edit.toHtml() if self._has_rich_formatting() else self.text_edit.toPlainText()

    def _has_rich_formatting(self) -> bool:
        """본문에 순수 텍스트로는 표현할 수 없는 서식이 있는지 확인합니다. (애매하면 있다고 봄)"""
        doc = self.text_edit.document()
        if doc.rootFrame().childFrames():
            return True
        try:
            base_size = float(self.memo_data.get('font_size', 11))
        except (TypeError, ValueError):
            base_size = 11.0
        base_families = {self.memo_data.get('font_family') or 'D2Coding', self.text_edit.font().family(), 'D2Coding'}
        default_colors = {"#000000", "#1c1c1e", "#333333", "#ffffff", "#f2f2f7", "#cccccc",
                          QColor(self._memo_theme_palette()['text']).name().lower()}
        non_left = Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignJustify
        block = doc.begin()
        while block.isValid():
            bf = block.blockFormat()
            if block.textList() is not None or bf.indent() > 0 or (bf.alignment() & non_left):
                return True
            it = block.begin()
            while not it.atEnd():
                f = it.fragment().charFormat()
                if f.isImageFormat() or f.isAnchor():
                    return True
                if f.fontWeight() >= 600 or f.fontItalic() or f.fontUnderline() or f.fontStrikeOut():
                    return True
                if f.background().style() != Qt.BrushStyle.NoBrush and f.background().color().alpha() > 0:
                    return True
                if f.hasProperty(QTextCharFormat.Property.ForegroundBrush) and f.foreground().color().name().lower() not in default_colors:
                    return True
                if f.hasProperty(QTextCharFormat.Property.FontPointSize) and abs(f.fontPointSize() - base_size) > 0.01:
                    return True
                families = f.fontFamilies() or []
                if isinstance(families, str):
                    families = [families]
                if families and families[0] not in base_families:
                    return True
                it += 1
            block = block.next()
        return False

    def _selected_blocks(self) -> list:
        """선택 영역(없으면 커서)이 걸친 문단들."""
        cursor = self.text_edit.textCursor()
        doc = self.text_edit.document()
        block = doc.findBlock(cursor.selectionStart())
        end = doc.findBlock(cursor.selectionEnd())
        # 선택이 다음 줄 맨 앞에서 끝났다면 그 줄은 포함하지 않습니다.
        if cursor.hasSelection() and end != block and end.position() == cursor.selectionEnd():
            end = end.previous()
        blocks = []
        while block.isValid():
            blocks.append(block)
            if block == end:
                break
            block = block.next()
        return blocks

    def _find_sibling_list(self, block: Any, style: Any, indent: int) -> Any:
        """block 위·아래로 이어진 목록 중 같은 종류·같은 단계의 목록을 찾습니다. (번호가 이어지도록 합치기 위함)"""
        for step in ("previous", "next"):
            other = getattr(block, step)()
            while other.isValid():
                lst = other.textList()
                if lst is None:
                    break
                level = lst.format().indent()
                if level == indent and lst.format().style() == style:
                    return lst
                if level < indent:
                    break
                other = getattr(other, step)()
        return None

    def _put_blocks_in_list(self, blocks: list, style: Any, indent: int) -> None:
        target = self._find_sibling_list(blocks[0], style, indent) or self._find_sibling_list(blocks[-1], style, indent)
        if target is None:
            fmt = QTextListFormat()
            fmt.setStyle(style)
            fmt.setIndent(indent)
            target = QTextCursor(blocks[0]).createList(fmt)
        for block in blocks:
            if target.itemNumber(block) < 0:
                target.add(block)
            bf = block.blockFormat()
            if bf.indent() != 0:
                # 목록의 단계가 들여쓰기를 대신하므로 문단 들여쓰기는 지웁니다. (이중으로 밀리는 것 방지)
                bf.setIndent(0)
                QTextCursor(block).setBlockFormat(bf)

    def _toggle_list(self, style: Any) -> None:
        """선택한 줄들만 목록으로 만들거나(이미 그 목록이면) 해제합니다."""
        blocks = self._selected_blocks()
        if not blocks:
            return

        def in_style(block: Any) -> bool:
            lst = block.textList()
            return lst is not None and lst.format().style() == style

        edit_cursor = self.text_edit.textCursor()
        edit_cursor.beginEditBlock()
        if all(in_style(b) for b in blocks):
            for block in blocks:
                lst = block.textList()
                bf = block.blockFormat()
                bf.setObjectIndex(-1)
                lst.remove(block)
                QTextCursor(block).setBlockFormat(bf)
        else:
            current = blocks[0].textList()
            indent = current.format().indent() if current is not None else max(1, blocks[0].blockFormat().indent())
            self._put_blocks_in_list(blocks, style, indent)
        edit_cursor.endEditBlock()
        self.update_toolbar_button_states()
        self._mark_edited()

    def apply_bullet(self) -> None:
        self._toggle_list(QTextListFormat.Style.ListDisc)

    def apply_number(self) -> None:
        self._toggle_list(QTextListFormat.Style.ListDecimal)

    def toggle_checklist(self) -> None:
        """선택한 줄들 앞에 체크 상자(☐)를 붙이거나 뗍니다. 모두 체크리스트 줄이면 떼고, 아니면 없는 줄에 붙입니다."""
        if self.is_sealed():
            return
        blocks = self._selected_blocks()
        if not blocks:
            return
        new_lines = checklist.toggle_boxes([b.text() for b in blocks])
        cursor = self.text_edit.textCursor()
        cursor.beginEditBlock()
        for block, new_text in zip(blocks, new_lines):
            if block.text() == new_text:
                continue
            # 줄 전체를 바꾸면 굵게·색 같은 서식이 사라지므로, 상자 글자만 넣거나 뺍니다.
            index = checklist.box_index(block.text())
            edit = QTextCursor(block)
            if index >= 0:
                edit.setPosition(block.position() + index)
                edit.setPosition(block.position() + index + len(block.text()) - len(new_text), QTextCursor.MoveMode.KeepAnchor)
                edit.removeSelectedText()
            else:
                indent = len(block.text()) - len(block.text().lstrip(" \t"))
                edit.setPosition(block.position() + indent)
                edit.insertText(checklist.UNCHECKED + " ")
        cursor.endEditBlock()
        self._mark_edited()

    def apply_indent(self) -> None:
        self._shift_indent(1)

    def apply_outdent(self) -> None:
        self._shift_indent(-1)

    def _shift_indent(self, delta: int) -> None:
        """선택한 줄마다 한 단계씩 들여쓰거나 내어 씁니다. 목록 항목은 하위/상위 목록으로 옮깁니다."""
        if self.memo_data.get('is_code_memo', False):
            self.text_edit.shift_code_indent(delta)
            self._mark_edited()
            return
        changed = False
        edit_cursor = self.text_edit.textCursor()
        edit_cursor.beginEditBlock()
        for block in self._selected_blocks():
            lst = block.textList()
            if lst is not None:
                level = lst.format().indent() + delta
                if 1 <= level <= self.MAX_INDENT:
                    self._put_blocks_in_list([block], lst.format().style(), level)
                    changed = True
            else:
                bf = block.blockFormat()
                level = bf.indent() + delta
                if 0 <= level <= self.MAX_INDENT:
                    bf.setIndent(level)
                    QTextCursor(block).setBlockFormat(bf)
                    changed = True
        edit_cursor.endEditBlock()
        if changed:
            self.update_toolbar_button_states()
            self._mark_edited()
