"""예약된 알림 목록: 미리보기 옆의 버튼, 빨리 울리는 순서, 미루기·건너뛰기·해제·되돌리기, 열기·바꾸기."""
import datetime as dt
import unittest
from unittest import mock

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QLabel, QPushButton

# support 를 먼저 가져와야 합니다. (offscreen 설정과 프로젝트 경로)
import support
from core import reminders
from ui.reminder_list import ReminderListPanel, ask_reminder_list, time_left

D = dt.datetime


class PostponeRuleTest(unittest.TestCase):
    def test_one_shot_moves_from_its_own_time_not_from_now(self) -> None:
        now = D(2026, 10, 11, 12, 0)
        later = reminders.postponed(reminders.make(D(2026, 10, 13, 9, 0)), 60, now)
        self.assertEqual(reminders.due_at(later), D(2026, 10, 13, 10, 0))
        self.assertEqual(later["repeat"], "none")
        overdue = reminders.postponed(reminders.make(D(2026, 10, 11, 9, 0)), 10, now)      # 이미 지났으면 지금부터
        self.assertEqual(reminders.due_at(overdue), D(2026, 10, 11, 12, 10))
        self.assertIsNone(reminders.postponed({"at": "nonsense"}, 10, now))

    def test_repeat_is_late_once_and_then_back_on_schedule(self) -> None:
        now = D(2026, 10, 11, 12, 0)
        daily = reminders.make_repeating("daily", 9, 0, now)                               # 다음: 12일 9시
        later = reminders.postponed(daily, 60, now)
        self.assertEqual(reminders.due_at(later), D(2026, 10, 12, 10, 0))
        self.assertEqual(reminders.due_at(reminders.following(later, D(2026, 10, 12, 10, 0, 1))), D(2026, 10, 13, 9, 0))
        twice = reminders.postponed(later, 60, now)                                        # 또 미뤄도 원래 일정은 그대로
        self.assertEqual(twice["resume"], later["resume"])
        self.assertEqual(reminders.due_at(reminders.following(twice, D(2026, 10, 12, 11, 0, 1))), D(2026, 10, 13, 9, 0))

    def test_skipping_goes_to_the_next_turn(self) -> None:
        now = D(2026, 10, 11, 12, 0)
        daily = reminders.make_repeating("daily", 9, 0, now)
        self.assertEqual(reminders.due_at(reminders.skipped(daily, now)), D(2026, 10, 13, 9, 0))
        snoozed = reminders.snoozed(daily, 10, now)                                        # 12:10 으로 미뤄 둔 것을 건너뛰면 원래 일정으로
        self.assertEqual(reminders.due_at(reminders.skipped(snoozed, now)), D(2026, 10, 12, 9, 0))
        postponed = reminders.postponed(daily, 60, now)                                    # 12일 10시로 늦춘 것을 건너뛰면 그다음 차례
        self.assertEqual(reminders.due_at(reminders.skipped(postponed, now)), D(2026, 10, 13, 9, 0))
        self.assertIsNone(reminders.skipped(reminders.make(D(2026, 10, 13, 9, 0)), now))   # 한 번짜리는 건너뛸 것이 없음

    def test_time_left(self) -> None:
        now = D(2026, 10, 11, 12, 0)
        self.assertEqual(time_left(now - dt.timedelta(minutes=1), now), "지남")
        self.assertEqual(time_left(now + dt.timedelta(seconds=30), now), "곧")
        self.assertEqual(time_left(now + dt.timedelta(minutes=25), now), "25분 뒤")
        self.assertEqual(time_left(now + dt.timedelta(hours=3, minutes=10), now), "3시간 10분 뒤")
        self.assertEqual(time_left(now + dt.timedelta(days=2, hours=4, minutes=30), now), "2일 4시간 뒤")


