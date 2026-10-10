"""콤보박스·숫자칸·슬라이더가 마우스 휠로 값이 바뀌지 않게 막는 도우미."""
from typing import Any

from PyQt6.QtCore import QEvent, QObject, Qt


class WheelGuard(QObject):
    """지나가던 휠에 옵션이 걸려 바뀌는 일을 막습니다. 값은 클릭(또는 키보드)으로만 바꿉니다."""

    def eventFilter(self, obj: Any, event: Any) -> bool:
        if event.type() == QEvent.Type.Wheel:
            event.ignore()      # 처리하지 않은 것으로 두면 부모(스크롤 영역)가 받아 화면이 스크롤됩니다.
            return True
        return False


def guard_wheel(owner: Any, widgets: Any) -> None:
    """widgets 가 휠에 반응하지 않게 합니다. 가드는 owner 가 살아 있는 동안 유지됩니다."""
    guard = getattr(owner, "_wheel_guard", None)
    if guard is None:
        guard = owner._wheel_guard = WheelGuard(owner)
    for widget in widgets:
        widget.setFocusPolicy(Qt.FocusPolicy.StrongFocus)     # 휠로는 포커스도 가져가지 않음
        widget.installEventFilter(guard)
