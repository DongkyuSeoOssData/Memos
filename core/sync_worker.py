import json
import uuid
import hashlib
from datetime import datetime
from typing import Any, List, Dict, Optional
from pathlib import Path
from PyQt6.QtCore import pyqtSignal, QObject
from utils.file_utils import MEMO_IO_LOCK, atomic_write_json


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

    def __init__(self, sync_manager: Any) -> None:
        super().__init__()
        self.sm = sync_manager
        self.target_method: str = ""
        self.titles_to_delete: List[str] = []
        # 메모별 마지막 동기화 지점. {memo_id: {"hash": 로컬 파일 해시, "remote": 원격 수정시각}}
        # "_url" 키에는 이 상태가 어느 GAS 주소 기준인지 기록합니다.
        self.state_path: Path = self.sm.base_path / "sync_state.json"
        self.state: Dict[str, Dict[str, Any]] = {}

    def execute(self) -> None:
        try:
            if self.target_method == "run_sync":
                self.run_sync()
            elif self.target_method == "run_push":
                self.run_push()
            elif self.target_method == "run_pull":
                self.run_pull()
            elif self.target_method == "run_delete_batch":
                self.run_delete_batch(self.titles_to_delete)
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
        url = self.sm.drive_api.web_app_url or ""
        if self.state.get("_url") != url:
            self.state = {"_url": url}

    def _save_state(self) -> None:
        try:
            atomic_write_json(self.state_path, self.state)
        except Exception as e:
            self.sm.log_error(f"동기화 상태 저장 실패: {e}", e)

    def _read_local(self, path: Path) -> Optional[tuple]:
        """(메모 dict, 파일 해시)를 반환합니다. 읽을 수 없으면 None."""
        try:
            with MEMO_IO_LOCK:
                raw = path.read_bytes()
            memo = json.loads(raw.decode("utf-8"))
            if isinstance(memo, dict):
                return memo, hashlib.sha1(raw).hexdigest()
        except Exception as e:
            self.sm.log_error(f"동기화 파일 읽기 실패 ({path.name}): {e}", e)
        return None

    def _write_local(self, memo_id: str, memo: Dict[str, Any]) -> str:
        path = self.sm.local_path / f"{memo_id}.json"
        with MEMO_IO_LOCK:
            atomic_write_json(path, memo)
            return hashlib.sha1(path.read_bytes()).hexdigest()

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
        pulled = self._pull()
        pushed = self._push()
        self._save_state()
        if pulled or pushed:
            self.finished.emit(True, f"동기화 완료 (가져오기 {pulled}개 / 업로드 {pushed}개)")
        else:
            self.finished.emit(True, "동기화 완료 (변경사항 없음)")

    def run_push(self) -> None:
        if not self._check_available():
            return
        self._load_state()
        count = self._push()
        self._save_state()
        if count > 0:
            self.finished.emit(True, f"{count}개의 암호화된 메모 업로드 완료")
        else:
            self.finished.emit(True, "업로드 완료 (변경사항 없음)")

    def run_pull(self) -> None:
        if not self._check_available():
            return
        self._load_state()
        count = self._pull()
        self._save_state()
        self.finished.emit(True, f"클라우드에서 {count}개의 메모 가져오기 완료")

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
        """마지막 동기화 이후 파일이 바뀐 메모만 올립니다."""
        count = 0
        for f in list(self.sm.local_path.glob("*.json")):
            if "trash_bin" in str(f):
                continue
            local = self._read_local(f)
            if not local:
                continue
            memo_data, file_hash = local
            memo_id = memo_data.get('id')
            if not memo_id or str(memo_id).startswith("_"):
                continue
            entry = self.state.setdefault(memo_id, {})
            if entry.get("hash") == file_hash:
                continue
            if self.sm.drive_api.upload_file(f"{memo_id}.json", memo_data):
                entry["hash"] = file_hash
                # 업로드로 원격 수정시각이 바뀌었으므로 다음 pull에서 한 번 다시 확인합니다.
                entry.pop("remote", None)
                count += 1
        return count

    def _pull(self) -> int:
        """원격 목록의 수정시각이 지난번과 달라진 파일만 받아, 로컬보다 최신이면 반영합니다."""
        files = self.sm.drive_api.list_files()
        pulled_ids: List[str] = []
        if files is None:
            # 목록 조회 실패: 받을 것도, 삭제로 판단할 것도 없음
            return 0

        pending = set(self.sm.get_pending_deletes())
        remote_ids = {f.get("name", "")[:-5] for f in files if str(f.get("name", "")).endswith(".json")}
        self._apply_remote_deletions(remote_ids, pending)

        for f in files:
            name = f.get("name")
            if not name or not name.endswith(".json"):
                continue
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
            if not isinstance(data_json, dict) or 'id' not in data_json:
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
                        remote_dt = _parse_dt(data_json.get('updated_at', ''))
                        local_dt = _parse_dt(local_memo.get('updated_at', ''))
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

                    entry["hash"] = self._write_local(memo_id, data_json)
                if remote_marker is not None:
                    entry["remote"] = remote_marker
                pulled_ids.append(memo_id)
            except Exception as e:
                self.sm.log_error(f"Pull 처리 중 에러 ({name}): {e}", e)

        if pulled_ids:
            self.pulled.emit(pulled_ids)
        return len(pulled_ids)

    def run_delete_batch(self, ids: List[str]) -> None:
        if not self._check_available():
            return
        self._load_state()
        self.sm.add_pending_deletes(ids)
        self._flush_pending_deletes()
        self._save_state()
        self.finished.emit(True, "")
