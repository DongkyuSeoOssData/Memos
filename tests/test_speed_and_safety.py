"""메모가 많아도 느려지지 않게 하는 장치(바뀐 파일만 다시 읽기)와, 저장·암호문의 안전 장치."""
import builtins
import json
import os
import unittest
from unittest import mock

# support 를 먼저 가져와야 합니다. (offscreen 설정과 프로젝트 경로)
import support
from test_core import SyncManagerTestCase
from utils import crypto_manager, file_utils, text_utils
from utils.crypto_manager import CryptoManager


class FileCacheTest(SyncManagerTestCase):
    def fill(self, count: int = 5) -> None:
        for n in range(count):
            self.sm.save_memo_locally(self._memo(f"memo-{n:04d}", f"body {n}"))

    def opens_during(self, func) -> int:
        """func 를 하는 동안 메모 파일을 몇 번 열어 읽는지."""
        real_open, opened = builtins.open, []

        def counting(path, mode="r", *args, **kwargs):
            if "r" in mode and str(path).endswith(".json") and str(self.memo_dir) in str(path):
                opened.append(str(path))
            return real_open(path, mode, *args, **kwargs)

        with mock.patch("builtins.open", counting):
            func()
        return len(opened)

    def test_unchanged_files_are_not_read_again(self) -> None:
        self.fill()
        self.assertEqual(self.opens_during(self.sm.load_local_memos), 5)       # 처음에는 모두 읽음
        self.assertEqual(self.opens_during(self.sm.load_local_memos), 0)       # 그 뒤로는 읽지 않음
        self.assertEqual(self._contents(), [f"body {n}" for n in range(5)])

    def test_only_the_saved_memo_is_read_again(self) -> None:
        self.fill()
        self.sm.load_local_memos()
        self.sm.save_memo_locally(self._memo("memo-0002", "edited"))
        self.assertEqual(self.opens_during(self.sm.load_local_memos), 1)
        self.assertIn("edited", self._contents())

    def test_file_changed_by_another_program_is_noticed(self) -> None:
        self.fill()
        self.sm.load_local_memos()
        path = self.memo_dir / "memo-0001.json"
        changed = dict(self._disk("memo-0001"), content="changed outside, and longer")
        path.write_text(json.dumps(changed, ensure_ascii=False), encoding="utf-8")
        self.assertIn("changed outside, and longer", self._contents())

    def test_same_size_change_is_noticed_through_the_time(self) -> None:
        self.fill()
        self.sm.load_local_memos()
        path = self.memo_dir / "memo-0001.json"
        text = path.read_text(encoding="utf-8").replace("body 1", "BODY 1")      # 크기는 같음
        path.write_text(text, encoding="utf-8")
        later = path.stat().st_mtime_ns + 2_000_000_000
        os.utime(path, ns=(later, later))
        self.assertIn("BODY 1", self._contents())

    def test_returned_memos_can_be_changed_without_touching_the_cache(self) -> None:
        memo = self._memo("memo-0000", "body")
        memo["reminder"] = {"at": "2030-01-01T09:00:00", "repeat": "weekly", "weekdays": [1, 3]}
        self.sm.save_memo_locally(memo)
        first = self.sm.load_local_memos()[0]
        first["title"] = "scribbled"
        first["reminder"]["weekdays"].append(5)
        again = self.sm.load_local_memos()[0]
        self.assertEqual(again["title"], "memo-0000")
        self.assertEqual(again["reminder"]["weekdays"], [1, 3])
        self.assertIsNot(first, again)

    def test_deleted_and_restored_memos_follow(self) -> None:
        self.fill(3)
        self.sm.load_local_memos()
        self.sm.delete_memo_locally("memo-0001")
        self.assertEqual(self._contents(), ["body 0", "body 2"])
        self.assertNotIn("memo-0001.json", self.sm._file_cache)                  # 없어진 파일은 읽어 둔 것도 버림
        self.assertTrue(self.sm.restore_memo_locally("memo-0001"))
        self.assertEqual(self._contents(), ["body 0", "body 1", "body 2"])

    def test_unlocked_text_is_never_kept_in_the_file_cache(self) -> None:
        memo = self._memo("memo-0000", "top secret")
        self.sm.save_memo_locally(memo)
        self.sm.set_memo_password(memo, "pw12")
        self.assertEqual(self.sm.load_local_memos()[0]["content"], "top secret")     # 풀려 있는 동안은 보임
        self.assertNotIn("top secret", json.dumps(self.sm._file_cache["memo-0000.json"][1], ensure_ascii=False))
        self.sm.relock_memo("memo-0000")
        locked = self.sm.load_local_memos()[0]
        self.assertTrue(locked.get("_locked"))
        self.assertEqual(locked["content"], "")

    def test_pulled_memo_from_another_device_is_read_again(self) -> None:
        self.sm.save_memo_locally(self._memo("memo-0000", "one"))
        self._sync()
        self.sm.load_local_memos()
        remote = dict(self.drive.files["memo-0000.json"][0], content="from phone", updated_at="2026-09-01T00:00:00")
        self.drive.put("memo-0000.json", remote)
        self._sync()
        self.assertEqual(self._contents(), ["from phone"])


