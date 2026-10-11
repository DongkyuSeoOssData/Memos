"""체크리스트와 취소선: 글자 규칙, 진행률, 메모·탐색기에서의 그리기와 조작."""
import unittest
from unittest import mock

from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtGui import QTextCursor
from PyQt6.QtTest import QTest

# support 를 먼저 가져와야 합니다. (offscreen 설정과 프로젝트 경로)
import support
from ui import checklist


class ChecklistRuleTest(unittest.TestCase):
    def test_toggle_boxes(self) -> None:
        self.assertEqual(checklist.toggle_boxes(["a", "  b", ""]), ["☐ a", "  ☐ b", ""])
        self.assertEqual(checklist.toggle_boxes(["☐ a", "☑ b"]), ["a", "b"])
        self.assertEqual(checklist.toggle_boxes(["☑ a", "b"]), ["☑ a", "☐ b"])
        self.assertEqual(checklist.toggle_boxes([""]), ["☐ "])

    def test_state_and_toggle(self) -> None:
        self.assertIsNone(checklist.state("plain"))
        self.assertFalse(checklist.state("  ☐ x"))
        self.assertEqual(checklist.toggled("  ☐ x"), "  ☑ x")
        self.assertEqual(checklist.toggled("  ☑ x"), "  ☐ x")
        self.assertEqual(checklist.toggled("x ☐"), "x ☐")

    def test_continuation(self) -> None:
        self.assertEqual(checklist.continuation("  ☑ done"), ("  ☐ ", False))
        self.assertEqual(checklist.continuation("☐ "), ("", True))
        self.assertEqual(checklist.continuation("text"), ("", False))


