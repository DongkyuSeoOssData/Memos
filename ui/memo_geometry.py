"""메모 창의 위치와 크기 규칙.

창을 띄우지 않고 숫자만으로 따질 수 있게, 화면(위젯)과 무관한 계산만 모아 둡니다.
메모 창(MemoWindow)은 지금 상태를 넘겨주고 여기서 돌려준 자리에 창을 놓기만 합니다.

규칙
 - 접힌 상태와 펼친 상태의 크기는 서로 따로 기억합니다.
     접힘: rolled_width / rolled_height        펼침: unrolled_width / unrolled_height (width / height 도 같은 값)
   마지막 자리(앱을 다시 켜거나 숨겼다 보일 때 쓰는 자리)도 상태마다 적어 둡니다.
     접힘: rolled_position_x / rolled_position_y        펼침: position_x / position_y
 - 접거나 펼 때(위치 고정이 없으면): 메모의 왼쪽 아래 모서리를 그대로 두고 위·오른쪽으로 커지거나 줄어듭니다.
   위쪽으로 커질 자리가 모니터 밖이면 윗변을 두고 아래로, 오른쪽으로 커질 자리가 모니터 밖이면 오른쪽 변을 두고 왼쪽으로 커집니다.
 - 위치 고정: 펼친 상태와 접은 상태마다 자리를 하나씩 고정해 둘 수 있습니다. (unrolled_pin / rolled_pin)
   고정해 둔 상태로 바뀔 때는 그 자리로 갑니다. 고정할 때의 모니터 배치(그 모니터의 위치와 크기)도 함께 적어 두어,
   모니터가 바뀌었으면(다른 PC, 모니터를 떼거나 해상도를 바꿈) 고정을 쓰지 않고 위의 기본 규칙을 따릅니다.
   이 PC에만 두는 값이라 동기화하지 않습니다. (sync_worker 의 DEVICE_ONLY_PREFIXES: rolled_ / unrolled_)
 - 잠긴 암호 메모는 펼쳤을 때 암호 입력용 크기(LOCKED_SIZE)로 뜹니다. 그 크기는 메모의 크기로 기억하지 않고,
   접을 너비를 정할 때도 메모 본래의 크기를 기준으로 삼습니다.
 - 어느 경우든 마지막에 모니터 안으로 당깁니다.
"""
from typing import Any, Dict, Iterable, Optional, Tuple

LOCKED_SIZE = (340, 290)        # 잠긴 암호 메모를 펼쳤을 때의 크기. 암호 칸이 가운데에 넉넉히 들어가는 크기입니다.
MIN_UNROLLED = (200, 150)       # 이보다 작게 기억된 펼친 크기는 잘못된 값으로 보고 쓰지 않습니다.
FALLBACK_SIZE = 300

Box = Tuple[int, int, int, int]     # (x, y, 너비, 높이)


def clamp(area: Any, x: int, y: int, w: int, h: int) -> Tuple[int, int]:
    """창이 area(모니터의 작업 영역) 밖으로 나가지 않도록 좌표를 당깁니다."""
    if x + w > area.right():
        x = area.right() - w
    if x < area.left():
        x = area.left()
    if y + h > area.bottom():
        y = area.bottom() - h
    if y < area.top():
        y = area.top()
    return x, y


def is_locked_compact(data: Dict[str, Any], rolled: bool) -> bool:
    """잠겨 있어서 암호 입력용 작은 크기로 떠 있는지. (이때의 크기는 메모의 크기로 기억하지 않음)"""
    return bool(data.get('_locked')) and not rolled


def remember(data: Dict[str, Any], rolled: bool, box: Box) -> None:
    """지금 상태(접힘/펼침)의 위치와 크기를 그 상태의 것으로 data 에 기억합니다."""
    x, y, w, h = box
    if rolled:
        data['rolled_position_x'], data['rolled_position_y'] = x, y
        data['rolled_width'], data['rolled_height'] = w, h
        return
    data['position_x'], data['position_y'] = x, y
    if not is_locked_compact(data, rolled):
        data['unrolled_width'] = data['width'] = w
        data['unrolled_height'] = data['height'] = h


def saved_unrolled_size(data: Dict[str, Any], default_height: int = FALLBACK_SIZE) -> Tuple[int, int]:
    """기억해 둔 펼친 크기. (잠겨 있든 아니든 메모 본래의 크기)"""
    width = data.get('unrolled_width', data.get('width', 500))
    height = data.get('unrolled_height', data.get('height', default_height))
    return (width if width >= MIN_UNROLLED[0] else FALLBACK_SIZE), (height if height >= MIN_UNROLLED[1] else FALLBACK_SIZE)


def unrolled_size(data: Dict[str, Any], default_height: int = FALLBACK_SIZE) -> Tuple[int, int]:
    """펼쳤을 때의 크기. 잠긴 메모는 암호를 풀기 전까지 암호 입력용 크기로 뜹니다."""
    return LOCKED_SIZE if data.get('_locked') else saved_unrolled_size(data, default_height)


def own_size(data: Dict[str, Any], rolled: bool, box: Box, default_height: int = FALLBACK_SIZE) -> Tuple[int, int]:
    """자리를 따질 때 기준으로 삼는 지금 창의 크기.

    잠겨서 암호 입력용 크기로 떠 있는 메모는 그 크기가 아니라 메모 본래의 크기로 따집니다.
    (그러지 않으면 잠긴 메모를 처음 접을 때 암호 입력용 너비가 접은 메모의 너비로 굳어 버림)
    """
    return saved_unrolled_size(data, default_height) if is_locked_compact(data, rolled) else (box[2], box[3])


