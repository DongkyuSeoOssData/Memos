"""메모 창의 위치와 크기 규칙.

창을 띄우지 않고 숫자만으로 따질 수 있게, 화면(위젯)과 무관한 계산만 모아 둡니다.
메모 창(MemoWindow)은 지금 상태를 넘겨주고 여기서 돌려준 자리에 창을 놓기만 합니다.

규칙
 - 접힌 상태와 펼친 상태는 위치와 크기를 서로 따로 기억합니다.
     접힘: rolled_position_x / rolled_position_y / rolled_width / rolled_height
     펼침: position_x / position_y / unrolled_width / unrolled_height (width / height 도 같은 값)
   한쪽 상태에서 옮기거나 크기를 바꿔도 다른 쪽 상태의 값은 달라지지 않습니다.
 - 잠긴 암호 메모는 펼쳤을 때 암호 입력용 크기(LOCKED_SIZE)로 뜹니다. 그 크기는 메모의 크기로 기억하지 않고,
   접을 자리와 너비를 정할 때도 메모 본래의 크기를 기준으로 삼습니다.
 - 처음 접는 메모(접힌 자리를 기억한 적 없는 메모)는 화면 가장자리에 가까운 모서리를 고정점으로 삼아 접습니다.
 - 펼칠 자리가 한 줄로 쌓아 둔 다른 접은 메모를 가리면, 쌓인 줄의 바깥쪽에 폅니다.
 - 기억해 둔 자리가 다른 모니터에 있으면 그 모니터를 기준으로 화면 안에 둡니다.
"""
from typing import Any, Callable, Dict, Optional, Tuple

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


def _anchor(box_xy: Tuple[int, int], size: Tuple[int, int], area: Any) -> Tuple[bool, bool, int, int]:
    """화면 가장자리에 가까운 모서리. → (위쪽에 가까운지, 오른쪽에 가까운지, 고정점 x, 고정점 y)"""
    x, y = box_xy
    w, h = size
    near_top = (y + h / 2) < area.top() + area.height() / 3
    near_right = (x + w / 2) > area.left() + area.width() / 2
    return near_top, near_right, (x + w if near_right else x), (y if near_top else y + h)


def fold_target(data: Dict[str, Any], box: Box, rolled_height: int, area: Any,
                default_height: int = FALLBACK_SIZE) -> Box:
    """펼친 메모를 접을 때 놓을 자리. box 는 지금 창, area 는 지금 창이 있는 모니터의 작업 영역.

    접힌 상태로 기억해 둔 자리와 너비가 있으면 그대로, 처음 접는 메모는 가장자리에 가까운 모서리를 고정점으로 삼습니다.
    """
    size = own_size(data, False, box, default_height)
    width = data.get('rolled_width', size[0])
    if 'rolled_position_x' in data and 'rolled_position_y' in data:
        return data['rolled_position_x'], data['rolled_position_y'], width, rolled_height
    near_top, near_right, anchor_x, anchor_y = _anchor((box[0], box[1]), size, area)
    return (anchor_x - width if near_right else anchor_x), (anchor_y if near_top else anchor_y - rolled_height), width, rolled_height


def unfold_target(data: Dict[str, Any], box: Box, area: Any, area_for: Callable[[Box], Any],
                  stack: Optional[Tuple[int, int]] = None, covers: Optional[Callable[[Box], bool]] = None,
                  default_height: int = FALLBACK_SIZE) -> Box:
    """접은 메모를 펼 때 놓을 자리. box 는 지금(접힌) 창, area 는 지금 창이 있는 모니터의 작업 영역.

    area_for(자리) 는 그 자리가 속한 모니터의 작업 영역을 돌려줍니다. stack 은 이 메모가 다른 접은 메모들과 쌓여 있는
    줄의 (왼쪽 끝, 오른쪽 끝)이고, covers(자리) 는 그 자리에 펼치면 다른 접은 메모를 가리는지 알려 줍니다.
    """
    width, height = unrolled_size(data, default_height)
    x, y = data.get('position_x', box[0]), data.get('position_y', box[1])
    x, y = clamp(area_for((x, y, width, height)), x, y, width, height)
    if stack is not None and covers is not None and covers((x, y, width, height)):
        near_top, near_right, _, anchor_y = _anchor((box[0], box[1]), (box[2], box[3]), area)
        beside = stack[0] - width if near_right else stack[1]
        if area.left() <= beside and beside + width <= area.left() + area.width():
            x = beside
            y = anchor_y if near_top else anchor_y - height
    return x, y, width, height


def show_target(data: Dict[str, Any], rolled: bool, was_rolled: bool, visible: bool, position: Tuple[int, int],
                rolled_height: int, default_height: int = FALLBACK_SIZE) -> Box:
    """메모를 화면에 올리거나 다시 맞출 때 놓을 자리. (앱을 켤 때, 탐색기에서 열 때, 내용이 바뀌어 창을 다시 맞출 때)

    이미 보이는 창은 지금 자리를 지키고, 숨어 있던 창은 기억해 둔 자리로 갑니다.
    """
    here_x, here_y = position
    if rolled:
        width = data.get('rolled_width', saved_unrolled_size(data, default_height)[0])
        x = here_x if visible else data.get('rolled_position_x', data.get('position_x', 100))
        y = here_y if visible else data.get('rolled_position_y', 100)
        return x, y, width, rolled_height
    width, height = unrolled_size(data, default_height)
    x = here_x if visible else data.get('position_x', 100)
    y = here_y if (visible and not was_rolled) else data.get('position_y', 100)
    return x, y, width, height
