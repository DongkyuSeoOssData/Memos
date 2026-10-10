"""메모 폴더.

메모마다 'folder' 값(예: "업무", "업무/프로젝트A")을 하나 가집니다. 비어 있으면 미분류입니다.
'/' 로 하위 폴더를 나타내며, 상위 폴더를 고르면 그 아래 폴더의 메모도 함께 보입니다.

폴더는 디스크의 실제 폴더가 아니라 메모에 붙는 '분류 이름'입니다. 메모 파일은 모두 메모 폴더 한곳에 그대로 있습니다.
폴더 목록과 순서는 이 PC의 설정(settings.json 의 "folders")에 저장하며 따로 동기화하지 않습니다.
목록은 설정에 적어 둔 폴더(만든 순서, 또는 사용자가 끌어서 바꾼 순서)에, 메모들이 실제로 들어 있는 폴더를 합쳐서 만듭니다.
(다른 PC나 폰에서 만든 폴더도 그 폴더에 메모가 하나라도 있으면 목록 끝에 나타납니다)
"""
from typing import Any, Dict, Iterable, List

SEP = "/"
ALL = ""                    # 전체 메모
UNFILED = "/unfiled"        # 폴더가 없는 메모만 (정리된 폴더 경로는 "/"로 시작하지 않으므로 겹치지 않음)
DEFAULT_FOLDERS = ["개인", "업무"]
# 탐색기에서 폴더를 고르는 화면 방식
UI_MODES = ("tabs", "sidebar", "dropdown")


def normalize(path: Any) -> str:
    """앞뒤 공백과 빈 단계를 없앤 폴더 경로. ("  업무 / /A " → "업무/A")"""
    if not isinstance(path, str):
        return ""
    return SEP.join(part.strip() for part in path.replace("\\", SEP).split(SEP) if part.strip())


def folder_of(memo: Dict[str, Any]) -> str:
    return normalize(memo.get("folder", ""))


def contains(selected: str, memo_folder: str) -> bool:
    """selected 를 골랐을 때 memo_folder 에 든 메모가 보여야 하는지."""
    if selected == ALL:
        return True
    if selected == UNFILED:
        return memo_folder == ""
    return memo_folder == selected or memo_folder.startswith(selected + SEP)


def arrange(paths: Iterable[str]) -> List[str]:
    """주어진 순서를 지키면서 폴더를 나무 모양으로 늘어놓습니다.

    - 상위 폴더가 빠져 있으면 채워 넣습니다. ("업무/A" 가 있으면 "업무" 도 포함)
    - 하위 폴더는 항상 자기 상위 폴더 바로 아래에 모읍니다.
    - 같은 단계의 폴더끼리는 처음 나온 순서를 따릅니다.
    """
    order: Dict[str, int] = {}
    for path in paths:
        parts = normalize(path).split(SEP) if normalize(path) else []
        for level in range(1, len(parts) + 1):
            order.setdefault(SEP.join(parts[:level]), len(order))

    def children(parent: str) -> List[str]:
        level = depth(parent) + 1 if parent else 0
        prefix = parent + SEP if parent else ""
        return sorted((p for p in order if depth(p) == level and p.startswith(prefix)), key=order.__getitem__)

    out: List[str] = []

    def walk(parent: str) -> None:
        for child in children(parent):
            out.append(child)
            walk(child)

    walk("")
    return out


def all_folders(saved: Iterable[str], memos: Iterable[Dict[str, Any]]) -> List[str]:
    """보여 줄 폴더 목록. 설정에 저장된 순서가 먼저이고, 메모에서만 발견된 폴더는 이름순으로 뒤에 붙습니다."""
    known = arrange(saved or [])
    found = sorted({folder_of(m) for m in memos} - {""}, key=lambda p: [part.casefold() for part in p.split(SEP)])
    return arrange(known + found)


def reorder(names: List[str], path: str, before: Any) -> List[str]:
    """path 폴더(하위 폴더 포함)를 before 폴더 앞으로 옮긴 새 순서. before 가 None 이면 같은 단계의 맨 뒤로 보냅니다."""
    parent_of = lambda p: p.rsplit(SEP, 1)[0] if SEP in p else ""
    if before is not None and parent_of(before) != parent_of(path):
        return list(names)
    block = [n for n in names if contains(path, n)]
    rest = [n for n in names if n not in block]
    if before in rest:
        at = rest.index(before)
    else:
        parent = path.rsplit(SEP, 1)[0] if SEP in path else ""
        siblings_and_below = [i for i, n in enumerate(rest) if not parent or contains(parent, n)]
        at = (siblings_and_below[-1] + 1) if siblings_and_below else len(rest)
    return arrange(rest[:at] + block + rest[at:])


def moved(path: str, old: str, new: str) -> str:
    """old 폴더를 new 로 바꿨을 때 path 가 어떻게 되는지. (old 와 그 아래가 아니면 그대로)"""
    if path == old:
        return new
    if path.startswith(old + SEP):
        return normalize(new + SEP + path[len(old) + 1:])
    return path


def top(path: str) -> str:
    """가장 위 단계의 폴더. ("업무/A/B" → "업무")"""
    return path.split(SEP, 1)[0]


def counts(memos: Iterable[Dict[str, Any]]) -> Dict[str, int]:
    """폴더별 메모 개수. 하위 폴더의 메모도 상위 폴더에 포함해 셉니다. ALL·UNFILED 키도 들어 있습니다."""
    out: Dict[str, int] = {ALL: 0, UNFILED: 0}
    for memo in memos:
        out[ALL] += 1
        path = folder_of(memo)
        if not path:
            out[UNFILED] += 1
            continue
        parts = path.split(SEP)
        for level in range(1, len(parts) + 1):
            key = SEP.join(parts[:level])
            out[key] = out.get(key, 0) + 1
    return out


def depth(path: str) -> int:
    return path.count(SEP)


def leaf(path: str) -> str:
    return path.rsplit(SEP, 1)[-1]
