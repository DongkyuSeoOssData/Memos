"""탐색기: 너비와 위치, 여러 메모 고르기와 삭제, 미리보기."""
import unittest
from unittest import mock

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QTextCursor
from PyQt6.QtTest import QTest

# support 를 먼저 가져와야 합니다. (offscreen 설정과 프로젝트 경로)
import support


class ExplorerWidthTest(support.UiTestCase):
    """폴더 이름이 길거나 폴더가 많아도 탐색기를 강제로 넓히지 않습니다."""

    def test_folder_ui_never_widens_the_explorer(self) -> None:
        names = ["업무", "업무/아주아주긴하위폴더이름입니다", "개인", "이름이정말정말정말긴폴더"] + [f"폴더{i}" for i in range(12)]
        self.sm.save_settings({"folders": names, "folder_sidebar_open": False})
        ex = self.explorer()
        ex.resize(ex.MIN_WIDTH, ex.height())
        support.app.processEvents()
        for mode in ("tabs", "dropdown", "sidebar"):
            self.sm.save_settings({"folder_ui": mode})
            for folder in ("", "업무", "업무/아주아주긴하위폴더이름입니다", "이름이정말정말정말긴폴더"):
                ex.current_folder = folder
                ex.refresh()
                support.app.processEvents()
                self.assertEqual((ex.width(), ex.minimumWidth()), (ex.MIN_WIDTH, ex.MIN_WIDTH), (mode, folder))
                # 왼쪽 묶음(폴더 버튼/드롭다운 + 라이트·다크 버튼)이 가운데의 'Memos' 를 넘지 않음
                if mode != "tabs":
                    left_end = ex.btn_app_theme.mapTo(ex, ex.btn_app_theme.rect().topRight()).x()
                    title_start = ex.title_label.mapTo(ex, ex.title_label.rect().topLeft()).x()
                    self.assertLessEqual(left_end, title_start, (mode, folder))

    def test_dropdown_is_as_wide_as_the_sidebar_button(self) -> None:
        self.sm.save_settings({"folders": ["이름이정말정말정말긴폴더"], "folder_ui": "dropdown"})
        ex = self.explorer()
        ex.current_folder = "이름이정말정말정말긴폴더"
        ex.refresh()
        self.assertEqual(ex.folder_combo.width(), ex.btn_folder.width())
        self.assertTrue(ex.folder_combo.toolTip().startswith("이름이정말정말정말긴폴더"))


class ExplorerPositionTest(support.UiTestCase):
    """탐색기의 위치는 옆에 덧붙은 영역을 뺀 본래 영역의 것으로 기억합니다."""

    # ── 9. 왼쪽에 붙은 사이드바가 탐색기 위치로 저장되지 않음 ──
    def test_saved_explorer_position_ignores_the_left_sidebar(self) -> None:
        self.sm.save_settings({"folder_ui": "sidebar", "folder_sidebar_open": True})
        ex = self.explorer()
        ex.move(900, 200)
        ex.refresh()
        support.app.processEvents()
        self.assertGreater(ex._sidebar_extra, 0)
        self.assertEqual(ex.content_x(), ex.x() + ex._sidebar_extra)
        self.ui.open_settings()
        self.ui.settings_window.save()
        self.assertEqual(self.sm.settings["explorer_geom"][0], ex.content_x())


