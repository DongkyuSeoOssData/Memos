"""3.2 기능 테스트: 알림(반복·크론식), 변경 기록, 체크리스트, 빠른 검색."""
import datetime as dt
import unittest
from unittest import mock

from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtGui import QTextCursor
from PyQt6.QtTest import QTest

import test_ui
from core import reminders
from ui import checklist
from ui.dialogs import HistoryDialog
from ui.quick_search import QuickSearch
from ui.reminder_ui import ReminderDialog, ReminderPopup, quick_choices

D = dt.datetime


class CronTest(unittest.TestCase):
    def test_next_occurrence(self) -> None:
        cases = [
            ("0 9 * * *", D(2026, 10, 10, 8, 0), D(2026, 10, 10, 9, 0)),
            ("0 9 * * *", D(2026, 10, 10, 9, 0), D(2026, 10, 11, 9, 0)),          # 같은 분은 다음 번으로
            ("*/15 * * * *", D(2026, 10, 10, 9, 1), D(2026, 10, 10, 9, 15)),
            ("0 9 * * 1-5", D(2026, 10, 10, 10, 0), D(2026, 10, 12, 9, 0)),       # 토요일 → 월요일
            ("30 18 1 * *", D(2026, 10, 10, 0, 0), D(2026, 11, 1, 18, 30)),
            ("0 0 29 2 *", D(2026, 10, 10, 0, 0), D(2028, 2, 29, 0, 0)),          # 윤년
            ("0 8 * * 0", D(2026, 10, 10, 0, 0), D(2026, 10, 11, 8, 0)),          # 0 = 일요일
            ("0 8 * * 7", D(2026, 10, 10, 0, 0), D(2026, 10, 11, 8, 0)),          # 7 도 일요일
            ("0 9,18 * * *", D(2026, 10, 10, 9, 30), D(2026, 10, 10, 18, 0)),
        ]
        for expr, after, expected in cases:
            self.assertEqual(reminders.next_cron(expr, after), expected, expr)

    def test_bad_expressions_are_rejected(self) -> None:
        for expr in ("", "0 9 * *", "60 9 * * *", "0 24 * * *", "a b c d e", "*/0 * * * *", "0 9 31 2 *", "5-1 * * * *"):
            with self.assertRaises(ValueError, msg=expr):
                reminders.next_cron(expr, D(2026, 10, 10))


