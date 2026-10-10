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
        self.aux_uploads = []
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
        # '_'로 시작하는 부속 파일(공유 설정)은 메모 업로드 기록과 따로 셉니다.
        (self.aux_uploads if filename.startswith("_") else self.uploads).append(filename)
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

    def test_meta_only_change_from_another_device_is_pulled(self) -> None:
        self.sm.save_memo_locally(self._memo("memo-aaaa", "one"))
        self._sync()
        remote = dict(self.drive.files["memo-aaaa.json"][0])
        remote.update({"folder": "업무", "is_favorite": True, "meta_updated_at": "2026-03-01T00:00:00"})   # 본문·수정일시는 그대로
        self.drive.put("memo-aaaa.json", remote)
        self._sync()
        disk = self._disk("memo-aaaa")
        self.assertEqual((disk["folder"], disk["is_favorite"]), ("업무", True))
        self.assertEqual(disk["updated_at"], "2026-01-01T00:00:00")               # 화면의 수정일시는 바뀌지 않음

        older = dict(remote)
        older.update({"folder": "개인", "meta_updated_at": "2026-02-01T00:00:00"})  # 더 예전의 속성 변경
        self.drive.put("memo-aaaa.json", older)
        self._sync()
        self.assertEqual(self._disk("memo-aaaa")["folder"], "업무")

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


class DriveApiTokenTest(unittest.TestCase):
    """접근 암호를 설정하면 모든 요청에 함께 보내고, 설정하지 않으면 보내지 않습니다."""

    class _Resp:
        def __init__(self, text: str, payload=None) -> None:
            self.status_code, self.text, self._payload = 200, text, payload

        def json(self):
            if self._payload is None:
                raise ValueError("not json")
            return self._payload

    def _api(self, token: str):
        from drive_api import DriveAPI
        api = DriveAPI()
        api.set_web_app_url("https://example.invalid/exec")
        api.set_access_token(token)
        calls = []

        def get(url, params=None, timeout=None):
            calls.append(dict(params))
            if params.get("token", "") != "s3cret":
                return self._Resp("Unauthorized")
            return self._Resp("", {"files": []} if params["action"] == "list" else {"content": "{}"})

        def post(url, data=None, timeout=None):
            body = json.loads(data)
            calls.append(body)
            if body.get("token", "") != "s3cret":
                return self._Resp("Unauthorized")
            return self._Resp("Success" if body["action"] == "upload" else "Moved to Trash")

        api._session = mock.Mock(get=get, post=post)
        return api, calls

    def test_token_is_sent_with_every_request(self) -> None:
        api, calls = self._api("s3cret")
        self.assertEqual(api.list_files(), [])
        self.assertTrue(api.upload_file("a.json", {"id": "a"}))
        self.assertEqual(api.download_file("a.json"), {})
        self.assertTrue(api.delete_file("a.json"))
        self.assertTrue(api.ping_web_app())
        self.assertTrue(all(c.get("token") == "s3cret" for c in calls), calls)

    def test_wrong_or_missing_token_fails_cleanly(self) -> None:
        for token in ("", "wrong"):
            api, calls = self._api(token)
            self.assertIsNone(api.list_files())              # '파일 없음'이 아니라 '조회 실패'
            self.assertFalse(api.upload_file("a.json", {"id": "a"}))
            self.assertIsNone(api.download_file("a.json"))
            self.assertFalse(api.delete_file("a.json"))
            self.assertFalse(api.ping_web_app())             # 연결 테스트도 실패로 표시
            if not token:
                self.assertTrue(all("token" not in c for c in calls))

    def test_settings_token_reaches_the_drive_api(self) -> None:
        from drive_api import DriveAPI
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home / ".memoit_custom").mkdir()
            (home / ".memoit_custom" / "settings.json").write_text(json.dumps(
                {"local_memo_path": str(home / "memos"), "use_sync": False, "drive_access_token": "abc"}), encoding="utf-8")
            with mock.patch.object(Path, "home", return_value=home):
                api = DriveAPI()
                sm = SyncManager(api)
                self.assertEqual(api.access_token, "abc")
                sm.save_settings({"drive_access_token": "xyz"})
                self.assertEqual(api.access_token, "xyz")
                sm.sync_timer.stop()
                sm._purge_timer.stop()


