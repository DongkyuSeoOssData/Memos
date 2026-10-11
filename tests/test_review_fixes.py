"""3.2.3 에서 고친 문제: 끊긴 동기화 알림, 받은 설정값의 형식, 스레드에서의 삭제 반영, 충돌 사본, 제목 바꾸기."""
import unittest

# support 를 먼저 가져와야 합니다. (offscreen 설정과 프로젝트 경로)
import support
from core import shared_settings
from core.sync_worker import SYNC_CHANGED, SYNC_OFFLINE, SyncWorker
from test_core import SyncManagerTestCase


class OfflineSyncTest(SyncManagerTestCase):
    def run_worker(self, push_ids=None):
        results = []
        worker = SyncWorker(self.sm)
        worker.push_ids = push_ids
        worker.finished.connect(lambda *a: results.append(a))
        worker.run_sync()
        return worker, results

    def test_unreachable_drive_is_reported_as_a_failure(self) -> None:
        self.sm.save_memo_locally(self._memo("memo-aaaa", "one"))
        self.drive.online = False
        _, results = self.run_worker()
        self.assertEqual(len(results), 1)
        success, message, outcome = results[0]
        self.assertFalse(success)
        self.assertEqual(outcome, SYNC_OFFLINE)
        self.assertIn("연결하지 못했습니다", message)
        self.assertEqual(self.drive.uploads, [])

        self.drive.online = True                                     # 다시 연결되면 그대로 올라감
        _, results = self.run_worker()
        self.assertEqual(results[0][0], True)
        self.assertEqual(results[0][2], SYNC_CHANGED)
        self.assertEqual(self.drive.uploads, ["memo-aaaa.json"])

    def test_unsent_changes_are_kept_for_the_next_sync(self) -> None:
        self.sm.settings["use_sync"] = True
        self.sm._start_worker = lambda worker: None                  # 스레드를 띄우지 않고 직접 돌림
        self.sm.save_memo_locally(self._memo("memo-aaaa", "one"))
        self.assertEqual(self.sm._dirty_ids, {"memo-aaaa"})
        self.drive.online = False
        self.sm._start_sync()
        worker = self.sm._current_worker
        worker.finished.connect(self.sm._on_sync_cycle_done)
        worker.run_sync()
        self.assertEqual(self.sm._dirty_ids, {"memo-aaaa"})          # 올리지 못한 메모는 그대로 남음
        self.sm._push_timer.stop()

    def test_conflict_copy_is_uploaded_in_the_same_sync_and_has_no_reminder(self) -> None:
        self.sm.save_memo_locally(self._memo("memo-aaaa", "one"))
        self.run_worker()
        remote = self._disk("memo-aaaa")
        remote.update(content="remote edit", updated_at="2026-03-01T00:00:00")
        self.drive.put("memo-aaaa.json", remote)
        local = self._memo("memo-aaaa", "local edit", "2026-02-01T00:00:00")
        local["reminder"] = {"at": "2030-01-01T09:00:00", "repeat": "none"}
        self.sm.save_memo_locally(local)
        self.drive.uploads.clear()

        self.run_worker(push_ids={"memo-aaaa"})                       # 바뀐 메모만 올리는 동기화
        copies = [m for m in self.sm.load_local_memos() if m["content"] == "local edit"]
        self.assertEqual(len(copies), 1)
        self.assertNotIn("reminder", copies[0])
        self.assertIn(f"{copies[0]['id']}.json", self.drive.uploads)

    def test_remote_deletion_only_moves_the_file_on_the_worker(self) -> None:
        memo = self._memo("memo-aaaa", "one")
        memo["reminder"] = {"at": "2030-01-01T09:00:00", "repeat": "none"}
        self.sm.save_memo_locally(memo)
        self.sm.save_memo_locally(self._memo("memo-bbbb", "two"))
        self.sm.save_memo_locally(self._memo("memo-cccc", "three"))
        self.sm.save_memo_locally(self._memo("memo-dddd", "four"))
        self.run_worker()
        self.drive.files.pop("memo-aaaa.json")                       # 다른 기기에서 지움
        removed = []
        worker = SyncWorker(self.sm)
        worker.removed.connect(removed.append)
        worker.run_sync()
        self.assertEqual(removed, [["memo-aaaa"]])
        self.assertTrue((self.sm.trash_path / "memo-aaaa.json").exists())
        self.assertIn("memo-aaaa", self.sm.reminders)                # 알림 목록은 동기화 스레드가 건드리지 않음
        self.sm.on_memos_removed(removed[0])                         # 주 스레드에서 받아 정리
        self.assertNotIn("memo-aaaa", self.sm.reminders)


