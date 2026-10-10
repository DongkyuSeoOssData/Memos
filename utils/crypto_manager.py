import os
import base64
import hashlib
from typing import Optional, Dict, Any, List

from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes, serialization

from core.master_public_key import MASTER_PUBLIC_KEY_PEM

# 3: 암호에서 유도한 키로 본문을 직접 암호화 (구형)
# 4: 본문은 임의의 DEK로 암호화하고, DEK를 [암호 키] + [관리자 공개키]로 각각 감싸 둠
MEMO_LOCK_VERSIONS = (3, 4)
MEMO_LOCK_ITERATIONS = 600000

# ── 구버전(v2) 호환 전용 ──────────────────────────────────────────────────────
# v2.0.x 까지는 모든 메모를 아래 상수에서 유도한 마스터키로도 암호화했습니다.
# 지금은 새로 암호화하는 데 쓰지 않으며, 예전 파일을 평문으로 되돌리는 변환에만 사용합니다.
_LEGACY_TOTP_SEED = "JBSWY3DPEHPK3PXP"
_LEGACY_MASTER_SALT = b"MEMOIT_ADMIN_MASTER_SALT_2026"
_LEGACY_MASTER_KEY = b"MEMOIT_EMERGENCY_MASTER_KEY_2026"

_OAEP = padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode('utf-8')


