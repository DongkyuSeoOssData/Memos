"""UI 동작 회귀 테스트 (화면 없이 offscreen으로 실행). 실행: python -m unittest discover -s tests

실제 사용자 폴더·레지스트리·전역 단축키를 건드리지 않도록 모두 임시 값/대역으로 바꿔 놓고 수행합니다.
"""
import ctypes
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtGui import QKeyEvent, QTextCursor
from PyQt6.QtCore import QEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QFileDialog, QInputDialog, QMessageBox

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

import core.sync_manager as smm
import ui.settings_window as sw
import ui.ui_manager as uim
import utils.crypto_manager as cm
from drive_api import DriveAPI
from ui.global_hotkeys import GlobalHotkeys, WM_HOTKEY, parse_shortcut
from ui.memo_editor import CodeHighlighter
from utils.crypto_manager import CryptoManager

_app = QApplication.instance() or QApplication([])


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
            json.dumps({"local_memo_path": str(self.memo_dir), "use_sync": False}), encoding="utf-8")

        self.auto_start = {"on": False, "calls": []}
        self.answers = []
        self.warnings = []

        def fake_set(enable, *a, **k):
            self.auto_start["on"] = enable
            self.auto_start["calls"].append(enable)
            return True

        is_enabled = lambda *a, **k: self.auto_start["on"]
        patches = [
            mock.patch.object(Path, "home", return_value=self.home),
            mock.patch.object(cm, "MEMO_LOCK_ITERATIONS", 1000),
            mock.patch.object(smm, "set_auto_start", fake_set),
            mock.patch.object(smm, "is_auto_start_enabled", is_enabled),
            mock.patch.object(sw, "is_auto_start_enabled", is_enabled),
            mock.patch.object(uim, "GlobalHotkeys", FakeHotkeys),
            mock.patch.object(QInputDialog, "getText",
                              staticmethod(lambda *a, **k: (self.answers.pop(0), True) if self.answers else ("", False))),
            mock.patch.object(QMessageBox, "information", staticmethod(lambda *a, **k: None)),
            mock.patch.object(QMessageBox, "warning", staticmethod(lambda *a, **k: self.warnings.append(a[2]))),
            mock.patch.object(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)),
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


class StartupTest(UiTestCase):
    def test_starts_without_login_and_registers_hotkeys(self) -> None:
        self.assertEqual(len(self.ui.memo_windows), 3)
        self.assertEqual(len(self.ui._hotkeys.registered), 6)


class AutoSaveTest(UiTestCase):
    def test_saves_one_minute_after_last_input(self) -> None:
        w = self.open_window("memo-0000")
        w.text_edit.setPlainText("typing")
        self.assertTrue(w._auto_save_timer.isActive())
        self.assertEqual(w._auto_save_timer.interval(), 60000)
        QTest.qWait(250)
        w.text_edit.setPlainText("typing more")
        self.assertGreater(w._auto_save_timer.remainingTime(), 59800)   # 재입력 시 다시 1분
        self.assertNotIn("typing more", self.disk("memo-0000")["content"])

    def test_continuous_typing_is_capped(self) -> None:
        w = self.open_window("memo-0000")
        w.text_edit.setPlainText("a")
        w._dirty_since -= 595
        w.text_edit.setPlainText("ab")
        self.assertLessEqual(w._auto_save_timer.interval(), 5000)

    def test_close_and_quit_flush_unsaved_input(self) -> None:
        w = self.open_window("memo-0000")
        w.text_edit.setPlainText("saved on close")
        w.close()
        self.assertIn("saved on close", self.disk("memo-0000")["content"])

        w1 = self.open_window("memo-0001")
        w1.text_edit.setPlainText("saved on quit")
        self.ui.flush_pending_saves()
        self.assertIn("saved on quit", self.disk("memo-0001")["content"])

    def test_recolor_does_not_revert_unsaved_input(self) -> None:
        w = self.open_window("memo-0000")
        w.text_edit.setPlainText("unsaved before recolor")
        w.change_color("#DCFCE7")
        self.assertIn("unsaved before recolor", w.text_edit.toPlainText())

    def test_plain_click_does_not_save(self) -> None:
        w = self.open_window("memo-0000")
        with mock.patch.object(self.sm, "save_memo_locally", wraps=self.sm.save_memo_locally) as spy:
            QTest.mouseClick(w, Qt.MouseButton.LeftButton, pos=QPoint(2, 2))
        self.assertEqual(spy.call_count, 0)

    def test_arrange_saves_new_positions(self) -> None:
        w = self.open_window("memo-0000")
        with mock.patch.object(uim.threading, "Thread") as thread_cls:
            self.ui.arrange_memos()
            thread_cls.call_args.kwargs["target"]()          # 저장 작업을 같은 스레드에서 실행
        self.assertEqual(self.disk("memo-0000")["position_x"], w.x())
        self.assertFalse((self.home / ".memoit_custom" / "error.log").exists())


