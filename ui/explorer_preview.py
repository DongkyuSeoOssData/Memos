"""메모 탐색기의 미리보기.

목록에서 고른 메모를 아래 칸에 보여 주고, 그 자리에서 고친 내용을 저장합니다. 체크 상자 누르기(서식이 있는 메모는
서식을 지킨 채), 우클릭 메뉴도 여기서 합니다. (MemoExplorerWindow 에 섞어 쓰는 부분)
"""
from core import reminders
from ui import checklist
from ui import modern_style
import datetime
from typing import List, Dict, Any, Optional
from PyQt6.QtWidgets import QMenu
from PyQt6.QtCore import QEvent, Qt, QPoint
from PyQt6.QtGui import QTextCursor, QTextDocument
from utils.text_utils import clean_plain_text, is_html_content


class ExplorerPreviewMixin:
    """탐색기의 미리보기."""

    def on_cell_click(self, r: int, c: int) -> None:
        """셀 클릭 시 미리보기 업데이트 — 코드 메모는 D2Coding 폰트 적용."""
        m_item = self.table.item(r, 2)
        if m_item:
            m = m_item.data(Qt.ItemDataRole.UserRole)
            if m:
                self._flush_preview_save()
                self._is_loading_preview = True
                sealed = bool(m.get('_locked') or m.get('_unreadable'))
                # 창에 아직 저장되지 않은 입력이 있으면 먼저 저장하고 그 내용을 보여줍니다.
                w = self.ui_manager.memo_windows.get(m.get('id', ''))
                if w and not sealed and not w.is_sealed():
                    w.flush_auto_save()
                    # 저장하면서 목록이 새로 그려지면 줄 선택이 풀립니다. 같은 메모를 다시 골라 두어야
                    # 이어서 미리보기에서 고친 내용이 이 메모에 저장됩니다.
                    m = self._reselect_memo(m)
                    m['content'] = w.memo_data.get('content', m.get('content', ''))
                content = m.get('content', '')
                if m.get('_locked'):
                    clean_text = "🔒 암호 메모입니다. 메모를 열어 암호를 입력하면 볼 수 있습니다."
                elif m.get('_unreadable'):
                    clean_text = "⚠ 본문을 복호화할 수 없는 메모입니다."
                else:
                    clean_text = clean_plain_text(content)
                self.pv.setReadOnly(self.is_trash_mode or sealed)
                self.pv.setPlainText(clean_text)
                self._is_loading_preview = False

    # ── 미리보기 우클릭 메뉴: 지금 보고 있는 본문에 하는 일만 둡니다 ──────────────
    def _preview_memo(self) -> Optional[Dict[str, Any]]:
        item = self.table.item(self.table.currentRow(), 2) if self.table.currentRow() >= 0 else None
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def preview_menu_actions(self) -> List[tuple]:
        """미리보기 우클릭 메뉴의 항목들. [(글자, 동작, 쓸 수 있는지)] — 글자가 None 이면 구분선."""
        m = self._preview_memo()
        if not m:
            return []
        pv = self.pv
        has_selection = pv.textCursor().hasSelection()
        copy_part = ("복사", pv.copy, has_selection)
        copy_all = ("전체 내용 복사", lambda: self.copy_memo_text(m), not (m.get('_locked') or m.get('_unreadable')))
        if self.is_trash_mode:
            return [copy_part, copy_all]
        if m.get('_locked'):
            return [("🔓 잠금 해제 (암호 입력)", lambda: self._lock_action(m, "prompt_unlock"), True)]
        if m.get('_unreadable'):
            return []
        has_reminder = bool(reminders.normalize(m.get('reminder')))
        return [
            ("메모 열기", lambda: self.ui_manager.show_specific_memo(m.get('id')), True),
            (None, None, False),
            ("체크리스트 켜기/끄기", self.toggle_preview_checklist, not pv.isReadOnly()),
            (None, None, False),
            copy_part,
            ("붙여넣기", pv.paste, not pv.isReadOnly() and pv.canPaste()),
            ("모두 선택", pv.selectAll, bool(pv.toPlainText())),
            copy_all,
            (None, None, False),
            ("⏰ 알림 바꾸기…" if has_reminder else "⏰ 알림 설정…", lambda: self.edit_reminder(m), True),
            ("이전 내용 보기…", lambda: self.show_history(m), True),
        ]

    def show_preview_menu(self, pos: QPoint) -> None:
        actions = self.preview_menu_actions()
        if not actions:
            return
        menu = QMenu(self)
        menu.setStyleSheet(modern_style.menu_qss(self.ui_manager.sync_manager.settings))
        for text, action, enabled in actions:
            if text is None:
                menu.addSeparator()
                continue
            entry = menu.addAction(text)
            entry.setEnabled(enabled)
            entry.triggered.connect(lambda checked=False, run=action: run())
        menu.exec(self.pv.viewport().mapToGlobal(pos))

    def toggle_preview_checklist(self) -> None:
        """미리보기에서 커서가 있는 줄(여러 줄을 골랐으면 그 줄들)에 체크 상자를 붙이거나 뗍니다."""
        pv = self.pv
        if pv.isReadOnly():
            return
        cursor = pv.textCursor()
        document = pv.document()
        first = document.findBlock(cursor.selectionStart())
        last = document.findBlock(cursor.selectionEnd())
        blocks = []
        block = first
        while block.isValid():
            blocks.append(block)
            if block == last:
                break
            block = block.next()
        new_lines = checklist.toggle_boxes([b.text() for b in blocks])
        cursor.beginEditBlock()
        for block, new_text in zip(blocks, new_lines):
            if block.text() != new_text:
                edit = QTextCursor(block)
                edit.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
                edit.insertText(new_text)
        cursor.endEditBlock()

    def _reselect_memo(self, memo: Dict[str, Any]) -> Dict[str, Any]:
        """목록에서 memo 와 같은 메모의 줄을 (신호 없이) 다시 고르고, 그 줄이 들고 있는 메모 데이터를 돌려줍니다."""
        memo_id = memo.get('id')
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 2)
            data = item.data(Qt.ItemDataRole.UserRole) if item else None
            if data and data.get('id') == memo_id:
                if self.table.currentRow() != row:
                    self.table.blockSignals(True)
                    self.table.setCurrentCell(row, 2)
                    self.table.blockSignals(False)
                return data
        return memo

    def _preview_check_colors(self) -> Dict[str, Any]:
        return modern_style.check_colors(modern_style.app_colors(self.ui_manager.sync_manager.settings))

    def eventFilter(self, obj: Any, event: Any) -> bool:
        if obj is getattr(self, 'pv', None) and event.type() == QEvent.Type.FocusIn:
            self._save_window_typing_first()
        return super().eventFilter(obj, event)

    def _save_window_typing_first(self) -> None:
        """미리보기에서 고치기 시작할 때, 같은 메모의 창에서 쓰고 아직 저장되지 않은 글을 먼저 저장합니다.

        미리보기는 저장된 내용을 보여 주므로, 그대로 고치면 창에서 쓰던 글을 예전 내용으로 덮어 버립니다.
        저장하면 목록이 다시 그려지면서 미리보기도 방금 쓴 글로 바뀝니다.
        """
        m = self._preview_memo()
        w = self.ui_manager.memo_windows.get(m.get('id', '')) if m else None
        if w is not None and w._auto_save_timer.isActive():
            self.on_cell_click(self.table.currentRow(), 2)       # 창의 글을 저장하고 미리보기를 다시 채움

    def on_preview_changed(self) -> None:
        if self._is_loading_preview or self.is_trash_mode:
            return
        r = self.table.currentRow()
        if r < 0:
            return
        m_item = self.table.item(r, 2)
        if m_item:
            m = m_item.data(Qt.ItemDataRole.UserRole)
            if not m: return
            if m.get('_locked') or m.get('_unreadable') or self.pv.isReadOnly():
                return
            new_content = self.pv.toPlainText()
            if new_content == clean_plain_text(m.get('content', '')):
                return                      # 글자가 그대로면 수정이 아님
            if is_html_content(m.get('content', '')):
                # 미리보기는 글자만 다루므로, 서식이 있는 메모를 여기서 고치면 서식이 사라집니다. 그 사실을 알립니다.
                self.show_toast("서식이 있는 메모라 글자만 저장했습니다 (이전 내용 보기로 되돌릴 수 있음)", warn=True)
            self._commit_preview_content(m, new_content, r)

    def _commit_preview_content(self, m: Dict[str, Any], new_content: str, row: int) -> None:
        """미리보기에서 고친 본문을 메모에 반영합니다. (잠시 뒤 저장, 열려 있는 메모 창과 목록의 수정일시도 맞춤)"""
        memo_id = m.get('id', '')
        m['content'] = new_content
        m['updated_at'] = datetime.datetime.now().isoformat()

        if self._pending_preview_memo is not None and self._pending_preview_memo is not m:
            self._flush_preview_save()
        self._pending_preview_memo = m
        self._preview_save_timer.start()

        if memo_id in self.ui_manager.memo_windows:
            w = self.ui_manager.memo_windows[memo_id]
            w._is_updating_from_explorer = True
            if is_html_content(new_content):
                w.text_edit.setHtml(new_content)
            else:
                w.text_edit.setPlainText(new_content)
            w._is_updating_from_explorer = False
            # 창이 들고 있는 데이터도 맞춰 두어야, 창이 나중에 저장할 때 미리보기 편집을 되돌리지 않습니다.
            w.memo_data['content'] = new_content
            w.memo_data['updated_at'] = m['updated_at']
            # 미리보기에서의 입력도 '마지막 입력'으로 보고 자동 잠금 시간을 다시 셉니다.
            w.restart_relock_timer()

        if self.table.item(row, 3):
            self.table.item(row, 3).setText(datetime.datetime.now().strftime("%y.%m.%d %H:%M"))      # 목록과 같은 표기

    def _toggle_preview_box_keeping_format(self, block: Any) -> bool:
        """미리보기에서 체크 상자를 눌렀을 때: 서식이 있는 메모면 서식을 지킨 채 그 상자만 바꿉니다.

        처리했으면 True. 서식이 없는 메모는 False 를 돌려주어 보통대로(글자를 바꾸는 방식으로) 처리되게 합니다.
        """
        m = self._preview_memo()
        row = self.table.currentRow()
        content = m.get('content', '') if m else ''
        if not m or not isinstance(content, str) or not is_html_content(content):
            return False
        # 미리보기의 몇 번째 체크리스트 줄인지 세고, 원본 문서에서 같은 번째 줄을 찾습니다.
        order, probe = 0, self.pv.document().begin()
        while probe.isValid() and probe != block:
            order += checklist.box_index(probe.text()) >= 0
            probe = probe.next()
        document = QTextDocument()
        document.setHtml(content)
        target, seen, source = None, 0, document.begin()
        while source.isValid():
            if checklist.box_index(source.text()) >= 0:
                if seen == order:
                    target = source
                    break
                seen += 1
            source = source.next()
        if target is None or target.text().strip() != block.text().strip():
            # 줄이 서로 맞지 않으면(목록 안의 체크 상자 등) 엉뚱한 줄을 바꾸지 않습니다.
            self.show_toast("이 줄은 메모를 열어서 체크하세요 (서식이 있는 메모)", warn=True)
            return True
        index = checklist.box_index(target.text())
        flipped = checklist.CHECKED if target.text()[index] == checklist.UNCHECKED else checklist.UNCHECKED
        edit = QTextCursor(target)
        edit.setPosition(target.position() + index)
        edit.setPosition(target.position() + index + 1, QTextCursor.MoveMode.KeepAnchor)
        edit.insertText(flipped)
        # 미리보기의 글자도 같이 바꾸되, 이것을 '미리보기에서 고침'(글자만 저장)으로 처리하지 않게 합니다.
        self._is_loading_preview = True
        try:
            shown = QTextCursor(block)
            at = checklist.box_index(block.text())
            shown.setPosition(block.position() + at)
            shown.setPosition(block.position() + at + 1, QTextCursor.MoveMode.KeepAnchor)
            shown.insertText(flipped)
        finally:
            self._is_loading_preview = False
        self._commit_preview_content(m, document.toHtml(), row)
        return True

    def _flush_preview_save(self) -> None:
        self._preview_save_timer.stop()
        m = self._pending_preview_memo
        self._pending_preview_memo = None
        if m is not None:
            sm = self.ui_manager.sync_manager
            if not (sm.save_memo_locally(m) or sm.is_blank_draft(m)):
                # 저장하지 못했으면 알리고, 그사이 다른 메모를 고치기 시작하지 않았다면 조금 뒤에 다시 시도합니다.
                self.show_toast("미리보기에서 고친 내용을 저장하지 못했습니다 · 메모 폴더를 확인하세요", warn=True)
                if self._pending_preview_memo is None:
                    self._pending_preview_memo = m
                    self._preview_save_timer.start()