def grow_from_corner(box: Box, size: Tuple[int, int], area: Any) -> Tuple[int, int]:
    """box 자리의 창을 size 로 바꿀 때의 새 왼쪽 위 좌표. (위치 고정이 없을 때의 기본 규칙)

    왼쪽 아래 모서리를 그대로 두고 위·오른쪽으로 커지거나 줄어듭니다. 위로 커질 자리가 모니터 밖이면 윗변을 두고 아래로,
    오른쪽으로 커질 자리가 모니터 밖이면 오른쪽 변을 두고 왼쪽으로 커집니다. 그래도 넘치면 모니터 안으로 당깁니다.
    """
    x, y, w, h = box
    new_w, new_h = size
    new_x, new_y = x, y + h - new_h
    if new_y < area.top():
        new_y = y
    if new_x + new_w - 1 > area.right():
        new_x = x + w - new_w
    return clamp(area, new_x, new_y, new_w, new_h)


# ── 위치 고정 ──────────────────────────────────────────────────────────────────
def pin_key(rolled: bool) -> str:
    return 'rolled_pin' if rolled else 'unrolled_pin'


def has_pin(data: Dict[str, Any], rolled: bool) -> bool:
    return isinstance(data.get(pin_key(rolled)), dict)


def set_pin(data: Dict[str, Any], rolled: bool, xy: Tuple[int, int], screen: Box) -> None:
    """지금 상태의 자리를 고정합니다. screen 은 그 자리가 있는 모니터의 (x, y, 너비, 높이)."""
    data[pin_key(rolled)] = {"x": int(xy[0]), "y": int(xy[1]), "screen": [int(v) for v in screen]}


def clear_pin(data: Dict[str, Any], rolled: bool) -> None:
    data.pop(pin_key(rolled), None)


def pinned_spot(data: Dict[str, Any], rolled: bool, screens: Iterable[Box]) -> Optional[Tuple[int, int]]:
    """고정해 둔 자리. 고정하지 않았거나, 고정할 때의 모니터가 지금 없으면(배치·해상도가 바뀜) None."""
    pin = data.get(pin_key(rolled))
    if not isinstance(pin, dict):
        return None
    try:
        spot, screen = (int(pin["x"]), int(pin["y"])), [int(v) for v in pin["screen"]]
    except (KeyError, TypeError, ValueError):
        return None
    return spot if any(list(geom) == screen for geom in screens) else None


# ── 접기 · 펴기 ────────────────────────────────────────────────────────────────
def fold_target(data: Dict[str, Any], box: Box, rolled_height: int, area: Any,
                pinned: Optional[Tuple[int, int]] = None, default_height: int = FALLBACK_SIZE) -> Box:
    """펼친 메모를 접을 때 놓을 자리. box 는 지금 창, area 는 지금 창이 있는 모니터의 작업 영역.

    접은 위치를 고정해 두었으면(pinned) 그 자리, 아니면 지금 창의 왼쪽 아래 모서리를 그대로 둡니다.
    너비는 접은 너비로 기억해 둔 것, 없으면 메모 본래의 너비입니다.
    """
    width = data.get('rolled_width', own_size(data, False, box, default_height)[0])
    if pinned is not None:
        return pinned[0], pinned[1], width, rolled_height
    return (*grow_from_corner(box, (width, rolled_height), area), width, rolled_height)


def unfold_target(data: Dict[str, Any], box: Box, area: Any,
                  pinned: Optional[Tuple[int, int]] = None, default_height: int = FALLBACK_SIZE) -> Box:
    """접은 메모를 펼 때 놓을 자리. box 는 지금(접힌) 창, area 는 지금 창이 있는 모니터의 작업 영역.

    펼친 위치를 고정해 두었으면(pinned) 그 자리, 아니면 지금 창의 왼쪽 아래 모서리에서 위·오른쪽으로 폅니다.
    """
    width, height = unrolled_size(data, default_height)
    if pinned is not None:
        return pinned[0], pinned[1], width, height
    return (*grow_from_corner(box, (width, height), area), width, height)


def show_target(data: Dict[str, Any], rolled: bool, visible: bool, position: Tuple[int, int],
                rolled_height: int, pinned: Optional[Tuple[int, int]] = None,
                default_height: int = FALLBACK_SIZE) -> Box:
    """메모를 화면에 올리거나 다시 맞출 때 놓을 자리. (앱을 켤 때, 탐색기에서 열 때, 내용이 바뀌어 창을 다시 맞출 때)

    이미 보이는 창은 지금 자리를 지킵니다. 숨어 있던 창은 그 상태의 위치를 고정해 두었으면(pinned) 그 자리로,
    아니면 마지막에 있던 자리로 갑니다.
    """
    if rolled:
        size = (data.get('rolled_width', saved_unrolled_size(data, default_height)[0]), rolled_height)
        remembered = (data.get('rolled_position_x', data.get('position_x', 100)), data.get('rolled_position_y', 100))
    else:
        size = unrolled_size(data, default_height)
        remembered = (data.get('position_x', 100), data.get('position_y', 100))
    x, y = position if visible else (pinned or remembered)
    return x, y, size[0], size[1]
