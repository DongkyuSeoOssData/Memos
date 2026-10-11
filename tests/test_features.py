"""3.2 기능 테스트: 알림(반복·크론식), 변경 기록, 체크리스트, 빠른 검색."""
import datetime as dt
import json
import pathlib
import unittest
from unittest import mock

from PyQt6.QtCore import QDate, QPoint, Qt
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

    def test_weekly_on_several_weekdays(self) -> None:
        now = D(2026, 10, 11, 10, 0)                               # 일요일
        r = reminders.make_repeating("weekly", 9, 0, now, weekdays=[2, 0, 2])
        self.assertEqual(r["weekdays"], [0, 2])
        self.assertEqual(reminders.upcoming(r, 4), [D(2026, 10, 12, 9), D(2026, 10, 14, 9), D(2026, 10, 19, 9), D(2026, 10, 21, 9)])
        self.assertEqual(reminders.describe(r), "10.12(월) 09:00 · 매주 월·수")
        today = reminders.make_repeating("weekly", 11, 0, now, weekdays=[6])
        self.assertEqual(reminders.due_at(today), D(2026, 10, 11, 11, 0))       # 오늘 아직 안 지난 시각이면 오늘부터
        with self.assertRaises(ValueError):
            reminders.make_repeating("weekly", 9, 0, now, weekdays=[])
        with self.assertRaises(ValueError):
            reminders.make_repeating("weekly", 9, 0, now, weekdays=[9])

    def test_monthly_on_several_days(self) -> None:
        now = D(2026, 10, 11, 10, 0)
        r = reminders.make_repeating("monthly", 8, 30, now, days=[31, 1, 15])
        self.assertEqual(reminders.upcoming(r, 5), [D(2026, 10, 15, 8, 30), D(2026, 10, 31, 8, 30), D(2026, 11, 1, 8, 30),
                                                    D(2026, 11, 15, 8, 30), D(2026, 11, 30, 8, 30)])      # 11월은 30일까지
        self.assertEqual(reminders.repeat_text(r), "매월 1·15·31일")
        both = reminders.make_repeating("monthly", 9, 0, D(2027, 2, 1), days=[30, 31])
        self.assertEqual(reminders.upcoming(both, 2), [D(2027, 2, 28, 9), D(2027, 3, 30, 9)])              # 말일로 겹치면 한 번만
        with self.assertRaises(ValueError):
            reminders.make_repeating("monthly", 9, 0, now, days=[])

    def test_daily_and_weekdays_start_at_the_next_time(self) -> None:
        now = D(2026, 10, 9, 10, 0)                                # 금요일
        self.assertEqual(reminders.due_at(reminders.make_repeating("daily", 9, 0, now)), D(2026, 10, 10, 9, 0))
        self.assertEqual(reminders.due_at(reminders.make_repeating("daily", 10, 1, now)), D(2026, 10, 9, 10, 1))
        self.assertEqual(reminders.due_at(reminders.make_repeating("weekdays", 9, 0, now)), D(2026, 10, 12, 9, 0))
        with self.assertRaises(ValueError):
            reminders.make_repeating("cron", 9, 0, now)

    def test_reminders_saved_by_older_versions_still_work(self) -> None:
        old_monthly = {"at": "2026-01-31T09:00:00", "repeat": "monthly", "cron": "", "day": 31}
        self.assertEqual(reminders.normalize(old_monthly)["days"], [31])
        old_weekly = {"at": "2026-10-09T09:00:00", "repeat": "weekly", "cron": ""}
        self.assertEqual(reminders.normalize(old_weekly)["weekdays"], [4])
        self.assertEqual(reminders.due_at(reminders.following(old_weekly, D(2026, 10, 9, 9, 1))), D(2026, 10, 16, 9, 0))

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


class TimeInputTest(test_ui.UiTestCase):
    def test_12_hour_mode_shows_am_pm(self) -> None:
        from ui.reminder_ui import TimeInput
        t = TimeInput(15, 5, use_24h=False)
        self.addCleanup(t.close)
        t.show()
        self.assertTrue(t.btn_am.isVisible() and t.btn_pm.isVisible())
        self.assertEqual((t.hour.text(), t.minute.text(), t.btn_pm.isChecked()), ("3", "05", True))
        self.assertEqual(t.time(), (15, 5))
        t.btn_am.click()
        self.assertEqual(t.time(), (3, 5))
        t.set_time(0, 0)
        self.assertEqual((t.hour.text(), t.btn_am.isChecked(), t.time()), ("12", True, (0, 0)))      # 오전 12시 = 0시
        t.set_time(12, 0)
        self.assertEqual((t.hour.text(), t.btn_pm.isChecked(), t.time()), ("12", True, (12, 0)))      # 오후 12시 = 정오

    def test_typing_numbers_moves_on_and_understands_24_hour_values(self) -> None:
        from ui.reminder_ui import TimeInput
        t = TimeInput(9, 0, use_24h=False)
        self.addCleanup(t.close)
        t.show()
        moved = []
        t.minute.setFocus = lambda *a: moved.append(True)            # 분 칸으로 넘어가는지 지켜봄

        def type_hour(text: str) -> None:
            t.hour.selectAll()
            QTest.keyClicks(t.hour, text)

        type_hour("7")                                               # 한 자리로 정해지면 바로 분 칸으로
        self.assertEqual(moved, [True])
        t.minute.selectAll()
        QTest.keyClicks(t.minute, "45")
        self.assertEqual(t.time(), (7, 45))
        type_hour("15")                                              # 24시간식으로 적으면 오후 3시로
        self.assertEqual((t.hour.text(), t.btn_pm.isChecked(), t.time()), ("3", True, (15, 45)))
        del moved[:]
        type_hour("1")                                               # 10~12 일 수 있으니 기다림
        self.assertEqual(moved, [])
        QTest.keyClicks(t.hour, "1")
        self.assertEqual(moved, [True])
        self.assertEqual(t.time(), (23, 45))                         # 오후 11시

        day = TimeInput(9, 0, use_24h=True)
        self.addCleanup(day.close)
        day.show()
        seen = []
        day.minute.setFocus = lambda *a: seen.append(True)
        day.hour.selectAll()
        QTest.keyClicks(day.hour, "2")                               # 20~23 일 수 있으니 기다림
        self.assertEqual(seen, [])
        QTest.keyClicks(day.hour, "1")
        self.assertEqual((seen, day.time()), ([True], (21, 0)))

    def test_24_hour_mode_and_switching(self) -> None:
        from ui.reminder_ui import TimeInput
        t = TimeInput(15, 30, use_24h=True)
        self.addCleanup(t.close)
        t.show()
        self.assertFalse(t.btn_am.isVisible())
        self.assertEqual((t.hour.text(), t.time()), ("15", (15, 30)))
        changes = []
        t.format_changed.connect(changes.append)
        t.check_24h.setChecked(False)
        self.assertEqual((t.hour.text(), t.btn_pm.isChecked(), t.btn_pm.isVisible(), t.time()), ("3", True, True, (15, 30)))
        t.check_24h.setChecked(True)
        self.assertEqual((t.hour.text(), t.time(), changes), ("15", (15, 30), [False, True]))
        for hour, minute in (("24", "00"), ("9", "60"), ("", "10")):
            t.hour.setText(hour)
            t.minute.setText(minute)
            self.assertIsNone(t.time(), (hour, minute))

    def test_choice_is_remembered_and_changes_how_times_are_shown(self) -> None:
        self.addCleanup(reminders.set_ampm, False)
        d = ReminderDialog(None, None, "t")
        self.addCleanup(d.close)
        self.assertTrue(d.time.is_24h())                             # 시험 설정은 24시간제
        r = reminders.make(D(2031, 3, 4, 15, 30))
        self.assertEqual(reminders.describe(r), "3.04(화) 15:30")
        d.time.check_24h.setChecked(False)
        self.assertFalse(self.sm.settings["time_24h"])
        self.assertEqual(reminders.describe(r), "3.04(화) 오후 3:30")
        self.assertFalse(ReminderDialog(None, None, "t").time.is_24h())
        d.time.check_24h.setChecked(True)
        self.assertEqual(reminders.describe(r), "3.04(화) 15:30")


class ChecklistProgressTest(test_ui.UiTestCase):
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

    def test_history_opens_beside_the_memo_and_restores(self) -> None:
        from PyQt6.QtCore import QTimer
        w = self.open_window("memo-0000")
        w.text_edit.setPlainText("rewritten")
        w.text_edit.document().setModified(True)
        w.execute_auto_save()
        seen = {}

        def steps() -> None:
            side = w.side_panel()
            view = side.panel
            seen["visible"] = side.isVisible()
            seen["attached"] = abs(side.x() - (w.bg.mapToGlobal(QPoint(0, 0)).x() + w.bg.width() - 1)) <= 1      # 메모 오른쪽에 붙음
            seen["same_color"] = w.memo_bg_color().lower() in side.styleSheet().lower()
            seen["tall_enough"] = side.height() >= 460
            view.list.setCurrentRow(0)
            view._restore()

        QTimer.singleShot(0, steps)
        w.show_history()
        self.assertEqual(seen, {"visible": True, "attached": True, "same_color": True, "tall_enough": True})
        self.assertEqual(w.text_edit.toPlainText(), "body 0 #tag0")
        self.assertEqual(self.sm.list_history("memo-0000")[0]["text"], "rewritten")
        self.assertFalse(w.side_panel().isVisible())

    def test_history_panel_closes_with_the_memo(self) -> None:
        from PyQt6.QtCore import QTimer
        w = self.open_window("memo-0000")
        QTimer.singleShot(0, w.hide)                                 # 메모를 숨기면 옆 패널도 닫히고 기다림이 끝남
        w.show_history()
        self.assertFalse(w.side_panel().isVisible())
        self.assertEqual(w.text_edit.toPlainText(), "body 0 #tag0")

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


class StrikeThroughTest(test_ui.UiTestCase):
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


class ExplorerWidthTest(test_ui.UiTestCase):
    """폴더 이름이 길거나 폴더가 많아도 탐색기를 강제로 넓히지 않습니다."""

    def test_folder_ui_never_widens_the_explorer(self) -> None:
        names = ["업무", "업무/아주아주긴하위폴더이름입니다", "개인", "이름이정말정말정말긴폴더"] + [f"폴더{i}" for i in range(12)]
        self.sm.save_settings({"folders": names, "folder_sidebar_open": False})
        ex = self.explorer()
        ex.resize(ex.MIN_WIDTH, ex.height())
        test_ui._app.processEvents()
        for mode in ("tabs", "dropdown", "sidebar"):
            self.sm.save_settings({"folder_ui": mode})
            for folder in ("", "업무", "업무/아주아주긴하위폴더이름입니다", "이름이정말정말정말긴폴더"):
                ex.current_folder = folder
                ex.refresh()
                test_ui._app.processEvents()
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


