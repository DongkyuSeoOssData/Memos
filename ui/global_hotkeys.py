import sys
import ctypes
import ctypes.wintypes
from typing import Any, Callable, Dict, Optional, Tuple

from PyQt6.QtCore import QAbstractNativeEventFilter, Qt
from PyQt6.QtGui import QKeySequence
from PyQt6.QtWidgets import QApplication

WM_HOTKEY = 0x0312
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

_SPECIAL_KEYS = {
    Qt.Key.Key_Space: 0x20, Qt.Key.Key_Tab: 0x09, Qt.Key.Key_Return: 0x0D, Qt.Key.Key_Enter: 0x0D,
    Qt.Key.Key_Escape: 0x1B, Qt.Key.Key_Backspace: 0x08, Qt.Key.Key_Insert: 0x2D, Qt.Key.Key_Delete: 0x2E,
    Qt.Key.Key_Home: 0x24, Qt.Key.Key_End: 0x23, Qt.Key.Key_PageUp: 0x21, Qt.Key.Key_PageDown: 0x22,
    Qt.Key.Key_Left: 0x25, Qt.Key.Key_Up: 0x26, Qt.Key.Key_Right: 0x27, Qt.Key.Key_Down: 0x28,
}


def parse_shortcut(text: str) -> Optional[Tuple[int, int]]:
    """'Alt+Shift+N' 형태의 단축키를 (Win32 modifiers, virtual-key)로 변환합니다. 지원하지 않으면 None."""
    seq = QKeySequence(text or "")
    if seq.count() != 1:
        return None
    combo = seq[0]
    key = combo.key()
    qt_mods = combo.keyboardModifiers()

    mods = 0
    if qt_mods & Qt.KeyboardModifier.AltModifier:
        mods |= MOD_ALT
    if qt_mods & Qt.KeyboardModifier.ControlModifier:
        mods |= MOD_CONTROL
    if qt_mods & Qt.KeyboardModifier.ShiftModifier:
        mods |= MOD_SHIFT
    if qt_mods & Qt.KeyboardModifier.MetaModifier:
        mods |= MOD_WIN

    code = key.value
    if Qt.Key.Key_A.value <= code <= Qt.Key.Key_Z.value or Qt.Key.Key_0.value <= code <= Qt.Key.Key_9.value:
        vk = code  # 영문자·숫자는 Qt 키 값과 가상 키 코드가 같음
    elif Qt.Key.Key_F1.value <= code <= Qt.Key.Key_F24.value:
        vk = 0x70 + (code - Qt.Key.Key_F1.value)
    elif key in _SPECIAL_KEYS:
        vk = _SPECIAL_KEYS[key]
    else:
        return None
    return mods, vk


class GlobalHotkeys(QAbstractNativeEventFilter):
    """Windows RegisterHotKey 기반 전역 단축키.

    등록된 조합은 이 앱만 받고 다른 프로그램에는 전달되지 않습니다.
    (키보드 전체를 후킹하지 않으므로 다른 입력을 엿보지 않습니다.)
    """

    def __init__(self) -> None:
        super().__init__()
        self._user32 = ctypes.WinDLL("user32", use_last_error=True)
        self._user32.RegisterHotKey.argtypes = [ctypes.wintypes.HWND, ctypes.c_int, ctypes.wintypes.UINT, ctypes.wintypes.UINT]
        self._user32.RegisterHotKey.restype = ctypes.wintypes.BOOL
        self._user32.UnregisterHotKey.argtypes = [ctypes.wintypes.HWND, ctypes.c_int]
        self._user32.UnregisterHotKey.restype = ctypes.wintypes.BOOL
        self._callbacks: Dict[int, Callable[[], None]] = {}
        self._next_id = 1
        app = QApplication.instance()
        if app:
            app.installNativeEventFilter(self)

    def register(self, shortcut: str, callback: Callable[[], None]) -> bool:
        """단축키를 등록합니다. 형식이 잘못됐거나 다른 프로그램이 이미 쓰고 있으면 False."""
        parsed = parse_shortcut(shortcut)
        if not parsed:
            return False
        mods, vk = parsed
        hotkey_id = self._next_id
        if not self._user32.RegisterHotKey(None, hotkey_id, mods | MOD_NOREPEAT, vk):
            return False
        self._next_id += 1
        self._callbacks[hotkey_id] = callback
        return True

    def unregister_all(self) -> None:
        for hotkey_id in list(self._callbacks):
            self._user32.UnregisterHotKey(None, hotkey_id)
        self._callbacks.clear()

    def nativeEventFilter(self, event_type: Any, message: Any) -> Tuple[bool, int]:
        try:
            msg = ctypes.wintypes.MSG.from_address(int(message))
            callback = self._callbacks.get(int(msg.wParam)) if msg.message == WM_HOTKEY else None
        except Exception:
            return False, 0
        if callback is None:
            return False, 0
        try:
            callback()
        except Exception:
            # 단축키로 실행한 동작의 오류도 다른 오류와 같게 기록·보고되도록 넘깁니다. (여기서 삼키면 흔적이 남지 않음)
            sys.excepthook(*sys.exc_info())
        return True, 0
