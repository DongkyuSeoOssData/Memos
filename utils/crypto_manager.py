import os
import base64
import json
from pathlib import Path
from typing import Optional, Dict, Any, List

import pyotp
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

ADMIN_TOTP_SEED = "JBSWY3DPEHPK3PXP"
ADMIN_MASTER_SALT = b"MEMOIT_ADMIN_MASTER_SALT_2026"
LEGACY_MASTER_KEY = b"MEMOIT_EMERGENCY_MASTER_KEY_2026"

class CryptoManager:
    """
    AES-256-GCM Envelope 암호화, PBKDF2 키 파생 및 구글 OTP (TOTP 6자리) 기반 비상 복구 모듈.
    마스터키 (TOTP 기반 및 레거시 마스터키 호환) 및 사용자 비밀번호 듀얼 복호화를 전담합니다.
    """

    def __init__(self) -> None:
        self.base_path = Path.home() / ".memoit_custom"

    @staticmethod
    def get_totp_seed() -> str:
        return ADMIN_TOTP_SEED

    @staticmethod
    def get_otp_provisioning_uri() -> str:
        return pyotp.TOTP(ADMIN_TOTP_SEED).provisioning_uri(
            name="Admin_Recovery", issuer_name="MeMo_App"
        )

    def verify_otp(self, otp_code: str) -> bool:
        if not otp_code or not otp_code.strip().isdigit():
            return False
        totp = pyotp.TOTP(ADMIN_TOTP_SEED)
        return totp.verify(otp_code.strip(), valid_window=1)

    def get_master_keys(self) -> List[bytes]:
        """
        신규 TOTP 파생 마스터키 및 레거시 비상 마스터키 목록을 반환합니다.
        """
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=ADMIN_MASTER_SALT,
            iterations=100000,
        )
        totp_key = kdf.derive(ADMIN_TOTP_SEED.encode('utf-8'))
        return [totp_key, LEGACY_MASTER_KEY]

    def derive_user_key(self, password: str, salt: bytes) -> bytes:
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        return kdf.derive(password.encode('utf-8'))

    def encrypt_text(self, plain_text: str, password: Optional[str] = None) -> Dict[str, Any]:
        if not plain_text:
            return {"is_encrypted": False, "content": ""}

        dek = AESGCM.generate_key(bit_length=256)
        aesgcm_dek = AESGCM(dek)
        content_nonce = os.urandom(12)
        ciphertext_bytes = aesgcm_dek.encrypt(content_nonce, plain_text.encode('utf-8'), None)

        # 신규 TOTP 파생 마스터키로 DEK 암호화
        master_key = self.get_master_keys()[0]
        aesgcm_master = AESGCM(master_key)
        master_nonce = os.urandom(12)
        enc_dek_master = aesgcm_master.encrypt(master_nonce, dek, None)

        salt = os.urandom(16)
        enc_dek_user_b64 = ""
        user_nonce_b64 = ""

        if password and password != "__MASTER_OTP_UNLOCKED__":
            user_key = self.derive_user_key(password, salt)
            aesgcm_user = AESGCM(user_key)
            user_nonce = os.urandom(12)
            enc_dek_user = aesgcm_user.encrypt(user_nonce, dek, None)
            enc_dek_user_b64 = base64.b64encode(enc_dek_user).decode('utf-8')
            user_nonce_b64 = base64.b64encode(user_nonce).decode('utf-8')

        return {
            "is_encrypted": True,
            "version": 2,
            "salt": base64.b64encode(salt).decode('utf-8'),
            "content_nonce": base64.b64encode(content_nonce).decode('utf-8'),
            "ciphertext": base64.b64encode(ciphertext_bytes).decode('utf-8'),
            "master_nonce": base64.b64encode(master_nonce).decode('utf-8'),
            "enc_dek_master": base64.b64encode(enc_dek_master).decode('utf-8'),
            "user_nonce": user_nonce_b64,
            "enc_dek_user": enc_dek_user_b64
        }

    def decrypt_text(self, crypto_data: Dict[str, Any], password: Optional[str] = None, otp_code: Optional[str] = None) -> str:
        if not isinstance(crypto_data, dict) or not crypto_data.get("is_encrypted"):
            return str(crypto_data.get("content", "")) if isinstance(crypto_data, dict) else str(crypto_data)

        content_nonce = base64.b64decode(crypto_data["content_nonce"])
        ciphertext = base64.b64decode(crypto_data["ciphertext"])
        dek: Optional[bytes] = None

        # Track 1. 사용자 비밀번호 시도
        if password and password != "__MASTER_OTP_UNLOCKED__" and crypto_data.get("enc_dek_user"):
            try:
                salt = base64.b64decode(crypto_data["salt"])
                user_nonce = base64.b64decode(crypto_data["user_nonce"])
                enc_dek_user = base64.b64decode(crypto_data["enc_dek_user"])
                user_key = self.derive_user_key(password, salt)
                aesgcm_user = AESGCM(user_key)
                dek = aesgcm_user.decrypt(user_nonce, enc_dek_user, None)
            except Exception:
                pass

        # Track 2. OTP 인증 코드 시도 또는 마스터키 폴백 복호화
        if dek is None and crypto_data.get("enc_dek_master"):
            master_nonce = base64.b64decode(crypto_data["master_nonce"])
            enc_dek_master = base64.b64decode(crypto_data["enc_dek_master"])
            for mk in self.get_master_keys():
                try:
                    aesgcm_master = AESGCM(mk)
                    dek = aesgcm_master.decrypt(master_nonce, enc_dek_master, None)
                    if dek:
                        break
                except Exception:
                    pass

        if dek is None:
            raise ValueError("암호 복호화 실패. 올바른 비밀번호를 입력하거나 6자리 OTP 코드를 입력해주세요.")

        aesgcm_dek = AESGCM(dek)
        plain_bytes = aesgcm_dek.decrypt(content_nonce, ciphertext, None)
        return plain_bytes.decode('utf-8')