class MobileApiTest(unittest.TestCase):
    """tools/mobile_dev_server.py: mobile/Code.gs 의 api() 와 같은 규칙을 따르는 시험용 구현."""

    def setUp(self) -> None:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "mobile_dev_server", Path(__file__).resolve().parent.parent / "tools" / "mobile_dev_server.py")
        self.srv = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.srv)
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.folder = Path(self._tmp.name)

    def call(self, token: str = "", **req):
        return self.srv.handle_api(self.folder, token, req)

    def test_crud_and_conflict(self) -> None:
        self.assertEqual(self.call(action="list"), {"files": []})
        saved = self.call(action="save", name="a.json", content='{"id": "a"}')
        self.assertTrue(saved["ok"])
        self.assertEqual(self.call(action="getMany", names=["a.json", "zz.json"])["items"][0]["content"], '{"id": "a"}')
        self.assertTrue(self.call(action="save", name="a.json", content="{}", ifUpdated=saved["updated"])["ok"])
        self.assertTrue(self.call(action="save", name="a.json", content="{}", ifUpdated=1)["conflict"])
        self.assertTrue(self.call(action="remove", name="a.json")["ok"])
        self.assertEqual(self.call(action="list"), {"files": []})
        self.assertTrue((self.folder / "trash_bin" / "a.json").exists())

    def test_rejects_bad_names_and_tokens(self) -> None:
        for bad in ("../x.json", "a/b.json", "x.txt", ""):
            self.assertEqual(self.call(action="save", name=bad, content="{}"), {"error": "name"})
        self.assertFalse((self.folder.parent / "x.json").exists())
        self.assertEqual(self.srv.handle_api(self.folder, "pw", {"action": "list"}), {"error": "auth"})
        self.assertEqual(self.srv.handle_api(self.folder, "pw", {"action": "list", "token": "pw"}), {"files": []})

    def test_demo_memos_are_readable_by_the_desktop_crypto(self) -> None:
        self.srv.seed_demo(self.folder)
        crypto = CryptoManager()
        for memo_id in ("demo-lock4", "demo-lock3"):
            payload = json.loads((self.folder / f"{memo_id}.json").read_text(encoding="utf-8"))["content"]
            self.assertTrue(crypto.decrypt_locked(payload, crypto.key_for_payload(payload, "1234")))


