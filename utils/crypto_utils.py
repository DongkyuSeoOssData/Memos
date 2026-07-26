import os
import sys
import json
import shutil
import uuid
import winreg
import ctypes
import ctypes.wintypes
import base64
import re
import traceback
import html
from datetime import datetime
from typing import Any, List, Dict, Optional, Tuple
from pathlib import Path
from PyQt6.QtCore import QTimer, QThread, pyqtSignal, QObject
from PyQt6.QtWidgets import QSystemTrayIcon
from crypto_manager import CryptoManager

class DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", ctypes.wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def dpapi_encrypt(plain_text: str) -> str:
    if not plain_text:
        return ""
    try:
        b = plain_text.encode('utf-8')
        ib = DATA_BLOB(len(b), ctypes.cast(ctypes.create_string_buffer(b, len(b)), ctypes.POINTER(ctypes.c_byte)))
        ob = DATA_BLOB()
        if ctypes.windll.crypt32.CryptProtectData(ctypes.byref(ib), "MeMoAppPwd", None, None, None, 0, ctypes.byref(ob)):
            res = ctypes.string_at(ob.pbData, ob.cbData)
            ctypes.windll.kernel32.LocalFree(ob.pbData)
            return base64.b64encode(res).decode('utf-8')
    except Exception as e:
        print(f"DPAPI encrypt error: {e}")
    return ""

def dpapi_decrypt(cipher_b64: str) -> str:
    if not cipher_b64:
        return ""
    try:
        b = base64.b64decode(cipher_b64)
        ib = DATA_BLOB(len(b), ctypes.cast(ctypes.create_string_buffer(b, len(b)), ctypes.POINTER(ctypes.c_byte)))
        ob = DATA_BLOB()
        if ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(ib), None, None, None, None, 0, ctypes.byref(ob)):
            res = ctypes.string_at(ob.pbData, ob.cbData)
            ctypes.windll.kernel32.LocalFree(ob.pbData)
            return res.decode('utf-8')
    except Exception as e:
        print(f"DPAPI decrypt error: {e}")
    return ""

ENG_KEY_MAP = {
    'q': 'ㅂ', 'Q': 'ㅃ', 'w': 'ㅈ', 'W': 'ㅉ', 'e': 'ㄷ', 'E': 'ㄸ', 'r': 'ㄱ', 'R': 'ㄲ', 't': 'ㅅ', 'T': 'ㅆ',
    'y': 'ㅛ', 'u': 'ㅕ', 'i': 'ㅑ', 'o': 'ㅐ', 'O': 'ㅒ', 'p': 'ㅔ', 'P': 'ㅖ', 'a': 'ㅁ', 's': 'ㄴ', 'd': 'ㅇ',
    'f': 'ㄹ', 'g': 'ㅎ', 'h': 'ㅗ', 'j': 'ㅓ', 'k': 'ㅏ', 'l': 'ㅣ', 'z': 'ㅋ', 'x': 'ㅌ', 'c': 'ㅊ', 'v': 'ㅍ',
    'b': 'ㅠ', 'n': 'ㅜ', 'm': 'ㅡ'
}

KOR_KEY_MAP = {v: k for k, v in ENG_KEY_MAP.items()}