class ExplorerTest(UiTestCase):
    def test_toast_sits_next_to_preview_title(self) -> None:
        ex = self.explorer()
        _app.processEvents()
        ex.show_toast("hello")
        _app.processEvents()
        self.assertTrue(ex.toast.isVisible())
        gap = ex.pv.mapTo(ex, QPoint(0, 0)).y() - ex.toast.mapTo(ex, QPoint(0, 0)).y()
        self.assertTrue(0 < gap < 60, gap)

    def test_search_is_debounced(self) -> None:
        ex = self.explorer()
        ex.s_in.setText("t1")
        self.assertEqual(ex.table.rowCount(), 3)
        QTest.qWait(450)
        self.assertEqual(ex.table.rowCount(), 1)

    def test_hashtag_filter_matches_whole_tag(self) -> None:
        self.sm.save_memo_locally({"id": "memo-long", "title": "long", "content": "x #tag1extra",
                                   "updated_at": "2026-01-05T00:00:00", "is_visible": False})
        ex = self.explorer()
        ex.refresh()
        ex.tag_combo.setCurrentText("#tag1")
        ex.refresh()
        self.assertEqual([m["id"] for m in ex.filtered_memos], ["memo-0001"])

    def test_favorite_survives_window_save(self) -> None:
        w = self.open_window("memo-0000")
        ex = self.explorer()
        ex.toggle_fav(next(m for m in self.sm.load_local_memos() if m["id"] == "memo-0000"))
        w.save_callback(w.memo_data)
        self.assertTrue(self.disk("memo-0000")["is_favorite"])

    def test_preview_shows_unsaved_window_text(self) -> None:
        w = self.open_window("memo-0000")
        w.text_edit.setPlainText("fresh text")
        ex = self.explorer()
        ex.on_cell_click(self.row_of(ex, "memo-0000"), 2)
        self.assertIn("fresh text", ex.pv.toPlainText())

    def test_broken_timestamp_does_not_break_listing(self) -> None:
        self.sm.save_memo_locally({"id": "memo-bad1", "title": "bad", "content": "x",
                                   "updated_at": "not-a-date", "is_visible": False})
        ex = self.explorer()
        ex.refresh()
        self.assertEqual(ex.table.rowCount(), 4)

    def test_fixed_size_option(self) -> None:
        ex = self.explorer()
        self.sm.settings["explorer_fixed_size"] = True
        self.sm.settings["explorer_geom"] = [10, 10, 800, 600]
        ex.apply_size_settings()
        ex.resize(1200, 900)
        _app.processEvents()
        self.assertEqual((ex.width(), ex.height()), (800, 600))
        self.assertFalse(ex.grip.isVisible())


class LockedMemoUiTest(UiTestCase):
    def lock(self, memo_id: str = "memo-0000"):
        w = self.open_window(memo_id)
        w.text_edit.setPlainText("top secret")
        self.answers[:] = ["pw", "pw"]
        w.set_memo_password()
        return w

    def test_lock_relock_unlock_cycle(self) -> None:
        w = self.lock()
        self.assertTrue(self.disk("memo-0000")["is_locked"])
        self.assertNotIn("top secret", self.raw("memo-0000"))
        self.assertEqual(w._relock_timer.interval(), 5 * 60000)

        w._relock_timer.timeout.emit()                       # 자동 잠금 시각 도래
        self.assertTrue(w.memo_data.get("_locked"))
        self.assertEqual(w.text_edit.toPlainText(), "")
        self.assertTrue(w.text_edit.isReadOnly())
        self.assertFalse(self.sm.is_memo_unlocked("memo-0000"))

        self.answers[:] = ["wrong"]
        w.prompt_unlock()
        self.assertTrue(self.warnings and w.memo_data.get("_locked"))
        self.answers[:] = ["pw"]
        w.prompt_unlock()
        self.assertEqual(w.text_edit.toPlainText(), "top secret")
        self.assertFalse(w.text_edit.isReadOnly())

    def test_closing_locked_window_keeps_memo(self) -> None:
        w = self.lock()
        w.lock_now()
        w.close()
        self.assertTrue((self.memo_dir / "memo-0000.json").exists())
        self.assertFalse((self.memo_dir / "trash_bin" / "memo-0000.json").exists())
        self.assertIn("top secret", self.sm.unlock_memo("memo-0000", "pw") or "")

    def test_closing_unlocked_window_drops_key(self) -> None:
        w = self.lock()
        w.close()
        self.assertFalse(self.sm.is_memo_unlocked("memo-0000"))

    def test_explorer_hides_locked_content(self) -> None:
        w = self.lock()
        w.lock_now()
        ex = self.explorer()
        ex.refresh()
        row = self.row_of(ex, "memo-0000")
        self.assertTrue(ex.table.item(row, 2).text().startswith("🔒"))
        ex.on_cell_click(row, 2)
        self.assertTrue(ex.pv.isReadOnly())
        self.assertNotIn("top secret", ex.pv.toPlainText())

    def test_master_key_recovery_from_window(self) -> None:
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        public_pem = private_key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
        key_file = self.home / "master.pem"
        key_file.write_bytes(private_key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
            serialization.BestAvailableEncryption(b"keypass")))
        self.sm.crypto = CryptoManager(public_pem)

        w = self.lock()
        w.lock_now()                                         # 사용자가 암호를 잊었다고 가정
        self.assertTrue(self.sm.memo_has_master_recovery("memo-0000"))
        with mock.patch.object(QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: (str(key_file), ""))):
            self.answers[:] = ["keypass", "newpw", "newpw"]
            w.recover_with_master_key()
        self.assertEqual(w.text_edit.toPlainText(), "top secret")
        w.lock_now()
        self.assertIsNone(self.sm.unlock_memo("memo-0000", "pw"))
        self.assertIn("top secret", self.sm.unlock_memo("memo-0000", "newpw") or "")


