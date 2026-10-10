"""체크리스트.

줄 맨 앞에 ☐(할 일) 또는 ☑(끝낸 일)을 두는 방식입니다. 그냥 글자이므로 서식 없는 메모·코드 메모·폰 화면·
미리보기·검색 어디서나 똑같이 보이고, 저장 형식도 달라지지 않습니다.
"""
from typing import List, Optional, Tuple

UNCHECKED = "☐"
CHECKED = "☑"
BOXES = (UNCHECKED, CHECKED)


def box_index(line: str) -> int:
    """줄에서 체크 상자가 있는 위치. (앞의 공백은 건너뜀) 체크리스트 줄이 아니면 -1."""
    stripped = line.lstrip(" \t")
    if stripped[:1] in BOXES:
        return len(line) - len(stripped)
    return -1


def state(line: str) -> Optional[bool]:
    """체크됨 True / 안 됨 False / 체크리스트 줄이 아님 None."""
    index = box_index(line)
    return None if index < 0 else line[index] == CHECKED


def toggled(line: str) -> str:
    """체크 상태를 뒤집은 줄. 체크리스트 줄이 아니면 그대로."""
    index = box_index(line)
    if index < 0:
        return line
    return line[:index] + (UNCHECKED if line[index] == CHECKED else CHECKED) + line[index + 1:]


def with_box(line: str) -> str:
    """체크 상자를 붙인 줄. 이미 있으면 그대로."""
    if box_index(line) >= 0:
        return line
    indent = len(line) - len(line.lstrip(" \t"))
    return line[:indent] + UNCHECKED + " " + line[indent:]


def without_box(line: str) -> str:
    """체크 상자를 뗀 줄."""
    index = box_index(line)
    if index < 0:
        return line
    rest = line[index + 1:]
    return line[:index] + (rest[1:] if rest[:1] == " " else rest)


def toggle_boxes(lines: List[str]) -> List[str]:
    """여러 줄에 체크 상자를 붙이거나 뗍니다. 모두 체크리스트 줄이면 떼고, 아니면 없는 줄에 붙입니다. (빈 줄은 건너뜀)"""
    real = [line for line in lines if line.strip()]
    if real and all(box_index(line) >= 0 for line in real):
        return [without_box(line) for line in lines]
    return [with_box(line) if line.strip() or len(lines) == 1 else line for line in lines]


def continuation(line: str) -> Tuple[str, bool]:
    """체크리스트 줄 끝에서 Enter 를 쳤을 때.

    돌려주는 값: (다음 줄 앞에 넣을 글자, 지금 줄의 체크 상자를 지울지)
    내용이 있는 줄이면 다음 줄도 체크 상자로 시작하고, 상자만 있는 빈 줄이면 상자를 지워 체크리스트를 끝냅니다.
    """
    index = box_index(line)
    if index < 0:
        return "", False
    if not line[index + 1:].strip():
        return "", True
    return line[:index] + UNCHECKED + " ", False
