"""지금 설정을 화면 부품에 알려 주는 통로.

대화상자·가림막·입력 화면이 앱 색 테마와 사용자의 선택(예: 시간을 24시간제로 볼지)을 따르도록, 앱이 시작할 때
UIManager 가 설정을 돌려주는 함수와 저장하는 함수를 여기에 넣어 둡니다. (부품들이 UIManager 를 직접 알지 않아도 되게)
"""
from typing import Any, Callable, Dict, Optional

_source: Optional[Callable[[], Dict[str, Any]]] = None
_saver: Optional[Callable[[Dict[str, Any]], None]] = None


def use(source: Callable[[], Dict[str, Any]], saver: Optional[Callable[[Dict[str, Any]], None]] = None) -> None:
    global _source, _saver
    _source = source
    _saver = saver


def current() -> Dict[str, Any]:
    return _source() if _source else {}


def save(changes: Dict[str, Any]) -> None:
    """화면 안에서 바꾼 선택(예: 시간을 24시간제로 볼지)을 설정에 기억합니다."""
    if _saver:
        _saver(changes)