class ChecklistProgressTest(support.UiTestCase):
    def test_progress_label_shows_whether_everything_is_done(self) -> None:
        self.assertEqual(checklist.progress_label("☑ a\n☐ b"), "☐ 1/2")
        self.assertEqual(checklist.progress_label("☑ a\n☑ b"), "☑ 2/2")
        self.assertEqual(checklist.progress_label("plain"), "")

    def test_backspace_removes_the_box_and_its_space_at_once(self) -> None:
        w = self.open_window("memo-0000")
        w.text_edit.setPlainText("☐ milk\n  ☑ eggs")
        cursor = w.text_edit.textCursor()
        cursor.setPosition(2)                                        # '☐ ' 바로 뒤
        w.text_edit.setTextCursor(cursor)
        QTest.keyClick(w.text_edit, Qt.Key.Key_Backspace)
        self.assertEqual(w.text_edit.toPlainText(), "milk\n  ☑ eggs")
        cursor.setPosition(5 + 2 + 1)                                # 둘째 줄의 상자 바로 뒤 (공백 앞)
        w.text_edit.setTextCursor(cursor)
        QTest.keyClick(w.text_edit, Qt.Key.Key_Backspace)
        self.assertEqual(w.text_edit.toPlainText(), "milk\n  eggs")
        # 상자가 없는 곳에서는 보통대로 한 글자만
        cursor.setPosition(2)
        w.text_edit.setTextCursor(cursor)
        QTest.keyClick(w.text_edit, Qt.Key.Key_Backspace)
        self.assertEqual(w.text_edit.toPlainText(), "mlk\n  eggs")

    def test_preview_draws_boxes_and_lets_you_check_them(self) -> None:
        w = self.open_window("memo-0001")
        w.text_edit.setPlainText("☐ a\n☐ b")
        w.text_edit.document().setModified(True)
        w.execute_auto_save()
        ex = self.explorer()
        ex.refresh()
        row = self.row_of(ex, "memo-0001")
        ex.table.setCurrentCell(row, 2)
        ex.on_cell_click(row, 2)
        self.assertEqual(ex.pv.toPlainText(), "☐ a\n☐ b")
        hidden = [m for m in ex.pv.extraSelections() if m.format.foreground().color().alpha() == 0]
        self.assertEqual(len(hidden), 2)                             # 글자 대신 네모로 그림
        box = ex.pv.check_marks.box_rect(ex.pv.document().findBlockByNumber(1), 0)
        QTest.mouseClick(ex.pv.viewport(), Qt.MouseButton.LeftButton, pos=box.center())
        self.assertEqual(ex.pv.toPlainText(), "☐ a\n☑ b")
        ex._flush_preview_save()
        self.assertIn("☑ b", self.raw("memo-0001"))
        self.assertEqual(w.text_edit.toPlainText(), "☐ a\n☑ b")       # 열려 있는 메모 창에도 반영
        ex.pv.viewport().grab()

    def test_progress_rule(self) -> None:
        self.assertEqual(checklist.progress("☑ a\n☐ b\n  ☑ c\nplain ☐"), (2, 3))
        self.assertEqual(checklist.progress_text("☑ a\n☐ b"), "1/2")
        self.assertEqual(checklist.progress_text("no boxes"), "")

    def test_title_bar_shows_progress_and_follows_edits(self) -> None:
        w = self.open_window("memo-0000")
        self.assertTrue(w.lbl_progress.isHidden())
        w.text_edit.setPlainText("☐ milk\n☐ eggs\nnote")
        self.assertFalse(w.lbl_progress.isHidden())
        self.assertEqual(w.lbl_progress.text(), "☐ 0/2")
        box = w.text_edit._check_box_rect(w.text_edit.document().findBlockByNumber(1), 0)
        QTest.mouseClick(w.text_edit.viewport(), Qt.MouseButton.LeftButton, pos=box.center())
        self.assertEqual(w.lbl_progress.text(), "☐ 1/2")
        box = w.text_edit._check_box_rect(w.text_edit.document().findBlockByNumber(0), 0)
        QTest.mouseClick(w.text_edit.viewport(), Qt.MouseButton.LeftButton, pos=box.center())
        self.assertEqual(w.lbl_progress.text(), "☑ 2/2")              # 다 끝내면 체크된 상자
        w.toggle_rollup()                                            # 접어도 보임
        self.assertFalse(w.lbl_progress.isHidden())
        w.toggle_rollup()
        w.text_edit.setPlainText("plain")
        self.assertTrue(w.lbl_progress.isHidden())

    def test_explorer_shows_progress_next_to_the_title(self) -> None:
        w = self.open_window("memo-0001")
        w.text_edit.setPlainText("☑ a\n☑ b\n☐ c")
        w.text_edit.document().setModified(True)
        w.execute_auto_save()
        ex = self.explorer()
        ex.refresh()
        row = self.row_of(ex, "memo-0001")
        texts = [ex.table.item(row, c).text() for c in range(ex.table.columnCount()) if ex.table.item(row, c)]
        self.assertTrue(any(t.endswith("☐ 2/3") for t in texts), texts)        # 남은 일이 있으면 빈 상자
        other = self.row_of(ex, "memo-0002")
        self.assertFalse(any("☑" in ex.table.item(other, c).text() for c in range(ex.table.columnCount()) if ex.table.item(other, c)))

    def test_boxes_are_drawn_instead_of_shown_as_letters(self) -> None:
        w = self.open_window("memo-0000")
        w.text_edit.setPlainText("☑ done\n☐ todo\nplain")
        marks = w.text_edit.extraSelections()
        hidden = [m for m in marks if m.format.foreground().color().alpha() == 0]
        self.assertEqual([(m.cursor.selectionStart(), m.cursor.selectedText()) for m in hidden], [(0, "☑"), (7, "☐")])
        faded = [m.cursor.selectedText() for m in marks if m.format.foreground().color().alpha() == 255]
        self.assertEqual(faded, [" done"])                            # 끝낸 줄만 흐리게
        self.assertEqual(w.text_edit.toPlainText(), "☑ done\n☐ todo\nplain")      # 저장되는 글자는 그대로
        self.assertFalse(w.text_edit.document().isModified())
        w.resize(360, 300)
        w.text_edit.viewport().grab()                                # 그리는 과정에서 오류가 없어야 함
        w.text_edit.setPlainText("plain")
        self.assertEqual(w.text_edit.extraSelections(), [])


