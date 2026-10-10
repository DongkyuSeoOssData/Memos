from utils.text_utils import clean_plain_text
from utils.file_utils import MEMO_IO_LOCK, atomic_write_json, is_safe_memo_id
from core.sync_worker import SyncWorker, shared_hash
from core.defaults import DEFAULT_SHORTCUTS
from core.folders import DEFAULT_FOLDERS
from core import shared_settings
from core import reminders
import copy
import os
import traceback
import sys
import json
import shutil
import uuid
import winreg
from datetime import datetime, timedelta
from typing import Any, List, Dict, Optional, Tuple
from pathlib import Path
from PyQt6.QtCore import QTimer, QThread, QObject, pyqtSignal
from PyQt6.QtWidgets import QSystemTrayIcon
from utils.crypto_manager import CryptoManager


AUTO_START_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
AUTO_START_APP_NAME = "MemoitApp"


def _auto_start_command() -> str:
    # 경로에 공백이 있어도 동작하도록 반드시 따옴표로 감쌉니다.
    if getattr(sys, 'frozen', False):
        return f'"{sys.executable}"'
    return f'"{sys.executable}" "{os.path.abspath(sys.argv[0])}"'


def is_auto_start_enabled(key_path: str = AUTO_START_KEY_PATH, app_name: str = AUTO_START_APP_NAME) -> bool:
    """레지스트리에 자동 실행 항목이 실제로 등록되어 있는지 확인합니다."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_QUERY_VALUE) as key:
            value, _ = winreg.QueryValueEx(key, app_name)
            return bool(value)
    except OSError:
        return False


def set_auto_start(enable: bool, key_path: str = AUTO_START_KEY_PATH, app_name: str = AUTO_START_APP_NAME) -> bool:
    """윈도우 시작 시 자동 실행을 등록/해제합니다. 요청한 상태가 실제로 반영되었으면 True."""
    try:
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
            if enable:
                winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, _auto_start_command())
            else:
                try:
                    winreg.DeleteValue(key, app_name)
                except FileNotFoundError:
                    pass
    except OSError as e:
        print(f"Auto start registry error: {e}")
    return is_auto_start_enabled(key_path, app_name) == enable


class SyncManager(QObject):
    # 동기화할 변경이 생겼음을 알립니다. (저장이 다른 스레드에서 일어나도 타이머는 주 스레드에서 걸리도록 신호로 전달)
    _changes_pending = pyqtSignal()
    # 이 PC에서 바뀐 것이 없을 때, 다른 기기의 변경을 확인하는 간격. 확인은 파일 목록 요청 한 번입니다.
    REMOTE_CHECK_SEC = 15 * 60
    # 변경 뒤 동기화까지 기다리는 시간 (환경설정의 sync_interval_index 로 고름)
    PUSH_DELAYS_SEC = [60, 600, 1800, 3600]
    # 메모 변경 기록: 메모마다 보관하는 이전 내용의 개수와, 연달아 저장할 때 기록을 남기는 최소 간격
    HISTORY_KEEP = 20
    HISTORY_MIN_GAP_SEC = 10 * 60
    # 메모의 알림이 바뀌었음을 알립니다. (화면 쪽에서 다음 알림 시각을 다시 잡음)
    reminders_changed = pyqtSignal()
    DEFAULT_SETTINGS: Dict[str, Any] = {
        "use_sync": False,
        "drive_folder_id": "",
        "drive_access_token": "",
        "local_memo_path": str(Path.home() / ".memoit_custom" / "memos"),
        "sync_interval_index": 0,
        "auto_start": False,
        "default_memo_color": "#E0F2FE",
        "default_font_family": "D2Coding",
        "default_code_font_family": "D2Coding",
        "default_code_lang": "JSON",
        "default_code_theme": "dark",
        "auto_eng_kor_convert": True,
        "default_gen_line_numbers": False,
        "default_gen_line_bg": False,
        "default_code_line_numbers": True,
        "default_code_line_bg": False,
        "default_show_line_numbers": False,
        "default_show_line_bg": False,
        "default_is_pinned": False,
        "trash_auto_delete_days": 0,
        "app_theme": "white",
        "default_memo_opacity": 1.0,
        "default_memo_width": 350,
        "default_memo_height": 380,
        "default_code_memo_width": 700,
        "default_code_memo_height": 380,
        "default_rolled_height": 53,
        "auto_save_idle_sec": 60,
        "locked_memo_relock_min": 5,
        "explorer_is_pinned": True,
        "explorer_fixed_size": False,
        # 탐색기 폴더 목록(이 PC에 적어 둔 것)과 마지막으로 고른 폴더
        "folders": list(DEFAULT_FOLDERS),
        "explorer_folder": "",
        # 탐색기에서 폴더를 고르는 방식: "tabs"(탭 줄) / "sidebar"(왼쪽 목록) / "dropdown"
        "folder_ui": "tabs",
        "folder_sidebar_open": True,
        "shortcuts": dict(DEFAULT_SHORTCUTS)
    }

    def __init__(self, drive_api: Any) -> None:
        super().__init__()
        self.drive_api = drive_api
        self.crypto = CryptoManager()

        self.base_path = Path.home() / ".memoit_custom"
        self.settings_path = self.base_path / "settings.json"
        self.pending_deletes_path = self.base_path / "pending_deletes.json"
        self.error_log_path = self.base_path / "error.log"

        self.settings = self.load_settings()
        # 공유 설정(여러 기기가 함께 쓰는 설정)을 마지막으로 바꾼 시각. 처음이면 설정 파일의 수정 시각으로 둡니다.
        if not self.settings.get(shared_settings.STAMP_KEY):
            try:
                stamp = datetime.fromtimestamp(self.settings_path.stat().st_mtime)
            except OSError:
                stamp = datetime.now()
            self.settings[shared_settings.STAMP_KEY] = stamp.isoformat()
        self._shared_fingerprint = shared_settings.fingerprint(self.settings)

        self.ui_manager: Any = None
        self._sync_running: bool = False
        self._resync_requested: bool = False
        # 마지막 동기화 이후 이 PC에서 내용이 바뀐 메모 id. 이것들만 읽어서 올립니다.
        self._dirty_ids: set = set()
        self._sending_ids: set = set()
        # 메모별 '공유하는 부분'의 해시. 창을 옮기는 것처럼 동기화와 무관한 저장을 가려내는 데 씁니다.
        self._shared_hashes: Dict[str, str] = {}
        # 앱을 켠 뒤 첫 동기화와 수동 동기화는 모든 메모를 훑습니다. (꺼져 있는 동안 바뀐 것을 놓치지 않도록)
        self._full_scan_pending: bool = True
        self._current_worker: Optional[SyncWorker] = None
        self._announce_next_sync: bool = False
        self._last_sync_at: Optional[datetime] = None
        self._push_timer = QTimer()
        self._push_timer.setSingleShot(True)
        self._push_timer.timeout.connect(self._sync_changes)
        self._changes_pending.connect(self._arm_push_timer)
        # 잠금 해제된 암호 메모의 (키, 솔트). 메모리에만 두며 다시 잠그면 지웁니다.
        self._memo_keys: Dict[str, Tuple[bytes, bytes]] = {}
        self.active_threads: List[QThread] = []

        cp = self.settings.get("local_memo_path")
        self.local_path = Path(cp) if cp else self.base_path / "memos"
        self.local_path.mkdir(parents=True, exist_ok=True)
        self.trash_path = self.local_path / "trash_bin"
        self.trash_path.mkdir(parents=True, exist_ok=True)
        # 메모 id → 알림. 알림 시각을 확인할 때마다 모든 메모 파일을 읽지 않도록 메모리에 모아 둡니다.
        self.reminders: Dict[str, Dict[str, Any]] = {}
        self._reminders_loaded = False

        self.drive_api.set_web_app_url(self.settings.get("drive_folder_id", ""))
        self._apply_access_token()
        self.sync_timer = QTimer()
        self.setup_timer()

        QTimer.singleShot(3000, self.sync_all)

        # 휴지통 보관 기간이 지난 메모 정리 (시작 직후 1회 + 6시간마다)
        self._purge_timer = QTimer()
        self._purge_timer.timeout.connect(self.purge_trash)
        self._purge_timer.start(6 * 60 * 60 * 1000)
        QTimer.singleShot(5000, self.purge_trash)

    # ── 암호 메모 ────────────────────────────────────────────────────────────
    def is_memo_unlocked(self, memo_id: str) -> bool:
        return memo_id in self._memo_keys

    def set_memo_password(self, memo: Dict[str, Any], password: str) -> bool:
        """메모에 암호를 겁니다. (이미 잠금 해제된 암호 메모라면 암호 변경)"""
        memo_id = memo.get('id')
        if not memo_id or not password or memo.get('_locked') or memo.get('_unreadable'):
            return False
        salt = self.crypto.new_salt()
        self._memo_keys[memo_id] = (self.crypto.derive_key(password, salt), salt)
        memo['is_locked'] = True
        memo['is_draft'] = False
        return self.save_memo_locally(memo)

    def unlock_memo(self, memo_id: str, password: str) -> Optional[str]:
        """암호가 맞으면 본문을 돌려주고 키를 메모리에 보관합니다. 틀리면 None."""
        payload = self._read_raw_content(memo_id)
        if not self.crypto.is_locked_payload(payload):
            return None
        try:
            key = self.crypto.key_for_payload(payload, password)
            plain = self.crypto.decrypt_locked(payload, key)
        except ValueError:
            return None
        self._memo_keys[memo_id] = (key, self.crypto.payload_salt(payload))
        return plain

    def memo_has_master_recovery(self, memo_id: str) -> bool:
        """이 메모가 관리자 개인키로 복구할 수 있는 형태로 잠겨 있는지 여부."""
        return self.crypto.has_master_recovery(self._read_raw_content(memo_id))

    def recover_memo_with_master(self, memo_id: str, private_key_pem: bytes,
                                 passphrase: Optional[str], new_password: str) -> str:
        """관리자 개인키로 본문을 복구하고 새 암호로 다시 잠급니다. 복구한 본문을 돌려주며, 실패하면 ValueError."""
        if not new_password:
            raise ValueError("새 암호를 입력해야 합니다.")
        with MEMO_IO_LOCK:
            path = self.local_path / f"{memo_id}.json"
            try:
                with open(path, "r", encoding="utf-8") as f:
                    memo = json.load(f)
            except Exception as e:
                raise ValueError("메모 파일을 읽을 수 없습니다.") from e
            plain = self.crypto.recover_with_private_key(memo.get('content'), private_key_pem, passphrase)
            salt = self.crypto.new_salt()
            self._memo_keys[memo_id] = (self.crypto.derive_key(new_password, salt), salt)
            memo['content'] = plain
            memo['is_locked'] = True
            if not self.save_memo_locally(memo):
                raise ValueError("복구한 메모를 저장하지 못했습니다.")
        return plain

    def relock_memo(self, memo_id: str) -> None:
        self._memo_keys.pop(memo_id, None)

    def remove_memo_password(self, memo: Dict[str, Any]) -> bool:
        """암호를 없애고 일반 메모로 되돌립니다. 잠금 해제 상태에서만 가능합니다."""
        memo_id = memo.get('id')
        if not memo_id or memo.get('_locked') or memo_id not in self._memo_keys:
            return False
        memo['is_locked'] = False
        self._memo_keys.pop(memo_id, None)
        return self.save_memo_locally(memo)

    def _read_raw_content(self, memo_id: str) -> Any:
        try:
            with MEMO_IO_LOCK:
                with open(self.local_path / f"{memo_id}.json", "r", encoding="utf-8") as f:
                    data = json.load(f)
            return data.get('content') if isinstance(data, dict) else None
        except Exception:
            return None

    def _open_content(self, m: Dict[str, Any], raw_content: Any) -> bool:
        """디스크의 content를 메모리용 평문으로 바꿔 m에 넣습니다.

        읽을 수 없는 본문은 비워 두고 '_locked'(암호 필요) 또는 '_unreadable'(손상) 표시를 남겨,
        저장 시 디스크의 원본 암호문이 덮이지 않도록 합니다. 평문으로 다시 써야 하면 True를 반환합니다.
        """
        m.pop('_locked', None)
        m.pop('_unreadable', None)
        if self.crypto.is_locked_payload(raw_content):
            m['is_locked'] = True
            entry = self._memo_keys.get(m.get('id', ''))
            if entry:
                try:
                    m['content'] = self.crypto.decrypt_locked(raw_content, entry[0])
                    return False
                except ValueError:
                    # 다른 PC에서 암호가 바뀐 경우 등: 보관 중인 키가 더 이상 맞지 않음
                    self._memo_keys.pop(m.get('id', ''), None)
            m['content'] = ""
            m['_locked'] = True
            return False
        if self.crypto.is_legacy_payload(raw_content):
            try:
                m['content'] = self.crypto.decrypt_legacy(raw_content)
                return True
            except ValueError:
                m['content'] = ""
                m['_unreadable'] = True
                return False
        if isinstance(raw_content, dict):
            m['content'] = str(raw_content.get("content", ""))
            return True
        m['content'] = str(raw_content) if raw_content is not None else ""
        return False

    def log_error(self, message: str, exc: Optional[Exception] = None) -> None:
        try:
            self.base_path.mkdir(parents=True, exist_ok=True)
            # 로그가 끝없이 커지지 않도록 1MB를 넘으면 이전 로그 하나만 남기고 새로 시작합니다.
            if self.error_log_path.exists() and self.error_log_path.stat().st_size > 1024 * 1024:
                os.replace(self.error_log_path, self.error_log_path.with_name("error.log.1"))
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            log_entry = f"[{now_str}] {message}\n"
            if exc:
                log_entry += f"{traceback.format_exc()}\n"
            with open(self.error_log_path, "a", encoding="utf-8") as f:
                f.write(log_entry)
        except Exception:
            pass

    def set_ui_manager(self, ui_manager: Any) -> None:
        self.ui_manager = ui_manager

    def load_settings(self) -> Dict[str, Any]:
        defaults = copy.deepcopy(self.DEFAULT_SETTINGS)
        self.base_path.mkdir(parents=True, exist_ok=True)
        if self.settings_path.exists():
            try:
                with open(self.settings_path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    loaded_shortcuts = loaded.get("shortcuts", {})
                    merged_shortcuts = {**defaults.get("shortcuts", {}), **loaded_shortcuts}
                    return {**defaults, **loaded, "shortcuts": merged_shortcuts}
            except Exception as e:
                self.log_error("설정 파일 로드 실패", e)
        return defaults

    def save_settings(self, new_s: Dict[str, Any], stamp_shared: bool = True) -> None:
        # 넘겨받은 키만 갱신합니다. 통째로 교체하면 new_s에 없는 키(창 위치 등)가 사라집니다.
        merged_shortcuts = {**self.settings.get("shortcuts", {}), **new_s.get("shortcuts", {})}
        self.settings.update(new_s)
        self.settings["shortcuts"] = merged_shortcuts
        # 공유 설정이 바뀌었으면 바꾼 시각을 적어 둡니다. 다음 동기화 때 다른 기기로 전해집니다.
        fingerprint = shared_settings.fingerprint(self.settings)
        if fingerprint != self._shared_fingerprint:
            self._shared_fingerprint = fingerprint
            if stamp_shared:
                self.settings[shared_settings.STAMP_KEY] = datetime.now().isoformat()
                self._changes_pending.emit()
        try:
            atomic_write_json(self.settings_path, self.settings)
            self.local_path = Path(self.settings.get("local_memo_path", str(self.base_path / "memos")))
            self.local_path.mkdir(parents=True, exist_ok=True)
            self.trash_path = self.local_path / "trash_bin"
            self.trash_path.mkdir(parents=True, exist_ok=True)
            self.drive_api.set_web_app_url(self.settings.get("drive_folder_id", ""))
            self._apply_access_token()
            self.setup_timer()
        except Exception as e:
            self.log_error("설정 파일 저장 실패", e)

    def _apply_access_token(self) -> None:
        # 시험용 가짜 드라이브처럼 접근 암호를 받지 않는 구현도 있으므로 있을 때만 넘깁니다.
        setter = getattr(self.drive_api, "set_access_token", None)
        if setter:
            setter(self.settings.get("drive_access_token", ""))

    def apply_auto_start(self, enable: bool) -> bool:
        """자동 실행을 레지스트리에 반영하고, 실제 반영된 상태를 설정에 기록합니다."""
        ok = set_auto_start(enable)
        if not ok:
            self.log_error(f"윈도우 자동 실행 {'등록' if enable else '해제'} 실패")
        self.settings["auto_start"] = is_auto_start_enabled()
        return ok

    def setup_timer(self) -> None:
        """동기화 타이머를 설정에 맞춥니다.

        정해진 간격마다 무조건 동기화하지 않습니다.
        - 이 PC에서 내용이 바뀌면, 그때부터 설정한 시간만큼 기다렸다가 바뀐 메모만 올립니다.
        - 바뀐 것이 없을 때는 다른 기기의 변경이 있는지 가끔(REMOTE_CHECK_SEC) 파일 목록만 확인합니다.
        """
        self.sync_timer.stop()
        try:
            self.sync_timer.timeout.disconnect()
        except Exception:
            pass
        if not self.settings.get("use_sync", True):
            self._push_timer.stop()
            return
        self.sync_timer.timeout.connect(self.check_remote)
        self.sync_timer.start(self.REMOTE_CHECK_SEC * 1000)
        if self._dirty_ids and not self._push_timer.isActive():
            self._arm_push_timer()

    def push_delay_sec(self) -> int:
        idx = self.settings.get("sync_interval_index", 0)
        try:
            idx = max(0, min(int(idx), len(self.PUSH_DELAYS_SEC) - 1))
        except (TypeError, ValueError):
            idx = 0
        return self.PUSH_DELAYS_SEC[idx]

    def mark_dirty(self, memo_id: str) -> None:
        """이 메모가 바뀌었으니 다음 동기화 때 올려야 함을 적어 둡니다."""
        if memo_id:
            self._dirty_ids.add(memo_id)
            self._changes_pending.emit()

    def _arm_push_timer(self) -> None:
        """변경이 생긴 뒤 설정한 시간만큼 기다렸다가 동기화합니다. 이미 기다리는 중이면 그대로 둡니다."""
        if self.settings.get("use_sync", True) and not self._push_timer.isActive():
            self._push_timer.start(self.push_delay_sec() * 1000)

    def _sync_changes(self) -> None:
        self._start_sync()

    def check_remote(self) -> None:
        """다른 기기에서 바뀐 것이 있는지 확인합니다. 이 PC의 메모 파일은 바뀐 것만 읽습니다."""
        self._start_sync()

    def check_remote_if_stale(self, max_age_sec: int = 60) -> None:
        """마지막 동기화가 오래됐으면 다른 기기의 변경을 확인합니다. (탐색기를 열 때 등)"""
        if not self.settings.get("use_sync", True):
            return
        if self._last_sync_at is None or (datetime.now() - self._last_sync_at).total_seconds() >= max_age_sec:
            self.check_remote()

    def load_local_memos(self) -> List[Dict[str, Any]]:
        with MEMO_IO_LOCK:
            return self._load_local_memos()

    def _load_local_memos(self) -> List[Dict[str, Any]]:
        memos: List[Dict[str, Any]] = []
        seen_ids = set()

        if not self.local_path.exists():
            return memos

        for f in list(self.local_path.glob("*.json")):
            if "trash_bin" in str(f):
                continue
            try:
                with open(f, "r", encoding="utf-8") as file:
                    m = json.load(file)

                if isinstance(m, dict):
                    memo_id = m.get('id')
                    if not memo_id or len(memo_id) < 8:
                        memo_id = str(uuid.uuid4())
                        m['id'] = memo_id

                    if memo_id in seen_ids:
                        continue

                    # 휴지통에 동일 ID나 파일명이 이미 존재하는 경우 (삭제 후 잔존한 껍데기 파일 자동 삭제)
                    if (self.trash_path / f.name).exists() or (self.trash_path / f"{memo_id}.json").exists():
                        try:
                            f.unlink()
                        except Exception:
                            pass
                        continue

                    seen_ids.add(memo_id)

                    needs_rewrite = self._open_content(m, m.get('content'))
                    sealed = m.get('_locked') or m.get('_unreadable')

                    # 0자 내용인 빈 초안 메모는 디스크에서 자동으로 깔끔히 청소 및 제외
                    if (not sealed and not m.get('is_locked') and m.get('is_draft')
                            and not m.get('is_manually_saved') and not clean_plain_text(m['content'])):
                        try:
                            f.unlink()
                        except Exception:
                            pass
                        continue

                    memos.append(m)
                    self._note_reminder(memo_id, m.get('reminder'), quiet=True)

                    expected_file = self.local_path / f"{memo_id}.json"
                    if f.name != expected_file.name:
                        # 구버전 파일명: 원본 바이트를 그대로 옮겨 암호문이 훼손되지 않게 합니다.
                        try:
                            if not expected_file.exists():
                                shutil.move(str(f), str(expected_file))
                            else:
                                f.unlink()
                        except Exception as e:
                            self.log_error(f"구버전 레거시 메모 파일 정리 실패 ({f.name}): {e}", e)
                    if needs_rewrite:
                        self.save_memo_locally(m)
            except Exception as e:
                self.log_error(f"로컬 메모 파일 읽기 에러 ({f.name}): {e}", e)

        # 사라진 메모(삭제·다른 기기에서 지움)의 알림은 목록에서 뺍니다.
        gone = set(self.reminders) - seen_ids
        for memo_id in gone:
            self.reminders.pop(memo_id, None)
        first_load, self._reminders_loaded = not self._reminders_loaded, True
        if gone or first_load:
            self.reminders_changed.emit()
        return memos

    # ── 알림 ─────────────────────────────────────────────────────────────────
    def _note_reminder(self, memo_id: str, reminder: Any, quiet: bool = False) -> None:
        """메모의 알림을 메모리 목록에 반영합니다. 바뀌었으면 화면 쪽에 알립니다."""
        normal = reminders.normalize(reminder)
        if self.reminders.get(memo_id) == normal or (normal is None and memo_id not in self.reminders):
            return
        if normal is None:
            self.reminders.pop(memo_id, None)
        else:
            self.reminders[memo_id] = normal
        if not quiet or self._reminders_loaded:
            self.reminders_changed.emit()

    def set_reminder(self, memo: Dict[str, Any], reminder: Optional[Dict[str, Any]]) -> bool:
        """메모에 알림을 걸거나(reminder) 풉니다(None). 본문을 고친 것이 아니므로 수정일시는 그대로 둡니다."""
        normal = reminders.normalize(reminder) if reminder else None
        if normal is None:
            memo.pop('reminder', None)
        else:
            memo['reminder'] = normal
        memo['meta_updated_at'] = datetime.now().isoformat()
        return self.save_memo_locally(memo)

    # ── 변경 기록 ────────────────────────────────────────────────────────────
    # 메모를 덮어쓰기 전의 내용을 메모 폴더의 history_bin/{id}.json 에 쌓아 둡니다. 이 PC에만 두며 동기화하지 않습니다.
    @property
    def history_path(self) -> Path:
        return self.local_path / "history_bin"

    def _history_file(self, memo_id: str) -> Path:
        return self.history_path / f"{memo_id}.json"

    def _read_history(self, memo_id: str) -> List[Dict[str, Any]]:
        try:
            with open(self._history_file(memo_id), "r", encoding="utf-8") as f:
                loaded = json.load(f)
            return [e for e in loaded if isinstance(e, dict)] if isinstance(loaded, list) else []
        except Exception:
            return []

    def _snapshot(self, memo_id: str, old: Dict[str, Any], reason: str = "", force: bool = False) -> None:
        """old(덮어쓰기 직전의 메모 파일 내용)를 변경 기록에 남깁니다.

        연달아 저장할 때마다 쌓이지 않도록, 마지막 기록에서 HISTORY_MIN_GAP_SEC 이 지났을 때만 남깁니다.
        (다른 기기의 내용으로 덮어쓰는 경우처럼 force 가 켜진 경우는 항상 남깁니다)
        """
        try:
            with MEMO_IO_LOCK:
                entries = self._read_history(memo_id)
                now = datetime.now()
                if entries and not force:
                    try:
                        if (now - datetime.fromisoformat(entries[-1].get("saved_at", ""))).total_seconds() < self.HISTORY_MIN_GAP_SEC:
                            return
                    except (TypeError, ValueError):
                        pass
                if entries and entries[-1].get("content") == old.get("content") and entries[-1].get("title") == old.get("title"):
                    return
                entries.append({
                    "saved_at": now.isoformat(), "reason": reason,
                    "title": old.get("title", ""), "content": old.get("content", ""),
                    "updated_at": old.get("updated_at", ""), "is_locked": bool(old.get("is_locked")),
                })
                self.history_path.mkdir(parents=True, exist_ok=True)
                atomic_write_json(self._history_file(memo_id), entries[-self.HISTORY_KEEP:])
        except Exception as e:
            self.log_error(f"변경 기록 저장 실패 ({memo_id}): {e}", e)

    def snapshot_before_overwrite(self, memo_id: str, old: Dict[str, Any], reason: str) -> None:
        """다른 기기의 내용으로 덮어쓰기 직전에 부릅니다. (동기화 워커가 사용)"""
        if is_safe_memo_id(memo_id) and isinstance(old, dict):
            self._snapshot(memo_id, old, reason=reason, force=True)

    def list_history(self, memo_id: str) -> List[Dict[str, Any]]:
        """이 메모의 이전 내용들. 최근 것이 앞에 옵니다. 암호 메모의 기록은 본문 대신 'locked' 표시만 줍니다."""
        out = []
        for index, entry in reversed(list(enumerate(self._read_history(memo_id)))):
            content = entry.get("content", "")
            sealed = isinstance(content, dict)
            out.append({
                "index": index, "saved_at": entry.get("saved_at", ""), "reason": entry.get("reason", ""),
                "title": entry.get("title", ""), "locked": sealed,
                "text": "" if sealed else clean_plain_text(content),
            })
        return out

    def restore_history(self, memo_id: str, index: int) -> bool:
        """index 번째 기록의 제목·본문으로 되돌립니다. 지금 내용은 먼저 기록에 남깁니다."""
        entries = self._read_history(memo_id)
        if not (0 <= index < len(entries)):
            return False
        entry = entries[index]
        path = self.local_path / f"{memo_id}.json"
        try:
            with MEMO_IO_LOCK:
                with open(path, "r", encoding="utf-8") as f:
                    current = json.load(f)
                self._snapshot(memo_id, current, reason="되돌리기 전", force=True)
                current["title"] = entry.get("title", current.get("title", ""))
                current["content"] = entry.get("content", "")
                current["is_locked"] = isinstance(entry.get("content"), dict)
                current["updated_at"] = datetime.now().isoformat()
                atomic_write_json(path, current)
        except Exception as e:
            self.log_error(f"변경 기록 되돌리기 실패 ({memo_id}): {e}", e)
            return False
        self._shared_hashes.pop(memo_id, None)
        self.mark_dirty(memo_id)
        return True

    def _drop_history(self, memo_id: str) -> None:
        try:
            self._history_file(memo_id).unlink()
        except OSError:
            pass

    def load_trash_memos(self) -> List[Dict[str, Any]]:
        memos: List[Dict[str, Any]] = []
        if not self.trash_path.exists(): return memos
        for f in list(self.trash_path.glob("*.json")):
            try:
                with MEMO_IO_LOCK:
                    with open(f, "r", encoding="utf-8") as file:
                        m = json.load(file)

                if isinstance(m, dict):
                    if 'id' not in m:
                        m['id'] = f.stem
                    self._open_content(m, m.get('content'))
                    memos.append(m)
            except Exception as e:
                self.log_error(f"휴지통 메모 읽기 에러 ({f.name}): {e}", e)
        return memos

    def restore_memo_locally(self, memo_id: str) -> bool:
        src = self.trash_path / f"{memo_id}.json"
        dst = self.local_path / f"{memo_id}.json"
        try:
            with MEMO_IO_LOCK:
                if not src.exists():
                    return False
                with open(src, "r", encoding="utf-8") as f:
                    data = json.load(f)
                # 수정시각을 갱신해 두어야 다음 동기화가 '원격에서 지워진 메모'로 보지 않고 다시 올립니다.
                data['updated_at'] = datetime.now().isoformat()
                data.pop('deleted_at', None)
                atomic_write_json(dst, data)
                src.unlink()
                self.remove_pending_delete(memo_id)
            self.mark_dirty(memo_id)
            return True
        except Exception as e:
            self.log_error(f"로컬 메모 복구 실패 ({memo_id}): {e}", e)
        return False

    def save_memo_locally(self, data: Dict[str, Any]) -> bool:
        memo_id = data.get('id')
        if not memo_id:
            memo_id = str(uuid.uuid4())
            data['id'] = memo_id
        if not is_safe_memo_id(memo_id):
            self.log_error(f"파일 이름으로 쓸 수 없는 메모 id라 저장을 건너뜀 ({memo_id!r})")
            return False

        f = self.local_path / f"{memo_id}.json"
        # '_'로 시작하는 키는 실행 중에만 쓰는 상태값이라 파일에 남기지 않습니다.
        memo_to_save = {k: v for k, v in data.items() if not str(k).startswith('_')}
        plain_content = str(data.get('content', ''))

        if data.get('_locked') or data.get('_unreadable'):
            # 본문을 읽지 못한 상태: 제목·위치 같은 정보만 갱신하고 디스크의 원본 본문은 그대로 둡니다.
            raw = self._read_raw_content(memo_id)
            if raw is None:
                self.log_error(f"잠긴 메모의 원본을 찾을 수 없어 저장을 건너뜀 ({memo_id})")
                return False
            memo_to_save['content'] = raw
        elif data.get('is_locked'):
            entry = self._memo_keys.get(memo_id)
            if not entry:
                self.log_error(f"암호 메모의 키가 없어 저장을 건너뜀 ({memo_id})")
                return False
            memo_to_save['content'] = self.crypto.encrypt_locked(plain_content, entry[0], entry[1])
        else:
            # 미작성 빈 초안 메모(is_draft == True, 내용 없음, 수동저장 안함)는 디스크 저장을 차단하며 기존 파일이 있으면 파기
            if data.get('is_draft') and not data.get('is_manually_saved') and not clean_plain_text(plain_content):
                if f.exists():
                    try:
                        f.unlink()
                    except Exception:
                        pass
                return False
            memo_to_save['content'] = plain_content

        try:
            with MEMO_IO_LOCK:
                # 본문이나 제목이 바뀌는 저장이면, 덮어쓰기 전의 내용을 변경 기록에 남깁니다.
                old = None
                if f.exists():
                    try:
                        with open(f, "r", encoding="utf-8") as existing:
                            old = json.load(existing)
                    except Exception:
                        old = None
                if isinstance(old, dict) and (old.get("content") != memo_to_save.get("content")
                                              or old.get("title") != memo_to_save.get("title")):
                    # 암호문은 저장할 때마다 달라지므로, 암호 메모는 수정일시가 바뀐 경우에만 기록합니다.
                    sealed_same = (isinstance(old.get("content"), dict) and isinstance(memo_to_save.get("content"), dict)
                                   and old.get("updated_at") == memo_to_save.get("updated_at")
                                   and old.get("title") == memo_to_save.get("title"))
                    if not sealed_same:
                        self._snapshot(memo_id, old)
                atomic_write_json(f, memo_to_save)
        except Exception as e:
            self.log_error(f"로컬 메모 저장 실패 ({memo_id}): {e}", e)
            return False
        self._note_reminder(memo_id, memo_to_save.get('reminder'))
        # 다른 기기와 공유하는 부분(본문·제목·폴더 등)이 실제로 바뀐 경우에만 동기화 대상으로 표시합니다.
        # 창 위치·크기처럼 이 PC에만 속한 값만 바뀐 저장은 동기화를 일으키지 않습니다.
        new_hash = shared_hash(memo_to_save)
        if self._shared_hashes.get(memo_id) != new_hash:
            self._shared_hashes[memo_id] = new_hash
            self.mark_dirty(memo_id)
        return True

    def rename_memo_locally(self, ot: str, nt: str, data: Dict[str, Any]) -> bool:
        try:
            data['title'] = nt
            self.save_memo_locally(data)
            return True
        except Exception as e:
            self.log_error(f"메모 제목 변경 실패 ({ot} -> {nt}): {e}", e)
            return False

    def delete_memo_locally(self, memo_id: str, title: Optional[str] = None) -> None:
        with MEMO_IO_LOCK:
            self._delete_memo_locally(memo_id)
            self._stamp_deleted(self.trash_path / f"{memo_id}.json")
        self.relock_memo(memo_id)
        self._note_reminder(memo_id, None)
        if self._trash_retention_days() < 0:
            self.purge_trash()

    # ── 휴지통 보관 기간 ─────────────────────────────────────────────────────
    def _trash_retention_days(self) -> int:
        """0: 자동 삭제 안 함, 음수: 즉시 삭제, 양수: 그 일수가 지나면 삭제."""
        try:
            return int(self.settings.get("trash_auto_delete_days", 0))
        except (TypeError, ValueError):
            return 0

    def _stamp_deleted(self, path: Path) -> Optional[str]:
        """휴지통 파일에 삭제 시각을 기록합니다. (이미 있으면 그대로 두고 그 값을 반환)"""
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return None
            if not data.get('deleted_at'):
                data['deleted_at'] = datetime.now().isoformat()
                atomic_write_json(path, data)
                return None
            return str(data['deleted_at'])
        except Exception:
            return None

    def purge_trash(self) -> int:
        """보관 기간이 지난 휴지통 메모를 영구 삭제하고, 지운 개수를 반환합니다.

        삭제 시각이 기록되지 않은 예전 휴지통 파일은 지금 시각을 기록만 해 두고 이번에는 지우지 않습니다.
        """
        days = self._trash_retention_days()
        if days == 0 or not self.trash_path.exists():
            return 0
        count = 0
        with MEMO_IO_LOCK:
            for f in list(self.trash_path.glob("*.json")):
                stamp = self._stamp_deleted(f)
                if not stamp:
                    continue
                try:
                    expired = days < 0 or datetime.now() - datetime.fromisoformat(stamp) >= timedelta(days=days)
                    if expired:
                        f.unlink()
                        self._drop_history(f.stem)
                        count += 1
                except Exception as e:
                    self.log_error(f"휴지통 자동 삭제 실패 ({f.name}): {e}", e)
        return count

    def _delete_memo_locally(self, memo_id: str) -> None:
        if not memo_id: return
        self.trash_path.mkdir(parents=True, exist_ok=True)

        # 1. ID 기반 파일 우선 이동
        src = self.local_path / f"{memo_id}.json"
        dst = self.trash_path / f"{memo_id}.json"

        if src.exists():
            try:
                if dst.exists(): dst.unlink()
                shutil.move(str(src), str(dst))
            except Exception as e:
                self.log_error(f"로컬 메모 휴지통 이동 실패 ({memo_id}): {e}", e)
            # 파일 이름이 id와 같으면 그 파일 하나뿐입니다. (불러올 때 id 이름으로 정리해 두기 때문)
            return

        # 2. ID 기반으로만 탐색 — title 기준 삭제는 동명 메모 오삭제 위험이 있어 제거
        #    (파일명이 memo_id가 아닌 레거시 파일 또는 JSON 내부 id가 memo_id인 경우만 이동)
        if self.local_path.exists():
            for f in list(self.local_path.glob("*.json")):
                if "trash_bin" in str(f) or f.is_dir(): continue
                try:
                    with open(f, "r", encoding="utf-8") as file:
                        m_data = json.load(file)
                    if isinstance(m_data, dict):
                        file_id = m_data.get('id')
                        # id가 일치하는 경우만 이동 (title은 사용하지 않음)
                        if file_id == memo_id:
                            target_dst = self.trash_path / f.name
                            if target_dst.exists(): target_dst.unlink()
                            shutil.move(str(f), str(target_dst))
                except Exception as e:
                    self.log_error(f"삭제할 메모 탐색 중 오류 ({f.name}): {e}", e)

    def empty_trash_locally(self) -> int:
        count = 0
        if self.trash_path.exists():
            with MEMO_IO_LOCK:
                for f in list(self.trash_path.glob("*.json")):
                    try:
                        f.unlink()
                        self._drop_history(f.stem)
                        count += 1
                    except Exception as e:
                        self.log_error(f"휴지통 비우기 실패 ({f.name}): {e}", e)
        return count

    # ── 원격 삭제 대기열 ─────────────────────────────────────────────────────
    # 오프라인 등으로 드라이브 삭제가 실패해도 다음 동기화에서 다시 시도하고,
    # 그동안 같은 메모를 다시 내려받지 않도록 삭제할 id를 파일에 남겨 둡니다.
    def get_pending_deletes(self) -> List[str]:
        with MEMO_IO_LOCK:
            try:
                with open(self.pending_deletes_path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                return [str(x) for x in loaded] if isinstance(loaded, list) else []
            except Exception:
                return []

    def _write_pending_deletes(self, ids: List[str]) -> None:
        try:
            atomic_write_json(self.pending_deletes_path, ids)
        except Exception as e:
            self.log_error(f"삭제 대기열 저장 실패: {e}", e)

    def add_pending_deletes(self, ids: List[str]) -> None:
        with MEMO_IO_LOCK:
            current = self.get_pending_deletes()
            self._write_pending_deletes(current + [i for i in ids if i and i not in current])

    def remove_pending_delete(self, memo_id: str) -> None:
        with MEMO_IO_LOCK:
            current = self.get_pending_deletes()
            if memo_id in current:
                self._write_pending_deletes([i for i in current if i != memo_id])

    def delete_memos_cloud(self, ids: List[str]) -> None:
        self.add_pending_deletes(ids)
        if not self.settings.get("use_sync", True): return
        if self._sync_running:
            self._resync_requested = True
        else:
            self._start_sync()

    def sync_all(self) -> None:
        """지금 바로 전부 동기화합니다. (동기화 버튼·트레이 메뉴·앱 시작 직후) 모든 메모를 훑어 빠진 것이 없게 합니다."""
        if not self.settings.get("use_sync", True):
            self.on_sync_finished(True, "로컬 모드로 작동 중입니다. (동기화 OFF)")
            return
        self._full_scan_pending = True
        self._announce_next_sync = True
        if self._sync_running:
            self._resync_requested = True
        else:
            self._start_sync()

    def _start_sync(self) -> None:
        if not self.settings.get("use_sync", True):
            return
        # 이전 주기가 아직 돌고 있으면 건너뜁니다. (두 워커가 같은 파일을 동시에 올리고 받는 것 방지)
        if self._sync_running:
            return
        self._sync_running = True
        self._push_timer.stop()
        worker = SyncWorker(self)
        # 전체를 훑을 때는 None, 아니면 바뀐 메모 id 만 넘겨 그것들만 읽고 올리게 합니다.
        self._sending_ids = set(self._dirty_ids)
        self._dirty_ids.clear()
        worker.push_ids = None if self._full_scan_pending else set(self._sending_ids)
        worker.quiet = not self._announce_next_sync
        self._announce_next_sync = False
        self._current_worker = worker
        worker.finished.connect(self._on_sync_cycle_done)
        worker.pulled.connect(self.on_memos_pulled)
        worker.removed.connect(self.on_memos_removed)
        worker.settings_pulled.connect(self.apply_remote_settings)
        self._start_worker(worker)

    def _on_sync_cycle_done(self, success: bool, message: str) -> None:
        worker, self._current_worker = self._current_worker, None
        self._last_sync_quiet = bool(getattr(worker, "quiet", False))
        self._sync_running = False
        self._last_sync_at = datetime.now()
        if success:
            self._full_scan_pending = False
            # 올리지 못한 메모는 다음에 다시 시도합니다.
            self._dirty_ids |= set(getattr(worker, "unsent_ids", set()))
        else:
            self._dirty_ids |= self._sending_ids
        self._sending_ids = set()
        if self._resync_requested:
            self._resync_requested = False
            QTimer.singleShot(0, self._start_sync)
        elif self._dirty_ids:
            self._arm_push_timer()

    def apply_remote_settings(self, remote: Dict[str, Any]) -> None:
        """다른 기기에서 바꾼 공유 설정을 이 PC에 반영합니다. (드라이브에서 받은 것이 더 최신일 때 호출)"""
        incoming = shared_settings.from_remote(remote)
        stamp = str(remote.get("updated_at", "")) if isinstance(remote, dict) else ""
        if not incoming or not stamp:
            return
        if "shortcuts" in incoming and isinstance(incoming["shortcuts"], dict):
            # 이 버전에 새로 생긴 단축키가 받은 쪽에 없더라도 사라지지 않게 기본값 위에 얹습니다.
            incoming["shortcuts"] = {**DEFAULT_SHORTCUTS, **incoming["shortcuts"]}
            self.settings["shortcuts"] = {}
        self.save_settings({**incoming, shared_settings.STAMP_KEY: stamp}, stamp_shared=False)
        if self.ui_manager and hasattr(self.ui_manager, "apply_settings_to_windows"):
            self.ui_manager.apply_settings_to_windows(reload_settings_window=True)

    def on_memos_pulled(self, memo_ids: List[str]) -> None:
        if memo_ids:
            self.load_local_memos()         # 다른 기기에서 걸거나 푼 알림을 알림 목록에 반영
        if memo_ids and self.ui_manager:
            self.ui_manager.reload_pulled_memos(memo_ids)

    def on_memos_removed(self, memo_ids: List[str]) -> None:
        """다른 기기에서 삭제되어 로컬 휴지통으로 옮겨진 메모의 창을 닫습니다."""
        for memo_id in memo_ids:
            self.relock_memo(memo_id)
            if self.ui_manager:
                self.ui_manager.close_memo_window_by_id(memo_id, is_deleting=True)

    def _start_worker(self, worker: SyncWorker) -> None:
        thread = QThread()
        thread.worker = worker
        worker.moveToThread(thread)
        thread.started.connect(worker.execute)

        worker.finished.connect(self.on_sync_finished)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)

        def cleanup():
            if thread in self.active_threads:
                self.active_threads.remove(thread)

        thread.finished.connect(cleanup)
        self.active_threads.append(thread)
        thread.start()

    def on_sync_finished(self, success: bool, message: str) -> None:
        if not message:
            return
        print(f"[동기화 로그] 성공: {success}, 내용: {message}")
        # 뒤에서 조용히 돈 확인에서 바뀐 것이 없었다면 알리지 않습니다.
        if success and "변경사항 없음" in message and getattr(self, "_last_sync_quiet", False):
            return
        if self.ui_manager:
            if self.ui_manager.explorer_window and self.ui_manager.explorer_window.isVisible():
                self.ui_manager.explorer_window.show_toast(message)
            else:
                if not success:
                    self.ui_manager.tray_icon.showMessage(
                        "Memos 동기화 오류",
                        message,
                        QSystemTrayIcon.MessageIcon.Warning,
                        3000
                    )
            if success and ("가져오기 완료" in message or "업로드 완료" in message or "동기화 완료" in message) and self.ui_manager.explorer_window:
                self.ui_manager.explorer_window.refresh()
