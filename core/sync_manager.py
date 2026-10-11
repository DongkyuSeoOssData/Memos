from utils.text_utils import clean_plain_text
from utils.file_utils import MEMO_IO_LOCK, atomic_write_json, is_safe_memo_id
from core.sync_worker import SYNC_CHANGED, SYNC_NOT_DONE, SYNC_OFFLINE, SYNC_UNCHANGED, SyncWorker, shared_hash
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
from datetime import datetime
from typing import Any, List, Dict, Optional, Tuple
from pathlib import Path
from PyQt6.QtCore import QTimer, QThread, QObject, pyqtSignal
from utils.crypto_manager import CryptoManager
from core.memo_password import MemoPasswordMixin
from core.memo_history import MemoHistoryMixin
from core.memo_trash import MemoTrashMixin
from core.memo_index import MemoIndexMixin
import threading


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


class SyncManager(MemoPasswordMixin, MemoHistoryMixin, MemoTrashMixin, MemoIndexMixin, QObject):
    # 동기화할 변경이 생겼음을 알립니다. (저장이 다른 스레드에서 일어나도 타이머는 주 스레드에서 걸리도록 신호로 전달)
    _changes_pending = pyqtSignal()
    # 읽어 둔 메모 파일이 달라져 색인을 다시 써야 함을 알립니다. (동기화 스레드에서도 보내므로 신호로 전달)
    _index_touched = pyqtSignal()
    # 이 PC에서 바뀐 것이 없을 때, 다른 기기의 변경을 확인하는 간격. 확인은 파일 목록 요청 한 번입니다.
    REMOTE_CHECK_SEC = 15 * 60
    # 변경 뒤 동기화까지 기다리는 시간 (환경설정의 sync_interval_index 로 고름)
    PUSH_DELAYS_SEC = [60, 600, 1800, 3600]
    # 메모 변경 기록: 메모마다 보관하는 이전 내용의 개수와, 연달아 저장할 때 기록을 남기는 최소 간격
    HISTORY_KEEP = 20
    HISTORY_MIN_GAP_SEC = 10 * 60
    # 메모의 알림이 바뀌었음을 알립니다. (화면 쪽에서 다음 알림 시각을 다시 잡음)
    reminders_changed = pyqtSignal()
    # 동기화 한 바퀴가 (성공이든 실패든) 끝났음을 알립니다.
    sync_cycle_finished = pyqtSignal()
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
        # 처리하지 못한 오류가 나면 동기화 스크립트를 통해 보고 메일을 보낼지
        "error_report": True,
        # 알림 창을 띄울 자리: 모니터 이름(비어 있으면 주 모니터)과 모서리
        "reminder_popup_screen": "",
        "reminder_popup_corner": "bottom_right",
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
        # 메모 파일을 읽어 둔 것. {파일 이름: ((수정시각, 크기), 파일 내용)}
        # 메모 목록은 저장할 때마다, 탐색기를 다시 그릴 때마다 필요하므로, 바뀌지 않은 파일은 다시 열지 않습니다.
        # 암호 메모는 파일에 든 암호문 그대로 들어 있습니다. (푼 내용은 여기에 두지 않음)
        # 이것을 파일 하나(로컬 색인)로 간직해 두어, 앱을 켤 때도 바뀐 파일만 읽습니다. → core/memo_index.py
        self._file_cache: Dict[str, Tuple[Tuple[int, int], Any]] = {}
        self._index_dirty = False
        self._index_write_lock = threading.Lock()
        self._index_timer = QTimer()
        self._index_timer.setSingleShot(True)
        self._index_timer.timeout.connect(self._save_index_in_background)
        self._index_touched.connect(self._arm_index_timer)
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
        self._load_index()
        # 메모 id → 알림. 알림 시각을 확인할 때마다 모든 메모 파일을 읽지 않도록 메모리에 모아 둡니다.
        self.reminders: Dict[str, Dict[str, Any]] = {}
        self._reminders_loaded = False

        self.drive_api.set_web_app_url(self.settings.get("drive_folder_id", ""))
        self._apply_access_token()
        self.sync_timer = QTimer()
        self.setup_timer()

        QTimer.singleShot(3000, self._startup_sync)

        # 휴지통 보관 기간이 지난 메모 정리 (시작 직후 1회 + 6시간마다)
        self._purge_timer = QTimer()
        self._purge_timer.timeout.connect(self.purge_trash)
        self._purge_timer.start(6 * 60 * 60 * 1000)
        QTimer.singleShot(5000, self.purge_trash)


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
            previous_folder = self.local_path
            self.local_path = Path(self.settings.get("local_memo_path", str(self.base_path / "memos")))
            if self.local_path != previous_folder:
                # 메모 폴더를 바꿨으면, 예전 폴더의 파일을 읽어 둔 것은 쓸 수 없습니다.
                with MEMO_IO_LOCK:
                    self._file_cache.clear()
                self._index_changed()
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
        if not self.settings.get("use_sync", False):
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
        if self.settings.get("use_sync", False) and not self._push_timer.isActive():
            self._push_timer.start(self.push_delay_sec() * 1000)

    def _sync_changes(self) -> None:
        self._start_sync()

    def check_remote(self) -> None:
        """다른 기기에서 바뀐 것이 있는지 확인합니다. 이 PC의 메모 파일은 바뀐 것만 읽습니다."""
        self._start_sync()

    def check_remote_if_stale(self, max_age_sec: int = 60) -> None:
        """마지막 동기화가 오래됐으면 다른 기기의 변경을 확인합니다. (탐색기를 열 때 등)"""
        if not self.settings.get("use_sync", False):
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

        # 폴더를 한 번만 훑습니다. 훑으면서 얻은 수정시각·크기가 지난번과 같은 파일은 읽어 둔 내용을 씁니다.
        try:
            with os.scandir(self.local_path) as listing:
                entries = [e for e in listing if e.name.endswith(".json") and e.is_file()]
            in_trash = set(os.listdir(self.trash_path)) if self.trash_path.exists() else set()
        except OSError as e:
            self.log_error(f"메모 폴더를 읽지 못함: {e}", e)
            return memos
        listed = set()
        cache_changed = False
        for entry in entries:
            # 메모가 많을 때 이 반복이 가장 자주 도는 곳이라, 경로 객체를 만들지 않고 이름(글자)만으로 다룹니다.
            if "trash_bin" in entry.path:
                continue
            listed.add(entry.name)
            try:
                status = entry.stat()
                stamp = (status.st_mtime_ns, status.st_size)
                kept = self._file_cache.get(entry.name)
                if kept is not None and kept[0] == stamp:
                    raw = kept[1]
                else:
                    with open(entry.path, "r", encoding="utf-8") as file:
                        raw = json.load(file)
                    self._file_cache[entry.name] = (stamp, raw)
                    cache_changed = True
                # 돌려주는 메모는 부르는 쪽이 고쳐 쓰므로, 읽어 둔 것과 따로인 사본을 줍니다.
                m = self._own_copy(raw)

                if isinstance(m, dict):
                    memo_id = m.get('id')
                    if not memo_id or len(memo_id) < 8:
                        memo_id = str(uuid.uuid4())
                        m['id'] = memo_id

                    if memo_id in seen_ids:
                        continue

                    # 휴지통에 동일 ID나 파일명이 이미 존재하는 경우 (삭제 후 잔존한 껍데기 파일 자동 삭제)
                    if entry.name in in_trash or f"{memo_id}.json" in in_trash:
                        try:
                            self._file_cache.pop(entry.name, None)
                            os.unlink(entry.path)
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
                            os.unlink(entry.path)
                        except Exception:
                            pass
                        continue

                    memos.append(m)
                    self._note_reminder(memo_id, m.get('reminder'), quiet=True)

                    if entry.name != f"{memo_id}.json":
                        # 구버전 파일명: 원본 바이트를 그대로 옮겨 암호문이 훼손되지 않게 합니다.
                        expected_file = self.local_path / f"{memo_id}.json"
                        try:
                            if not expected_file.exists():
                                shutil.move(entry.path, str(expected_file))
                            else:
                                os.unlink(entry.path)
                        except Exception as e:
                            self.log_error(f"구버전 레거시 메모 파일 정리 실패 ({entry.name}): {e}", e)
                    if needs_rewrite:
                        self.save_memo_locally(m)
            except Exception as e:
                self.log_error(f"로컬 메모 파일 읽기 에러 ({entry.name}): {e}", e)

        for name in [n for n in self._file_cache if n not in listed]:
            self._file_cache.pop(name, None)                 # 없어진 파일은 읽어 둔 것도 버림
            cache_changed = True
        if cache_changed:
            self._index_changed()

        # 사라진 메모(삭제·다른 기기에서 지움)의 알림은 목록에서 뺍니다.
        gone = set(self.reminders) - seen_ids
        for memo_id in gone:
            self.reminders.pop(memo_id, None)
        first_load, self._reminders_loaded = not self._reminders_loaded, True
        if gone or first_load:
            self.reminders_changed.emit()
        return memos

    @staticmethod
    def _own_copy(raw: Any) -> Any:
        """읽어 둔 파일 내용의 사본. (글자·숫자는 바뀌지 않는 값이라 그대로 두고, 그 밖의 것만 새로 만듦)"""
        if not isinstance(raw, dict):
            return raw
        return {k: v if isinstance(v, (str, int, float, bool, type(None))) else copy.deepcopy(v) for k, v in raw.items()}

    def forget_cached_file(self, memo_id: str) -> None:
        """이 메모의 파일을 방금 고쳐 썼거나 치웠으니, 읽어 둔 내용을 버리고 다음에 다시 읽게 합니다.

        색인 파일에도 예전 내용이 들어 있으므로 다시 쓰도록 표시합니다. (늦어도 앱을 끝낼 때는 쓰임)
        """
        if self._file_cache.pop(f"{memo_id}.json", None) is not None:
            self._index_changed()

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
        """메모에 알림을 걸거나(reminder) 풉니다(None).

        알림은 이 PC에만 두는 값입니다. (sync_worker.DEVICE_ONLY_KEYS) 본문이나 속성을 고친 것이 아니므로
        수정일시도, 다른 기기에 전하는 속성 변경 시각(meta_updated_at)도 건드리지 않아 동기화가 일어나지 않습니다.
        """
        normal = reminders.normalize(reminder) if reminder else None
        if normal is None:
            memo.pop('reminder', None)
        else:
            memo['reminder'] = normal
        saved = self.save_memo_locally(memo)
        if not saved and memo.get('id'):
            # 저장하지 못했더라도 메모리의 알림 목록은 넘겨 둡니다.
            # (안 그러면 방금 울린 알림이 '시각이 지난 알림'으로 남아 끝없이 다시 울림)
            self._note_reminder(memo['id'], normal)
        return saved


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
            if self.is_blank_draft(data):
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
                self.forget_cached_file(memo_id)
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
        """제목을 바꿔 저장합니다. 저장하지 못했으면 제목을 되돌리고 False."""
        data['title'] = nt
        try:
            # 아직 파일로 남기지 않는 빈 초안은 저장할 것이 없으므로 제목만 바꿔 둡니다.
            if self.save_memo_locally(data) or self.is_blank_draft(data):
                return True
        except Exception as e:
            self.log_error(f"메모 제목 변경 실패 ({ot} -> {nt}): {e}", e)
        data['title'] = ot
        return False

    @staticmethod
    def is_blank_draft(data: Dict[str, Any]) -> bool:
        """내용 없이 열어만 둔 새 메모인지. (이런 메모는 파일로 남기지 않음)"""
        if data.get('_locked') or data.get('_unreadable') or data.get('is_locked'):
            return False
        return bool(data.get('is_draft')) and not data.get('is_manually_saved') \
            and not clean_plain_text(str(data.get('content', '')))


    def delete_memos_cloud(self, ids: List[str]) -> None:
        self.add_pending_deletes(ids)
        if not self.settings.get("use_sync", False): return
        if self._sync_running:
            self._resync_requested = True
        else:
            self._start_sync()

    def sync_all(self) -> None:
        """지금 바로 전부 동기화합니다. (동기화 버튼·트레이 메뉴·앱 시작 직후) 모든 메모를 훑어 빠진 것이 없게 합니다."""
        if not self.settings.get("use_sync", False):
            self.on_sync_finished(True, "로컬 모드로 작동 중입니다. (동기화 OFF)")
            return
        self._full_scan_pending = True
        self._announce_next_sync = True
        if self._sync_running:
            self._resync_requested = True
        else:
            self._start_sync()

    def _startup_sync(self) -> None:
        """앱을 켠 직후의 동기화. 모든 메모를 훑되, 바뀐 것이 없거나 드라이브에 닿지 못했으면 알리지 않습니다.

        (인터넷 없이 PC를 켤 때마다 연결 실패 경고가 뜨지 않게)
        """
        self._full_scan_pending = True
        self._start_sync()

    def startup_sync_expected(self) -> bool:
        """앱을 켠 직후의 동기화가 돌 예정인지. (동기화를 쓰고 주소도 넣어 둔 경우)"""
        return bool(self.settings.get("use_sync", False)) and bool(self.drive_api.is_available())

    def _start_sync(self) -> None:
        if not self.settings.get("use_sync", False):
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
        self.sync_cycle_finished.emit()

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
            self.load_local_memos()         # 내려받아 새로 생기거나 바뀐 메모를 읽어 둠
        if memo_ids and self.ui_manager:
            self.ui_manager.reload_pulled_memos(memo_ids)

    def on_memos_removed(self, memo_ids: List[str]) -> None:
        """다른 기기에서 삭제되어 로컬 휴지통으로 옮겨진 메모의 창을 닫습니다."""
        for memo_id in memo_ids:
            self.forget_deleted(memo_id)
            if self.ui_manager:
                self.ui_manager.close_memo_window_by_id(memo_id, is_deleting=True)
        if memo_ids and self._trash_retention_days() < 0:
            self.purge_trash()                  # 휴지통을 거치지 않고 바로 지우는 설정

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

    def on_sync_finished(self, success: bool, message: str, outcome: str = SYNC_NOT_DONE) -> None:
        """동기화가 끝났음을 화면 쪽에 알립니다. 어떻게 보여 줄지(토스트·트레이 알림·목록 새로 고침)는 화면 쪽이 정합니다."""
        if not message:
            return
        print(f"[동기화 로그] 성공: {success}, 내용: {message}")
        # 뒤에서 조용히 돈 확인에서 바뀐 것이 없었다면 알리지 않습니다.
        quiet = getattr(self, "_last_sync_quiet", False)
        if success and outcome == SYNC_UNCHANGED and quiet:
            return
        # 뒤에서 돈 확인이 드라이브에 닿지 못한 것도 알리지 않습니다. (인터넷이 끊긴 동안 15분마다 경고가 뜨지 않게)
        if outcome == SYNC_OFFLINE and quiet:
            return
        if self.ui_manager:
            completed = success and outcome in (SYNC_CHANGED, SYNC_UNCHANGED)
            self.ui_manager.show_sync_result(success, message, completed)