class ThemedWindowTest(test_ui.UiTestCase):
    """확인·입력·알림을 Windows 기본 창이 아니라 앱 자체 창과 토스트로 보여 줍니다."""

    def test_dialogs_have_their_own_title_bar(self) -> None:
        from ui.dialogs import ConflictDialog, FolderPickDialog
        from ui.themed_dialog import ColorDialog, ThemedDialog
        ex = self.explorer()
        dialogs = [ReminderDialog(ex, None, "t"), HistoryDialog(ex, "t", []), FolderPickDialog(ex, ["a"], {}),
                   ConflictDialog("t", "a", "b", ex), ColorDialog(ex, "색")]
        for d in dialogs:
            self.addCleanup(d.close)
            self.assertIsInstance(d, ThemedDialog)
            self.assertTrue(d.windowFlags() & Qt.WindowType.FramelessWindowHint, type(d).__name__)
            self.assertTrue(d.title_label.text())
            self.assertIn("ThemedDialog", d.styleSheet())

    def test_no_native_message_boxes_are_left(self) -> None:
        import pathlib
        for path in pathlib.Path(test_ui.uim.__file__).parent.glob("*.py"):
            source = path.read_text(encoding="utf-8")
            for name in ("QMessageBox", "QInputDialog", "QColorDialog"):
                self.assertNotIn(name, source, path.name)

    def test_form_panel_keeps_asking_until_valid(self) -> None:
        from ui.themed_dialog import FormPanel
        got = []
        panel = FormPanel("t", "", [{"label": "a", "password": True}, {"label": "b", "password": True}],
                          validate=lambda v: None if v[0] == v[1] else "다릅니다")
        self.addCleanup(panel.close)
        panel.submitted.connect(got.append)
        panel.show()
        panel.inputs[0].setText("x")
        panel.inputs[1].setText("y")
        panel.submit()
        self.assertEqual(got, [])
        self.assertTrue(panel.error.isVisible())
        self.assertIn("다릅니다", panel.error.text())
        panel.inputs[1].setText("x")
        QTest.keyClick(panel.inputs[1], Qt.Key.Key_Return)             # 마지막 칸에서 Enter = 확인
        self.assertEqual(got, [["x", "x"]])

    def test_color_dialog(self) -> None:
        from ui.themed_dialog import ColorDialog
        d = ColorDialog(None, "색", "#112233")
        self.addCleanup(d.close)
        self.assertEqual(d.color().name(), "#112233")
        d.swatches[9].click()
        self.assertEqual(d.color().name().upper(), "#FF0000")
        d.code.setText("nope")
        self.assertIsNone(d.color())
        self.assertFalse(d.ok_button.isEnabled())

    def test_settings_window_reports_with_its_own_toast(self) -> None:
        win = test_ui.sw.SettingsWindow(self.sm)
        self.addCleanup(win.close)
        win.show()
        win.save()
        self.assertTrue(win.toast.isVisible())
        self.assertIn("저장", win.toast.toolTip())
        win.url_input.setText("not a url")
        win.test_gas_url()
        self.assertTrue(win.toast.toolTip().startswith("⚠"))
        self.assertEqual(self.warnings, [])                          # 창을 따로 띄우지 않음

    def test_folder_display_option_is_on_the_general_tab(self) -> None:
        win = test_ui.sw.SettingsWindow(self.sm)
        self.addCleanup(win.close)
        general = win.tabs.widget(0)
        self.assertEqual(win.tabs.tabText(0).strip(), "일반 설정")
        self.assertTrue(general.isAncestorOf(win.folder_ui_box))

    def test_duplicate_title_is_a_toast_in_the_memo(self) -> None:
        w = self.open_window("memo-0000")
        w.show_toast("안내")
        self.assertEqual(w.toast_label.text(), "안내")
        w.show_toast("문제", warn=True)
        self.assertEqual(w.toast_label.text(), "⚠ 문제")


class LockOverlayTest(test_ui.UiTestCase):
    """암호는 따로 창을 띄우지 않고 메모 창 안에서 묻습니다."""

    def setUp(self) -> None:
        super().setUp()
        from ui import lock_overlay
        self.lock_overlay = lock_overlay
        self.real_ask = self.real_form_ask
        self.w = self.open_window("memo-0000")
        self.w.resize(360, 380)
        test_ui._app.processEvents()

    def drive(self, steps) -> None:
        """입력 묶음이 뜨면 steps(panel) 을 실행합니다. (입력을 기다리는 동안 실행되도록 예약)"""
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(0, lambda: steps(self.w.lock_overlay.panel))

    def test_setting_a_password_happens_inside_the_memo(self) -> None:
        seen = {}

        def steps(panel) -> None:
            seen["overlay"] = self.w.lock_overlay.isVisible()
            seen["blurred"] = self.w.text_edit.graphicsEffect() is not None
            seen["parent"] = self.w.lock_overlay.isAncestorOf(panel)
            panel.inputs[0].setText("pw12")
            panel.inputs[1].setText("nope")
            panel.submit()
            seen["error"] = panel.error.text()
            panel.inputs[1].setText("pw12")
            panel.submit()

        self.drive(steps)
        with mock.patch.object(self.lock_overlay, "ask", self.real_ask):
            self.w.set_memo_password()
        self.assertEqual(seen, {"overlay": True, "blurred": True, "parent": True, "error": "⚠ 두 암호가 일치하지 않습니다."})
        self.assertTrue(self.disk("memo-0000")["is_locked"])
        self.assertIsNone(self.w.text_edit.graphicsEffect())         # 끝나면 흐림을 걷음
        self.assertTrue(self.w.lock_overlay.isHidden())

    def test_locked_memo_shows_a_password_box_in_the_middle_and_unlocks_in_place(self) -> None:
        self.answers[:] = ["pw12", "pw12"]
        self.w.set_memo_password()
        self.w.lock_now()
        overlay = self.w.lock_overlay
        panel = overlay.unlock_panel
        self.assertTrue(overlay.isVisible() and panel.isVisible())
        self.assertEqual(overlay.geometry().size(), self.w.text_edit.size())
        test_ui._app.processEvents()
        self.assertLessEqual(abs(panel.geometry().center().x() - overlay.rect().center().x()), 1)     # 한가운데
        self.assertLessEqual(abs(panel.geometry().center().y() - overlay.rect().center().y()), 1)
        self.assertIsNone(panel.cancel_button)

        panel.inputs[0].setText("wrong")
        QTest.keyClick(panel.inputs[0], Qt.Key.Key_Return)
        self.assertEqual(panel.error.text(), "⚠ 암호가 일치하지 않습니다.")
        self.assertTrue(self.w.memo_data.get("_locked"))
        panel.inputs[0].setText("pw12")
        QTest.keyClick(panel.inputs[0], Qt.Key.Key_Return)
        self.assertFalse(self.w.memo_data.get("_locked"))
        self.assertTrue(overlay.isHidden())
        self.assertIsNone(overlay.unlock_panel)
        self.assertEqual(self.w.text_edit.toPlainText(), "body 0 #tag0")

    def test_opening_a_locked_memo_from_the_explorer_never_pops_a_prompt(self) -> None:
        self.answers[:] = ["pw12", "pw12"]
        self.w.set_memo_password()
        self.w.lock_now()
        asked = []
        with mock.patch.object(self.lock_overlay, "ask", lambda *a, **k: asked.append(a)):
            # 펼친 메모: 암호 칸이 있는 화면으로 열림
            self.w.hide()
            self.ui.show_specific_memo("memo-0000")
            test_ui._app.processEvents()
            self.assertTrue(self.w.isVisible() and self.w.lock_overlay.unlock_panel.isVisible())
            # 접은 메모: 접힌 그대로 열리고 아무것도 묻지 않음. 펼치면 암호 칸이 나타남
            self.w.toggle_rollup()
            self.w.hide()
            self.ui.show_specific_memo("memo-0000")
            test_ui._app.processEvents()
            self.assertTrue(self.w.isVisible() and self.w._is_rolled_up)
            self.assertTrue(self.w.lock_overlay.isHidden())
            self.w.toggle_rollup()
            self.assertTrue(self.w.lock_overlay.unlock_panel.isVisible())
        self.assertEqual(asked, [])
        self.assertTrue(self.w.memo_data.get("_locked"))

    def test_cancel_leaves_everything_as_it_was(self) -> None:
        self.drive(lambda panel: panel.cancel_button.click())
        with mock.patch.object(self.lock_overlay, "ask", self.real_ask):
            self.w.set_memo_password()
        self.assertFalse(self.disk("memo-0000").get("is_locked"))
        self.assertTrue(self.w.lock_overlay.isHidden())
        self.assertIsNone(self.w.text_edit.graphicsEffect())

    def test_tiny_memo_asks_beside_itself(self) -> None:
        from PyQt6.QtCore import QTimer
        self.w.resize(200, 150)
        test_ui._app.processEvents()
        seen = {}

        def steps() -> None:
            side = self.w.side_panel()
            seen["beside"] = side.isVisible() and side.panel is not None
            side.panel.inputs[0].setText("pw12")
            side.panel.inputs[1].setText("pw12")
            side.panel.submit()

        QTimer.singleShot(0, steps)
        with mock.patch.object(self.lock_overlay, "ask", self.real_ask):
            self.w.set_memo_password()
        self.assertEqual(seen, {"beside": True})
        self.assertTrue(self.disk("memo-0000")["is_locked"])

    def test_password_form_is_centered(self) -> None:
        seen = {}

        def steps(panel) -> None:
            overlay = self.w.lock_overlay
            test_ui._app.processEvents()
            seen["dx"] = abs(panel.geometry().center().x() - overlay.rect().center().x()) <= 1
            seen["dy"] = abs(panel.geometry().center().y() - overlay.rect().center().y()) <= 1
            panel.cancel_button.click()

        self.drive(steps)
        with mock.patch.object(self.lock_overlay, "ask", self.real_ask):
            self.w.set_memo_password()
        self.assertEqual(seen, {"dx": True, "dy": True})

    def test_rolled_or_tiny_memo_cannot_host_the_form(self) -> None:
        overlay = self.w.lock_overlay
        self.assertTrue(overlay.can_host(230, 220))
        self.w.toggle_rollup()
        self.assertFalse(overlay.can_host(230, 100))                 # 접힌 메모는 대화상자로 묻음
        self.w.toggle_rollup()
        self.w.resize(200, 150)
        test_ui._app.processEvents()
        self.assertFalse(overlay.can_host(230, 220))

    def test_locked_overlay_hides_while_rolled_up(self) -> None:
        self.answers[:] = ["pw12", "pw12"]
        self.w.set_memo_password()
        self.w.lock_now()
        self.w.toggle_rollup()
        self.assertTrue(self.w.lock_overlay.isHidden())
        self.w.toggle_rollup()
        self.assertTrue(self.w.lock_overlay.isVisible())


