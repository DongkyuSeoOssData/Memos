"""코어 로직 회귀 테스트. 실행: python -m unittest discover -s tests

실제 사용자 폴더(~/.memoit_custom)와 레지스트리 자동 실행 항목을 건드리지 않도록
홈 디렉터리를 임시 폴더로 바꿔 놓고 수행합니다.
"""
import base64
import json
import os
import sys
import tempfile
import unittest
import winreg
from pathlib import Path
from unittest import mock

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# UI 테스트와 한 프로세스에서 함께 돌 수 있도록 QApplication을 화면 없이(offscreen) 만듭니다.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt6.QtWidgets import QApplication

from core import sync_manager as sync_manager_module
from core.defaults import DEFAULT_SHORTCUTS
from core.sync_manager import SyncManager, is_auto_start_enabled, set_auto_start
from core.sync_worker import SyncWorker
from utils import crypto_manager as crypto_module
from utils.crypto_manager import CryptoManager
from utils.text_utils import clean_plain_text, eng_to_kor, kor_to_eng

_app = QApplication.instance() or QApplication([])

# PBKDF2 60만 회를 테스트마다 돌리면 느리므로 반복 횟수만 낮춥니다.
crypto_module.MEMO_LOCK_ITERATIONS = 1000


class FakeDrive:
    """GAS 엔드포인트를 흉내 내는 메모리 저장소."""

    def __init__(self) -> None:
        self.files = {}
        self.clock = 0
        self.uploads = []
        self.downloads = []
        self.online = True
        self.web_app_url = "https://example.invalid/exec"

    def set_web_app_url(self, url: str) -> None:
        pass

    def is_available(self) -> bool:
        return True

    def put(self, name: str, content: dict) -> None:
        self.clock += 1
        self.files[name] = (json.loads(json.dumps(content)), self.clock)

    def list_files(self):
        if not self.online:
            return None
        return [{"name": n, "updated": u} for n, (_, u) in self.files.items()]

    def upload_file(self, filename: str, content: dict) -> bool:
        if not self.online:
            return False
        self.uploads.append(filename)
        self.put(filename, content)
        return True

    def download_file(self, filename: str):
        if not self.online:
            return None
        self.downloads.append(filename)
        return json.loads(json.dumps(self.files[filename][0]))

    def delete_file(self, filename: str) -> bool:
        if not self.online:
            return False
        self.files.pop(filename, None)
        return True


def legacy_v2_payload(plain: str) -> dict:
    """v2.0.x 가 만들던 마스터키 봉투 암호화 형식."""
    dek = AESGCM.generate_key(bit_length=256)
    content_nonce, master_nonce = os.urandom(12), os.urandom(12)
    master_key = CryptoManager()._legacy_master_keys()[0]
    b64 = lambda b: base64.b64encode(b).decode()
    return {
        "is_encrypted": True, "version": 2, "salt": b64(os.urandom(16)),
        "content_nonce": b64(content_nonce),
        "ciphertext": b64(AESGCM(dek).encrypt(content_nonce, plain.encode(), None)),
        "master_nonce": b64(master_nonce),
        "enc_dek_master": b64(AESGCM(master_key).encrypt(master_nonce, dek, None)),
        "user_nonce": "", "enc_dek_user": "",
    }


class SyncManagerTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.home = Path(self._tmp.name)
        self.memo_dir = self.home / "memos"
        base = self.home / ".memoit_custom"
        base.mkdir(parents=True)
        (base / "settings.json").write_text(
            json.dumps({"local_memo_path": str(self.memo_dir), "use_sync": False}), encoding="utf-8"
        )
        patcher = mock.patch.object(Path, "home", return_value=self.home)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self._tmp.cleanup)
        self.drive = FakeDrive()
        self.sm = SyncManager(self.drive)
        self.assertEqual(self.sm.local_path, self.memo_dir)

    def _memo(self, memo_id: str, content: str, updated_at: str = "2026-01-01T00:00:00") -> dict:
        return {"id": memo_id, "title": memo_id, "content": content, "updated_at": updated_at}

    def _disk(self, memo_id: str) -> dict:
        return json.loads((self.memo_dir / f"{memo_id}.json").read_text(encoding="utf-8"))

    def _contents(self) -> list:
        return sorted(m["content"] for m in self.sm.load_local_memos())

    def _sync(self) -> SyncWorker:
        worker = SyncWorker(self.sm)
        worker.run_sync()
        return worker