class SharedSettingsSyncTest(SyncManagerTestCase):
    """공유 설정(_settings.json): 어느 기기에서나 같아야 할 설정만 드라이브로 주고받습니다."""

    FILE = "_settings.json"

    def sync(self) -> SyncWorker:
        worker = SyncWorker(self.sm)
        worker.settings_pulled.connect(self.sm.apply_remote_settings)
        worker.run_sync()
        return worker

    def remote(self) -> dict:
        return self.drive.files[self.FILE][0]

    def test_first_sync_uploads_only_shared_settings(self) -> None:
        self.sm.save_settings({"drive_folder_id": "https://secret.example/exec", "drive_access_token": "tok",
                               "explorer_geom": [1, 2, 3, 4], "auto_start": True,
                               "ui_style": "neo", "folders": ["업무", "개인"]})
        self.sync()
        uploaded = self.remote()
        self.assertEqual(uploaded["updated_at"], self.sm.settings["settings_updated_at"])
        shared = uploaded["settings"]
        self.assertEqual((shared["ui_style"], shared["folders"]), ("neo", ["업무", "개인"]))
        self.assertIn("shortcuts", shared)
        for device_only in ("drive_folder_id", "drive_access_token", "local_memo_path", "explorer_geom",
                            "auto_start", "use_sync", "settings_updated_at", "explorer_folder"):
            self.assertNotIn(device_only, shared)
        self.assertNotIn("tok", json.dumps(uploaded))

        self.drive.aux_uploads.clear()
        self.sync()
        self.sync()
        self.assertEqual(self.drive.aux_uploads, [])                      # 바뀐 것이 없으면 다시 올리지 않음
        self.assertEqual(self._contents(), [])                           # 메모로 오인해 내려받지 않음

    def test_local_change_is_uploaded(self) -> None:
        self.sync()
        self.drive.aux_uploads.clear()
        self.sm.save_settings({"explorer_geom": [9, 9, 9, 9]})            # 이 PC에만 속한 설정
        self.sync()
        self.assertEqual(self.drive.aux_uploads, [])
        self.sm.save_settings({"folders": ["개인", "업무", "여행"]})
        self.sync()
        self.assertEqual(self.drive.aux_uploads, [self.FILE])
        self.assertEqual(self.remote()["settings"]["folders"], ["개인", "업무", "여행"])

    def test_newer_remote_settings_are_applied_here(self) -> None:
        self.sync()
        self.sm.save_settings({"local_memo_path": str(self.memo_dir), "explorer_geom": [5, 6, 7, 8]})
        before_shortcuts = dict(self.sm.settings["shortcuts"])
        other_pc = {"updated_at": "2099-01-01T00:00:00", "settings": {
            "ui_style": "neo", "app_theme": "dark", "folders": ["업무", "업무/A", "개인"],
            "shortcuts": {"save": "Ctrl+Alt+S"},
            # 공유 대상이 아닌 값이 섞여 와도 받아들이지 않음
            "local_memo_path": "Z:/somewhere", "drive_access_token": "evil", "explorer_geom": [0, 0, 1, 1]}}
        self.drive.put(self.FILE, other_pc)
        self.drive.aux_uploads.clear()
        self.sync()

        s = self.sm.settings
        self.assertEqual((s["ui_style"], s["app_theme"], s["folders"]), ("neo", "dark", ["업무", "업무/A", "개인"]))
        self.assertEqual(s["shortcuts"]["save"], "Ctrl+Alt+S")
        self.assertEqual(s["shortcuts"]["new_memo"], before_shortcuts["new_memo"])   # 받은 쪽에 없는 단축키는 기본값 유지
        self.assertEqual(s["local_memo_path"], str(self.memo_dir))
        self.assertEqual(s["explorer_geom"], [5, 6, 7, 8])
        self.assertNotEqual(s.get("drive_access_token"), "evil")
        self.assertEqual(s["settings_updated_at"], "2099-01-01T00:00:00")
        on_disk = json.loads(self.sm.settings_path.read_text(encoding="utf-8"))
        self.assertEqual(on_disk["ui_style"], "neo")

        self.sync()
        self.assertEqual(self.drive.aux_uploads, [])                      # 받은 것을 되올리지 않음

    def test_older_remote_settings_are_replaced_by_ours(self) -> None:
        self.sm.save_settings({"ui_style": "neo"})
        self.drive.put(self.FILE, {"updated_at": "2000-01-01T00:00:00", "settings": {"ui_style": "modern"}})
        self.sync()
        self.assertEqual(self.sm.settings["ui_style"], "neo")
        self.assertEqual(self.remote()["settings"]["ui_style"], "neo")

    def test_broken_remote_settings_are_ignored(self) -> None:
        for broken in ({"updated_at": "2099-01-01T00:00:00"}, {"settings": {"ui_style": "neo"}},
                       {"updated_at": "2099-01-01T00:00:00", "settings": "nope"}):
            self.drive.put(self.FILE, broken)
            self.sync()
            self.assertEqual(self.sm.settings.get("ui_style", "modern"), "modern")
            self.assertIn("shortcuts", self.remote()["settings"])            # 깨진 파일은 이 PC의 설정으로 다시 채움


