import ast
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

def clean_plain_text(content: Any) -> str:
    """HTML 및 Qt 내부 <style>...</style> 태그, 딕셔너리 래퍼를 완전히 제거하고 순수 본문 텍스트만 추출합니다."""
    if not content:
        return ""
    if isinstance(content, dict):
        content = content.get('content', '')
    content_str = str(content)
    if content_str.startswith("{") and "'is_encrypted'" in content_str:
        try:
            d = ast.literal_eval(content_str)
            if isinstance(d, dict) and 'content' in d:
                content_str = str(d['content'])
        except Exception:
            pass
    elif content_str.startswith("{") and '"is_encrypted"' in content_str:
        try:
            d = json.loads(content_str)
            if isinstance(d, dict) and 'content' in d:
                content_str = str(d['content'])
        except Exception:
            pass

    no_style = re.sub(r'<style[^>]*>.*?</style>', '', content_str, flags=re.DOTALL | re.IGNORECASE)
    no_script = re.sub(r'<script[^>]*>.*?</script>', '', no_style, flags=re.DOTALL | re.IGNORECASE)
    plain = re.sub(r'<[^>]+>', '', no_script).strip()
    plain = html.unescape(plain)
    return plain