class BothSidesEditedTest(SyncManagerTestCase):
    """두 기기에서 같은 메모를 고쳤을 때, 밀려나는 쪽이 사본으로 남습니다."""

    def synced(self) -> None:
        self.sm.save_memo_locally(self._memo("memo-aaaa", "one"))
        SyncWorker(self.sm).run_sync()

    def edit_remote(self, content: str, updated_at: str) -> None:
        remote = dict(self.drive.files["memo-aaaa.json"][0])
        remote.update(content=content, updated_at=updated_at)
        self.drive.put("memo-aaaa.json", remote)

    def test_newer_local_edit_keeps_the_remote_edit_as_a_copy(self) -> None:
        self.synced()
        self.edit_remote("phone edit", "2026-02-01T00:00:00")                     # 다른 기기에서 먼저 고침
        self.sm.save_memo_locally(self._memo("memo-aaaa", "pc edit", "2026-03-01T00:00:00"))   # 이 PC에서 더 나중에 고침
        worker = SyncWorker(self.sm)
        worker.push_ids = {"memo-aaaa"}
        worker.run_sync()
        self.assertEqual(self._contents(), ["pc edit", "phone edit"])
        self.assertEqual(self._disk("memo-aaaa")["content"], "pc edit")           # 원래 메모는 더 나중 것
        self.assertEqual(self.drive.files["memo-aaaa.json"][0]["content"], "pc edit")
        copy = next(m for m in self.sm.load_local_memos() if m["content"] == "phone edit")
        self.assertIn("충돌 사본", copy["title"])
        self.assertIn(f"{copy['id']}.json", self.drive.files)                     # 사본도 함께 올라감

        SyncWorker(self.sm).run_sync()                                            # 다시 돌려도 사본이 늘지 않음
        self.assertEqual(self._contents(), ["pc edit", "phone edit"])

    def test_copy_is_kept_only_once_while_uploads_keep_failing(self) -> None:
        self.synced()
        self.edit_remote("phone edit", "2026-02-01T00:00:00")
        self.sm.save_memo_locally(self._memo("memo-aaaa", "pc edit", "2026-03-01T00:00:00"))
        real_upload = self.drive.upload_file
        self.drive.upload_file = lambda name, content: False
        for _ in range(3):
            worker = SyncWorker(self.sm)
            worker.run_sync()
            # 원격 수정시각을 주지 않는 예전 스크립트처럼, 매번 다시 내려받게 만듭니다.
            state = worker.state
            state["memo-aaaa"].pop("remote", None)
            worker._save_state()
        self.assertEqual(self._contents(), ["pc edit", "phone edit"])
        self.drive.upload_file = real_upload

    def test_only_this_pc_edited_makes_no_copy(self) -> None:
        self.synced()
        self.sm.save_memo_locally(self._memo("memo-aaaa", "pc edit", "2026-03-01T00:00:00"))
        worker = SyncWorker(self.sm)
        worker._load_state()
        worker.state["memo-aaaa"].pop("remote", None)                             # 다시 내려받아 견주게 함
        worker._save_state()
        SyncWorker(self.sm).run_sync()
        self.assertEqual(self._contents(), ["pc edit"])


class RenameTest(SyncManagerTestCase):
    def test_rename_reports_a_failed_save_and_restores_the_title(self) -> None:
        memo = self._memo("memo-aaaa", "one")
        self.sm.save_memo_locally(memo)
        self.assertTrue(self.sm.rename_memo_locally("memo-aaaa", "새 제목", memo))
        self.assertEqual(self._disk("memo-aaaa")["title"], "새 제목")

        locked = {"id": "memo-bbbb", "title": "old", "content": "x", "is_locked": True}     # 키가 없는 암호 메모
        self.assertFalse(self.sm.rename_memo_locally("old", "new", locked))
        self.assertEqual(locked["title"], "old")

    def test_blank_draft_can_still_be_renamed(self) -> None:
        draft = {"id": "memo-cccc", "title": "새 메모", "content": "", "is_draft": True}
        self.assertTrue(self.sm.rename_memo_locally("새 메모", "장보기", draft))
        self.assertEqual(draft["title"], "장보기")
        self.assertFalse((self.memo_dir / "memo-cccc.json").exists())               # 빈 초안은 파일로 남기지 않음


class SharedSettingShapeTest(unittest.TestCase):
    def test_wrongly_typed_values_are_dropped(self) -> None:
        got = shared_settings.from_remote({"updated_at": "2026-01-01", "settings": {
            "default_memo_width": "abc", "default_memo_height": 400, "default_is_pinned": 1, "auto_eng_kor_convert": False,
            "folders": "업무", "reminder_quick_minutes": [5, 15, 45], "shortcuts": [], "ui_style": "neo", "app_theme": 3,
            "default_memo_opacity": 0.8, "sync_interval_index": True, "local_memo_path": "C:/x"}})
        self.assertEqual(got, {"default_memo_height": 400, "auto_eng_kor_convert": False, "reminder_quick_minutes": [5, 15, 45],
                               "ui_style": "neo", "default_memo_opacity": 0.8})

    def test_every_shared_default_is_well_formed(self) -> None:
        defaults = support.smm.SyncManager.DEFAULT_SETTINGS
        for key in shared_settings.SHARED_KEYS & set(defaults):
            self.assertTrue(shared_settings.well_formed(key, defaults[key]), key)