class ReminderListTest(support.UiTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.now = D.now().replace(microsecond=0)
        self.set("memo-0000", reminders.make(self.now + dt.timedelta(days=3)))
        self.set("memo-0001", reminders.make(self.now + dt.timedelta(hours=2)))
        self.set("memo-0002", reminders.make_repeating("daily", (self.now.hour + 5) % 24, 0, self.now))
        support.app.processEvents()

    def set(self, memo_id: str, reminder) -> None:
        self.sm.set_reminder(next(m for m in self.sm.load_local_memos() if m["id"] == memo_id), reminder)

    def due(self, memo_id: str) -> D:
        return reminders.due_at(self.disk(memo_id)["reminder"])

    def panel(self) -> ReminderListPanel:
        panel = ReminderListPanel(self.ui)
        self.addCleanup(panel.deleteLater)
        return panel

    def test_soonest_first_with_titles(self) -> None:
        entries = self.ui.reminder_entries()
        self.assertEqual([e["title"] for e in entries], ["t1", "t2", "t0"])
        panel = self.panel()
        self.assertEqual(list(panel.rows), ["memo-0001", "memo-0002", "memo-0000"])
        self.assertTrue(panel.empty_label.isHidden())
        self.assertIn("3개", panel.count_label.text())
        self.assertNotIn("skip", panel.rows["memo-0001"].buttons)          # 한 번짜리에는 건너뛰기가 없음
        self.assertIn("skip", panel.rows["memo-0002"].buttons)

    def test_postpone_moves_the_scheduled_time_and_reorders(self) -> None:
        panel = self.panel()
        before = self.due("memo-0001")
        panel.rows["memo-0001"].buttons[60].click()
        self.assertEqual(self.due("memo-0001"), before + dt.timedelta(hours=1))
        self.assertEqual(self.disk("memo-0001")["updated_at"], "2026-01-02T00:00:00")     # 수정일시는 그대로
        panel.rows["memo-0001"].buttons[1440].click()
        self.assertEqual(self.due("memo-0001"), before + dt.timedelta(hours=1, days=1))
        self.assertEqual(list(panel.rows), ["memo-0002", "memo-0001", "memo-0000"])
        self.assertIn("미뤘습니다", panel.status_label.text())
        support.app.processEvents()
        self.assertTrue(self.ui._reminder_timer.isActive())

    def test_skip_clear_and_undo(self) -> None:
        panel = self.panel()
        first = self.due("memo-0002")
        panel.rows["memo-0002"].buttons["skip"].click()
        self.assertEqual(self.due("memo-0002"), first + dt.timedelta(days=1))
        self.assertFalse(panel.undo_button.isHidden())
        panel.undo_button.click()
        self.assertEqual(self.due("memo-0002"), first)
        self.assertTrue(panel.undo_button.isHidden())                       # 되돌린 것을 또 되돌리지는 않음

        kept = dict(self.disk("memo-0000")["reminder"])
        panel.rows["memo-0000"].buttons["clear"].click()
        self.assertNotIn("reminder", self.disk("memo-0000"))
        self.assertNotIn("memo-0000", panel.rows)
        self.assertIn("해제", panel.status_label.text())
        panel.undo_button.click()
        self.assertEqual(self.disk("memo-0000")["reminder"], kept)
        self.assertIn("memo-0000", panel.rows)

    def test_open_window_keeps_its_own_data_in_step(self) -> None:
        w = self.open_window("memo-0001")
        panel = self.panel()
        panel.rows["memo-0001"].buttons[10].click()
        self.assertEqual(w.memo_data["reminder"], self.disk("memo-0001")["reminder"])
        panel.rows["memo-0001"].buttons["clear"].click()
        self.assertNotIn("reminder", w.memo_data)
        self.assertTrue(w.btn_reminder.isHidden())

    def test_failed_save_is_reported(self) -> None:
        panel = self.panel()
        with mock.patch.object(self.sm, "save_memo_locally", return_value=False):
            panel.rows["memo-0001"].buttons[10].click()
        self.assertIn("저장하지 못했습니다", panel.status_label.text())

    def test_list_follows_reminders_that_ring_meanwhile(self) -> None:
        panel = self.panel()
        self.set("memo-0001", reminders.make(D.now() - dt.timedelta(seconds=5)))
        self.ui.check_reminders()                                           # 울리면 한 번짜리는 풀림
        support.app.processEvents()
        self.assertNotIn("memo-0001", panel.rows)
        self.ui._reminder_popups[0].close()

    def test_empty_list_and_locked_memo(self) -> None:
        w = self.open_window("memo-0001")
        self.answers[:] = ["pw12", "pw12"]
        w.set_memo_password()
        w.close()
        panel = self.panel()
        self.assertTrue(panel.rows["memo-0001"].findChildren(type(panel.count_label))[2].text().startswith("🔒"))
        for memo_id in list(panel.rows):
            panel.rows[memo_id].buttons["clear"].click()
        self.assertEqual(panel.rows, {})
        self.assertFalse(panel.empty_label.isHidden())
        self.assertEqual(self.sm.reminders, {})

    # ── 탐색기 ───────────────────────────────────────────────────────────────
    def test_button_sits_beside_the_preview_title_and_counts(self) -> None:
        ex = self.explorer()
        self.assertFalse(ex.btn_reminders.icon().isNull())
        self.assertEqual(ex.btn_reminders.text().strip(), "3")
        self.assertEqual(ex.btn_reminders.y(), ex.btn_settings.y())
        # 왼쪽 끝에 환경설정, 가운데에 제목, 오른쪽 끝에 예약된 알림
        ex.resize(720, 640)
        support.app.processEvents()
        title = next(label for label in ex.findChildren(QLabel) if label.text() == "미리보기")
        self.assertEqual(ex.btn_settings.x(), ex.pv.x())
        self.assertEqual(ex.btn_reminders.x() + ex.btn_reminders.width(), ex.pv.x() + ex.pv.width())
        self.assertLessEqual(abs(title.geometry().center().x() - ex.pv.geometry().center().x()), 2)
        ex.show_toast("저장됨")                                             # 토스트는 환경설정 버튼 옆에
        support.app.processEvents()
        self.assertGreater(ex.toast.x(), ex.btn_settings.x())
        self.assertLess(ex.toast.x() + ex.toast.width(), title.x())
        self.ui.change_reminder("memo-0000", None)
        support.app.processEvents()
        self.assertEqual(ex.btn_reminders.text().strip(), "2")
        for memo_id in ("memo-0001", "memo-0002"):
            self.ui.change_reminder(memo_id, None)
        support.app.processEvents()
        self.assertEqual(ex.btn_reminders.text(), "")
        self.assertIn("없음", ex.btn_reminders.toolTip())

    def test_list_opens_inside_the_explorer(self) -> None:
        ex = self.explorer()
        ex.resize(720, 640)
        support.app.processEvents()
        seen = {}

        def steps() -> None:
            overlay = ex.inline_overlay
            seen["inside"] = overlay.isVisible() and isinstance(overlay.panel, ReminderListPanel)
            before = self.due("memo-0001")
            overlay.panel.rows["memo-0001"].buttons[10].click()            # 목록을 닫지 않고 미룸
            seen["postponed"] = self.due("memo-0001") == before + dt.timedelta(minutes=10)
            seen["still open"] = overlay.panel is not None and overlay.isVisible()
            overlay.panel.close_button.click()

        QTimer.singleShot(0, steps)
        ex.btn_reminders.click()
        self.assertEqual(seen, {"inside": True, "postponed": True, "still open": True})
        self.assertTrue(ex.inline_overlay.isHidden())

    def test_card_is_as_tall_as_its_content(self) -> None:
        """카드가 처음 잰 작은 크기로 굳어 아래쪽 버튼이 잘리던 문제."""
        from ui.reminder_ui import ReminderForm, ask_reminder
        ex = self.explorer()
        ex.resize(900, 760)
        support.app.processEvents()
        seen = {}

        def check(name: str, last_button) -> None:
            overlay = ex.inline_overlay
            support.app.processEvents()
            card, inner = overlay._card, overlay._card.widget()
            seen[name] = (card.height() >= inner.sizeHint().height()
                          and card.verticalScrollBar().maximum() == 0
                          and last_button(overlay.panel).mapTo(card, last_button(overlay.panel).rect().bottomLeft()).y() < card.height())
            overlay.panel.cancelled.emit()

        QTimer.singleShot(0, lambda: check("list", lambda panel: panel.close_button))
        ex.btn_reminders.click()
        QTimer.singleShot(0, lambda: check("form", lambda form: form.findChildren(QPushButton)[-1]))
        ask_reminder(ex, None, "t")
        self.assertEqual(seen, {"list": True, "form": True})

    def test_form_that_does_not_fit_opens_as_a_dialog(self) -> None:
        from ui.reminder_ui import ReminderDialog, ask_reminder
        ex = self.explorer()
        ex.resize(600, 460)                                                 # 요일·날짜 단추 줄이 들어가지 않는 너비
        support.app.processEvents()
        seen = {}

        def steps() -> None:
            dialog = support.app.activeModalWidget()
            seen["dialog"] = isinstance(dialog, ReminderDialog)
            seen["overlay"] = ex.inline_overlay.isVisible()
            dialog.reject()

        QTimer.singleShot(0, steps)
        self.assertEqual(ask_reminder(ex, None, "t"), (False, None))
        self.assertEqual(seen, {"dialog": True, "overlay": False})

    def test_many_reminders_scroll_inside_the_list(self) -> None:
        for i in range(3, 10):
            self.sm.save_memo_locally({"id": f"memo-000{i}", "title": f"t{i}", "content": "x",
                                       "updated_at": "2026-01-01T00:00:00", "is_visible": False,
                                       "reminder": reminders.make(self.now + dt.timedelta(days=i))})
        self.sm.load_local_memos()
        panel = self.panel()
        panel.show()
        support.app.processEvents()
        self.assertEqual(len(panel.rows), 10)
        self.assertEqual(panel.rows_scroll.height(), panel.MAX_ROWS_HEIGHT)
        self.assertGreater(panel.rows_scroll.verticalScrollBar().maximum(), 0)
        self.assertLess(panel.sizeHint().height(), panel.MAX_ROWS_HEIGHT + 140)
        for memo_id in list(panel.rows)[2:]:
            panel.clear(memo_id)
        support.app.processEvents()
        self.assertLess(panel.rows_scroll.height(), panel.MAX_ROWS_HEIGHT)    # 줄이 줄면 목록 칸도 줄어듦
        self.assertEqual(panel.rows_scroll.verticalScrollBar().maximum(), 0)
        panel.hide()

    def test_open_and_edit_from_the_list(self) -> None:
        ex = self.explorer()
        with mock.patch("ui.memo_explorer.ask_reminder_list", side_effect=[("open", "memo-0001")]):
            ex.show_reminder_list()
        self.assertTrue(self.ui.memo_windows["memo-0001"].isVisible())

        new = reminders.make(self.now + dt.timedelta(days=9))
        with mock.patch("ui.memo_explorer.ask_reminder_list", side_effect=[("edit", "memo-0000"), None]) as asked, \
                mock.patch("ui.memo_explorer.ask_reminder", return_value=(True, new)):
            ex.show_reminder_list()
        self.assertEqual(asked.call_count, 2)                               # 바꾼 뒤 목록으로 돌아옴
        self.assertEqual(self.disk("memo-0000")["reminder"]["at"], new["at"])

    def test_dialog_is_used_when_there_is_no_room(self) -> None:
        seen = {}

        def steps() -> None:
            dialog = support.app.activeModalWidget()
            seen["dialog"] = dialog is not None and bool(dialog.findChildren(ReminderListPanel))
            dialog.findChildren(ReminderListPanel)[0].rows["memo-0001"].buttons["open"].click()

        QTimer.singleShot(0, steps)
        self.assertEqual(ask_reminder_list(None, self.ui), ("open", "memo-0001"))
        self.assertTrue(seen["dialog"])


if __name__ == "__main__":
    unittest.main()
