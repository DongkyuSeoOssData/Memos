"""이전 내용(변경 기록): 메모를 덮어쓰기 전의 내용을 history_bin 에 남기고, 보여 주고, 되돌립니다.

암호 메모의 기록은 메모와 같은 암호로 잠급니다. 암호를 걸거나 풀 때 이미 남아 있던 기록도 함께 잠그거나 풉니다.
(SyncManager 에 섞어 쓰는 부분)
"""
from utils.text_utils import clean_plain_text
from utils.file_utils import MEMO_IO_LOCK, atomic_write_json, is_safe_memo_id
import json
from datetime import datetime
from typing import Any, List, Dict, Optional
from pathlib import Path


class MemoHistoryMixin:
    """SyncManager 의 이전 내용 기능."""

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

    def _rewrite_history(self, memo_id: str, convert: Any) -> None:
        """기록의 항목마다 convert(본문) 을 불러, 돌려준 값이 있으면(None 이 아니면) 그 값으로 바꿔 씁니다."""
        try:
            with MEMO_IO_LOCK:
                entries = self._read_history(memo_id)
                changed = False
                for entry in entries:
                    new_content = convert(entry.get("content", ""))
                    if new_content is not None:
                        entry["content"] = new_content
                        entry["is_locked"] = isinstance(new_content, dict)
                        changed = True
                if changed:
                    atomic_write_json(self._history_file(memo_id), entries)
        except Exception as e:
            self.log_error(f"변경 기록 다시 쓰기 실패 ({memo_id}): {e}", e)

    def _seal_history(self, memo_id: str, previous_key: Optional[bytes] = None) -> None:
        """이 메모의 기록을 지금 암호로 잠급니다. (암호 메모의 내용이 기록에 평문으로 남지 않도록)

        평문 기록은 모두 잠그고, previous_key(바꾸기 전의 암호 키)로 열리는 기록은 새 암호로 다시 잠급니다.
        다른 암호로 잠긴 더 오래된 기록은 풀 수 없으므로 그대로 둡니다.
        """
        holder = self._memo_keys.get(memo_id)
        if not holder:
            return
        key, salt = holder

        def convert(content: Any) -> Any:
            if isinstance(content, str):
                return self.crypto.encrypt_locked(content, key, salt)
            if previous_key is not None and self.crypto.is_locked_payload(content):
                try:
                    return self.crypto.encrypt_locked(self.crypto.decrypt_locked(content, previous_key), key, salt)
                except ValueError:
                    return None
            return None

        self._rewrite_history(memo_id, convert)

    def _unseal_history(self, memo_id: str, key: bytes) -> None:
        """암호를 없앤 메모: key 로 열리는 기록을 평문으로 되돌립니다."""
        def convert(content: Any) -> Any:
            if self.crypto.is_locked_payload(content):
                try:
                    return self.crypto.decrypt_locked(content, key)
                except ValueError:
                    return None
            return None

        self._rewrite_history(memo_id, convert)

    def _history_plain(self, memo_id: str, content: Any, password: str = "") -> Optional[str]:
        """기록의 본문을 평문으로. 암호문이면 이 메모를 열 때 쓴 키, 그다음 password 로 풀어 봅니다. 못 풀면 None."""
        if isinstance(content, str):
            return content
        if not self.crypto.is_locked_payload(content):
            return None
        holder = self._memo_keys.get(memo_id)
        keys = [holder[0]] if holder else []
        if password:
            try:
                keys.append(self.crypto.key_for_payload(content, password))
            except Exception:
                pass
        for key in keys:
            try:
                return self.crypto.decrypt_locked(content, key)
            except ValueError:
                continue
        return None

    def read_history_text(self, memo_id: str, index: int, password: str = "") -> Optional[str]:
        """기록(index 번째)의 본문 글자. 암호 메모의 기록은 메모가 열려 있으면 그 키로, 아니면 password 로 풉니다.

        풀 수 없으면 None. 되돌리기 전에 내용을 확인하는 용도이며, 푼 내용이나 키를 어디에도 남기지 않습니다.
        """
        entries = self._read_history(memo_id)
        if not (0 <= index < len(entries)):
            return None
        plain = self._history_plain(memo_id, entries[index].get("content"), password)
        return None if plain is None else clean_plain_text(plain)

    def restore_problem(self, memo_id: str, index: int, password: str = "") -> str:
        """이 기록으로 되돌릴 수 없는 이유. 되돌릴 수 있으면 빈 글자."""
        entries = self._read_history(memo_id)
        if not (0 <= index < len(entries)):
            return "기록을 찾을 수 없습니다."
        current = self._read_raw_content(memo_id)
        if current is None:
            return "메모를 찾을 수 없습니다."
        if self.crypto.is_locked_payload(current) and memo_id not in self._memo_keys:
            return "먼저 메모의 잠금을 푸세요."
        if self._history_plain(memo_id, entries[index].get("content"), password) is None:
            return "이 기록은 다른 암호로 잠겨 있습니다. 그때 쓰던 암호를 넣으세요." if not password else "암호가 일치하지 않습니다."
        return ""

    def restore_history(self, memo_id: str, index: int, password: str = "") -> bool:
        """index 번째 기록의 제목·본문으로 되돌립니다. 지금 내용은 먼저 기록에 남깁니다.

        되돌려도 메모의 잠금 상태와 암호는 지금 그대로입니다. 암호 메모는 되돌린 내용을 지금 암호로 다시 잠가 저장하고,
        일반 메모는 평문으로 저장합니다. (그래서 암호 메모는 잠금을 푼 상태에서만, 다른 암호로 잠긴 기록은 그 암호를 넣어야 되돌릴 수 있음)
        """
        if self.restore_problem(memo_id, index, password):
            return False
        entry = self._read_history(memo_id)[index]
        path = self.local_path / f"{memo_id}.json"
        try:
            with MEMO_IO_LOCK:
                with open(path, "r", encoding="utf-8") as f:
                    current = json.load(f)
                plain = self._history_plain(memo_id, entry.get("content"), password)
                if plain is None:
                    return False
                self._snapshot(memo_id, current, reason="되돌리기 전", force=True)
                current["title"] = entry.get("title", current.get("title", ""))
                if self.crypto.is_locked_payload(current.get("content")):
                    key, salt = self._memo_keys[memo_id]
                    current["content"] = self.crypto.encrypt_locked(plain, key, salt)
                    current["is_locked"] = True
                else:
                    current["content"] = plain
                    current["is_locked"] = False
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
