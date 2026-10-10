"""창이 모니터의 작업 영역(작업 표시줄을 뺀 화면) 밖으로 나가거나 그보다 커지지 않게 하는 도우미."""
from typing import Any, Optional, Tuple

from PyQt6.QtCore import QPoint, QRect
from PyQt6.QtGui import QGuiApplication


def work_area(widget: Any, at: Optional[QPoint] = None) -> Optional[QRect]:
    """at 지점(없으면 창 한가운데)이 놓인 모니터의 작업 영역. 모니터를 알 수 없으면 주 모니터."""
    point = at if at is not None else widget.frameGeometry().center()
    screen = QGuiApplication.screenAt(point) or QGuiApplication.primaryScreen()
    return screen.availableGeometry() if screen else None


def clamp_position(area: QRect, x: int, y: int, width: int, height: int) -> Tuple[int, int]:
    """창(width x height)이 area 안에 온전히 들어오는 위치로 당깁니다. 창이 더 크면 왼쪽·위쪽에 맞춥니다."""
    x = max(area.left(), min(x, area.left() + area.width() - width))
    y = max(area.top(), min(y, area.top() + area.height() - height))
    return x, y


SNAP_DISTANCE = 15      # 가장자리에서 이 거리 안으로 들어오면 붙습니다. (메모 창끼리 붙는 거리와 같음)


def snap_to_edges(area: QRect, x: int, y: int, width: int, height: int, distance: int = SNAP_DISTANCE) -> Tuple[int, int]:
    """창이 작업 영역의 가장자리에 가까우면 그 가장자리에 딱 붙인 위치를 돌려줍니다. (자석 효과)"""
    right, bottom = area.left() + area.width() - width, area.top() + area.height() - height
    if abs(x - area.left()) <= distance:
        x = area.left()
    elif abs(x - right) <= distance:
        x = right
    if abs(y - area.top()) <= distance:
        y = area.top()
    elif abs(y - bottom) <= distance:
        y = bottom
    return x, y


def grown(area: QRect, inset: int) -> QRect:
    """창 둘레에 투명한 여백(inset)이 있는 창을 위한 영역.

    탐색기처럼 눈에 보이는 테두리가 창의 실제 크기보다 안쪽에 있으면, 창 자체는 화면 밖으로 그만큼 나가야
    보이는 테두리가 화면 끝에 닿습니다. 그래서 작업 영역을 여백만큼 넓혀서 계산합니다.
    """
    return area.adjusted(-inset, -inset, inset, inset) if inset else QRect(area)


def drag_position(widget: Any, start_cursor: QPoint, start_pos: QPoint, cursor: QPoint,
                  inset: int = 0, snap: bool = True) -> Tuple[int, int]:
    """창을 끌 때 놓일 위치. 끌기 시작한 지점을 기준으로 계산해, 가장자리에 붙었다가도 자연스럽게 떨어집니다."""
    x = start_pos.x() + cursor.x() - start_cursor.x()
    y = start_pos.y() + cursor.y() - start_cursor.y()
    area = work_area(widget, cursor)
    if area is None:
        return x, y
    area = grown(area, inset)
    if snap:
        x, y = snap_to_edges(area, x, y, widget.width(), widget.height())
    return clamp_position(area, x, y, widget.width(), widget.height())


def keep_inside(widget: Any, at: Optional[QPoint] = None, inset: int = 0) -> None:
    """창을 작업 영역 안으로: 영역보다 크면 줄이고, 밖으로 나가 있으면 안으로 옮깁니다. (최대화 상태에서는 건드리지 않음)"""
    if widget.isMaximized() or widget.isFullScreen():
        return
    area = work_area(widget, at)
    if area is None:
        return
    area = grown(area, inset)
    frame, inner = widget.frameGeometry(), widget.geometry()
    # 제목 줄·테두리가 있는 창은 그만큼을 뺀 크기까지만 허용합니다.
    extra_w, extra_h = max(0, frame.width() - inner.width()), max(0, frame.height() - inner.height())
    max_w, max_h = max(1, area.width() - extra_w), max(1, area.height() - extra_h)
    if inner.width() > max_w or inner.height() > max_h:
        widget.resize(min(inner.width(), max_w), min(inner.height(), max_h))
        frame, inner = widget.frameGeometry(), widget.geometry()
    x, y = clamp_position(area, frame.x(), frame.y(), frame.width(), frame.height())
    if (x, y) != (frame.x(), frame.y()):
        widget.move(x, y)


def max_inner_size(widget: Any, at: Optional[QPoint] = None, inset: int = 0) -> Optional[Tuple[int, int]]:
    """이 창이 가질 수 있는 가장 큰 크기(작업 영역에서 제목 줄·테두리를 뺀 크기)."""
    area = work_area(widget, at)
    if area is None:
        return None
    area = grown(area, inset)
    frame, inner = widget.frameGeometry(), widget.geometry()
    return (max(1, area.width() - max(0, frame.width() - inner.width())),
            max(1, area.height() - max(0, frame.height() - inner.height())))