class ReminderRuleTest(unittest.TestCase):
    def test_one_shot_is_cleared_after_firing(self) -> None:
        r = reminders.make(D(2026, 10, 10, 9, 0))
        self.assertIsNone(reminders.following(r, D(2026, 10, 10, 9, 0, 5)))

    def test_repeats_move_to_the_next_time_after_now(self) -> None:
        at = D(2026, 10, 9, 9, 0)                                # 금요일
        now = D(2026, 10, 10, 12, 0)                             # 토요일 (하루 넘게 꺼져 있었음)
        self.assertEqual(reminders.due_at(reminders.following(reminders.make(at, "daily"), now)), D(2026, 10, 11, 9, 0))
        self.assertEqual(reminders.due_at(reminders.following(reminders.make(at, "weekdays"), now)), D(2026, 10, 12, 9, 0))
        self.assertEqual(reminders.due_at(reminders.following(reminders.make(at, "weekly"), now)), D(2026, 10, 16, 9, 0))
        self.assertEqual(reminders.due_at(reminders.following(reminders.make(at, "monthly"), now)), D(2026, 11, 9, 9, 0))

    def test_monthly_keeps_the_day_when_a_month_is_short(self) -> None:
        r = reminders.make(D(2026, 1, 31, 9, 0), "monthly")
        feb = reminders.following(r, D(2026, 1, 31, 9, 1))
        self.assertEqual(reminders.due_at(feb), D(2026, 2, 28, 9, 0))
        self.assertEqual(reminders.due_at(reminders.following(feb, D(2026, 2, 28, 9, 1))), D(2026, 3, 31, 9, 0))

    def test_cron_reminder(self) -> None:
        with mock.patch.object(reminders, "datetime") as fake:
            fake.now.return_value = D(2026, 10, 10, 10, 0)
            fake.fromisoformat = D.fromisoformat
            r = reminders.make(D(2026, 1, 1), "cron", "0 9 * * 1-5")
        self.assertEqual(reminders.due_at(r), D(2026, 10, 12, 9, 0))
        self.assertEqual(reminders.due_at(reminders.following(r, D(2026, 10, 12, 9, 0, 1))), D(2026, 10, 13, 9, 0))
        with self.assertRaises(ValueError):
            reminders.make(D(2026, 1, 1), "cron", "nope")

    def test_snooze_keeps_the_repeat_schedule(self) -> None:
        r = reminders.following(reminders.make(D(2026, 10, 10, 9, 0), "daily"), D(2026, 10, 10, 9, 0, 1))
        s = reminders.snoozed(r, 10, D(2026, 10, 10, 9, 0, 30))
        self.assertEqual(reminders.due_at(s), D(2026, 10, 10, 9, 10, 30))
        self.assertEqual(s["repeat"], "daily")
        after = reminders.following(s, D(2026, 10, 10, 9, 11))
        self.assertEqual(reminders.due_at(after), D(2026, 10, 11, 9, 0))          # 미룬 뒤에도 원래 시각으로 돌아옴

    def test_snoozing_a_one_shot(self) -> None:
        s = reminders.snoozed(None, 60, D(2026, 10, 10, 9, 0))
        self.assertEqual(reminders.due_at(s), D(2026, 10, 10, 10, 0))
        self.assertIsNone(reminders.following(s, D(2026, 10, 10, 10, 1)))

    def test_broken_values_are_ignored(self) -> None:
        for bad in (None, "", 3, {}, {"at": "soon"}, {"at": "2026-10-10T09:00:00", "repeat": "cron", "cron": "x"}):
            self.assertIsNone(reminders.normalize(bad))
            self.assertEqual(reminders.describe(bad), "")
        self.assertTrue(reminders.describe(reminders.make(D(2026, 10, 10, 9, 0), "weekly")))


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


class HistoryTest(test_ui.UiTestCase):
    def test_saving_new_content_keeps_the_old_one(self) -> None:
        memo = next(m for m in self.sm.load_local_memos() if m["id"] == "memo-0000")
        memo["content"] = "second"
        self.sm.save_memo_locally(memo)
        history = self.sm.list_history("memo-0000")
        self.assertEqual([h["text"] for h in history], ["body 0 #tag0"])

        # 연달아 저장한 것은 쌓지 않음 (10분 간격)
        memo["content"] = "third"
        self.sm.save_memo_locally(memo)
        self.assertEqual(len(self.sm.list_history("memo-0000")), 1)

    def test_meta_only_saves_do_not_add_history(self) -> None:
        memo = next(m for m in self.sm.load_local_memos() if m["id"] == "memo-0001")
        memo["is_favorite"] = True
        self.sm.save_memo_locally(memo)
        self.sm.set_reminder(memo, reminders.make(D(2030, 1, 1, 9, 0)))
        self.assertEqual(self.sm.list_history("memo-0001"), [])

    def test_restore_brings_back_the_content_and_can_be_undone(self) -> None:
        memo = next(m for m in self.sm.load_local_memos() if m["id"] == "memo-0000")
        memo["content"], memo["title"] = "second", "new title"
        self.sm.save_memo_locally(memo)
        index = self.sm.list_history("memo-0000")[0]["index"]
        self.assertTrue(self.sm.restore_history("memo-0000", index))
        self.assertEqual(self.disk("memo-0000")["title"], "t0")
        restored = next(m for m in self.sm.load_local_memos() if m["id"] == "memo-0000")
        self.assertEqual(restored["content"], "body 0 #tag0")
        self.assertEqual(self.sm.list_history("memo-0000")[0]["text"], "second")     # 되돌리기 직전 내용도 남음
        self.assertFalse(self.sm.restore_history("memo-0000", 99))

    def test_history_is_capped_and_removed_with_the_memo(self) -> None:
        memo = next(m for m in self.sm.load_local_memos() if m["id"] == "memo-0002")
        with mock.patch.object(self.sm, "HISTORY_MIN_GAP_SEC", 0):
            for i in range(self.sm.HISTORY_KEEP + 5):
                memo["content"] = f"v{i}"
                self.sm.save_memo_locally(memo)
        self.assertEqual(len(self.sm.list_history("memo-0002")), self.sm.HISTORY_KEEP)
        self.assertTrue((self.memo_dir / "history_bin" / "memo-0002.json").exists())
        self.sm.delete_memo_locally("memo-0002")
        self.sm.empty_trash_locally()
        self.assertFalse((self.memo_dir / "history_bin" / "memo-0002.json").exists())

    def test_history_folder_is_not_listed_as_memos(self) -> None:
        memo = next(m for m in self.sm.load_local_memos() if m["id"] == "memo-0000")
        memo["content"] = "second"
        self.sm.save_memo_locally(memo)
        self.assertEqual(len(self.sm.load_local_memos()), 3)

    def test_window_restores_through_the_dialog(self) -> None:
        w = self.open_window("memo-0000")
        w.text_edit.setPlainText("rewritten")
        w.text_edit.document().setModified(True)
        w.execute_auto_save()
        with mock.patch.object(HistoryDialog, "exec", lambda d: (d.list.setCurrentRow(0), d._restore(), True)[2]):
            w.show_history()
        self.assertEqual(w.text_edit.toPlainText(), "body 0 #tag0")
        self.assertEqual(self.sm.list_history("memo-0000")[0]["text"], "rewritten")

    def test_dialog_with_no_history(self) -> None:
        d = HistoryDialog(None, "t", [])
        self.assertFalse(d.restore_button.isEnabled())
        d.close()