class InlineAndFixesTest(test_ui.UiTestCase):
    def test_confirm_and_name_input_happen_inside_the_explorer(self) -> None:
        from PyQt6.QtCore import QTimer
        from ui import themed_dialog
        ex = self.explorer()
        ex.resize(720, 640)
        test_ui._app.processEvents()
        seen = {}

        def press(which: str) -> None:
            overlay = ex.inline_overlay
            seen[which] = overlay.isVisible() and overlay.panel is not None
            (overlay.panel.ok_button if which != "no" else overlay.panel.cancel_button).click()

        confirm = self.real["confirm"]
        QTimer.singleShot(0, lambda: press("yes"))
        self.assertTrue(confirm(ex, "삭제", "지울까요?", ok_text="삭제", danger=True))
        QTimer.singleShot(0, lambda: press("no"))
        self.assertFalse(confirm(ex, "삭제", "지울까요?"))
        self.assertEqual(seen, {"yes": True, "no": True})
        self.assertTrue(ex.inline_overlay.isHidden())

        def type_name() -> None:
            panel = ex.inline_overlay.panel
            panel.inputs[0].setText("업무/새폴더")
            panel.submit()

        QTimer.singleShot(0, type_name)
        self.assertEqual(self.real["ask_form"](ex, "새 폴더", "", [{"label": "폴더 이름"}]), ["업무/새폴더"])
        self.assertIsNotNone(themed_dialog.NO_HOST)

    def test_color_is_picked_inside_the_memo(self) -> None:
        from PyQt6.QtCore import QTimer
        w = self.open_window("memo-0000")
        w.resize(380, 460)
        test_ui._app.processEvents()
        w.text_edit.setPlainText("mark me")
        w.text_edit.selectAll()
        seen = {}

        def steps() -> None:
            panel = w.lock_overlay.panel
            seen["inside"] = w.lock_overlay.isVisible() and w.lock_overlay.isAncestorOf(panel)
            panel.code.setText("#12AB34")
            panel.submit()

        QTimer.singleShot(0, steps)
        w.choose_bg_color()                                          # 형광펜 '사용자 지정 색'
        self.assertEqual(seen, {"inside": True})
        probe = QTextCursor(w.text_edit.document())
        probe.setPosition(3)
        self.assertEqual(probe.charFormat().background().color().name().upper(), "#12AB34")

        QTimer.singleShot(0, lambda: w.lock_overlay.panel.cancel_button.click())
        w.choose_fg_color()                                          # 취소하면 그대로
        self.assertTrue(w.lock_overlay.isHidden())

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

    def test_rolled_password_memo_shows_a_lock(self) -> None:
        w = self.open_window("memo-0000")
        self.assertTrue(w.lbl_lock.isHidden())
        self.answers[:] = ["pw12", "pw12"]
        w.set_memo_password()
        self.assertTrue(w.lbl_lock.isHidden())                       # 펼쳐져 있을 때는 본문 쪽에서 알 수 있음
        w.toggle_rollup()
        self.assertFalse(w.lbl_lock.isHidden())
        w.toggle_rollup()
        self.assertTrue(w.lbl_lock.isHidden())

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

    def test_preview_edit_keeps_the_date_format(self) -> None:
        ex = self.explorer()
        row = self.row_of(ex, "memo-0001")
        ex.table.setCurrentCell(row, 2)
        ex.on_cell_click(row, 2)
        ex.pv.setPlainText("edited")
        text = ex.table.item(ex.table.currentRow(), 3).text()
        self.assertRegex(text, r"^\d\d\.\d\d\.\d\d \d\d:\d\d$")

    def test_preview_menu(self) -> None:
        ex = self.explorer()
        row = self.row_of(ex, "memo-0001")
        ex.table.setCurrentCell(row, 2)
        ex.on_cell_click(row, 2)
        labels = [text for text, _, _ in ex.preview_menu_actions() if text]
        self.assertEqual(labels, ["메모 열기", "체크리스트 켜기/끄기", "복사", "붙여넣기", "모두 선택", "전체 내용 복사",
                                  "⏰ 알림 설정…", "이전 내용 보기…"])
        actions = {text: (run, enabled) for text, run, enabled in ex.preview_menu_actions() if text}
        self.assertFalse(actions["복사"][1])                         # 고른 글자가 없으면 못 누름
        actions["체크리스트 켜기/끄기"][0]()
        self.assertTrue(ex.pv.toPlainText().startswith("☐ "))
        actions["메모 열기"][0]()
        self.assertIn("memo-0001", self.ui.memo_windows)

        w = self.ui.memo_windows["memo-0001"]
        self.answers[:] = ["pw12", "pw12"]
        w.set_memo_password()
        w.lock_now()
        ex.refresh()
        row = self.row_of(ex, "memo-0001")
        ex.table.setCurrentCell(row, 2)
        ex.on_cell_click(row, 2)
        self.assertEqual([text for text, _, _ in ex.preview_menu_actions()], ["🔓 잠금 해제 (암호 입력)"])

    def test_font_can_be_searched_and_size_typed(self) -> None:
        w = self.open_window("memo-0000")
        self.assertTrue(w.font_box.isEditable() and w.size_box.isEditable())
        if w.font_box.count() < 2:                                   # 화면 없는 시험 환경에는 글꼴 목록이 비어 있음
            w.font_box.addItems(["Alpha Sans", "Beta Mono"])
        families = [w.font_box.itemText(i) for i in range(w.font_box.count())]
        target = next((f for f in families if f != (w.memo_data.get("font_family") or "")), families[0])
        w.font_box.setEditText(target[:max(3, len(target) - 1)].upper())      # 이름의 일부만, 대소문자 달라도
        w.font_box.lineEdit().editingFinished.emit()
        self.assertIn(target[:3].lower(), w.memo_data["font_family"].lower())
        applied = w.memo_data["font_family"]
        w.font_box.setEditText("no such font zzz")
        w.font_box.lineEdit().editingFinished.emit()
        self.assertEqual((w.memo_data["font_family"], w.font_box.currentText()), (applied, applied))   # 없는 이름은 되돌림

        w.size_box.setEditText("17")
        w.size_box.lineEdit().editingFinished.emit()
        self.assertEqual(w.memo_data["font_size"], 17)
        w.size_box.setEditText("300")
        w.size_box.lineEdit().editingFinished.emit()
        self.assertEqual((w.memo_data["font_size"], w.size_box.currentText()), (17, "17"))

    def test_duplicate_shortcut_clears_the_other_one(self) -> None:
        from PyQt6.QtGui import QKeySequence
        win = test_ui.sw.SettingsWindow(self.sm)
        self.addCleanup(win.close)
        win.show()
        edits = {win.shortcut_table.item(r, 0).data(Qt.ItemDataRole.UserRole): win.shortcut_table.cellWidget(r, 1)
                 for r in range(win.shortcut_table.rowCount())}
        taken = edits["open_explorer"].keySequence().toString()
        edits["new_memo"].setKeySequence(QKeySequence(taken))
        cleared = win._resolve_shortcut_conflict(edits["new_memo"])
        self.assertEqual(len(cleared), 1)
        self.assertEqual(edits["open_explorer"].keySequence().toString(), "")            # 겹친 쪽을 비움
        self.assertEqual(edits["new_memo"].keySequence().toString(), taken)
        self.assertTrue(win.toast.isVisible() and win.toast.toolTip().startswith("⚠"))
        win.save()
        self.assertEqual((self.sm.settings["shortcuts"]["new_memo"], self.sm.settings["shortcuts"]["open_explorer"]), (taken, ""))
        self.assertEqual(win._resolve_shortcut_conflict(edits["new_memo"]), [])            # 겹치는 것이 없으면 그대로


class LayoutAndGuideTest(test_ui.UiTestCase):
    def test_first_run_leaves_guide_memos(self) -> None:
        from core import guide
        for path in self.memo_dir.glob("*.json"):
            path.unlink()
        self.ui.show_all_memos()
        memos = {m["id"]: m for m in self.sm.load_local_memos()}
        self.assertEqual(sorted(memos), ["guide-explorer", "guide-memo", "guide-settings"])
        self.assertTrue(all(m["folder"] == guide.FOLDER and m["content"].strip() for m in memos.values()))
        self.assertIn(guide.FOLDER, self.sm.settings["folders"])
        self.assertTrue(self.sm.settings["guide_memos_made"])
        self.assertEqual(list(self.ui.memo_windows), ["guide-memo"])           # 첫 안내만 화면에 띄움
        ex = self.explorer()
        ex.refresh()
        self.assertEqual(ex.table.item(0, 2).data(Qt.ItemDataRole.UserRole)["id"], "guide-memo")     # ①이 맨 위

        # 읽고 지운 뒤에는 다시 만들지 않음
        for w in list(self.ui.memo_windows.values()):
            w._is_deleting = True
            w.close()
        self.ui.memo_windows.clear()
        for path in self.memo_dir.glob("*.json"):
            path.unlink()
        self.ui.show_all_memos()
        self.assertFalse(any(m["id"].startswith("guide-") for m in self.sm.load_local_memos()))
        # 트레이 메뉴로는 다시 만들 수 있음
        self.ui.remake_guide_memos()
        self.assertEqual(len([m for m in self.sm.load_local_memos() if m["id"].startswith("guide-")]), 3)
        self.assertIn("guide-memo", self.ui.memo_windows)

    def test_existing_users_do_not_get_guides(self) -> None:
        self.assertFalse(any(m["id"].startswith("guide-") for m in self.sm.load_local_memos()))
        self.assertNotIn("guide_memos_made", self.sm.settings)

    def test_guide_checklist_is_usable(self) -> None:
        from core import guide
        self.assertEqual(checklist.progress(guide.MEMO_GUIDE)[1], 4)
        for memo in guide.build(D(2026, 1, 1)):
            self.assertTrue(test_ui.smm.is_safe_memo_id(memo["id"]) if hasattr(test_ui.smm, "is_safe_memo_id") else True)

    def test_settings_opens_as_a_panel_inside_the_explorer(self) -> None:
        ex = self.explorer()
        ex.move(300, 200)
        ex.resize(700, 600)
        test_ui._app.processEvents()
        before = ex.geometry()
        content = ex.content_width()
        table_left = ex.table.mapToGlobal(QPoint(0, 0)).x()
        self.ui.open_settings()
        test_ui._app.processEvents()
        panel = self.ui.settings_window
        self.assertIs(panel, ex.settings_panel)
        self.assertIs(panel.window(), ex)                            # 따로 뜬 창이 아니라 탐색기 창의 일부
        self.assertTrue(ex.bg.isAncestorOf(panel) and panel.isVisible())
        extra = ex.SETTINGS_WIDTH + ex.SIDEBAR_GAP
        self.assertEqual((ex.x(), ex.y(), ex.width(), ex.height()), (before.x(), before.y(), before.width() + extra, before.height()))
        self.assertEqual(ex.content_width(), content)                # 탐색기 본래 영역의 크기와 자리는 그대로
        self.assertEqual(ex.table.mapToGlobal(QPoint(0, 0)).x(), table_left)
        self.assertGreater(panel.mapTo(ex, QPoint(0, 0)).x(), ex.table.mapTo(ex, QPoint(0, 0)).x())     # 오른쪽에 붙음
        self.assertTrue(panel.btn_win_min.isHidden() and panel.grip.isHidden())
        self.assertIn("border: none", panel.styleSheet())

        panel.btn_win_close.click()                                  # 패널의 닫기는 패널만 닫음
        test_ui._app.processEvents()
        self.assertTrue(ex.isVisible())
        self.assertIsNone(ex.settings_panel)
        self.assertEqual(ex.geometry(), before)

    def test_settings_panel_goes_left_when_there_is_no_room_on_the_right(self) -> None:
        ex = self.explorer()
        ex.resize(700, 600)
        ex.move(4000 - ex.width(), 200)
        test_ui._app.processEvents()
        right_edge = ex.x() + ex.width()
        table_left = ex.table.mapToGlobal(QPoint(0, 0)).x()
        self.ui.open_settings()
        test_ui._app.processEvents()
        panel = ex.settings_panel
        self.assertEqual(ex._settings_side, "left")
        self.assertEqual(ex.x() + ex.width(), right_edge)            # 오른쪽 끝은 그대로, 왼쪽으로 늘어남
        self.assertEqual(ex.table.mapToGlobal(QPoint(0, 0)).x(), table_left)
        self.assertLess(panel.mapTo(ex, QPoint(0, 0)).x(), ex.table.mapTo(ex, QPoint(0, 0)).x())
        ex.close_settings_panel()
        self.assertEqual(ex.x() + ex.width(), right_edge)

    def test_settings_panel_closes_with_the_explorer_and_is_not_saved_into_its_size(self) -> None:
        ex = self.explorer()
        ex.move(300, 200)
        ex.resize(700, 600)
        test_ui._app.processEvents()
        self.ui.open_settings()
        ex.close()
        test_ui._app.processEvents()
        self.assertIsNone(ex.settings_panel)
        self.assertIsNone(self.ui.settings_window)
        self.assertEqual(self.sm.settings["explorer_geom"][2:], [700, 600])     # 패널 너비가 탐색기 크기로 저장되지 않음
        ex.show()
        self.assertEqual(ex.width(), 700)

        self.ui.open_settings()
        ex.hide()                                                    # Alt+W 로 숨겨도 닫힘
        test_ui._app.processEvents()
        self.assertIsNone(ex.settings_panel)

    def test_opening_settings_from_the_tray_brings_up_the_explorer(self) -> None:
        self.assertIsNone(self.ui.explorer_window)
        self.ui.open_settings()                                      # 탐색기가 닫혀 있어도
        ex = self.ui.explorer_window
        self.assertTrue(ex.isVisible() and ex.settings_open())       # 탐색기와 함께 열림

    def test_saving_in_the_panel_keeps_it_open_and_the_size_right(self) -> None:
        ex = self.explorer()
        ex.resize(700, 600)
        test_ui._app.processEvents()
        self.ui.open_settings()
        panel = ex.settings_panel
        content = ex.content_width()
        panel.save()
        test_ui._app.processEvents()
        self.assertIs(ex.settings_panel, panel)
        self.assertTrue(panel.isVisible() and panel.toast.isVisible())
        self.assertEqual(ex.content_width(), content)
        self.assertEqual(ex.width(), content + ex.SETTINGS_WIDTH + ex.SIDEBAR_GAP)

    def test_folder_sidebar_and_settings_panel_work_together(self) -> None:
        self.sm.save_settings({"folder_ui": "sidebar", "folder_sidebar_open": True})
        ex = self.explorer()
        ex.resize(ex.width(), 600)
        ex.move(900, 200)
        ex.refresh()
        test_ui._app.processEvents()
        content, sidebar = ex.content_width(), ex._sidebar_extra
        self.assertGreater(sidebar, 0)
        self.ui.open_settings()
        self.assertEqual(ex.content_width(), content)
        self.assertEqual(ex.width(), content + sidebar + ex.SETTINGS_WIDTH + ex.SIDEBAR_GAP)
        ex.toggle_folder_sidebar()                                   # 패널이 열린 채로 사이드바를 접어도
        self.assertEqual(ex.content_width(), content)
        self.assertTrue(ex.settings_open())
        ex.close_settings_panel()
        self.assertEqual(ex.width(), content)

    def test_quick_choice_rows_are_stacked(self) -> None:
        win = test_ui.sw.SettingsWindow(self.sm)
        self.addCleanup(win.close)
        win.show()
        test_ui._app.processEvents()
        tops = [spin.mapTo(win, QPoint(0, 0)).y() for spin in win.quick_minute_spins]
        lefts = {spin.mapTo(win, QPoint(0, 0)).x() for spin in win.quick_minute_spins}
        self.assertEqual(tops, sorted(set(tops)))                    # 한 줄에 하나씩 아래로
        self.assertEqual(len(lefts), 1)

    def test_lock_badge_sits_at_the_left_of_the_title(self) -> None:
        w = self.open_window("memo-0000")
        self.answers[:] = ["pw12", "pw12"]
        w.set_memo_password()
        w.toggle_rollup()
        test_ui._app.processEvents()
        self.assertFalse(w.lbl_lock.isHidden())
        self.assertEqual(w.lbl_lock.mapTo(w, QPoint(0, 0)).x(), w.title_edit.mapTo(w, QPoint(0, 0)).x())    # 제목 칸의 왼쪽 끝
        self.assertEqual(w.title_edit.textMargins().left(), w.LOCK_BADGE_WIDTH)                              # 제목 글자는 그 오른쪽부터
        w.toggle_rollup()
        self.assertTrue(w.lbl_lock.isHidden())
        self.assertEqual(w.title_edit.textMargins().left(), 0)

    def test_adding_a_password_never_widens_a_rolled_memo(self) -> None:
        w = self.open_window("memo-0000")
        w.setGeometry(100, 100, 500, 400)
        w.toggle_rollup()
        w.resize(10, w.height())                                     # 줄일 수 있는 데까지 좁게 접어 둔 메모
        test_ui._app.processEvents()
        narrowest, needed = w.width(), w.minimumSizeHint().width()
        self.assertLess(narrowest, 500)
        self.answers[:] = ["pw12", "pw12"]
        w.set_memo_password()                                        # 접힌 채로 암호를 걸면
        test_ui._app.processEvents()
        self.assertFalse(w.lbl_lock.isHidden())                      # 자물쇠가 바로 보이고
        self.assertEqual((w.width(), w.minimumSizeHint().width()), (narrowest, needed))      # 너비는 그대로
        w.lock_now()
        test_ui._app.processEvents()
        self.assertEqual((w.width(), w.minimumSizeHint().width(), w.memo_data["rolled_width"]), (narrowest, needed, narrowest))
        self.answers[:] = ["pw12"]
        w.prompt_unlock()
        self.answers[:] = []
        w.remove_memo_password()                                     # 암호를 없애면 자물쇠도 사라지고 너비는 그대로
        test_ui._app.processEvents()
        self.assertTrue(w.lbl_lock.isHidden())
        self.assertEqual(w.width(), narrowest)

    def test_font_and_size_have_separate_dropdown_buttons(self) -> None:
        w = self.open_window("memo-0000")
        w.toggle_sub_fmt_panel()
        test_ui._app.processEvents()
        for box, button in ((w.font_box, w.btn_font_drop), (w.size_box, w.btn_size_drop)):
            self.assertIn("drop-down { width: 0px", box.styleSheet())                   # 칸 안의 화살표는 없앰
            self.assertEqual(button.mapTo(w, QPoint(0, 0)).x(), box.mapTo(w, QPoint(0, 0)).x() + box.width())     # 칸 바로 오른쪽
            opened = []
            box.showPopup = lambda opened=opened: opened.append(True)
            button.clicked.disconnect()
            button.clicked.connect(lambda checked=False, b=box: b.showPopup())
            button.click()
            self.assertEqual(opened, [True])

    def test_checklist_button_uses_the_drawn_box_icon(self) -> None:
        w = self.open_window("memo-0000")
        self.assertEqual(w.btn_check.text(), "")
        self.assertFalse(w.btn_check.icon().isNull())

    def test_selecting_text_never_shows_the_raw_box_letter(self) -> None:
        w = self.open_window("memo-0000")
        w.resize(360, 300)
        w.text_edit.setPlainText("☐ milk\n☑ eggs\nplain")
        test_ui._app.processEvents()
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

    def test_history_shows_titles_first_and_body_on_click(self) -> None:
        from ui.dialogs import HistoryView
        entries = [{"index": 1, "saved_at": "2026-10-11T08:29:00", "reason": "", "title": "둘째", "locked": False, "text": "second body"},
                   {"index": 0, "saved_at": "2026-10-10T07:00:00", "reason": "", "title": "첫째", "locked": True, "text": ""}]
        view = HistoryView("메모", entries)
        self.addCleanup(view.close)
        view.show()
        changed = []
        view.layout_changed.connect(lambda: changed.append(True))
        self.assertTrue(view.detail.isHidden())                      # 처음에는 목록만
        self.assertEqual(view.list.item(0).text(), "10.11 08:29" + chr(10) + "둘째")
        self.assertIn("암호 메모", view.list.item(1).text())
        view.list.setCurrentRow(0)
        self.assertFalse(view.detail.isHidden())                     # 고르면 오른쪽에 본문이 펼쳐짐
        self.assertEqual((view.preview.toPlainText(), changed), ("second body", [True]))
        self.assertGreater(view.detail.mapTo(view, QPoint(0, 0)).x(), view.list.mapTo(view, QPoint(0, 0)).x() + view.list.width() - 1)
        got = []
        view.submitted.connect(got.append)
        view.restore_button.click()
        self.assertEqual(got, [1])

        empty = HistoryView("메모", [])
        self.addCleanup(empty.close)
        self.assertFalse(empty.restore_button.isEnabled())
        empty.list.setCurrentRow(0)
        self.assertTrue(empty.detail.isHidden())