class ChecklistUiTest(support.UiTestCase):
    def test_button_adds_and_removes_boxes_on_selected_lines(self) -> None:
        w = self.open_window("memo-0000")
        w.text_edit.setPlainText("milk\neggs")
        w.text_edit.selectAll()
        w.btn_check.click()
        self.assertEqual(w.text_edit.toPlainText(), "☐ milk\n☐ eggs")
        w.text_edit.selectAll()
        w.toggle_checklist()
        self.assertEqual(w.text_edit.toPlainText(), "milk\neggs")

    def test_adding_a_box_keeps_formatting(self) -> None:
        w = self.open_window("memo-0000")
        w.text_edit.setPlainText("milk")
        w.text_edit.selectAll()
        w.toggle_bold()
        w.toggle_checklist()
        cursor = w.text_edit.textCursor()
        cursor.setPosition(4)
        self.assertEqual(w.text_edit.toPlainText(), "☐ milk")
        self.assertGreater(cursor.charFormat().fontWeight(), 500)

    def test_clicking_the_box_toggles_it(self) -> None:
        w = self.open_window("memo-0000")
        w.text_edit.setPlainText("☐ milk\nplain")
        box = w.text_edit.cursorRect(QTextCursor(w.text_edit.document().findBlockByNumber(0)))
        spot = QPoint(box.left() + 4, box.center().y())
        QTest.mouseClick(w.text_edit.viewport(), Qt.MouseButton.LeftButton, pos=spot)
        self.assertEqual(w.text_edit.toPlainText(), "☑ milk\nplain")
        QTest.mouseClick(w.text_edit.viewport(), Qt.MouseButton.LeftButton, pos=spot)
        self.assertEqual(w.text_edit.toPlainText(), "☐ milk\nplain")
        # 상자가 아닌 곳을 누르면 그대로
        QTest.mouseClick(w.text_edit.viewport(), Qt.MouseButton.LeftButton, pos=QPoint(box.left() + 60, box.center().y()))
        self.assertEqual(w.text_edit.toPlainText(), "☐ milk\nplain")

    def test_enter_continues_and_ends_the_list(self) -> None:
        w = self.open_window("memo-0000")
        w.text_edit.setPlainText("☑ milk")
        w.text_edit.moveCursor(QTextCursor.MoveOperation.End)
        QTest.keyClick(w.text_edit, Qt.Key.Key_Return)
        self.assertEqual(w.text_edit.toPlainText(), "☑ milk\n☐ ")
        QTest.keyClick(w.text_edit, Qt.Key.Key_Return)
        self.assertEqual(w.text_edit.toPlainText(), "☑ milk\n")
        QTest.keyClick(w.text_edit, Qt.Key.Key_Return)
        self.assertEqual(w.text_edit.toPlainText(), "☑ milk\n\n")

    def test_checking_is_saved(self) -> None:
        w = self.open_window("memo-0000")
        w.text_edit.setPlainText("☐ milk")
        box = w.text_edit.cursorRect(QTextCursor(w.text_edit.document().findBlockByNumber(0)))
        QTest.mouseClick(w.text_edit.viewport(), Qt.MouseButton.LeftButton, pos=QPoint(box.left() + 4, box.center().y()))
        w.flush_auto_save()
        self.assertIn("☑ milk", self.raw("memo-0000"))


class StrikeThroughTest(support.UiTestCase):
    def test_button_strikes_the_selection_and_it_is_saved(self) -> None:
        w = self.open_window("memo-0000")
        w.text_edit.setPlainText("keep drop")
        cursor = w.text_edit.textCursor()
        cursor.setPosition(5)
        cursor.setPosition(9, QTextCursor.MoveMode.KeepAnchor)
        w.text_edit.setTextCursor(cursor)
        w.btn_strike.click()
        self.assertTrue(w.btn_strike.isChecked())
        self.assertIn("line-through", w.btn_strike.styleSheet())
        probe = QTextCursor(w.text_edit.document())
        probe.setPosition(3)
        self.assertFalse(probe.charFormat().fontStrikeOut())
        probe.setPosition(8)
        self.assertTrue(probe.charFormat().fontStrikeOut())
        w.execute_auto_save()
        self.assertIn("line-through", self.disk("memo-0000")["content"])

        # 다시 누르면 지워지고, 서식이 없어졌으므로 글자만 저장됨
        w.text_edit.setTextCursor(cursor)
        w.btn_strike.click()
        self.assertFalse(w.btn_strike.isChecked())
        w.execute_auto_save()
        self.assertEqual(self.disk("memo-0000")["content"], "keep drop")