class ExplorerSelectionTest(support.UiTestCase):
    """여러 메모를 고르고 한꺼번에 지웁니다."""

    def ids(self) -> list:
        return sorted(m["id"] for m in self.sm.load_local_memos())

    def test_delete_button_removes_every_selected_row(self) -> None:
        ex = self.explorer()
        ex.table.clearSelection()
        for memo_id in ("memo-0000", "memo-0002"):                   # Ctrl 로 두 줄을 고른 것처럼
            row = self.row_of(ex, memo_id)
            for col in range(ex.table.columnCount()):
                if ex.table.item(row, col):
                    ex.table.item(row, col).setSelected(True)
        self.assertEqual(sorted(m["id"] for m in ex.picked_memos()), ["memo-0000", "memo-0002"])
        ex.b_del.click()
        self.assertEqual(self.ids(), ["memo-0001"])

    def test_boxes_can_be_checked_one_by_one(self) -> None:
        ex = self.explorer()
        ex.table.clearSelection()
        for memo_id in ("memo-0000", "memo-0002"):                   # 체크 상자를 하나씩 누름 (누른 줄이 선택되면서)
            row = self.row_of(ex, memo_id)
            ex.table.item(row, 0).setCheckState(Qt.CheckState.Checked)
            ex.table.clearSelection()
            ex.table.setCurrentCell(row, 0)
        states = {memo_id: ex.table.item(self.row_of(ex, memo_id), 0).checkState() == Qt.CheckState.Checked
                  for memo_id in ("memo-0000", "memo-0001", "memo-0002")}
        self.assertEqual(states, {"memo-0000": True, "memo-0001": False, "memo-0002": True})    # 앞서 체크한 것이 풀리지 않음
        self.assertEqual(sorted(m["id"] for m in ex.picked_memos()), ["memo-0000", "memo-0002"])
        ex.b_del.click()
        self.assertEqual(self.ids(), ["memo-0001"])

    def test_checked_rows_win_over_the_selected_row(self) -> None:
        ex = self.explorer()
        ex.table.clearSelection()
        ex.table.item(self.row_of(ex, "memo-0000"), 0).setCheckState(Qt.CheckState.Checked)
        ex.table.setCurrentCell(self.row_of(ex, "memo-0001"), 2)      # 다른 줄을 눌러 미리보기만 본 상태
        self.assertEqual([m["id"] for m in ex.picked_memos()], ["memo-0000"])

    def test_ctrl_selection_checks_those_rows(self) -> None:
        ex = self.explorer()
        ex.table.clearSelection()
        for memo_id in ("memo-0001", "memo-0002"):
            ex.table.item(self.row_of(ex, memo_id), 2).setSelected(True)
        checked = sorted(ex.table.item(r, 2).data(Qt.ItemDataRole.UserRole)["id"] for r in range(ex.table.rowCount())
                         if ex.table.item(r, 0).checkState() == Qt.CheckState.Checked)
        self.assertEqual(checked, ["memo-0001", "memo-0002"])

    def test_right_click_delete_covers_the_whole_selection(self) -> None:
        ex = self.explorer()
        ex.table.clearSelection()
        rows = [self.row_of(ex, memo_id) for memo_id in ("memo-0000", "memo-0001")]
        for row in rows:
            ex.table.item(row, 2).setSelected(True)
        labels = []

        def run_menu(menu, *args):
            for action in menu.actions():
                labels.append(action.text())
                if "삭제 (휴지통)" in action.text():
                    action.trigger()

        with mock.patch.object(support.uim.QMenu, "exec", run_menu):
            ex.show_table_context_menu(ex.table.visualItemRect(ex.table.item(rows[0], 2)).center())
        self.assertIn("선택한 2개 삭제 (휴지통)", labels)
        self.assertEqual(self.ids(), ["memo-0002"])

    def test_nothing_picked_only_shows_a_toast(self) -> None:
        ex = self.explorer()
        ex.table.clearSelection()
        ex.table.setCurrentCell(-1, -1)
        ex.del_checked()
        self.assertEqual(len(self.ids()), 3)
        self.assertTrue(self.warnings == [] and ex.toast.text().startswith("⚠"))

    # ── 5. 체크해 둔 것이 유지되고, 지울 때 제목이 보임 ──
    def test_checks_survive_a_refresh_and_reset_in_the_trash(self) -> None:
        ex = self.explorer()
        ex.table.clearSelection()
        ex.table.item(self.row_of(ex, "memo-0000"), 0).setCheckState(Qt.CheckState.Checked)
        ex.refresh()                                                 # 동기화나 자동 저장으로 목록이 다시 그려져도
        self.assertEqual([m["id"] for m in ex.picked_memos()], ["memo-0000"])
        ex.t_btn.setChecked(True)
        ex.toggle_trash()
        ex.t_btn.setChecked(False)
        ex.toggle_trash()
        ex.table.clearSelection()
        self.assertEqual(ex.picked_memos(), [])                      # 휴지통을 다녀오면 체크를 이어 가지 않음

    def test_delete_confirmation_lists_the_titles(self) -> None:
        ex = self.explorer()
        ex.table.clearSelection()
        for memo_id in ("memo-0000", "memo-0002"):
            ex.table.item(self.row_of(ex, memo_id), 0).setCheckState(Qt.CheckState.Checked)
        asked = []
        with mock.patch.object(support.themed_dialog, "confirm", lambda parent, title, text, **k: asked.append(text) or False):
            ex.del_checked()
        self.assertEqual(len(asked), 1)
        self.assertIn("• t0", asked[0])
        self.assertIn("• t2", asked[0])
        self.assertEqual(len(self.sm.load_local_memos()), 3)         # 취소했으므로 그대로

    def test_delete_key_does_nothing_in_the_trash(self) -> None:
        ex = self.explorer()
        self.sm.delete_memo_locally("memo-0002")
        ex.t_btn.setChecked(True)
        ex.toggle_trash()
        ex.table.selectRow(0)
        with mock.patch.object(ex, "del_checked") as deleting:
            ex._delete_key.activated.emit()
            deleting.assert_not_called()


