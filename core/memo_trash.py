"""휴지통: 지운 메모 보관·복원·비우기, 보관 기간이 지난 메모 정리, 드라이브에서 지울 메모의 대기열.

(SyncManager 에 섞어 쓰는 부분)
"""
from utils.file_utils import MEMO_IO_LOCK, atomic_write_json
import json
import shutil
from datetime import datetime, timedelta
from typing import Any, List, Dict, Optional
from pathlib import Path


class MemoTrashMixin:
    """SyncManager 의 휴지통 기능."""

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
                self.forget_cached_file(memo_id)
                src.unlink()
                self.remove_pending_delete(memo_id)
            self.mark_dirty(memo_id)
            return True
        except Exception as e:
            self.log_error(f"로컬 메모 복구 실패 ({memo_id}): {e}", e)
        return False

    def move_to_trash(self, memo_id: str) -> None:
        """메모 파일을 휴지통으로 옮깁니다. 파일만 다루므로 동기화 스레드에서 불러도 됩니다."""
        with MEMO_IO_LOCK:
            self._delete_memo_locally(memo_id)
            self._stamp_deleted(self.trash_path / f"{memo_id}.json")

    def forget_deleted(self, memo_id: str) -> None:
        """지운 메모의 암호 키와 알림을 메모리에서 뺍니다. (주 스레드에서만 부름)"""
        self.relock_memo(memo_id)
        self._note_reminder(memo_id, None)

    def delete_memo_locally(self, memo_id: str, title: Optional[str] = None) -> None:
        self.move_to_trash(memo_id)
        self.forget_deleted(memo_id)
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
