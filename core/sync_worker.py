import json
import uuid
import hashlib
from datetime import datetime
from typing import Any, List, Dict, Optional
from pathlib import Path
from PyQt6.QtCore import pyqtSignal, QObject
from utils.file_utils import MEMO_IO_LOCK, atomic_write_json, is_safe_memo_id
from core import shared_settings


# 이 PC에서만 의미가 있는 값. 드라이브에 올리지 않고, 내려받을 때도 이 PC의 값을 그대로 둡니다.
# (창을 옮기거나 접는 것만으로 업로드가 일어나거나, 다른 PC의 창 배치를 덮어쓰는 일을 막습니다)
DEVICE_ONLY_KEYS = frozenset({"position_x", "position_y", "width", "height", "is_visible", "is_rolled_up"})
DEVICE_ONLY_PREFIXES = ("rolled_", "unrolled_")
# sync_state.json 형식 버전. 2: 해시를 '공유 부분'만으로 계산
STATE_VERSION = 2


def is_device_key(key: Any) -> bool:
    key = str(key)
    return key in DEVICE_ONLY_KEYS or key.startswith(DEVICE_ONLY_PREFIXES)


def shared_part(memo: Dict[str, Any]) -> Dict[str, Any]:
    """기기 간에 공유하는 부분 (본문·제목·색 등)."""
    return {k: v for k, v in memo.items() if not is_device_key(k)}


def device_part(memo: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in memo.items() if is_device_key(k)}


