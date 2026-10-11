"""처리하지 못한 오류의 기록과 보고 메일, 메모 창에서 지우기, 시작 직후 동기화, 암호 걸기 실패."""
import json
import sys
import threading
import unittest
from unittest import mock

from PyQt6.QtCore import QTimer
from PyQt6.QtTest import QTest

# support 를 먼저 가져와야 합니다. (offscreen 설정과 프로젝트 경로)
import support
from core import error_report
from core.sync_worker import SYNC_OFFLINE
from drive_api import DriveAPI
from test_core import SyncManagerTestCase


class Mailbox:
    """보고 메일을 받는 가짜 드라이브."""

    def __init__(self, available: bool = True) -> None:
        self.available = available
        self.mails = []
        self.arrived = threading.Event()

    def is_available(self) -> bool:
        return self.available

    def send_error_report(self, subject: str, body: str) -> bool:
        self.mails.append((subject, body))
        self.arrived.set()
        return True


def boom() -> None:
    raise ValueError("테스트용 오류")


def caught(func=boom):
    try:
        func()
    except Exception:
        return sys.exc_info()


class ErrorReportTest(SyncManagerTestCase):
    def reporter(self, available: bool = True, clock=None):
        self.box = Mailbox(available)
        self.sm.drive_api = self.box
        self.now = [0.0]
        return error_report.ErrorReporter(self.sm, clock or (lambda: self.now[0]))

    def log(self) -> str:
        path = self.sm.error_log_path
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def test_unhandled_error_is_logged_and_mailed(self) -> None:
        reporter = self.reporter()
        reporter.handle(*caught())
        self.assertTrue(self.box.arrived.wait(2))
        subject, body = self.box.mails[0]
        self.assertIn("ValueError: 테스트용 오류", subject)
        self.assertIn(error_report.APP_VERSION, subject)
        self.assertIn("Traceback", body)
        self.assertIn("in boom", body)
        self.assertIn("처리하지 못한 오류", self.log())
        self.assertIn("in boom", self.log())

    def test_same_error_is_mailed_once_and_others_are_spaced_out(self) -> None:
        reporter = self.reporter()
        info = caught()
        trace = "".join(error_report.traceback.format_exception(*info))
        self.assertTrue(reporter.submit("a", trace))
        self.assertFalse(reporter.submit("a", trace))                 # 같은 오류
        self.assertFalse(reporter.submit("b", trace + "other"))       # 다른 오류라도 너무 금방이면 보내지 않음
        self.now[0] += error_report.MIN_GAP_SEC
        self.assertTrue(reporter.submit("b", trace + "other"))

    def test_at_most_a_few_mails_per_run(self) -> None:
        reporter = self.reporter()
        sent = 0
        for n in range(error_report.MAX_PER_RUN + 3):
            self.now[0] += error_report.MIN_GAP_SEC
            sent += reporter.submit("e", f"trace {n}")
        self.assertEqual(sent, error_report.MAX_PER_RUN)

    def test_nothing_is_mailed_when_turned_off_or_sync_is_not_set_up(self) -> None:
        reporter = self.reporter()
        self.sm.settings["error_report"] = False
        self.assertFalse(reporter.submit("a", "trace"))
        reporter.handle(*caught())
        self.assertIn("처리하지 못한 오류", self.log())                 # 메일은 안 보내도 기록은 남김
        self.sm.settings["error_report"] = True
        self.assertFalse(self.reporter(available=False).submit("a", "trace"))
        self.assertEqual(self.box.mails, [])

    def test_a_failing_mail_never_raises(self) -> None:
        reporter = self.reporter()
        self.box.send_error_report = mock.Mock(side_effect=RuntimeError("network"))
        reporter.handle(*caught())                                    # 예외가 밖으로 나오지 않음
        self.sm.log_error = mock.Mock(side_effect=OSError("disk"))
        reporter.handle(*caught())

    def test_error_inside_a_qt_slot_does_not_stop_the_app(self) -> None:
        old_hook, old_thread_hook = sys.excepthook, threading.excepthook
        self.addCleanup(setattr, sys, "excepthook", old_hook)
        self.addCleanup(setattr, threading, "excepthook", old_thread_hook)
        self.box = Mailbox()
        self.sm.drive_api = self.box
        error_report.install(self.sm)
        after = []
        QTimer.singleShot(0, boom)
        QTimer.singleShot(10, lambda: after.append("still running"))
        QTest.qWait(100)
        self.assertEqual(after, ["still running"])
        self.assertTrue(self.box.arrived.wait(2))
        self.assertIn("in boom", self.log())

    def test_errors_in_other_threads_are_caught_too(self) -> None:
        old_hook, old_thread_hook = sys.excepthook, threading.excepthook
        self.addCleanup(setattr, sys, "excepthook", old_hook)
        self.addCleanup(setattr, threading, "excepthook", old_thread_hook)
        self.box = Mailbox()
        self.sm.drive_api = self.box
        error_report.install(self.sm)
        worker = threading.Thread(target=boom)
        worker.start()
        worker.join()
        self.assertTrue(self.box.arrived.wait(2))


