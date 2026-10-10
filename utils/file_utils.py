import os
import re
import json
import time
import threading
from pathlib import Path
from typing import Any

# UI 스레드·저장 스레드·SyncWorker가 같은 메모 폴더를 읽고 쓰므로 파일 I/O 구간을 직렬화합니다.
MEMO_IO_LOCK = threading.RLock()


_SAFE_MEMO_ID = re.compile(r"[A-Za-z0-9_-]{1,80}")


def is_safe_memo_id(memo_id: Any) -> bool:
    """메모 id를 파일 이름으로 써도 안전한지 확인합니다. (경로 구분자·'..' 등이 섞인 id 차단)"""
    return isinstance(memo_id, str) and _SAFE_MEMO_ID.fullmatch(memo_id) is not None


def atomic_write_json(path: Path, obj: Any) -> None:
    """임시 파일에 쓴 뒤 교체하여, 쓰는 도중 읽히거나 중단되어도 반쪽 파일이 남지 않게 합니다."""
    tmp = path.with_name(path.name + ".tmp")
    with MEMO_IO_LOCK:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
        for _ in range(5):
            try:
                os.replace(tmp, path)
                return
            except PermissionError:
                # 백신·클라우드 동기화 프로그램이 대상 파일을 잠시 잡고 있는 경우
                time.sleep(0.05)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(obj, f, ensure_ascii=False, indent=2)
        finally:
            try:
                tmp.unlink()
            except OSError:
                pass