class ExplorerPreviewTest(support.UiTestCase):
    """미리보기에서 고치기, 체크 상자 누르기, 우클릭 메뉴."""

    def rich_memo(self) -> str:
        """굵은 제목 한 줄과 체크리스트 두 줄로 된, 서식이 있는 메모. (편집기가 실제로 만드는 HTML 그대로)"""
        from PyQt6.QtGui import QFont, QTextCharFormat, QTextDocument
        document = QTextDocument()
        cursor = QTextCursor(document)
        bold = QTextCharFormat()
        bold.setFontWeight(QFont.Weight.Bold)
        cursor.insertText("bold title", bold)
        for line in ("☐ first", "☐ second"):
            cursor.insertBlock()
            cursor.insertText(line, QTextCharFormat())
        self.sm.save_memo_locally({"id": "memo-0005", "title": "rich", "content": document.toHtml(),
                                   "updated_at": "2026-04-01T00:00:00", "is_visible": False})
        return "memo-0005"

    def select(self, ex, memo_id: str) -> int:
        ex.refresh()
        row = self.row_of(ex, memo_id)
        ex.table.setCurrentCell(row, 2)
        ex.on_cell_click(row, 2)
        return row

    def test_preview_is_read_only(self) -> None:
        memo_id = self.rich_memo()
        ex = self.explorer()
        self.select(ex, memo_id)
        self.assertTrue(ex.pv.isReadOnly())
        self.assertEqual(ex.pv.toPlainText().splitlines()[-2:], ["☐ first", "☐ second"])
        before = self.raw(memo_id)
        block = ex.pv.document().findBlockByNumber(ex.pv.document().blockCount() - 1)
        box = ex.pv.check_marks.box_rect(block, 0)
        QTest.mouseClick(ex.pv.viewport(), Qt.MouseButton.LeftButton, pos=box.center())
        self.assertTrue(ex.pv.toPlainText().endswith("☐ second"))       # 눌러도 체크되지 않음
        ex.pv.setFocus()
        QTest.keyClicks(ex.pv, "typed")
        self.assertNotIn("typed", ex.pv.toPlainText())                     # 글자도 들어가지 않음
        self.assertEqual(self.raw(memo_id), before)                        # 메모는 그대로

    def test_preview_menu_only_copies(self) -> None:
        ex = self.explorer()
        self.select(ex, "memo-0001")
        actions = {text: (run, enabled) for text, run, enabled in ex.preview_menu_actions()}
        self.assertEqual(list(actions), ["복사", "전체 내용 복사"])
        self.assertFalse(actions["복사"][1])                               # 고른 글자가 없으면 못 누름
        ex.pv.selectAll()
        self.assertTrue(dict((t, e) for t, _, e in ex.preview_menu_actions())["복사"])
        support.app.clipboard().setText("")
        actions["전체 내용 복사"][0]()
        self.assertIn("body 1", support.app.clipboard().text())

        w = self.open_window("memo-0001")
        self.answers[:] = ["pw12", "pw12"]
        w.set_memo_password()
        w.lock_now()
        self.select(ex, "memo-0001")
        actions = {text: enabled for text, _, enabled in ex.preview_menu_actions()}
        self.assertFalse(actions["전체 내용 복사"])                         # 암호 메모는 복사 못 함

    def test_copy_button_beside_the_preview_title(self) -> None:
        ex = self.explorer()
        self.assertFalse(ex.btn_preview_copy.icon().isNull())
        ex.resize(ex.width(), ex.height() + 120)
        support.app.processEvents()
        btn, pv = ex.btn_preview_copy, ex.pv
        self.assertIs(btn.parent(), pv)                                    # 미리보기 칸 안의
        self.assertLess(btn.y(), 25)                                       # 위쪽
        self.assertLess(pv.width() - (btn.x() + btn.width()), 30)          # 오른쪽 구석
        support.app.clipboard().setText("")
        ex.btn_preview_copy.click()                                        # 고른 메모가 없으면 알리기만
        self.assertEqual(support.app.clipboard().text(), "")
        self.select(ex, "memo-0002")
        ex.btn_preview_copy.click()
        self.assertEqual(support.app.clipboard().text(), "body 2 #tag2")
        for i in range(3, 25):                                             # 쪽을 넘겨도 보이는 메모를 복사
            self.sm.save_memo_locally({"id": f"memo-{i:04d}", "title": f"t{i}", "content": f"page {i}",
                                       "updated_at": "2026-02-01T00:00:00", "is_visible": False})
        ex.refresh()
        self.select(ex, "memo-0003")
        ex.btn_last_page.click()
        support.app.clipboard().setText("")
        ex.btn_preview_copy.click()
        self.assertEqual(support.app.clipboard().text(), "page 3")
        ex.pv.clear()                                                      # 미리보기를 비우면 복사할 것이 없음
        self.assertIsNone(ex._preview_memo())

    def test_window_typing_shows_up_in_the_preview(self) -> None:
        w = self.open_window("memo-0001")
        w.text_edit.setPlainText("typed in the window")
        w.text_edit.document().setModified(True)
        w._schedule_auto_save()
        ex = self.explorer()
        self.select(ex, "memo-0001")
        self.assertIn("typed in the window", ex.pv.toPlainText())         # 창에서 쓰던 글을 저장하고 보여 줌
        self.assertIn("typed in the window", self.disk("memo-0001")["content"])


if __name__ == "__main__":
    unittest.main()