class LockedSizeAndEntryPointsTest(test_ui.UiTestCase):
    def test_locked_memo_opens_small_and_grows_back_after_the_password(self) -> None:
        w = self.open_window("memo-0000")
        w.setGeometry(200, 150, 520, 430)
        self.answers[:] = ["pw12", "pw12"]
        w.set_memo_password()
        self.assertEqual((w.width(), w.height()), (520, 430))        # 암호를 걸기만 해서는 그대로
        w.lock_now()
        self.assertEqual((w.width(), w.height()), w.LOCKED_SIZE)     # 잠기면 암호 입력용 크기로
        self.assertEqual((w.x(), w.y()), (200, 150))
        self.assertTrue(w.lock_overlay.unlock_panel.isVisible())
        self.assertGreaterEqual(w.text_edit.height(), w.lock_overlay.unlock_panel.sizeHint().height())    # 암호 칸이 잘리지 않음
        w.resize(300, 260)                                           # 잠긴 채로 크기를 바꿔도 메모의 크기로 기억하지 않음
        w.close()
        saved = self.disk("memo-0000")
        self.assertEqual((saved["unrolled_width"], saved["unrolled_height"], saved["width"], saved["height"]), (520, 430, 520, 430))

        w = self.open_window("memo-0000")
        self.assertEqual((w.width(), w.height()), w.LOCKED_SIZE)
        w.lock_overlay.unlock_panel.inputs[0].setText("pw12")
        w.lock_overlay.unlock_panel.submit()
        self.assertFalse(w.memo_data.get("_locked"))
        self.assertEqual((w.width(), w.height()), (520, 430))        # 암호를 넣으면 원래 크기로

    def test_locked_rolled_memo_unrolls_small(self) -> None:
        w = self.open_window("memo-0000")
        w.setGeometry(200, 150, 520, 430)
        self.answers[:] = ["pw12", "pw12"]
        w.set_memo_password()
        w.lock_now()
        w.toggle_rollup()
        w.toggle_rollup()
        self.assertEqual((w.width(), w.height()), w.LOCKED_SIZE)
        self.assertEqual(w.memo_data["unrolled_width"], 520)

    def test_explorer_has_a_settings_button_above_the_preview(self) -> None:
        ex = self.explorer()
        test_ui._app.processEvents()
        self.assertFalse(ex.btn_settings.icon().isNull())
        self.assertLess(ex.btn_settings.mapTo(ex, QPoint(0, 0)).y(), ex.pv.mapTo(ex, QPoint(0, 0)).y())
        ex.btn_settings.click()
        self.assertTrue(ex.settings_open() and self.ui.settings_window.isVisible())

    def test_guide_button_lives_in_settings_not_in_the_tray(self) -> None:
        win = test_ui.sw.SettingsWindow(self.sm)
        self.addCleanup(win.close)
        self.assertTrue(win.tabs.widget(0).isAncestorOf(win.btn_make_guide))
        win.btn_make_guide.click()
        self.assertEqual(len([m for m in self.sm.load_local_memos() if m["id"].startswith("guide-")]), 3)
        self.assertIn("guide-memo", self.ui.memo_windows)
        menu = self.ui.tray_icon.contextMenu()
        self.assertFalse(any("사용 안내" in action.text() for action in menu.actions()))

    def test_sync_tab_links_to_the_setup_guide(self) -> None:
        win = test_ui.sw.SettingsWindow(self.sm)
        self.addCleanup(win.close)
        self.assertTrue(win.tabs.widget(1).isAncestorOf(win.btn_sync_guide))
        opened = []
        with mock.patch.object(test_ui.sw.QDesktopServices, "openUrl", staticmethod(lambda url: opened.append(url.toString()))):
            win.btn_sync_guide.click()
        self.assertEqual(len(opened), 1)
        self.assertTrue(opened[0].startswith("https://github.com/DongkyuSeoOssData/Memos"))
        readme = (pathlib.Path(test_ui.sw.__file__).parent.parent / "README.md").read_text(encoding="utf-8")
        self.assertIn("### 설정 방법", readme)                        # 링크가 가리키는 대목이 README 에 있음
        self.assertTrue(test_ui.sw.SYNC_GUIDE_URL.endswith("#설정-방법"))
        for needed in ("mobile/Code.gs", "mobile/Index.html", "ACCESS_TOKEN", "웹 앱 URL"):
            self.assertIn(needed, readme)

    def test_dropdown_button_opens_a_list_you_can_type_into(self) -> None:
        w = self.open_window("memo-0000")
        w.toggle_sub_fmt_panel()
        if w.font_box.count() < 2:
            w.font_box.addItems(["Alpha Sans", "Beta Mono", "Beta Serif"])
        for box, button in ((w.font_box, w.btn_font_drop), (w.size_box, w.btn_size_drop)):
            finder = box.completer()
            shown = []
            finder.complete = lambda *a, shown=shown: shown.append(finder.completionPrefix())
            button.click()
            self.assertEqual(shown, [""])                            # 목록 전체를 펼침
            self.assertEqual(box.lineEdit().selectedText(), box.currentText())      # 바로 적으면 지금 글자를 대신함
            self.assertEqual(finder.completionMode(), finder.CompletionMode.PopupCompletion)
        # 목록이 떠 있는 동안 적으면 걸러짐
        finder = w.font_box.completer()
        finder.setCompletionPrefix("beta")
        names = [finder.completionModel().index(r, 0).data() for r in range(finder.completionModel().rowCount())]
        self.assertTrue(names and all("beta" in n.lower() for n in names), names)