class ReportRequestTest(unittest.TestCase):
    def test_request_carries_no_recipient_and_checks_the_reply(self) -> None:
        api = DriveAPI()
        api.set_web_app_url("https://example.invalid/exec")
        api.set_access_token("pw")
        reply = mock.Mock(status_code=200, text="Reported")
        with mock.patch("drive_api.requests.post", return_value=reply) as post:
            self.assertTrue(api.send_error_report("제목", "본문"))
        sent = json.loads(post.call_args.kwargs["data"])
        self.assertEqual(sent, {"action": "report", "subject": "제목", "body": "본문", "token": "pw"})
        reply.text = "Bad filename"                                   # 이 요청을 모르는 예전 스크립트
        with mock.patch("drive_api.requests.post", return_value=reply):
            self.assertFalse(api.send_error_report("제목", "본문"))
        with mock.patch("drive_api.requests.post", side_effect=OSError("offline")):
            self.assertFalse(api.send_error_report("제목", "본문"))
        self.assertFalse(DriveAPI().send_error_report("제목", "본문"))  # 동기화 주소가 없으면 보내지 않음


class StartupSyncTest(SyncManagerTestCase):
    def test_startup_sync_scans_everything_but_stays_quiet_offline(self) -> None:
        self.sm.settings["use_sync"] = True
        started = []
        self.sm._start_worker = started.append
        self.sm._startup_sync()
        worker = started[0]
        self.assertIsNone(worker.push_ids)                            # 모든 메모를 훑음
        self.assertTrue(worker.quiet)
        shown = []
        self.sm.ui_manager = mock.Mock(show_sync_result=lambda *a: shown.append(a))
        self.drive.online = False
        worker.finished.connect(self.sm.on_sync_finished)
        worker.run_sync()
        self.assertEqual(shown, [])                                   # 인터넷 없이 켜도 경고하지 않음
        self.sm._push_timer.stop()

    def test_sync_button_still_reports_a_failed_connection(self) -> None:
        self.sm.settings["use_sync"] = True
        started = []
        self.sm._start_worker = started.append
        self.sm.sync_all()
        worker = started[0]
        shown = []
        self.sm.ui_manager = mock.Mock(show_sync_result=lambda *a: shown.append(a))
        self.drive.online = False
        worker.finished.connect(self.sm.on_sync_finished)
        worker.run_sync()
        self.assertEqual(len(shown), 1)
        self.assertFalse(shown[0][0])
        self.sm._push_timer.stop()