class ChecklistDetailsTest(support.UiTestCase):
    """체크 상자의 세부 동작: 지우기, 더블클릭, 선택, 코드 메모, 암호 메모, 진행률 세기."""

    def test_backspace_at_the_start_of_a_list_item_removes_it_at_once(self) -> None:
        w = self.open_window("memo-0000")
        w.text_edit.setPlainText("item")
        w.text_edit.selectAll()
        w.apply_bullet()
        w.apply_indent()
        cursor = w.text_edit.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
        w.text_edit.setTextCursor(cursor)
        self.assertIsNotNone(cursor.block().textList())
        QTest.keyClick(w.text_edit, Qt.Key.Key_Backspace)
        block = w.text_edit.document().firstBlock()
        self.assertIsNone(block.textList())
        self.assertEqual((block.blockFormat().indent(), block.text()), (0, "item"))       # 들여쓰기도 남지 않음

    def test_double_click_on_a_box_does_not_select_text(self) -> None:
        w = self.open_window("memo-0000")
        w.text_edit.setPlainText("☐ milk")
        box = w.text_edit._check_box_rect(w.text_edit.document().firstBlock(), 0)
        QTest.mouseDClick(w.text_edit.viewport(), Qt.MouseButton.LeftButton, pos=box.center())
        self.assertFalse(w.text_edit.textCursor().hasSelection())
        self.assertIn(w.text_edit.toPlainText(), ("☐ milk", "☑ milk"))

    def test_explorer_never_shows_progress_for_password_memos(self) -> None:
        w = self.open_window("memo-0001")
        w.text_edit.setPlainText("☑ a\n☐ b")
        w.text_edit.document().setModified(True)
        w.execute_auto_save()
        ex = self.explorer()
        ex.refresh()
        title = lambda: ex.table.item(self.row_of(ex, "memo-0001"), 2).text()
        self.assertIn("1/2", title())
        self.answers[:] = ["pw12", "pw12"]
        w.set_memo_password()
        ex.refresh()
        self.assertNotIn("1/2", title())                             # 열려 있는 암호 메모
        w.lock_now()
        ex.refresh()
        self.assertNotIn("1/2", title())                             # 잠긴 암호 메모

    def test_code_memo_checklists_work_everywhere(self) -> None:
        self.sm.save_memo_locally({"id": "memo-0007", "title": "code", "content": "☑ build\n☐ ship", "is_code_memo": True,
                                   "code_lang": "Plain Text", "updated_at": "2026-03-01T00:00:00", "is_visible": False})
        ex = self.explorer()
        ex.refresh()
        row = self.row_of(ex, "memo-0007")
        self.assertTrue(ex.table.item(row, 2).text().endswith("☐ 1/2"))
        ex.table.setCurrentCell(row, 2)
        ex.on_cell_click(row, 2)
        self.assertEqual(len([m for m in ex.pv.extraSelections() if m.format.foreground().color().alpha() == 0]), 2)
        w = self.open_window("memo-0007")
        self.assertEqual(w.lbl_progress.text(), "☐ 1/2")
        self.assertEqual(len([m for m in w.text_edit.extraSelections() if m.format.foreground().color().alpha() == 0]), 2)
        box = w.text_edit._check_box_rect(w.text_edit.document().findBlockByNumber(1), 0)
        QTest.mouseClick(w.text_edit.viewport(), Qt.MouseButton.LeftButton, pos=box.center())
        self.assertEqual(w.lbl_progress.text(), "☑ 2/2")
        w.flush_auto_save()
        ex.refresh()
        self.assertTrue(ex.table.item(self.row_of(ex, "memo-0007"), 2).text().endswith("☑ 2/2"))

    def test_checklist_button_uses_the_drawn_box_icon(self) -> None:
        w = self.open_window("memo-0000")
        self.assertEqual(w.btn_check.text(), "")
        self.assertFalse(w.btn_check.icon().isNull())

    def test_selecting_text_never_shows_the_raw_box_letter(self) -> None:
        w = self.open_window("memo-0000")
        w.resize(360, 300)
        w.text_edit.setPlainText("☐ milk\n☑ eggs\nplain")
        support.app.processEvents()
        marks = w.text_edit.check_marks
        cell = marks.glyph_cell(w.text_edit.document().firstBlock(), 0)
        box = marks.box_rect(w.text_edit.document().firstBlock(), 0)
        self.assertTrue(cell.width() > 0 and cell.left() == box.left())
        self.assertGreaterEqual(cell.height(), box.height())

        # 전체를 선택했을 때: 상자 글자 칸이 선택 바탕색으로 덮이고 그 위에 네모가 그려짐
        w.text_edit.selectAll()
        w.text_edit.setFocus()
        image = w.text_edit.viewport().grab().toImage()
        highlight = w.text_edit.palette().color(w.text_edit.palette().ColorGroup.Inactive, w.text_edit.palette().ColorRole.Highlight)
        active = w.text_edit.palette().color(w.text_edit.palette().ColorGroup.Active, w.text_edit.palette().ColorRole.Highlight)
        corner = image.pixelColor(cell.right() - 1, cell.top() + 1)   # 네모 바깥, 글자 칸의 구석
        self.assertIn(corner.name(), (highlight.name(), active.name()))

    # ── 7. 체크 상자가 없는 메모는 줄을 훑지 않음 ──
    def test_progress_is_tracked_without_rescanning(self) -> None:
        w = self.open_window("memo-0000")
        marks = w.text_edit.check_marks
        w.text_edit.setPlainText("no boxes here")
        self.assertEqual((marks.has_boxes, marks.total, marks.progress_label()), (False, 0, ""))
        w.text_edit.setPlainText("☑ a\n☐ b\nmid ☐ line")
        self.assertEqual((marks.has_boxes, marks.done, marks.total, marks.progress_label()), (True, 1, 2, "☐ 1/2"))
        with mock.patch.object(type(w.text_edit), "toPlainText", side_effect=AssertionError("본문 전체를 다시 읽으면 안 됨")):
            w.refresh_progress()
            w.text_edit.viewport().grab()
        self.assertEqual(w.lbl_progress.text(), "☐ 1/2")


if __name__ == "__main__":
    unittest.main()
