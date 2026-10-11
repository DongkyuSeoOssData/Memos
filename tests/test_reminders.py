"""알림: 반복 규칙과 크론식, 시간 입력, 알림 설정 화면, 알림 창."""
import datetime as dt
import unittest
from unittest import mock

from PyQt6.QtCore import QDate, QPoint, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QLabel, QPushButton

# support 를 먼저 가져와야 합니다. (offscreen 설정과 프로젝트 경로)
import support
from core import reminders
from ui.reminder_ui import ReminderDialog, ReminderPopup, quick_choices
from drive_api import DriveAPI

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


class TimeInputTest(support.UiTestCase):
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


class ReminderUiTest(support.UiTestCase):
    def memo(self, memo_id: str) -> dict:
        return next(m for m in self.sm.load_local_memos() if m["id"] == memo_id)

    def test_setting_a_reminder_schedules_the_timer_without_touching_modified_time(self) -> None:
        self.assertFalse(self.ui._reminder_timer.isActive())
        self.sm.set_reminder(self.memo("memo-0000"), reminders.make(D.now() + dt.timedelta(minutes=30)))
        support.app.processEvents()
        self.assertTrue(self.ui._reminder_timer.isActive())
        self.assertLessEqual(self.ui._reminder_timer.interval(), 30 * 60 * 1000 + 300)
        self.assertEqual(self.disk("memo-0000")["updated_at"], "2026-01-01T00:00:00")
        self.assertNotIn("meta_updated_at", self.disk("memo-0000"))         # 알림은 이 PC만의 값이라 속성 변경으로 치지 않음
        self.sm.set_reminder(self.memo("memo-0000"), None)
        support.app.processEvents()
        self.assertFalse(self.ui._reminder_timer.isActive())
        self.assertNotIn("reminder", self.disk("memo-0000"))

    def test_far_reminders_are_rechecked_within_an_hour(self) -> None:
        self.sm.set_reminder(self.memo("memo-0000"), reminders.make(D.now() + dt.timedelta(days=30)))
        support.app.processEvents()
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
        fresh = support.smm.SyncManager(DriveAPI())
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
        support.app.processEvents()
        seen = {}

        def steps() -> None:
            side = w.side_panel()
            form = side.panel
            seen["attached"] = side.isVisible() and abs(side.x() - (w.bg.mapToGlobal(QPoint(0, 0)).x() + w.bg.width() - 1)) <= 1
            seen["whole"] = (side.height() >= side.sizeHint().height(), side.width() >= 350)
            form.repeat_check.setChecked(True)
            form.repeat.setCurrentIndex(form.repeat.findData("monthly"))        # 입력이 늘어나면 패널도 그만큼 커짐
            support.app.processEvents()
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
        support.app.processEvents()
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

        win = support.sw.SettingsWindow(self.sm)
        self.addCleanup(win.close)
        self.assertEqual([s.value() for s in win.quick_minute_spins], [10, 30, 60])
        for spin, value in zip(win.quick_minute_spins, (5, 45, 180)):
            spin.setValue(value)
        win.save()
        self.assertEqual(self.sm.settings["reminder_quick_minutes"], [5, 45, 180])
        d = ReminderDialog(None, None, "t")
        self.addCleanup(d.close)
        labels = [b.text() for b in d.once_box.findChildren(QPushButton)]
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
        texts = [label.text() for label in popup.findChildren(QLabel)]
        self.assertFalse(any("body 1" in t for t in texts), texts)   # 암호 메모의 내용은 보이지 않음
        self.assertIn("🔒 암호 메모", texts)                          # 대신 암호 메모임을 알림
        popup.close()

    def test_popup_buttons(self) -> None:
        opened, snoozed = [], []
        p = ReminderPopup(self.sm.settings, "memo-0000", "title", "detail", opened.append,
                          lambda memo_id, minutes: snoozed.append((memo_id, minutes)))
        p.show()
        buttons = {b.text(): b for b in p.findChildren(QPushButton)}
        buttons["1시간"].click()
        self.assertEqual(snoozed, [("memo-0000", 60)])
        self.assertEqual(opened, [])


if __name__ == "__main__":
    unittest.main()