class ChangeDrivenSyncTest(SyncManagerTestCase):
    """동기화는 정해진 간격마다 무조건 돌지 않고, 바뀐 것이 있을 때 바뀐 것만 다룹니다."""

    def setUp(self) -> None:
        super().setUp()
        self.sm.save_settings({"use_sync": True, "sync_interval_index": 1})
        self.sm._push_timer.stop()          # 위 설정 저장으로 걸린 대기는 시험과 무관하므로 풀어 둠
        self.addCleanup(self.sm._push_timer.stop)
        self.addCleanup(self.sm.sync_timer.stop)

    def test_content_change_schedules_a_sync_after_the_delay(self) -> None:
        self.assertFalse(self.sm._push_timer.isActive())
        self.sm.save_memo_locally(self._memo("memo-aaaa", "one"))
        self.assertEqual(self.sm._dirty_ids, {"memo-aaaa"})
        self.assertTrue(self.sm._push_timer.isActive())
        self.assertEqual(self.sm._push_timer.interval(), 600 * 1000)       # 설정한 '변경 후 대기 시간'
        remaining = self.sm._push_timer.remainingTime()
        self.sm.save_memo_locally(self._memo("memo-bbbb", "two"))           # 기다리는 중의 추가 변경은 같은 회차에
        self.assertLessEqual(self.sm._push_timer.remainingTime(), remaining)
        self.assertEqual(self.sm._dirty_ids, {"memo-aaaa", "memo-bbbb"})

    def test_window_moves_do_not_schedule_a_sync(self) -> None:
        memo = self._memo("memo-aaaa", "one")
        self.sm.save_memo_locally(memo)
        self.sm._dirty_ids.clear()
        self.sm._push_timer.stop()
        memo.update({"position_x": 900, "position_y": 10, "width": 500, "is_visible": False, "is_rolled_up": True})
        self.sm.save_memo_locally(memo)                                     # 창을 옮기고 접기만 함
        self.assertEqual(self.sm._dirty_ids, set())
        self.assertFalse(self.sm._push_timer.isActive())

        memo["folder"] = "업무"                                             # 폴더 변경은 다른 기기와 공유하는 내용
        self.sm.save_memo_locally(memo)
        self.assertEqual(self.sm._dirty_ids, {"memo-aaaa"})

    def test_shared_setting_change_schedules_a_sync(self) -> None:
        self.sm.save_settings({"explorer_geom": [1, 2, 3, 4]})              # 이 PC에만 속한 설정
        self.assertFalse(self.sm._push_timer.isActive())
        self.sm.save_settings({"folders": ["개인", "업무", "여행"]})
        self.assertTrue(self.sm._push_timer.isActive())

    def test_nothing_is_scheduled_when_sync_is_off(self) -> None:
        self.sm.settings["use_sync"] = False
        self.sm.save_memo_locally(self._memo("memo-aaaa", "one"))
        self.assertFalse(self.sm._push_timer.isActive())
        self.sm.setup_timer()
        self.assertFalse(self.sm.sync_timer.isActive())

    def test_remote_check_timer_is_separate_from_the_push_delay(self) -> None:
        self.sm.setup_timer()
        self.assertTrue(self.sm.sync_timer.isActive())
        self.assertEqual(self.sm.sync_timer.interval(), self.sm.REMOTE_CHECK_SEC * 1000)
        self.assertEqual(self.sm.push_delay_sec(), 600)

    def test_worker_reads_only_the_changed_memos(self) -> None:
        for memo_id in ("memo-aaaa", "memo-bbbb", "memo-cccc"):
            self.sm.save_memo_locally(self._memo(memo_id, memo_id))
        self._sync()                                                        # 처음에는 전부 올림
        self.drive.uploads.clear()
        self.sm.save_memo_locally(self._memo("memo-bbbb", "changed", "2026-02-01T00:00:00"))

        worker = SyncWorker(self.sm)
        worker.push_ids = {"memo-bbbb", "memo-zzzz"}                        # 없는 메모가 섞여 있어도 무시
        read = []
        real_read = worker._read_local
        worker._read_local = lambda path: (read.append(path.name), real_read(path))[1]
        worker._load_state()
        self.assertEqual(worker._push(), 1)
        self.assertEqual(self.drive.uploads, ["memo-bbbb.json"])
        self.assertEqual(read, ["memo-bbbb.json"])                          # 다른 메모 파일은 읽지도 않음

    def test_failed_uploads_are_reported_for_retry(self) -> None:
        self.sm.save_memo_locally(self._memo("memo-aaaa", "one"))
        self.drive.online = False
        worker = SyncWorker(self.sm)
        worker.push_ids = {"memo-aaaa"}
        worker._load_state()
        self.assertEqual(worker._push(), 0)
        self.assertEqual(worker.unsent_ids, {"memo-aaaa"})

    def test_cycle_bookkeeping(self) -> None:
        sm = self.sm
        sm._full_scan_pending = True
        sm._sending_ids = {"memo-aaaa", "memo-bbbb"}
        sm._current_worker = mock.Mock(unsent_ids={"memo-bbbb"}, quiet=True)
        sm._sync_running = True
        sm._on_sync_cycle_done(True, "동기화 완료 (변경사항 없음)")
        self.assertFalse(sm._full_scan_pending)                              # 그다음부터는 바뀐 것만
        self.assertEqual(sm._dirty_ids, {"memo-bbbb"})                       # 못 올린 것은 다시 대기
        self.assertTrue(sm._push_timer.isActive())

        sm._dirty_ids.clear()
        sm._sending_ids = {"memo-cccc"}
        sm._current_worker = mock.Mock(unsent_ids=set(), quiet=True)
        sm._on_sync_cycle_done(False, "연결 실패")
        self.assertEqual(sm._dirty_ids, {"memo-cccc"})                       # 실패한 회차의 것은 전부 다시


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