class MultiDeleteAndHistoryPasswordTest(test_ui.UiTestCase):
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

        with mock.patch.object(test_ui.uim.QMenu, "exec", run_menu):
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

    def test_settings_button_sits_left_of_the_title_and_toggles(self) -> None:
        ex = self.explorer()
        test_ui._app.processEvents()
        title = next(label for label in ex.findChildren(test_ui.QLabel) if label.text() == "미리보기")
        self.assertLess(ex.btn_settings.mapTo(ex, QPoint(0, 0)).x(), title.mapTo(ex, QPoint(0, 0)).x())
        ex.btn_settings.click()
        self.assertTrue(ex.settings_open())
        ex.btn_settings.click()                                      # 열려 있을 때 누르면 닫힘
        self.assertFalse(ex.settings_open())
        ex.btn_settings.click()
        self.assertTrue(ex.settings_open() and self.ui.settings_window.isVisible())

    def test_settings_layout_details(self) -> None:
        win = test_ui.sw.SettingsWindow(self.sm)
        self.addCleanup(win.close)
        win.show()
        test_ui._app.processEvents()
        general = win.tabs.widget(0)
        tops = {name: getattr(win, name).mapTo(general, QPoint(0, 0)).y() for name in ("folder_ui_box", "spin_relock_min", "btn_make_guide")}
        self.assertLess(tops["folder_ui_box"], tops["spin_relock_min"])          # 폴더 표시 방식이 맨 위
        self.assertLess(tops["spin_relock_min"], tops["btn_make_guide"])
        texts = " ".join(label.text() for label in win.findChildren(test_ui.QLabel))
        self.assertIn("단축키 설정", texts)
        self.assertNotIn("종]", texts)

    def test_locked_memo_keeps_its_rolled_width_and_shows_the_password_box_when_opened(self) -> None:
        w = self.open_window("memo-0000")
        w.setGeometry(200, 150, 520, 430)
        self.answers[:] = ["pw12", "pw12"]
        w.set_memo_password()
        w.toggle_rollup()
        w.resize(410, w.height())                                    # 접은 메모의 너비를 정해 둠
        w.move(300, 400)
        w.lock_now()
        self.assertEqual((w.x(), w.y(), w.width()), (300, 400, 410))
        for _ in range(3):                                           # 폈다 접기를 되풀이해도 접은 크기는 그대로
            w.toggle_rollup()
            test_ui._app.processEvents()
            self.assertEqual((w.width(), w.height()), w.LOCKED_SIZE)
            overlay, panel = w.lock_overlay, w.lock_overlay.unlock_panel
            self.assertTrue(overlay.isVisible() and panel.isVisible())
            self.assertEqual(overlay.geometry().size(), w.text_edit.size())
            self.assertTrue(overlay.rect().contains(panel.geometry()), (overlay.rect(), panel.geometry()))      # 암호 칸이 잘리지 않고
            self.assertLessEqual(abs(panel.geometry().center().x() - overlay.rect().center().x()), 1)           # 한가운데
            self.assertLessEqual(abs(panel.geometry().center().y() - overlay.rect().center().y()), 1)
            w.toggle_rollup()
            self.assertEqual((w.x(), w.y(), w.width()), (300, 400, 410))
        w.toggle_rollup()
        w.lock_overlay.unlock_panel.inputs[0].setText("pw12")
        w.lock_overlay.unlock_panel.submit()
        self.assertEqual((w.width(), w.height()), (520, 430))        # 암호를 풀면 원래 크기
        w.toggle_rollup()
        self.assertEqual(w.width(), 410)


class LockedFirstFoldTest(test_ui.UiTestCase):
    """잠긴 메모를 접고 펴도 접은 메모의 크기는 암호 입력용 크기에 끌려가지 않습니다."""

    def locked(self, memo_id: str, width: int = 500):
        w = self.open_window(memo_id)
        w.setGeometry(100, 100, width, 400)
        self.answers[:] = ["pw12", "pw12"]
        w.set_memo_password()
        w.lock_now()
        self.assertEqual((w.width(), w.height()), w.LOCKED_SIZE)
        return w

    def unlock(self, w) -> None:
        w.lock_overlay.unlock_panel.inputs[0].setText("pw12")
        w.lock_overlay.unlock_panel.submit()

    def test_first_fold_of_a_locked_memo_uses_its_real_width(self) -> None:
        w = self.locked("memo-0000")                                 # 한 번도 접은 적 없는 메모를 잠근 뒤
        w.toggle_rollup()
        test_ui._app.processEvents()
        self.assertEqual(w.width(), 500)                             # 암호 입력용 너비(340)가 아니라 메모 본래의 너비로 접힘
        spot = (w.x(), w.y(), w.width())
        for _ in range(3):
            w.toggle_rollup()
            test_ui._app.processEvents()
            self.assertEqual((w.width(), w.height()), w.LOCKED_SIZE)
            w.toggle_rollup()
            test_ui._app.processEvents()
            self.assertEqual((w.x(), w.y(), w.width()), spot)
        w.toggle_rollup()
        self.unlock(w)
        self.assertEqual((w.width(), w.height()), (500, 400))
        w.toggle_rollup()
        self.assertEqual((w.x(), w.y(), w.width()), spot)            # 암호를 푼 뒤에도 같은 자리·같은 너비
        self.assertEqual(w.memo_data["rolled_width"], 500)

    def test_first_fold_lands_where_an_unlocked_memo_would(self) -> None:
        plain = self.open_window("memo-0001")
        plain.setGeometry(100, 100, 500, 400)
        plain.toggle_rollup()
        locked = self.locked("memo-0000")
        locked.toggle_rollup()
        self.assertEqual((locked.x(), locked.y(), locked.width()), (plain.x(), plain.y(), plain.width()))

    def test_reopening_a_rolled_locked_memo_keeps_its_width(self) -> None:
        w = self.locked("memo-0000")
        w.toggle_rollup()
        w.resize(280, w.height())
        w.close()
        w = self.open_window("memo-0000")
        self.assertEqual((w._is_rolled_up, w.width()), (True, 280))
        w.toggle_rollup()
        w.close()
        w = self.open_window("memo-0000")                            # 잠긴 채 펼쳐진 상태로 다시 열림
        self.assertEqual((w.width(), w.height()), w.LOCKED_SIZE)
        w.toggle_rollup()
        self.assertEqual(w.width(), 280)
        saved = self.disk("memo-0000")
        self.assertEqual((saved["unrolled_width"], saved["unrolled_height"]), (500, 400))


class HotkeyScopeTest(test_ui.UiTestCase):
    def test_global_by_default(self) -> None:
        self.assertEqual(len(self.ui._hotkeys.registered), 7)
        self.assertEqual(self.ui._app_shortcuts, [])

    def test_app_only_mode_leaves_the_keys_to_other_programs(self) -> None:
        self.sm.save_settings({"global_hotkeys": False})
        self.ui.register_global_hotkeys()
        self.assertEqual(self.ui._hotkeys.registered, [])            # 전역으로는 아무것도 잡지 않음
        shortcuts = self.ui._app_shortcuts
        self.assertEqual(len(shortcuts), 7)
        self.assertTrue(all(s.context() == Qt.ShortcutContext.ApplicationShortcut for s in shortcuts))
        keys = {s.key().toString() for s in shortcuts}
        self.assertIn("Alt+W", keys)
        self.assertIn("Alt+Q", keys)
        opener = next(s for s in shortcuts if s.key().toString() == "Alt+W")
        opener.activated.emit()                                      # 앱 창이 앞에 있을 때 눌린 것처럼
        self.assertTrue(self.ui.explorer_window.isVisible())

        self.ui.register_global_hotkeys()                            # 다시 걸어도 겹쳐 쌓이지 않음
        self.assertEqual(len(self.ui._app_shortcuts), 7)
        self.sm.save_settings({"global_hotkeys": True})
        self.ui.register_global_hotkeys()
        self.assertEqual((len(self.ui._hotkeys.registered), self.ui._app_shortcuts), (7, []))

    def test_cleared_shortcut_is_skipped_in_both_modes(self) -> None:
        shortcuts = dict(self.sm.settings.get("shortcuts", {}), open_explorer="")
        self.sm.save_settings({"shortcuts": shortcuts, "global_hotkeys": False})
        self.ui.register_global_hotkeys()
        self.assertEqual(len(self.ui._app_shortcuts), 6)

    def test_option_is_on_the_shortcut_tab_and_applies_on_save(self) -> None:
        win = test_ui.sw.SettingsWindow(self.sm)
        self.addCleanup(win.close)
        self.assertTrue(win.tabs.widget(3).isAncestorOf(win.cb_global_hotkeys))
        self.assertTrue(win.cb_global_hotkeys.isChecked())
        win.cb_global_hotkeys.setChecked(False)
        win.save()
        self.assertFalse(self.sm.settings["global_hotkeys"])
        self.assertEqual((self.ui._hotkeys.registered, len(self.ui._app_shortcuts)), ([], 7))
        again = test_ui.sw.SettingsWindow(self.sm)
        self.addCleanup(again.close)
        self.assertFalse(again.cb_global_hotkeys.isChecked())


class UnsavedSettingsTest(test_ui.UiTestCase):
    """환경설정에서 바꾸고 저장하지 않은 채 닫으려 하면 저장할지 묻습니다."""

    def setUp(self) -> None:
        super().setUp()
        self.ex = self.explorer()
        self.ex.resize(720, 640)
        self.ui.open_settings()
        self.panel = self.ex.settings_panel
        test_ui._app.processEvents()

    def change(self) -> None:
        self.panel.spin_relock_min.setValue(self.panel.spin_relock_min.value() + 3)

    def test_untouched_settings_close_without_asking(self) -> None:
        self.assertFalse(self.panel.is_dirty())
        self.assertNotIn("●", self.panel.sb.text())
        self.ex.move(self.ex.x() + 40, self.ex.y() + 30)             # 탐색기를 옮기는 것은 설정을 바꾼 것이 아님
        self.assertFalse(self.panel.is_dirty())
        self.panel.btn_win_close.click()
        self.assertEqual(self.choices_asked, [])
        self.assertFalse(self.ex.settings_open())

    def test_changing_marks_the_save_button_and_reverting_clears_it(self) -> None:
        before = self.panel.spin_relock_min.value()
        self.change()
        self.assertTrue(self.panel.is_dirty())
        self.assertIn("●", self.panel.sb.text())
        self.panel.spin_relock_min.setValue(before)                   # 되돌리면 바뀐 것이 없는 것으로
        self.assertFalse(self.panel.is_dirty())
        self.assertNotIn("●", self.panel.sb.text())
        for toggle in (self.panel.cb_global_hotkeys, self.panel.cb_default_pin):
            toggle.setChecked(not toggle.isChecked())
            self.assertTrue(self.panel.is_dirty())
            toggle.setChecked(not toggle.isChecked())
        self.panel.url_input.setText("https://example.invalid/x")
        self.assertIn("●", self.panel.sb.text())

    def test_saving_clears_the_mark(self) -> None:
        self.change()
        self.panel.save()
        self.assertFalse(self.panel.is_dirty())
        self.assertNotIn("●", self.panel.sb.text())
        self.panel.btn_win_close.click()
        self.assertEqual(self.choices_asked, [])

    def test_cancel_keeps_everything_open(self) -> None:
        self.change()
        self.choice_answer = None
        value = self.panel.spin_relock_min.value()
        self.panel.btn_win_close.click()                             # 패널의 닫기
        self.ex.btn_settings.click()                                 # 톱니바퀴
        self.ui.toggle_explorer()                                    # Alt+W
        self.ex.close()                                              # 탐색기 닫기
        test_ui._app.processEvents()
        self.assertEqual(len(self.choices_asked), 4)
        self.assertTrue(self.ex.isVisible() and self.ex.settings_open())
        self.assertEqual(self.panel.spin_relock_min.value(), value)   # 고치던 값도 그대로

    def test_save_and_close(self) -> None:
        self.change()
        wanted = self.panel.spin_relock_min.value()
        self.choice_answer = "save"
        self.ex.close()
        test_ui._app.processEvents()
        self.assertEqual(self.choices_asked, ["저장하지 않은 변경이 있습니다"])
        self.assertFalse(self.ex.isVisible())
        self.assertEqual(self.sm.settings["locked_memo_relock_min"], wanted)

    def test_discard_and_close(self) -> None:
        before = self.sm.settings.get("locked_memo_relock_min", 5)
        self.change()
        self.choice_answer = "discard"
        self.ui.toggle_explorer()
        test_ui._app.processEvents()
        self.assertFalse(self.ex.isVisible())
        self.assertEqual(self.sm.settings.get("locked_memo_relock_min", 5), before)
        self.assertEqual(len(self.choices_asked), 1)

    def test_quitting_asks_too(self) -> None:
        self.change()
        with mock.patch.object(test_ui.uim.QApplication, "quit") as quit_app:
            self.choice_answer = None
            self.ui.quit_app()
            quit_app.assert_not_called()                             # 취소하면 끝내지 않음
            self.choice_answer = "save"
            wanted = self.panel.spin_relock_min.value()
            self.ui.quit_app()
            quit_app.assert_called_once()
        self.assertEqual(self.sm.settings["locked_memo_relock_min"], wanted)

    def test_quitting_with_nothing_changed_does_not_ask(self) -> None:
        with mock.patch.object(test_ui.uim.QApplication, "quit") as quit_app:
            self.ui.quit_app()
            quit_app.assert_called_once()
        self.assertEqual(self.choices_asked, [])

    def test_the_question_is_shown_inside_the_explorer(self) -> None:
        from PyQt6.QtCore import QTimer
        self.change()
        seen = {}

        def press() -> None:
            overlay = self.ex.inline_overlay
            seen["inside"] = overlay.isVisible() and overlay.isAncestorOf(overlay.panel)
            seen["buttons"] = [b.text() for b in overlay.panel.buttons.values()]
            overlay.panel.buttons[None].click()                      # 취소

        QTimer.singleShot(0, press)
        with mock.patch.object(test_ui.themed_dialog, "choose", self.real_choose):
            closed = self.ex.ask_and_close_settings_panel()
        self.assertEqual(seen, {"inside": True, "buttons": ["저장하고 닫기", "저장 안 함", "취소"]})
        self.assertFalse(closed)
        self.assertTrue(self.ex.settings_open())