class CryptoManager:
    """
    암호 메모 전용 AES-256-GCM 암복호화 모듈.

    메모마다 설정한 비밀번호에서 PBKDF2로 키를 유도하여 그 메모의 본문만 암호화합니다.
    관리자 공개키(core/master_public_key.py)가 설정되어 있으면 본문 키를 그 공개키로도 감싸 두어,
    짝이 되는 개인키를 가진 관리자가 암호 없이 복구할 수 있습니다. 공개키로는 복호화할 수 없으므로
    공개키가 저장소에 공개되어도 메모는 열리지 않습니다.
    """

    def __init__(self, master_public_key_pem: Optional[str] = None) -> None:
        pem = MASTER_PUBLIC_KEY_PEM if master_public_key_pem is None else master_public_key_pem
        self._master_public_key: Any = None
        self.master_key_id: str = ""
        if pem and pem.strip():
            try:
                self._master_public_key = serialization.load_pem_public_key(pem.strip().encode('utf-8'))
                der = self._master_public_key.public_bytes(
                    serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
                self.master_key_id = hashlib.sha256(der).hexdigest()[:16]
            except Exception as e:
                print(f"Master public key load error: {e}")

    @property
    def master_enabled(self) -> bool:
        return self._master_public_key is not None

    @staticmethod
    def new_salt() -> bytes:
        return os.urandom(16)

    @staticmethod
    def derive_key(password: str, salt: bytes, iterations: Optional[int] = None) -> bytes:
        kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=iterations or MEMO_LOCK_ITERATIONS)
        return kdf.derive(password.encode('utf-8'))

    @staticmethod
    def is_locked_payload(content: Any) -> bool:
        return isinstance(content, dict) and bool(content.get("is_encrypted")) and content.get("version") in MEMO_LOCK_VERSIONS

    @staticmethod
    def is_legacy_payload(content: Any) -> bool:
        return isinstance(content, dict) and bool(content.get("is_encrypted")) and content.get("version") not in MEMO_LOCK_VERSIONS

    @staticmethod
    def has_master_recovery(content: Any) -> bool:
        return isinstance(content, dict) and bool(content.get("enc_dek_master"))

    @staticmethod
    def payload_salt(payload: Dict[str, Any]) -> bytes:
        return base64.b64decode(payload["salt"])

    def key_for_payload(self, payload: Dict[str, Any], password: str) -> bytes:
        return self.derive_key(password, self.payload_salt(payload), int(payload.get("iterations", MEMO_LOCK_ITERATIONS)))

    def encrypt_locked(self, plain_text: str, key: bytes, salt: bytes) -> Dict[str, Any]:
        """본문을 새 DEK로 암호화하고, DEK를 암호 키(와 관리자 공개키)로 감쌉니다."""
        dek = AESGCM.generate_key(bit_length=256)
        nonce, user_nonce = os.urandom(12), os.urandom(12)
        payload = {
            "is_encrypted": True,
            "version": 4,
            "iterations": MEMO_LOCK_ITERATIONS,
            "salt": _b64(salt),
            "nonce": _b64(nonce),
            "ciphertext": _b64(AESGCM(dek).encrypt(nonce, plain_text.encode('utf-8'), None)),
            "user_nonce": _b64(user_nonce),
            "enc_dek_user": _b64(AESGCM(key).encrypt(user_nonce, dek, None)),
            "enc_dek_master": "",
            "master_key_id": "",
        }
        if self._master_public_key is not None:
            payload["enc_dek_master"] = _b64(self._master_public_key.encrypt(dek, _OAEP))
            payload["master_key_id"] = self.master_key_id
        return payload

    def _decrypt_body(self, payload: Dict[str, Any], dek: bytes) -> str:
        return AESGCM(dek).decrypt(base64.b64decode(payload["nonce"]), base64.b64decode(payload["ciphertext"]), None).decode('utf-8')

    def decrypt_locked(self, payload: Dict[str, Any], key: bytes) -> str:
        """암호에서 유도한 키로 복호화합니다. 키가 맞지 않으면 ValueError."""
        try:
            if payload.get("version") == 3:
                return self._decrypt_body(payload, key)
            dek = AESGCM(key).decrypt(base64.b64decode(payload["user_nonce"]), base64.b64decode(payload["enc_dek_user"]), None)
            return self._decrypt_body(payload, dek)
        except Exception as e:
            raise ValueError("암호가 일치하지 않습니다.") from e

    def recover_with_private_key(self, payload: Dict[str, Any], private_key_pem: bytes, passphrase: Optional[str] = None) -> str:
        """관리자 개인키로 본문을 복구합니다. 실패하면 ValueError(사유)."""
        if not self.has_master_recovery(payload):
            raise ValueError("이 메모에는 관리자 복구 정보가 들어 있지 않습니다.")
        try:
            private_key = serialization.load_pem_private_key(
                private_key_pem, password=passphrase.encode('utf-8') if passphrase else None)
        except Exception as e:
            raise ValueError("개인키 파일을 열 수 없습니다. (파일 또는 개인키 암호 확인)") from e
        try:
            dek = private_key.decrypt(base64.b64decode(payload["enc_dek_master"]), _OAEP)
            return self._decrypt_body(payload, dek)
        except Exception as e:
            raise ValueError("이 개인키로는 복구할 수 없습니다. (다른 관리자 키로 잠긴 메모)") from e

    # ── 구버전(v2) 파일 변환 ─────────────────────────────────────────────────
    def _legacy_master_keys(self) -> List[bytes]:
        if not hasattr(self, "_legacy_keys"):
            self._legacy_keys = [
                self.derive_key(_LEGACY_TOTP_SEED, _LEGACY_MASTER_SALT, 100000),
                _LEGACY_MASTER_KEY,
            ]
        return self._legacy_keys

    def decrypt_legacy(self, crypto_data: Dict[str, Any]) -> str:
        """v2 형식(마스터키 봉투 암호화) 본문을 평문으로 되돌립니다. 실패하면 ValueError."""
        try:
            content_nonce = base64.b64decode(crypto_data["content_nonce"])
            ciphertext = base64.b64decode(crypto_data["ciphertext"])
            master_nonce = base64.b64decode(crypto_data["master_nonce"])
            enc_dek_master = base64.b64decode(crypto_data["enc_dek_master"])
        except Exception as e:
            raise ValueError("구버전 암호문 형식이 올바르지 않습니다.") from e

        dek: Optional[bytes] = None
        for mk in self._legacy_master_keys():
            try:
                dek = AESGCM(mk).decrypt(master_nonce, enc_dek_master, None)
                break
            except Exception:
                continue
        if dek is None:
            raise ValueError("구버전 암호문을 복호화할 수 없습니다.")
        try:
            return AESGCM(dek).decrypt(content_nonce, ciphertext, None).decode('utf-8')
        except Exception as e:
            raise ValueError("구버전 암호문을 복호화할 수 없습니다.") from e