class SettingsTest(UiTestCase):
    def test_auto_start_follows_checkbox(self) -> None:
        win = sw.SettingsWindow(self.sm)
        self.assertFalse(win.auto_start_cb.isChecked())
        win.auto_start_cb.setChecked(True)
        win.save()
        self.assertEqual(self.auto_start["calls"], [True])
        self.assertTrue(self.sm.settings["auto_start"])
        win.auto_start_cb.setChecked(False)
        win.save()
        self.assertEqual(self.auto_start["calls"], [True, False])
        self.assertFalse(self.sm.settings["auto_start"])

    def test_options_round_trip(self) -> None:
        win = sw.SettingsWindow(self.sm)
        win.spin_relock_min.setValue(2)
        win.auto_save_interval_box.setCurrentIndex(win.auto_save_interval_box.findData(10))
        win.trash_auto_delete_box.setCurrentIndex(1)
        win.save()
        self.assertEqual(self.sm.settings["locked_memo_relock_min"], 2)
        self.assertEqual(self.sm.settings["auto_save_idle_sec"], 10)
        self.assertEqual(self.sm.settings["trash_auto_delete_days"], -1)
        self.assertEqual(sw.SettingsWindow(self.sm).trash_auto_delete_box.currentIndex(), 1)

    def test_every_shortcut_row_is_saved_by_key(self) -> None:
        win = sw.SettingsWindow(self.sm)
        win.shortcut_table.item(0, 0).setText("이름이 바뀌어도")
        win.save()
        self.assertEqual(set(self.sm.settings["shortcuts"]), set(sw.DEFAULT_SHORTCUTS))
        self.assertEqual(len(win.SHORTCUT_ROWS), len(sw.DEFAULT_SHORTCUTS))


class EditorTest(UiTestCase):
    def test_escape_clears_multi_cursor_before_closing(self) -> None:
        w = self.open_window("memo-0000")
        w.text_edit.extra_cursors.append(QTextCursor(w.text_edit.document()))
        esc = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
        w.text_edit.keyPressEvent(esc)
        self.assertEqual(w.text_edit.extra_cursors, [])
        self.assertTrue(w.isVisible())
        w.text_edit.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier))
        self.assertFalse(w.isVisible())

    def test_single_quote_is_comment_only_in_vb(self) -> None:
        def comment_patterns(lang):
            w = self.open_window("memo-0000")
            hl = CodeHighlighter(w.text_edit.document(), lang)
            return [p.pattern for p, fmt in hl.rules if fmt.fontItalic()]
        self.assertEqual(comment_patterns("PYTHON"), [r"#.*"])
        self.assertEqual(comment_patterns("JAVASCRIPT"), [r"//.*"])
        self.assertEqual(comment_patterns("VB.NET"), [r"'.*"])


class GlobalHotkeyTest(unittest.TestCase):
    def test_parse(self) -> None:
        self.assertEqual(parse_shortcut("Alt+N"), (0x1, 0x4E))
        self.assertEqual(parse_shortcut("Alt+Shift+N"), (0x1 | 0x4, 0x4E))
        self.assertEqual(parse_shortcut("Ctrl+F2"), (0x2, 0x71))
        self.assertIsNone(parse_shortcut(""))

    def test_register_and_receive(self) -> None:
        hk = GlobalHotkeys()
        self.addCleanup(hk.unregister_all)
        fired = []
        self.assertTrue(hk.register("Ctrl+Alt+Shift+F23", lambda: fired.append(1)))
        self.assertFalse(hk.register("Ctrl+Alt+Shift+F23", lambda: None))   # 이미 사용 중인 조합
        ctypes.windll.user32.PostThreadMessageW(ctypes.windll.kernel32.GetCurrentThreadId(), WM_HOTKEY, 1, 0)
        QTest.qWait(100)
        self.assertEqual(fired, [1])


if __name__ == "__main__":
    unittest.main()
