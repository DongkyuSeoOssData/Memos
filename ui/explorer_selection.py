"""메모 탐색기에서 여러 메모를 골라 한꺼번에 다루기.

체크 상자와 줄 선택, 고른 메모 지우기·복원하기, 휴지통 보기를 맡습니다. (MemoExplorerWindow 에 섞어 쓰는 부분)
"""
from ui.dialogs import ConflictDialog
from ui import themed_dialog
from typing import List, Dict, Any
from PyQt6.QtWidgets import QDialog
from PyQt6.QtCore import Qt


class ExplorerSelectionMixin:
    """탐색기의 고르기와 일괄 작업."""

    def sync_selection_and_checkboxes(self) -> None:
        """Ctrl·Shift 로 여러 줄을 고르면 그 줄들을 체크합니다.

        한 줄만 고른 경우(보통의 클릭)에는 체크를 건드리지 않습니다. 전에는 줄을 누를 때마다 다른 줄의 체크가
        풀려서, 체크 상자를 하나씩 눌러 여러 개를 고를 수가 없었습니다.
        """
        selected_rows = set(index.row() for index in self.table.selectedIndexes())
        if len(selected_rows) < 2:
            return
        for r in selected_rows:
            item_cb = self.table.item(r, 0)
            if item_cb:
                item_cb.setCheckState(Qt.CheckState.Checked)

    def _checked_memos(self) -> List[Dict[str, Any]]:
        out = []
        for r in range(self.table.rowCount()):
            item_cb, item = self.table.item(r, 0), self.table.item(r, 2)
            if item_cb and item and item_cb.checkState() == Qt.CheckState.Checked:
                out.append(item.data(Qt.ItemDataRole.UserRole))
        return out

    def _remember_checked(self) -> None:
        """지금 목록에 보이는 줄들의 체크 상태를 기억해 둡니다. (목록을 다시 그려도 유지되도록)"""
        for r in range(self.table.rowCount()):
            box, item = self.table.item(r, 0), self.table.item(r, 2)
            memo = item.data(Qt.ItemDataRole.UserRole) if item else None
            if not box or not memo or not memo.get('id'):
                continue
            if box.checkState() == Qt.CheckState.Checked:
                self._checked_ids.add(memo['id'])
            else:
                self._checked_ids.discard(memo['id'])

    def picked_memos(self) -> List[Dict[str, Any]]:
        """여러 개를 한꺼번에 다룰 때의 대상. 체크한 메모들이며, 체크한 것이 없으면 선택한 줄의 메모입니다. (목록 순서대로)"""
        checked = [r for r in range(self.table.rowCount())
                   if self.table.item(r, 0) and self.table.item(r, 0).checkState() == Qt.CheckState.Checked]
        rows = checked or sorted({index.row() for index in self.table.selectedIndexes()})
        picked: List[Dict[str, Any]] = []
        for r in rows:
            item = self.table.item(r, 2)
            m = item.data(Qt.ItemDataRole.UserRole) if item else None
            if m and all(m.get('id') != other.get('id') for other in picked):
                picked.append(m)
        return picked

    def del_checked(self) -> None:
        checked_memos = self.picked_memos()
        if not checked_memos:
            self.show_toast("지울 메모를 먼저 고르세요 (체크하거나 줄을 선택)", warn=True)
            return

        protected_memos = [m for m in checked_memos if m.get('is_protected')]
        if protected_memos:
            self.show_toast(f"🔒 {len(protected_memos)}개 메모가 삭제 방지 상태입니다.")
            checked_memos = [m for m in checked_memos if not m.get('is_protected')]

        # 어떤 메모가 지워지는지 제목으로 보여 줍니다. (예전에 체크해 둔 줄이 함께 지워지는 실수를 막기 위해)
        titles = [f"  • {str(m.get('title', '')) or '(제목 없음)'}" for m in checked_memos[:6]]
        if len(checked_memos) > 6:
            titles.append(f"  … 외 {len(checked_memos) - 6}개")
        question = f"선택한 {len(checked_memos)}개 메모를 휴지통으로 이동할까요?" + chr(10) + chr(10).join(titles)
        if checked_memos and themed_dialog.confirm(self, "일괄 삭제", question, ok_text="일괄 삭제", danger=True):
            self._checked_ids.difference_update(m.get('id') for m in checked_memos)
            deleted_ids = []
            for m in checked_memos:
                memo_id = m.get('id')
                if memo_id:
                    self.ui_manager.close_memo_window_by_id(memo_id, is_deleting=True)
                    self.ui_manager.sync_manager.delete_memo_locally(memo_id, title=m.get('title'))
                    deleted_ids.append(memo_id)
            self.ui_manager.sync_manager.delete_memos_cloud(deleted_ids)
            self.pv.clear()
            self.refresh()

    def res_checked(self) -> None:
        for r in range(self.table.rowCount()):
            if self.table.item(r, 0).checkState() == Qt.CheckState.Checked:
                m = self.table.item(r, 2).data(Qt.ItemDataRole.UserRole)
                memo_id = m.get('id')
                title = m.get('title', '')
                if memo_id:
                    ex = next((x for x in self.ui_manager.sync_manager.load_local_memos() if x.get('id') == memo_id), None)
                    # 암호 메모는 풀려 있더라도 견주는 창에 본문을 보이지 않습니다.
                    shown = lambda memo: ("🔒 암호 메모" if memo.get('is_locked') or memo.get('_locked') or memo.get('_unreadable')
                                          else memo.get('content', ''))
                    if not ex or ConflictDialog(title, shown(ex), shown(m), self).exec() == QDialog.DialogCode.Accepted:
                        self.ui_manager.sync_manager.restore_memo_locally(memo_id)
        self.pv.clear()
        self.refresh()

    def delete_single_memo(self, memo: Dict[str, Any]) -> None:
        if memo.get('is_protected'):
            self.show_toast("🔒 삭제 방지 설정된 메모입니다.")
            return
        memo_id = memo.get('id')
        if memo_id and themed_dialog.confirm(self, "삭제", f"'{memo.get('title','')}' 메모를 휴지통으로 이동할까요?", ok_text="삭제", danger=True):
            self.ui_manager.close_memo_window_by_id(memo_id, is_deleting=True)
            self.ui_manager.sync_manager.delete_memo_locally(memo_id, title=memo.get('title'))
            self.ui_manager.sync_manager.delete_memos_cloud([memo_id])
            self.pv.clear()
            self.refresh()

    def empty_trash(self) -> None:
        if themed_dialog.confirm(self, "휴지통 비우기", "휴지통의 모든 메모를 영구 삭제할까요? (복구 불가)", ok_text="휴지통 비우기", danger=True):
            cnt = self.ui_manager.sync_manager.empty_trash_locally()
            self.pv.clear()
            self.refresh()
            self.show_toast(f"🧹 휴지통의 메모 {cnt}개가 영구 삭제되었습니다.")

    def toggle_trash(self) -> None:
        self._remember_checked()
        self._checked_ids.clear()                # 목록과 휴지통은 서로 다른 메모들이므로 체크를 이어 가지 않음
        for r in range(self.table.rowCount()):
            if self.table.item(r, 0):
                self.table.item(r, 0).setCheckState(Qt.CheckState.Unchecked)
        self.is_trash_mode = self.t_btn.isChecked()
        self.t_btn.setText("목록으로 돌아가기" if self.is_trash_mode else "휴지통 보기")
        is_dark = self.ui_manager.sync_manager.settings.get('app_theme', 'white') == "dark"
        icon_name = "total.svg" if self.is_trash_mode else "trashbucket.svg"
        self.t_btn.setIcon(self.ui_manager.get_theme_icon(icon_name, is_dark))
        self.pv.setReadOnly(self.is_trash_mode)
        self.pv.clear()
        self.current_page = 1
        self.refresh()

    def on_header_click(self, idx: int) -> None:
        if idx == 0:
            all_c = all(self.table.item(r, 0).checkState() == Qt.CheckState.Checked for r in range(self.table.rowCount()))
            ns = Qt.CheckState.Unchecked if all_c else Qt.CheckState.Checked
            for r in range(self.table.rowCount()):
                self.table.item(r, 0).setCheckState(ns)