class SettingsTest(SyncManagerTestCase):
    def test_partial_save_keeps_other_keys(self) -> None:
        self.sm.settings["explorer_geom"] = [1, 2, 3, 4]
        self.sm.save_settings(self.sm.settings)

        self.sm.save_settings({"app_theme": "dark", "shortcuts": {"new_memo": "Alt+Q"}})

        on_disk = json.loads(self.sm.settings_path.read_text(encoding="utf-8"))
        self.assertEqual(on_disk["explorer_geom"], [1, 2, 3, 4])
        self.assertEqual(on_disk["app_theme"], "dark")
        self.assertEqual(on_disk["shortcuts"]["new_memo"], "Alt+Q")
        self.assertEqual(on_disk["shortcuts"]["toggle_all_memos"], DEFAULT_SHORTCUTS["toggle_all_memos"])

    def test_defaults_cover_every_shortcut(self) -> None:
        self.assertEqual(set(self.sm.settings["shortcuts"]), set(DEFAULT_SHORTCUTS))
        self.assertTrue(all(self.sm.settings["shortcuts"].values()))

    def test_save_settings_does_not_touch_auto_start(self) -> None:
        with mock.patch.object(sync_manager_module, "set_auto_start") as spy:
            self.sm.save_settings({"app_theme": "dark"})
        spy.assert_not_called()


class AutoStartTest(unittest.TestCase):
    """실제 Run 키 대신 시험용 키에서 등록/해제를 확인합니다."""
    KEY = r"Software\MemoitAppUnitTest"

    def tearDown(self) -> None:
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, self.KEY)
        except OSError:
            pass

    def test_enable_then_disable(self) -> None:
        self.assertFalse(is_auto_start_enabled(self.KEY))
        self.assertTrue(set_auto_start(True, self.KEY))
        self.assertTrue(is_auto_start_enabled(self.KEY))
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.KEY) as key:
            command, _ = winreg.QueryValueEx(key, "MemoitApp")
        self.assertTrue(command.startswith('"') and command.endswith('"'), command)
        self.assertTrue(set_auto_start(False, self.KEY))
        self.assertFalse(is_auto_start_enabled(self.KEY))
        self.assertTrue(set_auto_start(False, self.KEY))  # 이미 해제된 상태에서 다시 해제해도 성공


class PlainStoreTest(SyncManagerTestCase):
    def test_normal_memo_is_stored_as_plain_text(self) -> None:
        self.sm.save_memo_locally(self._memo("memo-aaaa", "hello"))
        self.assertEqual(self._disk("memo-aaaa")["content"], "hello")
        self.assertEqual(self._contents(), ["hello"])

    def test_runtime_flags_are_not_written(self) -> None:
        memo = self._memo("memo-aaaa", "hello")
        memo["_scratch"] = True
        self.sm.save_memo_locally(memo)
        self.assertNotIn("_scratch", self._disk("memo-aaaa"))

    def test_legacy_encrypted_memo_is_converted_to_plain(self) -> None:
        self.memo_dir.mkdir(parents=True, exist_ok=True)
        legacy = self._memo("memo-aaaa", "")
        legacy["content"] = legacy_v2_payload("old secret")
        (self.memo_dir / "memo-aaaa.json").write_text(json.dumps(legacy), encoding="utf-8")

        self.assertEqual(self._contents(), ["old secret"])
        self.assertEqual(self._disk("memo-aaaa")["content"], "old secret")

    def test_unreadable_memo_keeps_original_bytes(self) -> None:
        self.memo_dir.mkdir(parents=True, exist_ok=True)
        broken = self._memo("memo-aaaa", "")
        broken["content"] = legacy_v2_payload("x")
        broken["content"]["enc_dek_master"] = base64.b64encode(b"garbage" * 8).decode()
        (self.memo_dir / "memo-aaaa.json").write_text(json.dumps(broken), encoding="utf-8")

        memo = self.sm.load_local_memos()[0]
        self.assertTrue(memo.get("_unreadable"))
        memo["title"] = "renamed"
        memo["content"] = "this must never reach the disk"
        self.assertTrue(self.sm.save_memo_locally(memo))
        self.assertEqual(self._disk("memo-aaaa")["content"], broken["content"])
        self.assertEqual(self._disk("memo-aaaa")["title"], "renamed")


