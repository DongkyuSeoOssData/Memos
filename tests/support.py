"""UI 테스트의 공용 준비. (화면 없이 offscreen 으로 실행)

실제 사용자 폴더·레지스트리·전역 단축키를 건드리지 않도록 모두 임시 값/대역으로 바꿔 놓고 수행합니다.
UI 테스트 파일은 다른 것보다 먼저 이 모듈을 가져옵니다. (offscreen 설정과 프로젝트 경로가 여기서 잡힘)
 - UiTestCase : 임시 홈 폴더, 대역으로 바꾼 대화상자·자동 실행·전역 단축키. 테스트는 이것을 물려받습니다.
 - app        : 하나뿐인 QApplication
 - smm, sw, uim, overlay, themed_dialog : 테스트에서 자주 쓰는 모듈 (support.sw 처럼 씀)
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PyQt6.QtCore import QRect, Qt
from PyQt6.QtWidgets import QApplication

import core.sync_manager as smm
import ui.settings_window as sw
import ui.screen_bounds as screen_bounds
import ui.ui_manager as uim
import ui.overlay as overlay
import ui.themed_dialog as themed_dialog
import utils.crypto_manager as cm
from drive_api import DriveAPI

app = QApplication.instance() or QApplication([])


class FakeHotkeys:
    def __init__(self) -> None:
        self.registered = []

    def register(self, shortcut, callback) -> bool:
        self.registered.append(shortcut)
        return True

    def unregister_all(self) -> None:
        self.registered.clear()


class UiTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.home = Path(self._tmp.name)
        self.memo_dir = self.home / "memos"
        (self.home / ".memoit_custom").mkdir(parents=True)
        (self.home / ".memoit_custom" / "settings.json").write_text(
            json.dumps({"local_memo_path": str(self.memo_dir), "use_sync": False, "time_24h": True}), encoding="utf-8")

        self.auto_start = {"on": False, "calls": []}
        self.answers = []
        self.warnings = []

        def fake_set(enable, *a, **k):
            self.auto_start["on"] = enable
            self.auto_start["calls"].append(enable)
            return True

        is_enabled = lambda *a, **k: self.auto_start["on"]
        self.confirm_answer = True
        self.choice_answer = "discard"
        self.choices_asked = []
        self.real_choose = themed_dialog.choose

        def fake_choose(parent, title, text, options):
            self.choices_asked.append(title)
            return self.choice_answer

        self.real_form_ask = themed_dialog.ask_form
        self.real = {"confirm": themed_dialog.confirm, "ask_form": themed_dialog.ask_form}
        real_toast = themed_dialog.toast

        def spy_toast(widget, text, warn=False):
            if warn:
                self.warnings.append(text)
            real_toast(widget, text, warn)

        def fake_form(parent, title, text, fields, ok_text="확인", validate=None, danger=False):
            if len(self.answers) < len(fields):
                return None                                  # 답이 없으면 취소한 것으로
            values = [self.answers.pop(0) for _ in fields]
            error = validate(values) if validate else None
            if error:
                self.warnings.append(error)
                return None
            return values

        patches = [
            mock.patch.object(Path, "home", return_value=self.home),
            mock.patch.object(cm, "MEMO_LOCK_ITERATIONS", 1000),
            mock.patch.object(smm, "set_auto_start", fake_set),
            mock.patch.object(smm, "is_auto_start_enabled", is_enabled),
            mock.patch.object(sw, "is_auto_start_enabled", is_enabled),
            mock.patch.object(uim, "GlobalHotkeys", FakeHotkeys),
            # 시험 환경의 화면은 800x800 이라, 창 크기·위치 시험이 거기에 걸리지 않게 넓은 작업 영역을 줍니다.
            mock.patch.object(screen_bounds, "work_area", lambda widget, at=None: QRect(0, 0, 4000, 3000)),
            # 대화상자는 띄우지 않고 대역으로 답합니다: 한 줄 입력은 answers 에서 꺼내고, 확인 묻기는 '예',
            # 암호 입력(여러 칸)은 answers 에서 칸 수만큼 꺼내며, 경고 토스트와 입력 오류는 warnings 에 모읍니다.
            mock.patch.object(themed_dialog, "ask_text",
                              lambda *a, **k: (self.answers.pop(0), True) if self.answers else ("", False)),
            mock.patch.object(themed_dialog, "confirm", lambda *a, **k: self.confirm_answer),
            # 버튼 여러 개 중 고르기(저장하고 닫기 / 저장 안 함 / 취소)는 choice_answer 로 답하고, 물은 횟수를 셉니다.
            mock.patch.object(themed_dialog, "choose", fake_choose),
            mock.patch.object(themed_dialog, "toast", spy_toast),
            mock.patch.object(themed_dialog, "ask_form", fake_form),
            # 잠긴 메모의 암호 칸에 커서를 두는 대신, 위의 대역으로 암호를 묻게 합니다.
            mock.patch.object(overlay.LockOverlay, "focus_inline", lambda overlay: False),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(self._tmp.cleanup)

        self.sm = smm.SyncManager(DriveAPI())
        self.assertEqual(self.sm.local_path, self.memo_dir)
        for i in range(3):
            self.sm.save_memo_locally({
                "id": f"memo-000{i}", "title": f"t{i}", "content": f"body {i} #tag{i}",
                "updated_at": f"2026-01-0{i + 1}T00:00:00", "is_visible": False})
        self.ui = uim.UIManager(self.sm)
        self.addCleanup(self._close_windows)
        self.ui.show_all_memos()

    def _close_windows(self) -> None:
        for w in list(self.ui.memo_windows.values()):
            w._is_deleting = True
            w.close()
        if self.ui.explorer_window:
            self.ui.explorer_window.close()
        self.ui.tray_icon.hide()

    def disk(self, memo_id: str) -> dict:
        return json.loads((self.memo_dir / f"{memo_id}.json").read_text(encoding="utf-8"))

    def raw(self, memo_id: str) -> str:
        return (self.memo_dir / f"{memo_id}.json").read_text(encoding="utf-8")

    def open_window(self, memo_id: str):
        self.ui.show_specific_memo(memo_id)
        w = self.ui.memo_windows[memo_id]
        w._auto_save_timer.setTimerType(Qt.TimerType.PreciseTimer)
        w._relock_timer.setTimerType(Qt.TimerType.PreciseTimer)
        return w

    def explorer(self):
        self.ui.open_memo_explorer()
        return self.ui.explorer_window

    def row_of(self, ex, memo_id: str) -> int:
        for r in range(ex.table.rowCount()):
            if ex.table.item(r, 2).data(Qt.ItemDataRole.UserRole)["id"] == memo_id:
                return r
        self.fail(f"{memo_id} not listed")