class PasswordRollbackTest(SyncManagerTestCase):
    def test_failed_save_leaves_the_memo_unlocked_as_before(self) -> None:
        memo = self._memo("memo-aaaa", "secret")
        self.sm.save_memo_locally(memo)
        with mock.patch.object(self.sm, "save_memo_locally", return_value=False):
            self.assertFalse(self.sm.set_memo_password(memo, "pw12"))
        self.assertFalse(memo.get("is_locked"))
        self.assertFalse(self.sm.is_memo_unlocked("memo-aaaa"))
        self.assertEqual(self._disk("memo-aaaa")["content"], "secret")

    def test_failed_password_change_keeps_the_old_key(self) -> None:
        memo = self._memo("memo-aaaa", "secret")
        self.sm.save_memo_locally(memo)
        self.assertTrue(self.sm.set_memo_password(memo, "old1"))
        old_key = self.sm._memo_keys["memo-aaaa"]
        with mock.patch.object(self.sm, "save_memo_locally", return_value=False):
            self.assertFalse(self.sm.set_memo_password(memo, "new1"))
        self.assertEqual(self.sm._memo_keys["memo-aaaa"], old_key)
        self.sm.relock_memo("memo-aaaa")
        self.assertEqual(self.sm.unlock_memo("memo-aaaa", "old1"), "secret")       # 파일도 예전 암호 그대로

    def test_failed_removal_keeps_the_memo_locked(self) -> None:
        memo = self._memo("memo-aaaa", "secret")
        self.sm.save_memo_locally(memo)
        self.sm.set_memo_password(memo, "pw12")
        with mock.patch.object(self.sm, "save_memo_locally", return_value=False):
            self.assertFalse(self.sm.remove_memo_password(memo))
        self.assertTrue(memo["is_locked"])
        self.assertTrue(self.sm.is_memo_unlocked("memo-aaaa"))


class MemoDeleteTest(support.UiTestCase):
    def window(self, **changes):
        w = self.open_window("memo-0000")
        w.memo_data.update(changes)
        self.asked = []
        real = support.themed_dialog.confirm
        patcher = mock.patch.object(support.themed_dialog, "confirm",
                                    lambda *a, **k: (self.asked.append(a[2]), self.confirm_answer)[1])
        patcher.start()
        self.addCleanup(patcher.stop)
        return w

    def test_protected_memo_is_not_deleted_from_its_window(self) -> None:
        w = self.window(is_protected=True)
        w.request_delete()
        self.assertIn("memo-0000", self.ui.memo_windows)
        self.assertEqual(self.asked, [])
        self.assertTrue((self.memo_dir / "memo-0000.json").exists())

    def test_delete_asks_first_and_can_be_cancelled(self) -> None:
        w = self.window()
        self.confirm_answer = False
        w.request_delete()
        self.assertEqual(len(self.asked), 1)
        self.assertIn("memo-0000", self.ui.memo_windows)
        self.confirm_answer = True
        w.request_delete()
        self.assertNotIn("memo-0000", self.ui.memo_windows)
        self.assertTrue((self.sm.trash_path / "memo-0000.json").exists())

    def test_blank_memo_is_deleted_without_asking(self) -> None:
        self.ui.create_empty_memo()
        w = next(w for w in self.ui.memo_windows.values() if w.memo_data.get("is_draft"))
        memo_id = w.memo_data["id"]
        self.asked = []
        with mock.patch.object(support.themed_dialog, "confirm", lambda *a, **k: self.asked.append(a) or True):
            w.request_delete()
        self.assertEqual(self.asked, [])
        self.assertNotIn(memo_id, self.ui.memo_windows)

    def test_settings_has_the_error_report_switch(self) -> None:
        win = support.sw.SettingsWindow(self.sm)
        self.addCleanup(win.close)
        self.assertTrue(win.cb_error_report.isChecked())              # 기본은 켬
        win.cb_error_report.setChecked(False)
        self.assertFalse(win.collect()["error_report"])
        self.assertNotIn("error_report", support.smm.shared_settings.SHARED_KEYS)   # 기기마다 따로


if __name__ == "__main__":
    unittest.main()