class LockedMemoTest(SyncManagerTestCase):
    def _locked(self) -> dict:
        memo = self._memo("memo-lock", "top secret")
        self.assertTrue(self.sm.set_memo_password(memo, "pw"))
        return memo

    def test_locked_memo_is_encrypted_on_disk(self) -> None:
        self._locked()
        raw = (self.memo_dir / "memo-lock.json").read_text(encoding="utf-8")
        self.assertNotIn("top secret", raw)
        self.assertTrue(self._disk("memo-lock")["is_locked"])

    def test_relock_hides_content_and_wrong_password_fails(self) -> None:
        self._locked()
        self.sm.relock_memo("memo-lock")
        loaded = self.sm.load_local_memos()[0]
        self.assertEqual(loaded["content"], "")
        self.assertTrue(loaded["_locked"])
        self.assertIsNone(self.sm.unlock_memo("memo-lock", "nope"))
        self.assertFalse(self.sm.is_memo_unlocked("memo-lock"))
        self.assertEqual(self.sm.unlock_memo("memo-lock", "pw"), "top secret")
        self.assertEqual(self._contents(), ["top secret"])

    def test_saving_while_locked_preserves_ciphertext(self) -> None:
        self._locked()
        before = self._disk("memo-lock")["content"]
        self.sm.relock_memo("memo-lock")
        loaded = self.sm.load_local_memos()[0]
        loaded["is_favorite"] = True
        self.assertTrue(self.sm.save_memo_locally(loaded))
        after = self._disk("memo-lock")
        self.assertEqual(after["content"], before)
        self.assertTrue(after["is_favorite"])
        self.assertNotIn("_locked", after)
        self.assertEqual(self.sm.unlock_memo("memo-lock", "pw"), "top secret")

    def test_locked_memo_is_never_treated_as_empty_draft(self) -> None:
        memo = self._locked()
        self.sm.relock_memo("memo-lock")
        loaded = self.sm.load_local_memos()[0]
        loaded["is_draft"] = True
        self.sm.save_memo_locally(loaded)
        self.assertTrue((self.memo_dir / "memo-lock.json").exists())
        self.assertEqual(len(self.sm.load_local_memos()), 1)

    def test_edit_while_unlocked_and_remove_password(self) -> None:
        memo = self._locked()
        memo["content"] = "edited"
        self.assertTrue(self.sm.save_memo_locally(memo))
        self.assertNotIn("edited", (self.memo_dir / "memo-lock.json").read_text(encoding="utf-8"))
        self.assertTrue(self.sm.remove_memo_password(memo))
        self.assertEqual(self._disk("memo-lock")["content"], "edited")
        self.assertFalse(self._disk("memo-lock")["is_locked"])