class LocalIndexTest(FileCacheTest):
    """로컬 색인: 앱을 다시 켜도 바뀐 메모 파일만 읽습니다."""

    def restart(self):
        """앱을 껐다 켠 것처럼: 색인을 남기고, 같은 폴더로 SyncManager 를 새로 만듭니다."""
        from core.sync_manager import SyncManager
        self.sm.load_local_memos()
        self.sm.save_index_now()
        self.sm = SyncManager(self.drive)
        return self.sm

    def test_restart_reads_no_memo_files(self) -> None:
        self.fill()
        self.restart()
        self.assertEqual(self.opens_during(self.sm.load_local_memos), 0)
        self.assertEqual(self._contents(), [f"body {n}" for n in range(5)])

    def test_memo_changed_while_the_app_was_off_is_read_again(self) -> None:
        self.fill()
        self.sm.load_local_memos()
        self.sm.save_index_now()
        path = self.memo_dir / "memo-0003.json"
        path.write_text(json.dumps(dict(self._disk("memo-0003"), content="edited while off"), ensure_ascii=False), encoding="utf-8")
        (self.memo_dir / "memo-0004.json").unlink()                                # 꺼져 있는 동안 지워진 메모
        self.sm.save_memo_locally(self._memo("memo-0009", "made elsewhere"))        # 꺼져 있는 동안 생긴 메모 (색인에는 없음)
        self.sm._index_dirty = False
        from core.sync_manager import SyncManager
        self.sm = SyncManager(self.drive)
        self.assertEqual(self.opens_during(self.sm.load_local_memos), 2)           # 바뀐 것과 새 것만
        self.assertEqual(self._contents(), ["body 0", "body 1", "body 2", "edited while off", "made elsewhere"])

    def test_broken_or_foreign_index_is_ignored(self) -> None:
        self.fill(3)
        self.restart()
        for bad in ("not json", "[]", json.dumps({"v": 999, "folder": str(self.memo_dir), "files": {}}),
                    json.dumps({"v": 1, "folder": "C:/somewhere/else", "files": {"x.json": [[1, 2], {"id": "x"}]}}),
                    json.dumps({"v": 1, "folder": str(self.memo_dir), "files": {"memo-0000.json": "garbage"}})):
            self.sm.index_path.write_text(bad, encoding="utf-8")
            from core.sync_manager import SyncManager
            self.sm = SyncManager(self.drive)
            self.assertEqual(self.sm._file_cache, {}, bad[:30])
            self.assertEqual(self._contents(), ["body 0", "body 1", "body 2"], bad[:30])     # 메모 파일에서 다시 읽음

    def test_index_never_holds_unlocked_text_and_drops_deleted_memos(self) -> None:
        self.fill(2)
        memo = self._memo("memo-0005", "top secret")
        self.sm.save_memo_locally(memo)
        self.sm.set_memo_password(memo, "pw12")
        self.restart()
        text = self.sm.index_path.read_text(encoding="utf-8")
        self.assertNotIn("top secret", text)
        self.assertIn("body 1", text)
        self.sm.delete_memo_locally("memo-0001")
        self.restart()
        self.assertNotIn("body 1", self.sm.index_path.read_text(encoding="utf-8"))
        self.assertTrue(self.sm.load_local_memos()[-1].get("_locked") or any(m.get("_locked") for m in self.sm.load_local_memos()))

    def test_text_from_before_the_password_leaves_the_index_at_once(self) -> None:
        memo = self._memo("memo-0000", "written before the lock")
        self.sm.save_memo_locally(memo)
        self.sm.load_local_memos()
        self.sm.save_index_now()
        self.assertIn("written before the lock", self.sm.index_path.read_text(encoding="utf-8"))
        self.assertTrue(self.sm.set_memo_password(memo, "pw12"))                 # 탐색기를 다시 그리거나 앱을 끝내지 않아도
        self.assertNotIn("written before the lock", self.sm.index_path.read_text(encoding="utf-8"))

    def test_deleted_memo_is_dropped_from_the_index_by_the_time_the_app_quits(self) -> None:
        self.fill(2)
        self.sm.load_local_memos()
        self.sm.save_index_now()
        self.sm.delete_memo_locally("memo-0001")
        self.assertTrue(self.sm._index_dirty)                                    # 다시 써야 함을 표시해 둠
        self.sm.save_index_now()                                                 # 앱을 끝낼 때
        self.assertNotIn("body 1", self.sm.index_path.read_text(encoding="utf-8"))
        self.assertIn("body 0", self.sm.index_path.read_text(encoding="utf-8"))

    def test_saving_a_memo_marks_the_index_for_rewriting(self) -> None:
        self.fill(1)
        self.sm.load_local_memos()
        self.sm.save_index_now()
        self.sm.save_memo_locally(self._memo("memo-0000", "edited"))
        self.assertTrue(self.sm._index_dirty)

    def test_changing_the_memo_folder_starts_over(self) -> None:
        self.fill(2)
        self.sm.load_local_memos()
        other = self.home / "other"
        self.sm.save_settings({"local_memo_path": str(other)})
        self.assertEqual(self.sm._file_cache, {})
        self.assertEqual(self.sm.load_local_memos(), [])
        self.sm.save_index_now()
        self.assertEqual(json.loads(self.sm.index_path.read_text(encoding="utf-8"))["folder"], str(other))

    def test_index_is_written_after_changes_and_on_quit(self) -> None:
        self.fill(2)
        self.sm.load_local_memos()
        self.assertTrue(self.sm._index_dirty)
        self.sm.save_index_now()
        self.assertFalse(self.sm._index_dirty)
        self.assertTrue(self.sm.index_path.exists())
        self.sm.load_local_memos()                                                # 바뀐 것이 없으면 다시 쓰지 않음
        self.assertFalse(self.sm._index_dirty)


