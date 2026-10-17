"""메모 탐색기의 미리보기.

목록에서 고른 메모의 본문을 아래 칸에 보여 줍니다. 읽기만 하는 칸입니다. 고치기·체크 상자 누르기는 메모 창에서 하고,
여기서는 글자를 골라 복사하거나 본문 전체를 복사하는 것만 합니다. (MemoExplorerWindow 에 섞어 쓰는 부분)
"""
from ui import modern_style
from typing import List, Dict, Any, Optional
from PyQt6.QtWidgets import QMenu
from PyQt6.QtCore import Qt, QPoint
from utils.text_utils import clean_plain_text


class ExplorerPreviewMixin:
    """탐색기의 미리보기."""

    def on_cell_click(self, r: int, c: int) -> None:
        """줄을 고르면 그 메모의 본문을 미리보기에 보여 줍니다."""
        m_item = self.table.item(r, 2)
        if not m_item:
            return
        m = m_item.data(Qt.ItemDataRole.UserRole)
        if not m:
            return
        # 암호 메모는 풀려 있는 동안에도 미리보기에 본문을 보이지 않습니다. (메모 창에서만 봄)
        sealed = bool(m.get('is_locked') or m.get('_locked') or m.get('_unreadable'))
        content = m.get('content', '')
        # 창에 아직 저장되지 않은 입력이 있으면 먼저 저장하고 그 내용을 보여 줍니다.
        w = self.ui_manager.memo_windows.get(m.get('id', ''))
        if w and not sealed and not w.is_sealed():
            w.flush_auto_save()
            # 저장하면서 목록이 새로 그려지면 줄 선택이 풀리므로 같은 메모를 다시 골라 둡니다.
            self._reselect_memo(m)
            content = w.memo_data.get('content', content)
        if m.get('_unreadable'):
            text = "⚠ 본문을 복호화할 수 없는 메모입니다."
        elif m.get('is_locked') or m.get('_locked'):
            text = "🔒 암호 메모입니다. 메모를 열어 암호를 입력하면 볼 수 있습니다."
        else:
            text = clean_plain_text(content)
        self.pv.setPlainText(text)
        self._previewed_id = m.get('id')                  # 복사 버튼·우클릭은 지금 보이는 이 메모를 복사함

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

    # ── 미리보기 우클릭 메뉴: 복사만 ──────────────────────────────────────────────
    def _preview_memo(self) -> Optional[Dict[str, Any]]:
        """미리보기에 보이는 메모. (쪽을 넘겨 그 줄이 목록에 안 보여도 같은 메모, 지워졌거나 미리보기를 비웠으면 None)"""
        memo_id = getattr(self, '_previewed_id', None)
        if not memo_id or not self.pv.toPlainText():
            return None
        return next((m for m in self.filtered_memos if m.get('id') == memo_id), None)

    def preview_menu_actions(self) -> List[tuple]:
        """미리보기 우클릭 메뉴의 항목들. [(글자, 동작, 쓸 수 있는지)]"""
        m = self._preview_memo()
        if not m:
            return []
        sealed = m.get('is_locked') or m.get('_locked') or m.get('_unreadable')
        return [
            ("복사", self.pv.copy, self.pv.textCursor().hasSelection()),
            ("전체 내용 복사", lambda: self.copy_memo_text(m), not sealed),
        ]

    def copy_preview(self) -> None:
        """미리보기 옆의 복사 버튼: 고른 메모의 본문 전체를 클립보드에 넣습니다."""
        m = self._preview_memo()
        if not m:
            self.show_toast("복사할 메모를 먼저 고르세요", warn=True)
            return
        self.copy_memo_text(m)

    def show_preview_menu(self, pos: QPoint) -> None:
        actions = self.preview_menu_actions()
        if not actions:
            return
        menu = QMenu(self)
        menu.setStyleSheet(modern_style.menu_qss(self.ui_manager.sync_manager.settings))
        for text, action, enabled in actions:
            entry = menu.addAction(text)
            entry.setEnabled(enabled)
            entry.triggered.connect(lambda checked=False, run=action: run())
        menu.exec(self.pv.viewport().mapToGlobal(pos))