class SyncTest(SyncManagerTestCase):
    def _two_synced(self) -> None:
        self.sm.save_memo_locally(self._memo("memo-aaaa", "one"))
        self.sm.save_memo_locally(self._memo("memo-bbbb", "two"))
        self._sync()
        self._sync()

    def test_push_uploads_only_changed_memos(self) -> None:
        self.sm.save_memo_locally(self._memo("memo-aaaa", "one"))
        self.sm.save_memo_locally(self._memo("memo-bbbb", "two"))
        self._sync()
        self.assertEqual(sorted(self.drive.uploads), ["memo-aaaa.json", "memo-bbbb.json"])

        self.drive.uploads.clear()
        self._sync()
        self.assertEqual(self.drive.uploads, [])

        self.sm.save_memo_locally(self._memo("memo-aaaa", "one!", "2026-01-02T00:00:00"))
        self._sync()
        self.assertEqual(self.drive.uploads, ["memo-aaaa.json"])

    def test_pull_downloads_only_changed_remote_files(self) -> None:
        self._two_synced()
        self.drive.downloads.clear()
        self._sync()
        self.assertEqual(self.drive.downloads, [])

    def test_newer_remote_replaces_untouched_local(self) -> None:
        self._two_synced()
        remote = self._disk("memo-aaaa")
        remote["content"] = "from other pc"
        remote["updated_at"] = "2026-02-01T00:00:00"
        self.drive.put("memo-aaaa.json", remote)

        self.drive.uploads.clear()
        self._sync()
        self.assertEqual(self._contents(), ["from other pc", "two"])
        self.assertEqual(self.drive.uploads, [])  # 받은 것을 되올리지 않음

    def test_older_local_edit_is_kept_as_conflict_copy(self) -> None:
        self._two_synced()
        remote = self._disk("memo-aaaa")
        remote["content"] = "remote edit"
        remote["updated_at"] = "2026-03-01T00:00:00"
        self.drive.put("memo-aaaa.json", remote)
        self.sm.save_memo_locally(self._memo("memo-aaaa", "local edit", "2026-02-01T00:00:00"))

        self._sync()
        self.assertEqual(self._contents(), ["local edit", "remote edit", "two"])

    def test_local_newer_is_pushed_not_overwritten(self) -> None:
        self._two_synced()
        self.sm.save_memo_locally(self._memo("memo-aaaa", "local newer", "2026-05-01T00:00:00"))
        self._sync()
        self.assertEqual(self._contents(), ["local newer", "two"])
        self.assertEqual(self.drive.files["memo-aaaa.json"][0]["content"], "local newer")

    def test_offline_delete_is_retried_and_memo_does_not_come_back(self) -> None:
        self._two_synced()
        self.drive.online = False
        self.sm.delete_memo_locally("memo-aaaa")
        self.sm.delete_memos_cloud(["memo-aaaa"])
        self._sync()                                   # 오프라인: 삭제 실패
        self.assertEqual(self.sm.get_pending_deletes(), ["memo-aaaa"])
        self.sm.empty_trash_locally()

        self.drive.online = True
        self._sync()
        self.assertNotIn("memo-aaaa.json", self.drive.files)
        self.assertEqual(self.sm.get_pending_deletes(), [])
        self.assertEqual(self._contents(), ["two"])     # 휴지통을 비운 뒤에도 되살아나지 않음

    def test_delete_on_other_device_moves_local_to_trash(self) -> None:
        for i in range(6):
            self.sm.save_memo_locally(self._memo(f"memo-000{i}", f"m{i}"))
        self._sync()
        self._sync()
        del self.drive.files["memo-0000.json"]          # 다른 기기에서 삭제됨

        worker = self._sync()
        self.assertEqual(len(self.sm.load_local_memos()), 5)
        self.assertTrue((self.sm.trash_path / "memo-0000.json").exists())
        self.assertNotIn("memo-0000.json", self.drive.files)   # 되올리지 않음
        self.assertNotIn("memo-0000", worker.state)

    def test_locally_edited_memo_survives_remote_deletion(self) -> None:
        for i in range(6):
            self.sm.save_memo_locally(self._memo(f"memo-000{i}", f"m{i}"))
        self._sync()
        self._sync()
        del self.drive.files["memo-0000.json"]
        self.sm.save_memo_locally(self._memo("memo-0000", "edited here", "2026-06-01T00:00:00"))

        self._sync()
        self.assertEqual(len(self.sm.load_local_memos()), 6)
        self.assertEqual(self.drive.files["memo-0000.json"][0]["content"], "edited here")

    def test_mass_disappearance_is_not_treated_as_deletion(self) -> None:
        for i in range(6):
            self.sm.save_memo_locally(self._memo(f"memo-000{i}", f"m{i}"))
        self._sync()
        self._sync()
        self.drive.files.clear()                         # 드라이브 폴더가 통째로 비어 보이는 상황

        self._sync()
        self.assertEqual(len(self.sm.load_local_memos()), 6)

    def test_failed_listing_changes_nothing(self) -> None:
        self._two_synced()
        self.drive.online = False
        self._sync()
        self.assertEqual(self._contents(), ["one", "two"])

    def test_restored_memo_is_not_trashed_again(self) -> None:
        for i in range(6):
            self.sm.save_memo_locally(self._memo(f"memo-000{i}", f"m{i}"))
        self._sync()
        self._sync()
        self.sm.delete_memo_locally("memo-0000")
        self.sm.delete_memos_cloud(["memo-0000"])
        self._sync()
        self.assertTrue(self.sm.restore_memo_locally("memo-0000"))

        self._sync()
        self.assertEqual(len(self.sm.load_local_memos()), 6)
        self.assertIn("memo-0000.json", self.drive.files)

    def test_locked_memo_syncs_as_ciphertext(self) -> None:
        memo = self._memo("memo-lock", "top secret")
        self.sm.set_memo_password(memo, "pw")
        self._sync()
        self.assertNotIn("top secret", json.dumps(self.drive.files["memo-lock.json"][0]))


