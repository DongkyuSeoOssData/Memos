"""3.3.1 에서 바꾼 것: 글꼴 줄의 자리, 알림의 저장 실패·오류·시작 직후 확인, 오류 알림, 미리보기와 메모 창."""
import datetime as dt
import unittest
from unittest import mock

from PyQt6.QtCore import QEvent
from PyQt6.QtGui import QFocusEvent
from PyQt6.QtTest import QTest

# support 를 먼저 가져와야 합니다. (offscreen 설정과 프로젝트 경로)
import support
from core import error_report
from core.sync_worker import SYNC_OFFLINE, SyncWorker
from test_core import SyncManagerTestCase

PAST = {"at": "2020-01-01T09:00:00", "repeat": "none"}


class FontBarPlacementTest(support.UiTestCase):
    def test_font_bar_opens_above_and_the_format_buttons_stay_put(self) -> None:
        w = self.open_window("memo-0000")
        w.resize(420, 420)
        w.show()
        support.app.processEvents()
        before = w.btn_bold.mapTo(w, w.btn_bold.rect().topLeft())
        editor_height = w.text_edit.height()
        self.assertEqual(w.btn_toggle_sub_fmt.text(), "Aa ▴")
        w.toggle_sub_fmt_panel()
        support.app.processEvents()
        self.assertTrue(w.sub_fmt_widget.isVisible())
        self.assertEqual(w.btn_bold.mapTo(w, w.btn_bold.rect().topLeft()), before)        # 서식 버튼은 제자리
        font_bar_y = w.sub_fmt_widget.mapTo(w, w.sub_fmt_widget.rect().topLeft()).y()
        self.assertLess(font_bar_y, before.y())                                           # 글꼴 줄은 그 위에
        self.assertLess(w.text_edit.height(), editor_height)                              # 본문이 그만큼 줄어듦
        self.assertEqual(w.btn_toggle_sub_fmt.text(), "Aa ▾")
        w.toggle_sub_fmt_panel()
        support.app.processEvents()
        self.assertEqual(w.btn_bold.mapTo(w, w.btn_bold.rect().topLeft()), before)


class ReminderRobustnessTest(support.UiTestCase):
    def remind(self, memo_id: str = "memo-0000") -> None:
        memo = next(m for m in self.sm.load_local_memos() if m["id"] == memo_id)
        self.sm.set_reminder(memo, dict(PAST))
        support.app.processEvents()
        self.ui._reminder_timer.stop()

    def popups(self) -> int:
        return len(self.ui._reminder_popups)

    def test_reminder_that_cannot_be_saved_rings_only_once(self) -> None:
        self.remind()
        with mock.patch.object(self.sm, "save_memo_locally", return_value=False):
            self.ui.check_reminders()
            self.assertEqual(self.popups(), 1)
            self.sm.load_local_memos()                                # 파일에는 알림이 그대로 남아 있어 다시 읽힘
            self.ui.check_reminders()
            self.assertEqual(self.popups(), 1)                        # 그래도 같은 알림은 다시 울리지 않음
            support.app.processEvents()
            self.assertFalse(self.ui._reminder_timer.isActive())

    def test_one_broken_reminder_does_not_stop_the_others(self) -> None:
        self.remind("memo-0000")
        self.remind("memo-0001")
        real = self.ui.fire_reminder
        rung = []

        def fire(memo_id, reminder, now):
            if memo_id == "memo-0000":
                raise RuntimeError("broken")
            rung.append(memo_id)
            real(memo_id, reminder, now)

        self.ui.fire_reminder = fire
        self.ui.check_reminders()
        self.assertEqual(rung, ["memo-0001"])
        self.ui.check_reminders()
        self.assertEqual(rung, ["memo-0001"])                         # 문제의 알림을 되풀이해 시도하지 않음
        self.assertIn("알림을 울리지 못함", self.sm.error_log_path.read_text(encoding="utf-8"))

    def test_first_check_waits_for_the_startup_sync(self) -> None:
        self.remind()
        self.ui._reminders_on_hold = True                            # 동기화를 쓰는 PC에서 앱을 막 켠 상태
        self.ui.schedule_reminders()
        self.assertFalse(self.ui._reminder_timer.isActive())
        self.ui.release_reminders()                                  # 시작 동기화가 끝남
        self.assertTrue(self.ui._reminder_timer.isActive())
        self.assertFalse(self.ui._reminders_on_hold)
        self.ui._reminder_timer.stop()

    def test_hold_is_only_used_when_sync_is_set_up(self) -> None:
        self.assertFalse(self.ui._reminders_on_hold)                 # 이 시험 환경은 동기화를 쓰지 않음
        self.assertFalse(self.sm.startup_sync_expected())
        self.sm.settings["use_sync"] = True
        self.assertFalse(self.sm.startup_sync_expected())            # 주소가 없음
        self.sm.drive_api.set_web_app_url("https://example.invalid/exec")
        self.assertTrue(self.sm.startup_sync_expected())
        self.sm.settings["use_sync"] = False
        self.sm.drive_api.set_web_app_url("")