def shared_hash(memo: Dict[str, Any]) -> str:
    """공유하는 부분만의 해시. 창 위치처럼 이 PC에만 속한 값이 바뀌어도 달라지지 않습니다."""
    canonical = json.dumps(shared_part(memo), ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(canonical.encode("utf-8")).hexdigest()


def version_dt(memo: Dict[str, Any]) -> datetime:
    """어느 쪽이 더 최신인지 비교할 때 쓰는 시각.

    updated_at 은 본문·제목을 고친 시각(화면의 '수정일시')이고, meta_updated_at 은 폴더·즐겨찾기처럼
    속성만 바꾼 시각입니다. 속성만 바꿔도 다른 기기에 전해져야 하므로 둘 중 늦은 쪽으로 비교합니다.
    """
    return max(_parse_dt(memo.get('updated_at', '')), _parse_dt(memo.get('meta_updated_at', '')))


def _parse_dt(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value) if value else datetime.min
    except Exception:
        return datetime.min


class SyncWorker(QObject):
    finished = pyqtSignal(bool, str)
    # 원격 내용으로 로컬 파일이 교체된 메모 id 목록 (열려 있는 창 갱신용)
    pulled = pyqtSignal(list)
    # 다른 기기에서 삭제되어 로컬 휴지통으로 옮긴 메모 id 목록
    removed = pyqtSignal(list)
    # 드라이브에 있는 공유 설정이 이 PC 것보다 최신일 때: 받은 내용 그대로
    settings_pulled = pyqtSignal(dict)

    def __init__(self, sync_manager: Any) -> None:
        super().__init__()
        self.sm = sync_manager
        # 메모별 마지막 동기화 지점. {memo_id: {"hash": 공유 부분의 해시, "remote": 원격 수정시각}}
        # "_url" 키에는 이 상태가 어느 GAS 주소 기준인지 기록합니다.
        self.state_path: Path = self.sm.base_path / "sync_state.json"
        self.state: Dict[str, Dict[str, Any]] = {}
        # 올릴 후보. None 이면 모든 메모 파일을 훑고, 집합이면 그 id 의 파일만 읽습니다.
        self.push_ids: Optional[set] = None
        # 올리려 했지만 실패한 메모 id (다음 동기화에서 다시 시도)
        self.unsent_ids: set = set()
        # True 면 바뀐 것이 없을 때 화면에 알리지 않습니다. (뒤에서 도는 확인용)
        self.quiet: bool = False

    def execute(self) -> None:
        try:
            self.run_sync()
        except Exception as e:
            error_msg = f"동기화 치명적 오류: {str(e)}"
            self.sm.log_error(error_msg, e)
            self.finished.emit(False, error_msg)

    # ── 동기화 상태 ──────────────────────────────────────────────────────────
    def _load_state(self) -> None:
        try:
            with open(self.state_path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            self.state = loaded if isinstance(loaded, dict) else {}
        except Exception:
            self.state = {}
        # 동기화 대상 드라이브가 바뀌면 이전 기록은 의미가 없습니다. (새 드라이브에 없다고 삭제로 오인하면 안 됨)
        # 기록 형식이 바뀐 경우(해시 계산 방식 변경)에도 처음부터 다시 맞춥니다. 그동안은 삭제 반영만 한 번 쉬어 갑니다.
        url = self.sm.drive_api.web_app_url or ""
        if self.state.get("_url") != url or self.state.get("_v") != STATE_VERSION:
            self.state = {"_url": url, "_v": STATE_VERSION}

    def _save_state(self) -> None:
        try:
            atomic_write_json(self.state_path, self.state)
        except Exception as e:
            self.sm.log_error(f"동기화 상태 저장 실패: {e}", e)

    def _read_local(self, path: Path) -> Optional[tuple]:
        """(메모 dict, 공유 부분의 해시)를 반환합니다. 읽을 수 없으면 None."""
        try:
            with MEMO_IO_LOCK:
                raw = path.read_bytes()
            memo = json.loads(raw.decode("utf-8"))
            if isinstance(memo, dict):
                return memo, shared_hash(memo)
        except Exception as e:
            self.sm.log_error(f"동기화 파일 읽기 실패 ({path.name}): {e}", e)
        return None

    def _write_local(self, memo_id: str, memo: Dict[str, Any]) -> str:
        path = self.sm.local_path / f"{memo_id}.json"
        with MEMO_IO_LOCK:
            atomic_write_json(path, memo)
        return shared_hash(memo)

    def _same_content(self, a: Dict[str, Any], b: Dict[str, Any]) -> bool:
        return a.get("content") == b.get("content")

    def _keep_conflict_copy(self, local_memo: Dict[str, Any]) -> None:
        """양쪽에서 모두 수정된 메모는 로컬본을 별도 메모로 남겨 덮어쓰기로 사라지지 않게 합니다."""
        copy_memo = dict(local_memo)
        copy_memo["id"] = str(uuid.uuid4())
        copy_memo["title"] = f"{local_memo.get('title', '')} (충돌 사본)"
        copy_memo["is_visible"] = False
        self._write_local(copy_memo["id"], copy_memo)

    # ── 실행 단위 ────────────────────────────────────────────────────────────
    def run_sync(self) -> None:
        if not self._check_available():
            return
        self._load_state()
        self._flush_pending_deletes()
        files = self.sm.drive_api.list_files()
        pulled = self._pull(files)
        pushed = self._push()
        self._sync_settings(files)
        self._save_state()
        if pulled or pushed:
            self.finished.emit(True, f"동기화 완료 (가져오기 {pulled}개 / 업로드 {pushed}개)")
        else:
            self.finished.emit(True, "동기화 완료 (변경사항 없음)")

    def _check_available(self) -> bool:
        if not self.sm.drive_api.is_available():
            self.finished.emit(False, "환경설정에서 GAS URL을 먼저 입력해주세요.")
            return False
        return True

    def _flush_pending_deletes(self) -> None:
        """로컬에서 지운 메모를 드라이브 휴지통으로 옮깁니다. 실패한 것은 대기열에 남아 다음 주기에 재시도됩니다."""
        for memo_id in self.sm.get_pending_deletes():
            if self.sm.drive_api.delete_file(f"{memo_id}.json"):
                self.sm.remove_pending_delete(memo_id)
                self.state.pop(memo_id, None)

    def _apply_remote_deletions(self, remote_ids: set, pending: set) -> None:
        """이전에 동기화했던 메모가 원격 목록에서 사라졌으면 다른 기기에서 삭제된 것이므로 로컬 휴지통으로 옮깁니다."""
        candidates: List[str] = []
        local_count = 0
        for f in list(self.sm.local_path.glob("*.json")):
            if "trash_bin" not in str(f):
                local_count += 1
        for memo_id, entry in list(self.state.items()):
            if memo_id.startswith("_") or memo_id in remote_ids or memo_id in pending:
                continue
            if not isinstance(entry, dict) or not entry.get("hash"):
                # 원격에도 로컬에도 없는 메모의 기록은 더 볼 일이 없으므로 지웁니다. (기록 파일이 계속 커지는 것 방지)
                if not (self.sm.local_path / f"{memo_id}.json").exists():
                    self.state.pop(memo_id, None)
                continue
            local_file = self.sm.local_path / f"{memo_id}.json"
            local = self._read_local(local_file) if local_file.exists() else None
            if not local or local[1] != entry["hash"]:
                # 로컬에 없거나, 마지막 동기화 이후 이 PC에서 수정됨 → 기록만 지워 새 메모로 다시 올라가게 함
                self.state.pop(memo_id, None)
                continue
            candidates.append(memo_id)

        if not candidates:
            return
        # 안전장치: 한 번에 절반 넘게 사라졌다면 드라이브 쪽 문제일 가능성이 높으므로 건드리지 않습니다.
        if len(candidates) > max(3, local_count // 2):
            self.sm.log_error(f"원격에서 사라진 메모가 {len(candidates)}개로 너무 많아 삭제 반영을 건너뜀")
            return
        for memo_id in candidates:
            self.sm.delete_memo_locally(memo_id)
            self.state.pop(memo_id, None)
        self.removed.emit(candidates)

    def _push(self) -> int:
        """마지막 동기화 이후 파일이 바뀐 메모만 올립니다.

        push_ids 가 주어지면 그 메모 파일만 읽습니다. (바뀐 것이 없는데 모든 파일을 읽고 해시를 내는 낭비를 피함)
        """
        count = 0
        if self.push_ids is None:
            candidates = [f for f in self.sm.local_path.glob("*.json") if "trash_bin" not in str(f)]
        else:
            candidates = [self.sm.local_path / f"{memo_id}.json" for memo_id in sorted(self.push_ids)
                          if is_safe_memo_id(memo_id)]
            candidates = [f for f in candidates if f.exists()]
        for f in candidates:
            local = self._read_local(f)
            if not local:
                continue
            memo_data, file_hash = local
            memo_id = memo_data.get('id')
            if not is_safe_memo_id(memo_id) or memo_id.startswith("_"):
                continue
            entry = self.state.setdefault(memo_id, {})
            if entry.get("hash") == file_hash:
                continue
            if self.sm.drive_api.upload_file(f"{memo_id}.json", shared_part(memo_data)):
                entry["hash"] = file_hash
                # 업로드로 원격 수정시각이 바뀌었으므로 다음 pull에서 한 번 다시 확인합니다.
                entry.pop("remote", None)
                count += 1
            else:
                self.unsent_ids.add(memo_id)
        return count

    def _sync_settings(self, files: Optional[List[Dict[str, Any]]]) -> None:
        """공유 설정 파일(_settings.json)을 주고받습니다. 더 나중에 바꾼 쪽의 설정이 남습니다."""
        if files is None:
            return
        name = shared_settings.SETTINGS_FILE
        listed = next((f for f in files if f.get("name") == name), None)
        entry = self.state.setdefault("_settings", {})
        local_stamp = str(self.sm.settings.get(shared_settings.STAMP_KEY, ""))

        if listed is not None:
            marker = listed.get("updated")
            if marker is None or entry.get("remote") != marker:
                remote = self.sm.drive_api.download_file(name)
                if not isinstance(remote, dict):
                    return                      # 받지 못함: 다음 주기에 다시
                entry["remote"] = marker
                # 내용이 깨진 파일은 없는 것으로 보고, 아래에서 이 PC의 설정으로 다시 올립니다.
                remote_stamp = str(remote.get("updated_at", "")) if shared_settings.from_remote(remote) else ""
                entry["seen"] = remote_stamp
                if remote_stamp > local_stamp:
                    self.settings_pulled.emit(remote)
                    return
            # 드라이브의 것이 이 PC 것과 같거나 더 최신이면 올릴 필요 없음
            if str(entry.get("seen", "")) >= local_stamp:
                return

        if not local_stamp:
            return
        payload = {"updated_at": local_stamp, "settings": shared_settings.shared_subset(self.sm.settings)}
        if self.sm.drive_api.upload_file(name, payload):
            entry["seen"] = local_stamp
            entry.pop("remote", None)           # 올린 뒤 원격 수정시각이 바뀌므로 다음에 한 번 다시 확인

    def _pull(self, files: Optional[List[Dict[str, Any]]]) -> int:
        """원격 목록의 수정시각이 지난번과 달라진 파일만 받아, 로컬보다 최신이면 반영합니다."""
        pulled_ids: List[str] = []
        if files is None:
            # 목록 조회 실패: 받을 것도, 삭제로 판단할 것도 없음
            return 0

        pending = set(self.sm.get_pending_deletes())
        remote_ids = {f.get("name", "")[:-5] for f in files if str(f.get("name", "")).endswith(".json")}
        self._apply_remote_deletions(remote_ids, pending)

        for f in files:
            name = f.get("name")
            if not name or not name.endswith(".json") or name.startswith("_"):
                continue                        # '_'로 시작하는 것은 메모가 아니라 공유 설정 같은 부속 파일
            if name[:-5] in pending:
                # 이 PC에서 지웠지만 아직 드라이브에서 못 지운 메모: 다시 내려받지 않음
                continue
            # 구버전 GAS 스크립트는 updated를 주지 않습니다. 그 경우 매번 내려받아 비교합니다.
            remote_marker = f.get("updated")
            listed_id = name[:-5]
            local_file = self.sm.local_path / f"{listed_id}.json"
            entry = self.state.get(listed_id, {})
            if remote_marker is not None and entry.get("remote") == remote_marker and local_file.exists():
                continue

            data_json = self.sm.drive_api.download_file(name)
            # 받은 id는 파일 이름이 되므로, 경로를 벗어날 수 있는 값이면 버립니다.
            if not isinstance(data_json, dict) or not is_safe_memo_id(data_json.get('id')):
                continue
            try:
                memo_id = data_json['id']
                local_file = self.sm.local_path / f"{memo_id}.json"
                entry = self.state.setdefault(memo_id, {})
                # 비교와 교체 사이에 UI 저장이 끼어들지 않도록 한 구간으로 묶습니다.
                with MEMO_IO_LOCK:
                    local = self._read_local(local_file) if local_file.exists() else None

                    if local:
                        local_memo, local_hash = local
                        remote_dt = version_dt(data_json)
                        local_dt = version_dt(local_memo)
                        if remote_dt <= local_dt:
                            if remote_marker is not None:
                                entry["remote"] = remote_marker
                            if remote_dt == local_dt and not entry.get("hash") and self._same_content(local_memo, data_json):
                                # 같은 판본이 이미 원격에 있으므로 다시 올리지 않습니다.
                                entry["hash"] = local_hash
                            continue
                        locally_changed = bool(entry.get("hash")) and entry["hash"] != local_hash
                        if locally_changed and not self._same_content(local_memo, data_json):
                            self._keep_conflict_copy(local_memo)

                    # 창 위치·크기·표시 여부는 이 PC의 값을 유지합니다. 처음 받는 메모는 숨긴 채로 둡니다.
                    merged = {**shared_part(data_json), **(device_part(local[0]) if local else {"is_visible": False})}
                    entry["hash"] = self._write_local(memo_id, merged)
                if remote_marker is not None:
                    entry["remote"] = remote_marker
                pulled_ids.append(memo_id)
            except Exception as e:
                self.sm.log_error(f"Pull 처리 중 에러 ({name}): {e}", e)

        if pulled_ids:
            self.pulled.emit(pulled_ids)
        return len(pulled_ids)