class DeviceStateSyncTest(SyncManagerTestCase):
    """창 위치·크기·표시 여부는 PC마다 따로 두고 동기화하지 않습니다."""

    def test_moving_a_window_does_not_upload(self) -> None:
        self.sm.save_memo_locally(self._memo("memo-aaaa", "one"))
        self._sync()
        self._sync()
        self.drive.uploads.clear()
        memo = self._disk("memo-aaaa")
        memo.update({"position_x": 900, "position_y": 40, "width": 512, "is_visible": False,
                     "is_rolled_up": True, "rolled_width": 200, "unrolled_height": 380})
        self.sm.save_memo_locally(memo)
        self._sync()
        self.assertEqual(self.drive.uploads, [])

    def test_uploaded_file_has_no_device_state(self) -> None:
        memo = self._memo("memo-aaaa", "one")
        memo.update({"position_x": 900, "width": 512, "is_visible": True, "rolled_position_y": 7})
        self.sm.save_memo_locally(memo)
        self._sync()
        uploaded = self.drive.files["memo-aaaa.json"][0]
        self.assertEqual(uploaded["content"], "one")
        for key in ("position_x", "width", "is_visible", "rolled_position_y"):
            self.assertNotIn(key, uploaded)

    def test_pull_keeps_this_pcs_window_placement(self) -> None:
        memo = self._memo("memo-aaaa", "one")
        memo.update({"position_x": 900, "position_y": 40, "is_visible": True})
        self.sm.save_memo_locally(memo)
        self._sync()
        remote = dict(self.drive.files["memo-aaaa.json"][0])
        remote.update({"content": "from other pc", "updated_at": "2026-02-01T00:00:00",
                       "position_x": 5, "position_y": 5, "is_visible": False})     # 예전 버전이 올린 파일
        self.drive.put("memo-aaaa.json", remote)
        self._sync()
        disk = self._disk("memo-aaaa")
        self.assertEqual(disk["content"], "from other pc")
        self.assertEqual((disk["position_x"], disk["position_y"], disk["is_visible"]), (900, 40, True))

    def test_memo_first_seen_from_remote_starts_hidden(self) -> None:
        self.drive.put("memo-cccc.json", self._memo("memo-cccc", "new from other pc"))
        self._sync()
        self.assertFalse(self._disk("memo-cccc")["is_visible"])

    def test_remote_id_that_escapes_the_folder_is_ignored(self) -> None:
        for bad in ("../evil", "..\\evil", "a/b", ""):
            evil = self._memo(bad, "x")
            self.drive.put("evil.json", evil)
            self._sync()
        self.assertFalse((self.memo_dir.parent / "evil.json").exists())
        self.assertEqual(self._contents(), [])
        self.assertFalse(self.sm.save_memo_locally(self._memo("../evil", "x")))
        self.assertFalse((self.memo_dir.parent / "evil.json").exists())