class LockedHistoryTest(test_ui.UiTestCase):
    """암호 메모의 내용은 변경 기록에도 평문으로 남지 않고, 되돌려도 잠금 상태가 바뀌지 않습니다."""

    SECRET = "body 0 #tag0"

    def history_file(self, memo_id: str = "memo-0000") -> pathlib.Path:
        return self.memo_dir / "history_bin" / f"{memo_id}.json"

    def edit(self, w, text: str) -> None:
        with mock.patch.object(self.sm, "HISTORY_MIN_GAP_SEC", 0):
            w.text_edit.setPlainText(text)
            w.text_edit.document().setModified(True)
            w.execute_auto_save()

    def lock(self, memo_id: str = "memo-0000", password: str = "pw12"):
        w = self.open_window(memo_id)
        self.answers[:] = [password, password]
        w.set_memo_password()
        return w

    def test_setting_a_password_leaves_no_plaintext_in_the_history(self) -> None:
        w = self.open_window("memo-0000")
        self.edit(w, "second version")                               # 암호를 걸기 전에 쌓인 평문 기록
        self.assertIn(self.SECRET, self.history_file().read_text(encoding="utf-8"))
        self.answers[:] = ["pw12", "pw12"]
        w.set_memo_password()
        raw = self.history_file().read_text(encoding="utf-8")
        self.assertNotIn(self.SECRET, raw)                           # 예전 기록도
        self.assertNotIn("second version", raw)                      # 암호를 걸기 직전의 내용도 평문으로 남지 않음
        entries = self.sm.list_history("memo-0000")
        self.assertTrue(entries and all(e["locked"] and e["text"] == "" for e in entries))
        self.edit(w, "third version")                                # 잠긴 뒤에 쌓이는 기록도 암호문
        self.assertNotIn("second version", self.history_file().read_text(encoding="utf-8"))

    def test_history_opens_with_the_memo_key_or_the_password(self) -> None:
        w = self.lock()
        self.edit(w, "second version")
        index = self.sm.list_history("memo-0000")[-1]["index"]
        self.assertEqual(self.sm.read_history_text("memo-0000", index), self.SECRET)          # 메모가 열려 있으면 바로 보임
        w.lock_now()
        self.assertIsNone(self.sm.read_history_text("memo-0000", index))                      # 잠그면 암호가 필요
        self.assertIsNone(self.sm.read_history_text("memo-0000", index, "wrong"))
        self.assertEqual(self.sm.read_history_text("memo-0000", index, "pw12"), self.SECRET)

    def test_changing_the_password_reseals_the_history(self) -> None:
        w = self.lock()
        self.edit(w, "second version")
        self.answers[:] = ["new-pw", "new-pw"]
        w.set_memo_password()                                        # 암호 변경
        w.lock_now()
        for entry in self.sm.list_history("memo-0000"):
            self.assertIsNone(self.sm.read_history_text("memo-0000", entry["index"], "pw12"), entry)       # 예전 암호로는 안 열림
            self.assertIsNotNone(self.sm.read_history_text("memo-0000", entry["index"], "new-pw"), entry)  # 새 암호 하나로 다 열림

    def test_removing_the_password_opens_the_history_again(self) -> None:
        w = self.lock()
        self.edit(w, "second version")
        w.remove_memo_password()
        entries = self.sm.list_history("memo-0000")
        self.assertTrue(entries and all(not e["locked"] for e in entries))
        self.assertIn(self.SECRET, [e["text"] for e in entries])

    def test_plaintext_left_by_older_versions_is_sealed_on_unlock(self) -> None:
        w = self.lock()
        w.lock_now()
        self.history_file().parent.mkdir(parents=True, exist_ok=True)
        self.history_file().write_text(json.dumps([{                 # 예전 버전이 남긴 평문 기록
            "saved_at": "2026-01-01T00:00:00", "reason": "", "title": "t0", "content": "left in the clear",
            "updated_at": "", "is_locked": False}]), encoding="utf-8")
        w.lock_overlay.unlock_panel.inputs[0].setText("pw12")
        w.lock_overlay.unlock_panel.submit()                         # 잠금을 푸는 순간
        self.assertNotIn("left in the clear", self.history_file().read_text(encoding="utf-8"))
        self.assertEqual(self.sm.read_history_text("memo-0000", 0), "left in the clear")

    def test_restoring_keeps_the_memo_locked_with_its_current_password(self) -> None:
        w = self.open_window("memo-0000")
        self.edit(w, "second version")                               # 기록 0: 평문이었던 처음 내용
        self.answers[:] = ["pw12", "pw12"]
        w.set_memo_password()
        self.assertEqual(self.sm.restore_problem("memo-0000", 0), "")
        self.assertTrue(self.sm.restore_history("memo-0000", 0))
        self.ui.reload_pulled_memos(["memo-0000"])
        saved = self.disk("memo-0000")
        self.assertTrue(saved["is_locked"] and isinstance(saved["content"], dict))       # 여전히 암호 메모
        self.assertNotIn(self.SECRET, self.raw("memo-0000"))
        w.lock_now()
        self.answers[:] = ["pw12"]
        w.prompt_unlock()                                            # 지금 암호 그대로 열림
        self.assertEqual(w.text_edit.toPlainText(), self.SECRET)

    def test_locked_memo_must_be_unlocked_before_restoring(self) -> None:
        w = self.lock()
        self.edit(w, "second version")
        w.lock_now()
        before = self.raw("memo-0000")
        self.assertIn("잠금", self.sm.restore_problem("memo-0000", 0, "pw12"))
        self.assertFalse(self.sm.restore_history("memo-0000", 0, "pw12"))
        self.assertEqual(self.raw("memo-0000"), before)

    def test_history_under_another_password_needs_that_password(self) -> None:
        w = self.lock()
        crypto = self.sm.crypto
        salt = crypto.new_salt()
        foreign = crypto.encrypt_locked("old secret", crypto.derive_key("other-pw", salt), salt)
        self.history_file().parent.mkdir(parents=True, exist_ok=True)
        self.history_file().write_text(json.dumps([{
            "saved_at": "2026-01-01T00:00:00", "reason": "", "title": "old", "content": foreign,
            "updated_at": "", "is_locked": True}]), encoding="utf-8")
        self.assertIn("다른 암호", self.sm.restore_problem("memo-0000", 0))
        self.assertIn("일치하지", self.sm.restore_problem("memo-0000", 0, "nope"))
        self.assertFalse(self.sm.restore_history("memo-0000", 0, "nope"))
        self.assertTrue(self.sm.restore_history("memo-0000", 0, "other-pw"))
        self.ui.reload_pulled_memos(["memo-0000"])
        w.lock_now()
        self.answers[:] = ["pw12"]                                   # 되돌린 뒤에도 메모의 암호는 지금 것
        w.prompt_unlock()
        self.assertEqual((w.text_edit.toPlainText(), w.memo_data["title"]), ("old secret", "old"))

    def test_plain_memo_stays_plain_when_restoring_a_locked_entry(self) -> None:
        crypto = self.sm.crypto
        salt = crypto.new_salt()
        sealed = crypto.encrypt_locked("was secret once", crypto.derive_key("other-pw", salt), salt)
        self.history_file("memo-0001").parent.mkdir(parents=True, exist_ok=True)
        self.history_file("memo-0001").write_text(json.dumps([{
            "saved_at": "2026-01-01T00:00:00", "reason": "", "title": "t1", "content": sealed,
            "updated_at": "", "is_locked": True}]), encoding="utf-8")
        self.assertFalse(self.sm.restore_history("memo-0001", 0))
        self.assertTrue(self.sm.restore_history("memo-0001", 0, "other-pw"))
        saved = self.disk("memo-0001")
        self.assertEqual((saved["content"], saved["is_locked"]), ("was secret once", False))

    def test_history_screen_shows_and_checks_before_restoring(self) -> None:
        from ui.dialogs import HistoryView
        w = self.lock()
        self.edit(w, "second version")
        w.lock_now()
        entries = self.sm.list_history("memo-0000")
        view = HistoryView("t", entries,
                           reveal=lambda index, pwd: self.sm.read_history_text("memo-0000", index, pwd),
                           check=lambda index, pwd: self.sm.restore_problem("memo-0000", index, pwd))
        self.addCleanup(view.close)
        view.show()
        got = []
        view.submitted.connect(got.append)
        view.list.setCurrentRow(len(entries) - 1)
        self.assertTrue(view.unlock_row.isVisible())                 # 잠긴 메모: 암호를 넣어야 내용이 보임
        self.assertNotIn(self.SECRET, view.preview.toPlainText())
        view.password_edit.setText("wrong")
        view.unlock_button.click()
        self.assertTrue(view.unlock_error.isVisible())
        view.password_edit.setText("pw12")
        QTest.keyClick(view.password_edit, Qt.Key.Key_Return)
        self.assertEqual(view.preview.toPlainText(), self.SECRET)
        self.assertFalse(view.unlock_row.isVisible())
        view.restore_button.click()                                  # 메모가 잠겨 있으면 되돌리지 않고 이유를 알림
        self.assertEqual(got, [])
        self.assertIn("잠금", view.unlock_error.text())

        self.answers[:] = ["pw12"]
        w.prompt_unlock()
        view.restore_button.click()                                  # 잠금을 푼 뒤에는 되돌려짐
        self.assertEqual(got, [entries[-1]["index"]])

    def test_open_memo_shows_its_locked_history_without_asking(self) -> None:
        from ui.dialogs import HistoryView
        w = self.lock()
        self.edit(w, "second version")
        entries = self.sm.list_history("memo-0000")
        view = HistoryView("t", entries, reveal=lambda index, pwd: self.sm.read_history_text("memo-0000", index, pwd))
        self.addCleanup(view.close)
        view.show()
        view.list.setCurrentRow(len(entries) - 1)
        self.assertFalse(view.unlock_row.isVisible())
        self.assertEqual(view.preview.toPlainText(), self.SECRET)