class FolderRulesTest(unittest.TestCase):
    def test_folder_rules(self) -> None:
        from core import folders as f
        self.assertEqual(f.normalize("  업무 / /A\\B "), "업무/A/B")
        self.assertEqual(f.normalize(None), "")
        self.assertTrue(f.contains(f.ALL, "") and f.contains(f.ALL, "업무/A"))
        self.assertTrue(f.contains(f.UNFILED, "") and not f.contains(f.UNFILED, "업무"))
        self.assertTrue(f.contains("업무", "업무") and f.contains("업무", "업무/A"))
        self.assertFalse(f.contains("업무", "업무2") or f.contains("업무/A", "업무"))
        memos = [{"folder": "업무/A/깊이"}, {"folder": ""}, {}, {"folder": "개인"}]
        self.assertEqual(f.all_folders(["zz"], memos), ["zz", "개인", "업무", "업무/A", "업무/A/깊이"])
        self.assertEqual(f.moved("업무/A", "업무", "회사"), "회사/A")
        self.assertEqual(f.moved("업무2", "업무", "회사"), "업무2")
        self.assertNotEqual(f.UNFILED, f.normalize(f.UNFILED))        # 사용자가 같은 이름의 폴더를 만들 수 없음

    def test_folder_order_follows_the_saved_list(self) -> None:
        from core import folders as f
        self.assertEqual(f.arrange(["b", "a/y", "a/x", "b/z"]), ["b", "b/z", "a", "a/y", "a/x"])
        memos = [{"folder": "m2"}, {"folder": "a/new"}, {"folder": "m1"}]
        self.assertEqual(f.all_folders(["b", "a"], memos), ["b", "a", "a/new", "m1", "m2"])   # 저장된 순서 먼저
        names = ["a", "a/x", "a/y", "b", "c"]
        self.assertEqual(f.reorder(names, "c", "a"), ["c", "a", "a/x", "a/y", "b"])
        self.assertEqual(f.reorder(names, "a", None), ["b", "c", "a", "a/x", "a/y"])
        self.assertEqual(f.reorder(names, "a/y", "a/x"), ["a", "a/y", "a/x", "b", "c"])
        self.assertEqual(f.reorder(names, "a/x", None), ["a", "a/y", "a/x", "b", "c"])
        self.assertEqual(f.reorder(names, "a/x", "c"), names)                     # 다른 단계로는 옮겨지지 않음
        self.assertEqual(f.counts([{"folder": "a/x"}, {"folder": "a"}, {}]), {f.ALL: 3, f.UNFILED: 1, "a": 2, "a/x": 1})

    def test_folder_is_synced_but_window_placement_is_not(self) -> None:
        from core.sync_worker import shared_part
        shared = shared_part({"id": "a", "folder": "업무", "position_x": 5, "is_visible": True})
        self.assertEqual(shared, {"id": "a", "folder": "업무"})


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
