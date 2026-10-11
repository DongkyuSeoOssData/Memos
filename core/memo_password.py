"""암호 메모: 암호 걸기·풀기·없애기, 관리자 키로 복구, 잠긴 내용 열기.

암호를 건 메모는 본문이 암호화된 채로 저장됩니다. 풀어 둔 메모의 키는 프로그램이 켜져 있는 동안만 기억합니다.
(SyncManager 에 섞어 쓰는 부분. 설정·파일 경로·키 보관은 SyncManager 의 것)
"""
from utils.file_utils import MEMO_IO_LOCK
import json
from typing import Any, Dict, Optional


class MemoPasswordMixin:
    """SyncManager 의 암호 메모 기능."""

    # ── 암호 메모 ────────────────────────────────────────────────────────────
    def is_memo_unlocked(self, memo_id: str) -> bool:
        return memo_id in self._memo_keys

    def set_memo_password(self, memo: Dict[str, Any], password: str) -> bool:
        """메모에 암호를 겁니다. (이미 잠금 해제된 암호 메모라면 암호 변경)"""
        memo_id = memo.get('id')
        if not memo_id or not password or memo.get('_locked') or memo.get('_unreadable'):
            return False
        previous = self._memo_keys.get(memo_id)             # 암호를 바꾸는 경우: 지금까지 쓰던 키
        before = {k: memo[k] for k in ('is_locked', 'is_draft') if k in memo}
        salt = self.crypto.new_salt()
        self._memo_keys[memo_id] = (self.crypto.derive_key(password, salt), salt)
        memo['is_locked'] = True
        memo['is_draft'] = False
        if not self.save_memo_locally(memo):
            # 파일은 그대로이므로 키와 표시도 되돌립니다. (안 그러면 파일은 예전 암호인데 메모리는 새 암호를 들고 있게 됨)
            if previous:
                self._memo_keys[memo_id] = previous
            else:
                self._memo_keys.pop(memo_id, None)
            for k in ('is_locked', 'is_draft'):
                memo.pop(k, None)
            memo.update(before)
            return False
        # 암호를 걸기 전의 평문(방금 남긴 것 포함)과 예전 암호로 잠긴 기록을 새 암호로 잠급니다.
        self._seal_history(memo_id, previous[0] if previous else None)
        # 로컬 색인에도 걸기 전의 내용이 들어 있으므로, 미루지 않고 지금 다시 씁니다.
        self.save_index_now()
        return True

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
        # 예전 버전이 남긴 평문 기록이나, 다른 기기가 암호를 걸기 전에 이 PC에 남은 평문 기록을 이때 잠급니다.
        self._seal_history(memo_id)
        return plain

    def check_memo_password(self, memo_id: str, password: str) -> bool:
        """password 가 이 메모의 지금 암호인지. (잠금 상태나 보관 중인 키는 바꾸지 않음)"""
        payload = self._read_raw_content(memo_id)
        if not password or not self.crypto.is_locked_payload(payload):
            return False
        try:
            self.crypto.decrypt_locked(payload, self.crypto.key_for_payload(payload, password))
            return True
        except ValueError:
            return False

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
            self._seal_history(memo_id)
        return plain

    def relock_memo(self, memo_id: str) -> None:
        self._memo_keys.pop(memo_id, None)

    def remove_memo_password(self, memo: Dict[str, Any]) -> bool:
        """암호를 없애고 일반 메모로 되돌립니다. 잠금 해제 상태에서만 가능합니다."""
        memo_id = memo.get('id')
        if not memo_id or memo.get('_locked') or memo_id not in self._memo_keys:
            return False
        holder = self._memo_keys.pop(memo_id)
        memo['is_locked'] = False
        if not self.save_memo_locally(memo):
            memo['is_locked'] = True                        # 저장하지 못했으면 여전히 암호 메모입니다.
            self._memo_keys[memo_id] = holder
            return False
        self._unseal_history(memo_id, holder[0])            # 이제 비밀이 아니므로, 이 암호로 잠겨 있던 기록도 풉니다.
        return True

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