class ChecklistUiTest(test_ui.UiTestCase):
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


class QuickSearchTest(test_ui.UiTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.sm.save_memo_locally({"id": "memo-0009", "title": "회의 body", "content": "분기 계획", "folder": "업무",
                                   "updated_at": "2026-02-01T00:00:00", "is_visible": False})
        self.qs = QuickSearch(self.ui)
        self.addCleanup(self.qs.close)
        self.qs.popup()

    def ids(self, query: str) -> list:
        return [m["id"] for m in self.qs.search(query)]

    def test_empty_query_lists_recent_first(self) -> None:
        self.assertEqual(self.ids(""), ["memo-0009", "memo-0002", "memo-0001", "memo-0000"])

    def test_title_matches_come_before_body_matches(self) -> None:
        self.assertEqual(self.ids("body"), ["memo-0009", "memo-0002", "memo-0001", "memo-0000"])
        self.assertEqual(self.ids("BODY tag1"), ["memo-0001"])
        self.assertEqual(self.ids("업무"), ["memo-0009"])            # 폴더 이름으로도 찾음
        self.assertEqual(self.ids("없는말"), [])

    def test_typing_and_enter_opens_the_memo(self) -> None:
        QTest.keyClicks(self.qs.input, "tag1")
        self.assertEqual(self.qs.results.count(), 1)
        QTest.keyClick(self.qs.input, Qt.Key.Key_Return)
        self.assertFalse(self.qs.isVisible())
        self.assertIn("memo-0001", self.ui.memo_windows)

    def test_arrows_move_and_escape_closes(self) -> None:
        QTest.keyClick(self.qs.input, Qt.Key.Key_Down)
        self.assertEqual(self.qs.results.currentRow(), 1)
        QTest.keyClick(self.qs.input, Qt.Key.Key_Up)
        QTest.keyClick(self.qs.input, Qt.Key.Key_Up)
        self.assertEqual(self.qs.results.currentRow(), 3)            # 처음에서 위로 가면 끝으로
        QTest.keyClick(self.qs.input, Qt.Key.Key_Escape)
        self.assertFalse(self.qs.isVisible())

    def test_locked_memo_content_is_not_searched(self) -> None:
        w = self.open_window("memo-0000")
        self.answers[:] = ["pw12", "pw12"]
        w.set_memo_password()
        w.lock_now()
        self.qs.popup()
        self.assertNotIn("memo-0000", self.ids("tag0"))
        self.assertIn("memo-0000", self.ids("t0"))                   # 제목으로는 찾음

    def test_tray_and_hotkey_toggle(self) -> None:
        self.ui.toggle_quick_search()
        self.assertTrue(self.ui.quick_search.isVisible())
        self.ui.toggle_quick_search()
        self.assertFalse(self.ui.quick_search.isVisible())


class ReminderUiTest(test_ui.UiTestCase):
    def memo(self, memo_id: str) -> dict:
        return next(m for m in self.sm.load_local_memos() if m["id"] == memo_id)

    def test_setting_a_reminder_schedules_the_timer_without_touching_modified_time(self) -> None:
        self.assertFalse(self.ui._reminder_timer.isActive())
        self.sm.set_reminder(self.memo("memo-0000"), reminders.make(D.now() + dt.timedelta(minutes=30)))
        self.assertTrue(self.ui._reminder_timer.isActive())
        self.assertLessEqual(self.ui._reminder_timer.interval(), 30 * 60 * 1000 + 300)
        self.assertEqual(self.disk("memo-0000")["updated_at"], "2026-01-01T00:00:00")
        self.assertIn("meta_updated_at", self.disk("memo-0000"))
        self.sm.set_reminder(self.memo("memo-0000"), None)
        self.assertFalse(self.ui._reminder_timer.isActive())
        self.assertNotIn("reminder", self.disk("memo-0000"))

    def test_far_reminders_are_rechecked_within_an_hour(self) -> None:
        self.sm.set_reminder(self.memo("memo-0000"), reminders.make(D.now() + dt.timedelta(days=30)))
        self.assertEqual(self.ui._reminder_timer.interval(), self.ui.MAX_REMINDER_WAIT_MS)

    def test_due_one_shot_fires_once_and_is_cleared(self) -> None:
        self.sm.set_reminder(self.memo("memo-0001"), reminders.make(D.now() - dt.timedelta(seconds=5)))
        self.ui.check_reminders()
        self.assertEqual(len(self.ui._reminder_popups), 1)
        popup = self.ui._reminder_popups[0]
        self.assertEqual(popup.title_label.text(), "t1")
        self.assertNotIn("reminder", self.disk("memo-0001"))
        self.ui.check_reminders()
        self.assertEqual(len(self.ui._reminder_popups), 1)
        popup.close()

    def test_due_repeat_moves_on_and_keeps_the_timer(self) -> None:
        due = (D.now() - dt.timedelta(minutes=1)).replace(microsecond=0)
        self.sm.set_reminder(self.memo("memo-0001"), reminders.make(due, "daily"))
        self.ui.check_reminders()
        self.assertEqual(reminders.due_at(self.disk("memo-0001")["reminder"]), due + dt.timedelta(days=1))
        self.assertTrue(self.ui._reminder_timer.isActive())
        self.ui._reminder_popups[0].close()

    def test_snooze_from_the_popup(self) -> None:
        self.sm.set_reminder(self.memo("memo-0001"), reminders.make(D.now() - dt.timedelta(seconds=5)))
        self.ui.check_reminders()
        self.ui.snooze_reminder("memo-0001", 10)
        left = (reminders.due_at(self.disk("memo-0001")["reminder"]) - D.now()).total_seconds()
        self.assertTrue(9 * 60 < left <= 10 * 60)
        self.ui._reminder_popups[0].close()

    def test_open_window_shows_and_updates_the_badge(self) -> None:
        w = self.open_window("memo-0002")
        self.assertTrue(w.btn_reminder.isHidden())
        reminder = reminders.make(D.now() + dt.timedelta(hours=2), "weekly")
        with mock.patch("ui.memo_window.ask_reminder", return_value=(True, reminder)):
            w.edit_reminder()
        self.assertFalse(w.btn_reminder.isHidden())
        self.assertIn("⏰", w.btn_reminder.text())
        self.assertEqual(self.disk("memo-0002")["reminder"]["repeat"], "weekly")
        # 창이 나중에 저장해도 알림이 사라지지 않음
        w.text_edit.setPlainText("edited")
        w.text_edit.document().setModified(True)
        w.execute_auto_save()
        self.assertEqual(self.disk("memo-0002")["reminder"]["repeat"], "weekly")
        with mock.patch("ui.memo_window.ask_reminder", return_value=(True, None)):
            w.edit_reminder()
        self.assertTrue(w.btn_reminder.isHidden())
        with mock.patch("ui.memo_window.ask_reminder", return_value=(False, None)):
            w.edit_reminder()
        self.assertNotIn("reminder", self.disk("memo-0002"))

    def test_firing_while_the_window_is_open_updates_that_window(self) -> None:
        w = self.open_window("memo-0002")
        self.sm.set_reminder(w.memo_data, reminders.make(D.now() - dt.timedelta(seconds=5)))
        self.ui.check_reminders()
        self.assertNotIn("reminder", w.memo_data)
        self.assertTrue(w.btn_reminder.isHidden())
        self.ui._reminder_popups[0].close()

    def test_explorer_marks_and_edits_reminders(self) -> None:
        ex = self.explorer()
        memo = ex.table.item(self.row_of(ex, "memo-0001"), 2).data(Qt.ItemDataRole.UserRole)
        with mock.patch("ui.memo_explorer.ask_reminder", return_value=(True, reminders.make(D.now() + dt.timedelta(days=1)))):
            ex.edit_reminder(memo)
        cell = next(ex.table.item(self.row_of(ex, "memo-0001"), c) for c in range(ex.table.columnCount())
                    if ex.table.item(self.row_of(ex, "memo-0001"), c) and "⏰" in ex.table.item(self.row_of(ex, "memo-0001"), c).text())
        self.assertIn("알림", cell.toolTip())
        self.assertIn("memo-0001", self.sm.reminders)

    def test_reminders_survive_a_restart(self) -> None:
        self.sm.set_reminder(self.memo("memo-0000"), reminders.make(D(2031, 5, 5, 9, 0), "monthly"))
        fresh = test_ui.smm.SyncManager(test_ui.DriveAPI())
        fresh.load_local_memos()
        self.assertEqual(fresh.reminders["memo-0000"]["repeat"], "monthly")

    def test_dialog_builds_reminders_and_rejects_bad_cron(self) -> None:
        d = ReminderDialog(None, None, "t")
        ok = d.buttons.button(d.buttons.StandardButton.Ok)
        self.assertTrue(ok.isEnabled())
        d.repeat.setCurrentIndex(d.repeat.findData("cron"))
        self.assertFalse(ok.isEnabled())                             # 식이 비어 있음
        d.cron.setText("0 9 * * 1-5")
        self.assertTrue(ok.isEnabled())
        self.assertIn("다음 알림", d.preview.text())
        d._accept()
        self.assertEqual(d.result_reminder["cron"], "0 9 * * 1-5")
        d.cron.setText("0 99 * * *")
        self.assertFalse(ok.isEnabled())

        again = ReminderDialog(None, d.result_reminder, "t")
        self.assertEqual(again.repeat.currentData(), "cron")
        again._clear()
        self.assertTrue(again.cleared)
        self.assertIsNone(again.result_reminder)

    def test_quick_choices_are_in_the_future(self) -> None:
        now = D(2026, 10, 10, 19, 30)
        choices = quick_choices(now)
        self.assertTrue(all(moment > now for _, moment in choices))
        self.assertEqual(choices[-1][1], D(2026, 10, 12, 9, 0))

    def test_popup_buttons(self) -> None:
        opened, snoozed = [], []
        p = ReminderPopup(self.sm.settings, "memo-0000", "title", "detail", opened.append,
                          lambda memo_id, minutes: snoozed.append((memo_id, minutes)))
        p.show()
        buttons = {b.text(): b for b in p.findChildren(test_ui.QPushButton)}
        buttons["1시간"].click()
        self.assertEqual(snoozed, [("memo-0000", 60)])
        self.assertEqual(opened, [])


if __name__ == "__main__":
    unittest.main()