class ReviewFixesTest(test_ui.UiTestCase):
    """코드 리뷰에서 나온 문제들."""

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

    # ── 3. 미리보기에서 체크해도 서식이 남음 ──
    def test_checking_a_box_in_the_preview_keeps_formatting(self) -> None:
        memo_id = self.rich_memo()
        ex = self.explorer()
        self.select(ex, memo_id)
        self.assertEqual(ex.pv.toPlainText().splitlines()[-2:], ["☐ first", "☐ second"])
        block = ex.pv.document().findBlockByNumber(ex.pv.document().blockCount() - 1)
        box = ex.pv.check_marks.box_rect(block, 0)
        QTest.mouseClick(ex.pv.viewport(), Qt.MouseButton.LeftButton, pos=box.center())
        ex._flush_preview_save()
        saved = self.disk(memo_id)["content"]
        self.assertRegex(saved, r"font-weight:\s*(700|600|bold)")                      # 굵게 서식이 그대로
        self.assertIn("☑ second", saved)
        self.assertIn("☐ first", saved)                              # 누른 줄만 바뀜
        self.assertTrue(ex.pv.toPlainText().endswith("☑ second"))
        self.assertEqual(self.warnings, [])

    def test_typing_in_the_preview_of_a_formatted_memo_warns(self) -> None:
        memo_id = self.rich_memo()
        ex = self.explorer()
        self.select(ex, memo_id)
        ex.pv.setPlainText(ex.pv.toPlainText() + " more")
        self.assertTrue(ex.toast.text().startswith("⚠") and "서식" in ex.toast.text())
        ex._flush_preview_save()
        self.assertNotIn("<html>", self.disk(memo_id)["content"])     # 글자만 저장된다는 점은 예전과 같음

    def test_plain_memo_preview_still_toggles_normally(self) -> None:
        w = self.open_window("memo-0001")
        w.text_edit.setPlainText("☐ a")
        w.text_edit.document().setModified(True)
        w.flush_auto_save()
        w.execute_auto_save()
        ex = self.explorer()
        self.select(ex, "memo-0001")
        box = ex.pv.check_marks.box_rect(ex.pv.document().firstBlock(), 0)
        QTest.mouseClick(ex.pv.viewport(), Qt.MouseButton.LeftButton, pos=box.center())
        ex._flush_preview_save()
        self.assertEqual(self.disk("memo-0001")["content"], "☑ a")

    # ── 4. 다른 모니터에 기억해 둔 자리 ──
    def test_unrolling_goes_back_to_the_other_monitor(self) -> None:
        from PyQt6.QtCore import QRect
        left, right = QRect(0, 0, 1600, 900), QRect(1600, 0, 1600, 900)

        def screen_at(point):
            area = left if point.x() < 1600 else right
            return mock.Mock(availableGeometry=lambda: QRect(area))

        w = self.open_window("memo-0000")
        with mock.patch("ui.memo_window.QApplication.screenAt", side_effect=screen_at):
            w.setGeometry(2000, 200, 400, 300)                       # 펼친 자리는 오른쪽 모니터
            w.toggle_rollup()
            w.move(100, 700)                                         # 접은 메모는 왼쪽 모니터로 옮겨 둠
            w.toggle_rollup()
            self.assertEqual((w.x(), w.y(), w.width(), w.height()), (2000, 200, 400, 300))
            w.toggle_rollup()
            self.assertEqual((w.x(), w.y()), (100, 700))

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
        with mock.patch.object(test_ui.themed_dialog, "confirm", lambda parent, title, text, **k: asked.append(text) or False):
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

    # ── 6. 다른 기기에서 받은 설정이 고치던 값을 덮지 않음 ──
    def test_incoming_settings_do_not_overwrite_unsaved_edits(self) -> None:
        self.explorer()
        self.ui.open_settings()
        panel = self.ui.settings_window
        before = panel.spin_relock_min.value()
        panel.spin_relock_min.setValue(before + 7)
        self.sm.settings["locked_memo_relock_min"] = before + 1      # 다른 기기에서 받은 값
        self.ui.apply_settings_to_windows(reload_settings_window=True)
        self.assertEqual(panel.spin_relock_min.value(), before + 7)  # 고치던 값이 그대로
        self.assertTrue(panel.is_dirty())
        self.assertTrue(panel.toast.isVisible() and panel.toast.toolTip().startswith("⚠"))

        panel.spin_relock_min.setValue(before)
        panel.mark_clean()
        self.sm.settings["locked_memo_relock_min"] = before + 2
        self.ui.apply_settings_to_windows(reload_settings_window=True)
        self.assertEqual(panel.spin_relock_min.value(), before + 2)  # 고치던 것이 없으면 새 값으로 채움

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

    # ── 8. 동기화를 쓰는 PC 에서는 안내 메모를 자동으로 만들지 않음 ──
    def test_guides_are_not_auto_made_on_a_pc_joining_sync(self) -> None:
        for path in self.memo_dir.glob("*.json"):
            path.unlink()
        self.sm.settings.update({"use_sync": True, "drive_folder_id": "https://example.invalid/exec"})
        with mock.patch.object(self.sm, "check_remote_if_stale"), mock.patch.object(self.sm, "_start_sync", create=True):
            self.ui.show_all_memos()
        self.assertFalse(any(m["id"].startswith("guide-") for m in self.sm.load_local_memos()))

    # ── 9. 왼쪽에 붙은 사이드바가 탐색기 위치로 저장되지 않음 ──
    def test_saved_explorer_position_ignores_the_left_sidebar(self) -> None:
        self.sm.save_settings({"folder_ui": "sidebar", "folder_sidebar_open": True})
        ex = self.explorer()
        ex.move(900, 200)
        ex.refresh()
        test_ui._app.processEvents()
        self.assertGreater(ex._sidebar_extra, 0)
        self.assertEqual(ex.content_x(), ex.x() + ex._sidebar_extra)
        self.ui.open_settings()
        self.ui.settings_window.save()
        self.assertEqual(self.sm.settings["explorer_geom"][0], ex.content_x())

    # ── 그 밖에 ──
    def test_side_panel_is_removed_with_the_memo(self) -> None:
        w = self.open_window("memo-0000")
        panel = w.side_panel()
        w.close()
        test_ui._app.processEvents()
        self.assertIsNone(w._side_panel)
        with self.assertRaises(RuntimeError):                        # 패널 창도 없어짐
            panel.isVisible()

    def test_quick_search_hides_unlocked_password_memo_text(self) -> None:
        w = self.open_window("memo-0000")
        self.answers[:] = ["pw12", "pw12"]
        w.set_memo_password()                                        # 암호 메모지만 지금은 열려 있음
        qs = QuickSearch(self.ui)
        self.addCleanup(qs.close)
        qs.popup()
        self.assertNotIn("memo-0000", [m["id"] for m in qs.search("tag0")])      # 내용으로는 찾지 않음
        self.assertIn("memo-0000", [m["id"] for m in qs.search("t0")])           # 제목으로는 찾음
        qs.input.setText("t0")
        text = " ".join(qs.results.item(i).text() for i in range(qs.results.count()))
        self.assertNotIn("body 0", text)