class SettingsRobustnessTest(support.UiTestCase):
    def test_broken_saved_values_fall_back_to_defaults(self) -> None:
        self.sm.settings.update({"default_memo_width": "abc", "locked_memo_relock_min": None, "drive_folder_id": 7,
                                 "default_font_size": "12"})
        win = support.sw.SettingsWindow(self.sm)
        self.addCleanup(win.close)
        got = win.collect()
        self.assertEqual((got["default_memo_width"], got["locked_memo_relock_min"], got["drive_folder_id"],
                          got["default_font_size"]), (350, 5, "", 12))


class LookOnlyRefreshTest(support.UiTestCase):
    """모양만 바뀔 때는 본문을 다시 채우지 않습니다. (커서·실행 취소 기록이 그대로)"""

    def typing_window(self):
        w = self.open_window("memo-0000")
        w.text_edit.setPlainText("first\nsecond\nthird")
        cursor = w.text_edit.textCursor()
        cursor.setPosition(8)
        w.text_edit.setTextCursor(cursor)
        w.text_edit.insertPlainText("X")                                          # 실행 취소할 것이 생김
        return w

    def check_untouched(self, w) -> None:
        self.assertEqual(w.text_edit.textCursor().position(), 9)
        self.assertEqual(w.text_edit.toPlainText(), "first\nseXcond\nthird")
        self.assertTrue(w.text_edit.document().isUndoAvailable())

    def test_saving_settings_keeps_the_cursor_and_undo(self) -> None:
        w = self.typing_window()
        self.ui.apply_settings_to_windows()
        self.check_untouched(w)

    def test_pin_color_and_theme_keep_the_cursor_and_undo(self) -> None:
        w = self.typing_window()
        w.toggle_pin()
        self.check_untouched(w)
        w.change_color("#DCFCE7")
        self.check_untouched(w)
        self.assertEqual(w.memo_data["bg_color"], "#DCFCE7")
        self.explorer().toggle_app_theme() if hasattr(self.explorer(), "toggle_app_theme") else None
        self.check_untouched(w)

    def test_new_content_is_still_filled_in(self) -> None:
        w = self.typing_window()
        w._auto_save_timer.stop()
        w.memo_data["content"] = "from another device"
        w.apply_data()
        self.assertEqual(w.text_edit.toPlainText(), "from another device")

    def test_flash_border_is_removed_even_if_the_memo_is_hidden(self) -> None:
        from PyQt6.QtTest import QTest
        w = self.open_window("memo-0000")
        before = w.bg.styleSheet()
        self.ui._flash_memo_window(w)
        self.assertNotEqual(w.bg.styleSheet(), before)
        w.hide()
        QTest.qWait(950)
        self.assertEqual(w.bg.styleSheet(), before)
        self.assertFalse(w._is_flashing)

    def test_same_hotkey_failure_is_reported_once(self) -> None:
        told = []
        self.ui.tray_icon.showMessage = lambda *a, **k: told.append(a)
        self.ui._hotkeys.register = lambda shortcut, callback: False
        self.sm.settings["global_hotkeys"] = True
        self.ui.register_global_hotkeys()
        self.ui.register_global_hotkeys()
        self.assertEqual(len(told), 1)
        self.ui._hotkeys.register = lambda shortcut, callback: True               # 풀렸다가
        self.ui.register_global_hotkeys()
        self.ui._hotkeys.register = lambda shortcut, callback: False              # 다시 실패하면 다시 알림
        self.ui.register_global_hotkeys()
        self.assertEqual(len(told), 2)


class SyncNoticeTest(support.UiTestCase):
    def test_failure_toast_is_a_warning(self) -> None:
        explorer = self.explorer()
        self.ui.show_sync_result(False, "드라이브에 연결하지 못했습니다.", False)
        self.assertTrue(explorer.toast.text().startswith("⚠"))
        self.ui.show_sync_result(True, "동기화 완료 (변경사항 없음)", True)
        self.assertTrue(explorer.toast.text().startswith("✓"))

    def test_background_check_stays_silent_while_offline(self) -> None:
        shown = []
        self.ui.show_sync_result = lambda *a: shown.append(a)
        self.sm._last_sync_quiet = True
        self.sm.on_sync_finished(False, "드라이브에 연결하지 못했습니다.", SYNC_OFFLINE)
        self.assertEqual(shown, [])
        self.sm._last_sync_quiet = False                             # 직접 누른 동기화는 알림
        self.sm.on_sync_finished(False, "드라이브에 연결하지 못했습니다.", SYNC_OFFLINE)
        self.assertEqual(len(shown), 1)


if __name__ == "__main__":
    unittest.main()