class ExplorerDigestTest(support.UiTestCase):
    def test_unchanged_memos_are_not_cleaned_again_on_refresh(self) -> None:
        ex = self.explorer()
        ex.refresh()
        with mock.patch("ui.memo_explorer.clean_plain_text", wraps=text_utils.clean_plain_text) as cleaner:
            ex.refresh()
            self.assertEqual(cleaner.call_count, 0)                              # 바뀐 메모가 없으면 다시 정리하지 않음
            w = self.open_window("memo-0000")
            w.memo_data["content"] = "edited body #newtag"
            self.ui.notify_save(w.memo_data)
            self.assertEqual(cleaner.call_count, 1)                              # 고친 메모 하나만
        tags = [ex.tag_combo.itemText(i) for i in range(ex.tag_combo.count())]
        self.assertTrue(any("newtag" in t for t in tags), tags)

    def test_unlocked_password_memo_is_not_remembered(self) -> None:
        ex = self.explorer()
        w = self.open_window("memo-0000")
        w.memo_data["content"] = "very secret words"
        self.answers[:] = ["pw12", "pw12"]
        w.set_memo_password()
        ex.refresh()
        self.assertFalse(any("very secret words" in key[0] for key in ex._digest_cache))


class SafeWriteTest(unittest.TestCase):
    def test_file_is_flushed_to_disk_before_it_replaces_the_old_one(self) -> None:
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "memo.json"
            order = []
            real_fsync, real_replace = os.fsync, os.replace
            with mock.patch.object(file_utils.os, "fsync", lambda fd: (order.append("fsync"), real_fsync(fd))[1]), \
                 mock.patch.object(file_utils.os, "replace", lambda a, b: (order.append("replace"), real_replace(a, b))[1]):
                file_utils.atomic_write_json(path, {"a": 1})
            self.assertEqual(order, ["fsync", "replace"])
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"a": 1})
            with mock.patch.object(file_utils.os, "fsync", side_effect=OSError("not supported")):
                file_utils.atomic_write_json(path, {"a": 2})                     # 지원하지 않는 드라이브에서도 저장은 됨
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"a": 2})


class IterationLimitTest(unittest.TestCase):
    def setUp(self) -> None:
        patcher = mock.patch.object(crypto_manager, "MEMO_LOCK_ITERATIONS", 1000)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.crypto = CryptoManager("")
        salt = self.crypto.new_salt()
        self.payload = self.crypto.encrypt_locked("secret", self.crypto.derive_key("pw", salt), salt)

    def test_normal_payload_opens(self) -> None:
        key = self.crypto.key_for_payload(self.payload, "pw")
        self.assertEqual(self.crypto.decrypt_locked(self.payload, key), "secret")

    def test_absurd_iteration_counts_are_refused_at_once(self) -> None:
        for bad in (crypto_manager.MAX_LOCK_ITERATIONS + 1, 10 ** 12, 0, -5, "many", None):
            with self.assertRaises(ValueError, msg=repr(bad)):
                self.crypto.key_for_payload(dict(self.payload, iterations=bad), "pw")


if __name__ == "__main__":
    unittest.main()