class SyncCycleSignalTest(SyncManagerTestCase):
    def test_cycle_end_is_announced_even_when_it_fails(self) -> None:
        self.sm.settings["use_sync"] = True
        self.sm._start_worker = lambda worker: None
        ended = []
        self.sm.sync_cycle_finished.connect(lambda: ended.append(True))
        self.drive.online = False
        self.sm._startup_sync()
        self.sm._current_worker.run_sync()
        self.assertEqual(ended, [True])
        self.sm._push_timer.stop()

    def test_missing_address_counts_as_unreachable(self) -> None:
        self.drive.is_available = lambda: False
        results = []
        worker = SyncWorker(self.sm)
        worker.finished.connect(lambda *a: results.append(a))
        worker.run_sync()
        self.assertEqual(results[0][2], SYNC_OFFLINE)                # 시작 직후에는 알리지 않는 종류
        self.assertFalse(results[0][0])


class ErrorNoticeTest(SyncManagerTestCase):
    def test_user_is_told_once_per_burst(self) -> None:
        now = [0.0]
        reporter = error_report.ErrorReporter(self.sm, lambda: now[0])
        told = []
        reporter.notify = lambda: told.append(True)
        for _ in range(3):
            try:
                raise ValueError("x")
            except ValueError as e:
                reporter.handle(type(e), e, e.__traceback__)
        self.assertEqual(len(told), 1)
        now[0] += error_report.MIN_GAP_SEC
        try:
            raise ValueError("y")
        except ValueError as e:
            reporter.handle(type(e), e, e.__traceback__)
        self.assertEqual(len(told), 2)

    def test_a_failing_notice_is_swallowed(self) -> None:
        reporter = error_report.ErrorReporter(self.sm)
        reporter.notify = mock.Mock(side_effect=RuntimeError("no tray"))
        try:
            raise ValueError("x")
        except ValueError as e:
            reporter.handle(type(e), e, e.__traceback__)


class PreviewAndWindowTest(support.UiTestCase):
    def test_entering_the_preview_saves_what_was_typed_in_the_window(self) -> None:
        ex = self.explorer()
        w = self.open_window("memo-0000")
        row = next(r for r in range(ex.table.rowCount())
                   if ex.table.item(r, 2).data(support.Qt.ItemDataRole.UserRole)["id"] == "memo-0000")
        ex.table.selectRow(row)
        ex.on_cell_click(row, 2)
        w.text_edit.setPlainText("typed in the window")
        w.text_edit.document().setModified(True)
        w._schedule_auto_save()
        self.assertTrue(w._auto_save_timer.isActive())

        support.app.sendEvent(ex.pv, QFocusEvent(QEvent.Type.FocusIn))
        support.app.processEvents()
        self.assertFalse(w._auto_save_timer.isActive())
        saved = next(m for m in self.sm.load_local_memos() if m["id"] == "memo-0000")
        self.assertIn("typed in the window", saved["content"])
        self.assertIn("typed in the window", ex.pv.toPlainText())    # 미리보기도 방금 쓴 글로 바뀜


if __name__ == "__main__":
    unittest.main()
