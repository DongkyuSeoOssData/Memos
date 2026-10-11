"""로컬 색인: 메모 파일들을 읽어 둔 것을 파일 하나로 간직해, 앱을 켤 때 모든 메모 파일을 다시 읽지 않게 합니다.

메모는 파일 하나에 하나씩 들어 있어서, 색인이 없으면 앱을 켤 때 그 파일들을 전부 열어 읽어야 목록을 알 수 있습니다.
색인에는 파일마다 (수정시각, 크기, 파일 내용)을 적어 둡니다. 앱을 켜면 색인 하나를 읽고 메모 폴더를 한 번 훑어,
수정시각이나 크기가 달라진 파일만 다시 읽습니다. (그 판단은 SyncManager._load_local_memos 가 함)

지키는 것
 - 색인은 메모 파일에서 만들어 낸 것일 뿐입니다. 진짜는 메모 파일입니다. 색인이 없거나, 깨졌거나, 다른 메모 폴더의 것이면
   버리고 처음부터 다시 만듭니다. 색인이 틀려서 메모가 잘못 보이는 일이 없도록, 쓸 때마다 파일의 수정시각·크기와 견줍니다.
 - 이 PC에만 둡니다. (설정 폴더 ~/.memoit_custom/memo_index.json) 동기화하지 않습니다.
 - 암호 메모는 파일에 든 암호문 그대로 들어갑니다. 푼 내용은 넣지 않습니다.
 - 암호를 걸지 않은 메모는 메모 파일과 마찬가지로 내용이 그대로 들어 있습니다. 지운 메모는 다음에 색인을 쓸 때 빠집니다.

(SyncManager 에 섞어 쓰는 부분)
"""
import json
import os
import threading
from pathlib import Path
from typing import Any, Dict, Tuple

from utils.file_utils import MEMO_IO_LOCK

INDEX_FILE = "memo_index.json"
INDEX_VERSION = 1
INDEX_SAVE_DELAY_MS = 20 * 1000         # 읽어 둔 것이 바뀐 뒤 이만큼 지나 색인을 씁니다. (자주 쓰지 않도록 모아서)


class MemoIndexMixin:
    """SyncManager 의 로컬 색인."""

    @property
    def index_path(self) -> Path:
        return self.base_path / INDEX_FILE

    def _load_index(self) -> None:
        """앱을 켤 때 색인을 읽어 옵니다. 쓸 수 없는 색인이면 조용히 버립니다."""
        self._file_cache = {}
        try:
            with open(self.index_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict) or data.get("v") != INDEX_VERSION or data.get("folder") != str(self.local_path):
                return
            loaded: Dict[str, Tuple[Tuple[int, int], Any]] = {}
            for name, item in data.get("files", {}).items():
                stamp, raw = item
                if isinstance(raw, dict) and len(stamp) == 2:
                    loaded[str(name)] = ((int(stamp[0]), int(stamp[1])), raw)
            self._file_cache = loaded
        except Exception:
            self._file_cache = {}

    def _index_changed(self) -> None:
        """읽어 둔 것이 달라졌으니 조금 뒤에 색인을 다시 씁니다. (어느 스레드에서 불러도 됨)"""
        self._index_dirty = True
        self._index_touched.emit()

    def _arm_index_timer(self) -> None:
        if not self._index_timer.isActive():
            self._index_timer.start(INDEX_SAVE_DELAY_MS)

    def _snapshot_index(self) -> Dict[str, Any]:
        with MEMO_IO_LOCK:
            self._index_dirty = False
            files = {name: [list(stamp), raw] for name, (stamp, raw) in self._file_cache.items()}
        return {"v": INDEX_VERSION, "folder": str(self.local_path), "files": files}

    def _write_index(self, snapshot: Dict[str, Any]) -> None:
        try:
            with self._index_write_lock:
                tmp = self.index_path.with_name(INDEX_FILE + ".tmp")
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(snapshot, f, ensure_ascii=False, separators=(",", ":"))
                os.replace(tmp, self.index_path)
        except Exception as e:
            self._index_dirty = True            # 다음 기회에 다시
            self.log_error(f"색인 저장 실패: {e}", e)

    def _save_index_in_background(self) -> None:
        """색인을 뒤에서 씁니다. (메모가 많으면 파일이 커서, 화면이 멈칫하지 않게)"""
        if self._index_dirty:
            threading.Thread(target=self._write_index, args=(self._snapshot_index(),), daemon=True).start()

    def save_index_now(self) -> None:
        """색인을 지금 씁니다. (앱을 끝낼 때)"""
        self._index_timer.stop()
        if self._index_dirty:
            self._write_index(self._snapshot_index())