class TrashRetentionTest(SyncManagerTestCase):
    def _trash(self, memo_id: str) -> Path:
        return self.sm.trash_path / f"{memo_id}.json"

    def _set_deleted_at(self, memo_id: str, days_ago: int) -> None:
        from datetime import datetime, timedelta
        data = json.loads(self._trash(memo_id).read_text(encoding="utf-8"))
        data["deleted_at"] = (datetime.now() - timedelta(days=days_ago)).isoformat()
        self._trash(memo_id).write_text(json.dumps(data), encoding="utf-8")

    def test_no_retention_keeps_everything(self) -> None:
        self.sm.save_memo_locally(self._memo("memo-aaaa", "one"))
        self.sm.delete_memo_locally("memo-aaaa")
        self._set_deleted_at("memo-aaaa", 400)
        self.assertEqual(self.sm.purge_trash(), 0)
        self.assertTrue(self._trash("memo-aaaa").exists())

    def test_expired_memos_are_purged_and_recent_ones_kept(self) -> None:
        for memo_id in ("memo-aaaa", "memo-bbbb"):
            self.sm.save_memo_locally(self._memo(memo_id, "x"))
            self.sm.delete_memo_locally(memo_id)
        self._set_deleted_at("memo-aaaa", 20)
        self._set_deleted_at("memo-bbbb", 3)
        self.sm.settings["trash_auto_delete_days"] = 15
        self.assertEqual(self.sm.purge_trash(), 1)
        self.assertFalse(self._trash("memo-aaaa").exists())
        self.assertTrue(self._trash("memo-bbbb").exists())

    def test_old_trash_without_timestamp_gets_a_grace_period(self) -> None:
        self.sm.trash_path.mkdir(parents=True, exist_ok=True)
        self._trash("memo-old1").write_text(json.dumps(self._memo("memo-old1", "x", "2020-01-01T00:00:00")), encoding="utf-8")
        self.sm.settings["trash_auto_delete_days"] = 15
        self.assertEqual(self.sm.purge_trash(), 0)
        self.assertIn("deleted_at", json.loads(self._trash("memo-old1").read_text(encoding="utf-8")))

    def test_immediate_mode_purges_on_delete(self) -> None:
        self.sm.settings["trash_auto_delete_days"] = -1
        self.sm.save_memo_locally(self._memo("memo-aaaa", "one"))
        self.sm.delete_memo_locally("memo-aaaa")
        self.assertFalse(self._trash("memo-aaaa").exists())
        self.assertEqual(self.sm.load_local_memos(), [])

    def test_restore_clears_deletion_stamp(self) -> None:
        self.sm.save_memo_locally(self._memo("memo-aaaa", "one"))
        self.sm.delete_memo_locally("memo-aaaa")
        self.assertTrue(self.sm.restore_memo_locally("memo-aaaa"))
        self.assertNotIn("deleted_at", self._disk("memo-aaaa"))