class ColorSourceTest(test_ui.UiTestCase):
    """색은 modern_style 한곳에서 정하고, 화면의 각 부분은 거기서 받아 씁니다."""

    def colors_of(self, memo_id: str, ui_style: str, bg: str) -> dict:
        from ui import modern_style
        self.sm.settings["ui_style"] = ui_style
        w = self.open_window(memo_id)
        w.memo_data["bg_color"] = bg
        return modern_style.memo_colors(w)

    def test_memo_colors_follow_the_memo_and_the_design_style(self) -> None:
        from ui import modern_style
        light = self.colors_of("memo-0000", "modern", "#FEF9C3")
        self.assertEqual((light["bg"], light["dark"], light["neo"]), ("#FEF9C3", False, False))
        self.assertEqual((light["strong"], light["on_strong"]), (light["accent"], "#FFFFFF"))      # Modern: 강조색
        neo_light = self.colors_of("memo-0000", "neo", "#FEF9C3")
        self.assertEqual((neo_light["strong"], neo_light["on_strong"]), (neo_light["ink"], "#FFFFFF"))   # Neo: 흑백
        neo_dark = self.colors_of("memo-0000", "neo", "#2E3440")
        self.assertEqual((neo_dark["dark"], neo_dark["strong"], neo_dark["on_strong"]), (True, neo_dark["ink"], "#1C1C1E"))
        self.assertNotEqual(neo_dark["field"], neo_light["field"])
        self.assertEqual(modern_style.check_colors(neo_dark),
                         {"ink": neo_dark["ink"], "fill": neo_dark["ink"], "tick": "#1C1C1E", "dark": True})
        self.assertEqual(modern_style.check_colors(light)["fill"], light["accent"])

    def test_app_colors_follow_the_app_theme(self) -> None:
        from ui import modern_style
        modern = modern_style.app_colors({"ui_style": "modern", "app_theme": "white"})
        neo = modern_style.app_colors({"ui_style": "neo", "app_theme": "dark"})
        self.assertEqual((modern["neo"], modern["dark"], modern["strong"]), (False, False, modern["accent"]))
        self.assertEqual((neo["neo"], neo["dark"], neo["strong"], neo["on_strong"]), (True, True, neo["ink"], neo["bg"]))

    def test_every_part_takes_its_colors_from_the_one_source(self) -> None:
        from ui import modern_style
        for style in ("modern", "neo"):
            self.sm.settings["ui_style"] = style
            w = self.open_window("memo-0000")
            colors = modern_style.memo_colors(w)
            self.assertEqual(w.text_edit._check_colors(), modern_style.check_colors(colors))       # 본문의 체크 상자
            w.lock_overlay.apply_style()
            self.assertIn(colors["strong"], w.lock_overlay.styleSheet())                           # 암호 입력 가림막
            panel = w.side_panel()
            panel.apply_style()
            self.assertIn(colors["bg"], panel.styleSheet())                                        # 메모 옆 패널
            self.assertIn(colors["edge"], panel.styleSheet())
            ex = self.explorer()
            self.assertEqual(ex._preview_check_colors(),                                           # 탐색기 미리보기
                             modern_style.check_colors(modern_style.app_colors(self.sm.settings)))

    def test_no_screen_decides_colors_on_its_own(self) -> None:
        folder = pathlib.Path(test_ui.uim.__file__).parent
        for path in folder.glob("*.py"):
            if path.name in ("modern_style.py", "neo_style.py", "themes.py"):
                continue
            source = path.read_text(encoding="utf-8")
            self.assertNotRegex(source, r"modern_style\._[a-z]", path.name)       # 스타일 모듈의 내부 함수를 직접 쓰지 않음
            self.assertNotIn("is_neo(", source, path.name)                         # 디자인 스타일을 직접 가르지 않음


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
        test_ui._app.processEvents()
        self.assertTrue(self.ui._reminder_timer.isActive())
        self.assertLessEqual(self.ui._reminder_timer.interval(), 30 * 60 * 1000 + 300)
        self.assertEqual(self.disk("memo-0000")["updated_at"], "2026-01-01T00:00:00")
        self.assertIn("meta_updated_at", self.disk("memo-0000"))
        self.sm.set_reminder(self.memo("memo-0000"), None)
        test_ui._app.processEvents()
        self.assertFalse(self.ui._reminder_timer.isActive())
        self.assertNotIn("reminder", self.disk("memo-0000"))

    def test_far_reminders_are_rechecked_within_an_hour(self) -> None:
        self.sm.set_reminder(self.memo("memo-0000"), reminders.make(D.now() + dt.timedelta(days=30)))
        test_ui._app.processEvents()
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
        self.assertEqual(reminders.due_at(self.disk("memo-0001")["reminder"]), due.replace(second=0) + dt.timedelta(days=1))
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

    def dialog(self, current=None) -> ReminderDialog:
        d = ReminderDialog(None, current, "t")
        self.addCleanup(d.close)
        d.show()
        return d

    def pick_repeat(self, d: ReminderDialog, key: str) -> None:
        d.repeat_check.setChecked(True)
        d.repeat.setCurrentIndex(d.repeat.findData(key))

    def test_dialog_one_shot_shows_calendar_date_time_and_quick_buttons(self) -> None:
        d = self.dialog()
        self.assertFalse(d.repeat_check.isChecked())
        self.assertFalse(d.repeat.isEnabled())                       # 반복을 켜야 고를 수 있음
        self.assertTrue(d.once_box.isVisible() and d.time_box.isVisible())
        self.assertTrue(d.date.calendarPopup())                      # 날짜는 달력에서 고름
        for box in (d.weekday_box, d.day_box, d.cron_box):
            self.assertFalse(box.isVisible())
        d.date.setDate(QDate(2031, 3, 4))
        d.time.set_time(15, 30)
        d._accept()
        self.assertEqual(d.result_reminder, reminders.make(D(2031, 3, 4, 15, 30)))

    def test_dialog_daily_and_weekdays_ask_for_a_time_only(self) -> None:
        for key in ("daily", "weekdays"):
            d = self.dialog()
            self.pick_repeat(d, key)
            self.assertTrue(d.repeat.isEnabled())
            self.assertFalse(d.once_box.isVisible())                 # 10분 뒤 같은 버튼과 날짜 입력은 사라짐
            self.assertTrue(d.time_box.isVisible())
            for box in (d.weekday_box, d.day_box, d.cron_box):
                self.assertFalse(box.isVisible())
            d.time.set_time(7, 45)
            d._accept()
            due = reminders.due_at(d.result_reminder)
            self.assertEqual((d.result_reminder["repeat"], due.hour, due.minute), (key, 7, 45))
            self.assertGreater(due, D.now())
            if key == "weekdays":
                self.assertLess(due.weekday(), 5)

    def test_dialog_weekly_needs_weekdays_and_a_time(self) -> None:
        d = self.dialog()
        self.pick_repeat(d, "weekly")
        self.assertTrue(d.weekday_box.isVisible() and d.time_box.isVisible())
        self.assertFalse(d.once_box.isVisible() or d.day_box.isVisible() or d.cron_box.isVisible())
        for btn in d.weekday_buttons:
            btn.setChecked(False)
        self.assertFalse(d.ok_button.isEnabled())
        self.assertIn("요일", d.preview.text())
        d.weekday_buttons[1].setChecked(True)                        # 화
        d.weekday_buttons[4].setChecked(True)                        # 금
        self.assertTrue(d.ok_button.isEnabled())
        self.assertIn("매주 화·금", d.preview.text())
        d._accept()
        self.assertEqual(d.result_reminder["weekdays"], [1, 4])
        self.assertIn(reminders.due_at(d.result_reminder).weekday(), (1, 4))

    def test_dialog_monthly_picks_several_days(self) -> None:
        d = self.dialog()
        self.pick_repeat(d, "monthly")
        self.assertTrue(d.day_box.isVisible() and d.time_box.isVisible())
        self.assertFalse(d.once_box.isVisible() or d.weekday_box.isVisible() or d.cron_box.isVisible())
        self.assertEqual(len(d.day_buttons), 31)
        for btn in d.day_buttons.values():
            btn.setChecked(False)
        self.assertFalse(d.ok_button.isEnabled())
        for day in (1, 15, 31):
            d.day_buttons[day].setChecked(True)
        self.assertIn("매월 1·15·31일", d.preview.text())
        d._accept()
        self.assertEqual(d.result_reminder["days"], [1, 15, 31])

    def test_dialog_cron_shows_only_the_expression_with_help(self) -> None:
        d = self.dialog()
        self.pick_repeat(d, "cron")
        self.assertTrue(d.cron_box.isVisible())
        for box in (d.once_box, d.time_box, d.weekday_box, d.day_box):
            self.assertFalse(box.isVisible())
        self.assertFalse(d.ok_button.isEnabled())                    # 식이 비어 있음
        d.example_buttons[1].click()                                 # 예시를 누르면 입력됨
        self.assertEqual(d.cron.text(), "0 9 * * 1-5")
        self.assertTrue(d.ok_button.isEnabled())
        self.assertEqual(d.preview.text().count("09:00"), 3)         # 다음 세 번의 시각
        d._accept()
        self.assertEqual(d.result_reminder["cron"], "0 9 * * 1-5")
        d.cron.setText("0 99 * * *")
        self.assertFalse(d.ok_button.isEnabled())
        for expr, _ in d.CRON_EXAMPLES:                              # 예시는 모두 올바른 식
            reminders.parse_cron(expr)

    def test_dialog_loads_an_existing_reminder(self) -> None:
        weekly = reminders.make_repeating("weekly", 18, 30, D.now(), weekdays=[0, 6])
        d = self.dialog(weekly)
        self.assertTrue(d.repeat_check.isChecked())
        self.assertEqual(d.repeat.currentData(), "weekly")
        self.assertEqual([b.isChecked() for b in d.weekday_buttons], [True, False, False, False, False, False, True])
        self.assertEqual(d.time.time(), (18, 30))
        d._accept()
        self.assertEqual(d.result_reminder, weekly)

        monthly = self.dialog(reminders.make_repeating("monthly", 8, 0, D.now(), days=[5, 20]))
        self.assertEqual([day for day, b in monthly.day_buttons.items() if b.isChecked()], [5, 20])

        once = self.dialog(reminders.make(D(2031, 3, 4, 15, 30)))
        self.assertEqual((once.date.date(), once.time.time()), (QDate(2031, 3, 4), (15, 30)))
        self.assertIsNotNone(once.clear_button)

        # 미뤄 둔 반복 알림은 미룬 시각이 아니라 원래 시각을 보여 줌
        snoozed = reminders.snoozed(reminders.make_repeating("daily", 9, 0, D.now()), 7, D.now())
        self.assertEqual(self.dialog(snoozed).time.time(), (9, 0))

        again = self.dialog(weekly)
        again._clear()
        self.assertTrue(again.cleared)
        self.assertIsNone(again.result_reminder)

    def test_unchecking_repeat_goes_back_to_one_shot(self) -> None:
        d = self.dialog(reminders.make_repeating("daily", 9, 0, D.now()))
        d.repeat_check.setChecked(False)
        self.assertTrue(d.once_box.isVisible())
        d._accept()
        self.assertEqual(d.result_reminder["repeat"], "none")

    def test_bad_time_blocks_saving(self) -> None:
        d = self.dialog()
        d.time.hour.setText("")
        d.time.changed.emit()
        self.assertFalse(d.ok_button.isEnabled())
        self.assertIn("시간", d.preview.text())
        d.time.hour.setText("29")
        d.time.changed.emit()
        self.assertFalse(d.ok_button.isEnabled())
        d.time.set_time(8, 5)
        d.time.changed.emit()
        self.assertTrue(d.ok_button.isEnabled())

    def test_reminder_opens_beside_the_memo_showing_everything(self) -> None:
        from PyQt6.QtCore import QTimer
        from ui.reminder_ui import ask_reminder
        w = self.open_window("memo-0002")
        w.resize(260, 200)                                           # 작은 메모여도 잘리지 않음
        test_ui._app.processEvents()
        seen = {}

        def steps() -> None:
            side = w.side_panel()
            form = side.panel
            seen["attached"] = side.isVisible() and abs(side.x() - (w.bg.mapToGlobal(QPoint(0, 0)).x() + w.bg.width() - 1)) <= 1
            seen["whole"] = (side.height() >= side.sizeHint().height(), side.width() >= 350)
            form.repeat_check.setChecked(True)
            form.repeat.setCurrentIndex(form.repeat.findData("monthly"))        # 입력이 늘어나면 패널도 그만큼 커짐
            test_ui._app.processEvents()
            seen["grows"] = side.height() >= side.sizeHint().height()
            form.repeat.setCurrentIndex(form.repeat.findData("daily"))
            form.time.set_time(6, 10)
            form._accept()

        QTimer.singleShot(0, steps)
        changed, reminder = ask_reminder(w, None, "t")
        self.assertEqual(seen, {"attached": True, "whole": (True, True), "grows": True})
        self.assertTrue(changed)
        self.assertEqual((reminder["repeat"], reminders.due_at(reminder).hour, reminders.due_at(reminder).minute), ("daily", 6, 10))
        self.assertFalse(w.side_panel().isVisible())
        self.assertEqual((w.width(), w.height()), (260, 200))        # 메모 크기는 그대로

        QTimer.singleShot(0, lambda: w.side_panel().panel.cancel_button.click())
        self.assertEqual(ask_reminder(w, None, "t"), (False, None))

    def test_rolled_memo_also_uses_the_side_panel(self) -> None:
        from PyQt6.QtCore import QTimer
        from ui.reminder_ui import ask_reminder
        w = self.open_window("memo-0002")
        w.toggle_rollup()
        QTimer.singleShot(0, lambda: w.side_panel().panel._accept())
        changed, reminder = ask_reminder(w, None, "t")
        self.assertTrue(changed and reminder["repeat"] == "none")

    def test_explorer_asks_for_reminders_inside_itself(self) -> None:
        from PyQt6.QtCore import QTimer
        from ui.reminder_ui import ask_reminder
        ex = self.explorer()
        ex.resize(720, 640)
        test_ui._app.processEvents()
        seen = {}

        def steps() -> None:
            overlay = ex.inline_overlay
            seen["inside"] = overlay.isVisible() and overlay.isAncestorOf(overlay.panel)
            seen["covers"] = overlay.geometry() == ex.bg.rect()
            overlay.panel._accept()

        QTimer.singleShot(0, steps)
        changed, reminder = ask_reminder(ex, None, "t")
        self.assertEqual(seen, {"inside": True, "covers": True})
        self.assertTrue(changed)
        self.assertTrue(ex.inline_overlay.isHidden())

    def test_quick_choices_come_from_settings(self) -> None:
        from ui.reminder_ui import minutes_label, quick_minutes
        now = D(2026, 10, 10, 19, 30)
        self.assertEqual(quick_choices(now), [("10분 뒤", D(2026, 10, 10, 19, 40)), ("30분 뒤", D(2026, 10, 10, 20, 0)),
                                              ("1시간 뒤", D(2026, 10, 10, 20, 30))])
        self.assertEqual([minutes_label(m) for m in (5, 60, 90, 1440, 1500)], ["5분 뒤", "1시간 뒤", "1시간 30분 뒤", "1일 뒤", "1일 1시간 뒤"])
        self.assertEqual(quick_minutes({}), [10, 30, 60])
        self.assertEqual(quick_minutes({"reminder_quick_minutes": [5, 120, 1440]}), [5, 120, 1440])
        self.assertEqual(quick_minutes({"reminder_quick_minutes": ["x", 0]}), [10, 30, 60])

        win = test_ui.sw.SettingsWindow(self.sm)
        self.addCleanup(win.close)
        self.assertEqual([s.value() for s in win.quick_minute_spins], [10, 30, 60])
        for spin, value in zip(win.quick_minute_spins, (5, 45, 180)):
            spin.setValue(value)
        win.save()
        self.assertEqual(self.sm.settings["reminder_quick_minutes"], [5, 45, 180])
        d = ReminderDialog(None, None, "t")
        self.addCleanup(d.close)
        labels = [b.text() for b in d.once_box.findChildren(test_ui.QPushButton)]
        self.assertEqual(labels, ["5분 뒤", "45분 뒤", "3시간 뒤"])

    def test_alarm_shows_only_our_popup_and_hides_locked_content(self) -> None:
        w = self.open_window("memo-0001")
        self.answers[:] = ["pw12", "pw12"]
        w.set_memo_password()                                        # 암호 메모지만 지금은 열려 있음
        shown = []
        self.ui.tray_icon.showMessage = lambda *a, **k: shown.append(a)
        self.sm.set_reminder(w.memo_data, reminders.make(D.now() - dt.timedelta(seconds=5)))
        self.ui.check_reminders()
        popup = self.ui._reminder_popups[0]
        self.assertEqual(shown, [])                                  # Windows 알림은 띄우지 않음
        texts = [label.text() for label in popup.findChildren(test_ui.QLabel)]
        self.assertFalse(any("body 1" in t for t in texts), texts)   # 암호 메모의 내용은 보이지 않음
        self.assertIn("🔒 암호 메모", texts)                          # 대신 암호 메모임을 알림
        popup.close()

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