class MasterRecoveryTest(SyncManagerTestCase):
    def setUp(self) -> None:
        super().setUp()
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.private_pem = key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
            serialization.BestAvailableEncryption(b"keypass"))
        self.public_pem = key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
        other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.other_private_pem = other.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())

    def _lock_with_master(self) -> None:
        self.sm.crypto = CryptoManager(self.public_pem)
        self.sm.set_memo_password(self._memo("memo-lock", "top secret"), "forgotten")
        self.sm.relock_memo("memo-lock")

    def test_disabled_by_default(self) -> None:
        self.assertFalse(CryptoManager("").master_enabled)
        self.sm.crypto = CryptoManager("")
        self.sm.set_memo_password(self._memo("memo-lock", "top secret"), "pw")
        self.assertFalse(self.sm.memo_has_master_recovery("memo-lock"))
        with self.assertRaises(ValueError):
            self.sm.recover_memo_with_master("memo-lock", self.private_pem, "keypass", "new")

    def test_public_key_alone_cannot_open_the_memo(self) -> None:
        self._lock_with_master()
        raw = (self.memo_dir / "memo-lock.json").read_text(encoding="utf-8")
        self.assertNotIn("top secret", raw)
        self.assertIsNone(self.sm.unlock_memo("memo-lock", "guess"))

    def test_private_key_recovers_and_sets_new_password(self) -> None:
        self._lock_with_master()
        self.assertTrue(self.sm.memo_has_master_recovery("memo-lock"))
        plain = self.sm.recover_memo_with_master("memo-lock", self.private_pem, "keypass", "newpw")
        self.assertEqual(plain, "top secret")
        self.sm.relock_memo("memo-lock")
        self.assertIsNone(self.sm.unlock_memo("memo-lock", "forgotten"))
        self.assertEqual(self.sm.unlock_memo("memo-lock", "newpw"), "top secret")

    def test_wrong_private_key_or_passphrase_fails(self) -> None:
        self._lock_with_master()
        before = self._disk("memo-lock")
        with self.assertRaises(ValueError):
            self.sm.recover_memo_with_master("memo-lock", self.other_private_pem, None, "newpw")
        with self.assertRaises(ValueError):
            self.sm.recover_memo_with_master("memo-lock", self.private_pem, "wrong", "newpw")
        self.assertEqual(self._disk("memo-lock"), before)
        self.assertFalse(self.sm.is_memo_unlocked("memo-lock"))

    def test_older_direct_key_format_still_opens(self) -> None:
        crypto = self.sm.crypto
        salt = crypto.new_salt()
        key = crypto.derive_key("pw", salt)
        nonce = os.urandom(12)
        memo = self._memo("memo-v3xx", "")
        memo["is_locked"] = True
        memo["content"] = {
            "is_encrypted": True, "version": 3, "iterations": crypto_module.MEMO_LOCK_ITERATIONS,
            "salt": base64.b64encode(salt).decode(), "nonce": base64.b64encode(nonce).decode(),
            "ciphertext": base64.b64encode(AESGCM(key).encrypt(nonce, b"v3 body", None)).decode(),
        }
        self.memo_dir.mkdir(parents=True, exist_ok=True)
        (self.memo_dir / "memo-v3xx.json").write_text(json.dumps(memo), encoding="utf-8")
        self.assertEqual(self.sm.unlock_memo("memo-v3xx", "pw"), "v3 body")


class CryptoTest(unittest.TestCase):
    def test_wrong_key_is_rejected(self) -> None:
        crypto = CryptoManager("")
        salt = crypto.new_salt()
        payload = crypto.encrypt_locked("secret", crypto.derive_key("pw", salt), salt)
        self.assertEqual(crypto.decrypt_locked(payload, crypto.key_for_payload(payload, "pw")), "secret")
        with self.assertRaises(ValueError):
            crypto.decrypt_locked(payload, crypto.key_for_payload(payload, "nope"))


class TextUtilsTest(unittest.TestCase):
    def test_extract_hashtags(self) -> None:
        from utils.text_utils import extract_hashtags
        self.assertEqual(extract_hashtags("#a b #한글 c#no ##x #FFFFFF #ffffff80 #abc # 제목"), ["a", "한글", "abc"])
        self.assertEqual(extract_hashtags(""), [])

    def test_eng_kor_roundtrip(self) -> None:
        self.assertEqual(eng_to_kor("dkssudgktpdy"), "안녕하세요")
        self.assertEqual(kor_to_eng("안녕하세요"), "dkssudgktpdy")

    def test_clean_plain_text_strips_markup(self) -> None:
        # 편집기가 서식 있는 메모를 저장할 때 만드는 형태
        html_doc = ('<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.0//EN" "http://www.w3.org/TR/REC-html40/strict.dtd">'
                    '<html><head><meta name="qrichtext" content="1" /><style>p{color:red}</style></head>'
                    '<body><p>a &amp; b</p></body></html>')
        self.assertEqual(clean_plain_text(html_doc), "a & b")

    def test_clean_plain_text_keeps_plain_text_as_is(self) -> None:
        # 순수 텍스트 메모·코드 메모의 '<', '>' 는 태그가 아니므로 지우면 안 됨
        self.assertEqual(clean_plain_text("if a < b and c > d: List<int>"), "if a < b and c > d: List<int>")
        self.assertEqual(clean_plain_text("<html><body>my page</body></html>"), "<html><body>my page</body></html>")


if __name__ == "__main__":
    unittest.main()
