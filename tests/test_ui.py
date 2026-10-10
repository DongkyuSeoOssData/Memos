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
from PyQt6.QtGui import QKeyEvent, QTextCursor, QTextListFormat
from PyQt6.QtCore import QEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QFileDialog, QInputDialog, QMessageBox, QPushButton

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
        self.assertEqual(len(self.ui.memo_windows), 0)     # 숨겨 둔 메모는 창을 미리 만들지 않음
        self.assertEqual(len(self.ui._hotkeys.registered), 6)


class WindowManagementTest(UiTestCase):
    def test_only_visible_memos_get_a_window_at_startup(self) -> None:
        self.sm.save_memo_locally({"id": "memo-shown", "title": "shown", "content": "x",
                                   "updated_at": "2026-01-09T00:00:00", "is_visible": True})
        self.ui.show_all_memos()
        self.assertEqual(list(self.ui.memo_windows), ["memo-shown"])
        self.open_window("memo-0001")                       # 숨겨 둔 메모는 열 때 창이 만들어짐
        self.assertIn("memo-0001", self.ui.memo_windows)

    def test_new_memo_title_avoids_titles_of_closed_memos(self) -> None:
        self.sm.save_memo_locally({"id": "memo-named", "title": "새 메모", "content": "x",
                                   "updated_at": "2026-01-09T00:00:00", "is_visible": False})
        self.ui.create_empty_memo()
        self.ui.create_code_memo()
        titles = sorted(w.memo_data["title"] for w in self.ui.memo_windows.values())
        self.assertEqual(titles, ["새 메모 2", "코드 메모"])
        code = next(w for w in self.ui.memo_windows.values() if w.memo_data["is_code_memo"])
        self.assertEqual(code.memo_data["code_lang"], self.sm.settings["default_code_lang"])
        self.assertGreater(code.memo_data["width"], 400)

    def test_icons_are_cached(self) -> None:
        a = self.ui.get_theme_icon("memo.svg", False)
        self.assertFalse(a.isNull())
        self.assertIs(self.ui.get_theme_icon("memo.svg", False), a)
        self.assertIsNot(self.ui.get_theme_icon("memo.svg", True), a)                       # 색이 다르면 다른 아이콘
        self.assertIsNot(self.ui.get_theme_icon("memo.svg", False, override_color="#FF0000"), a)

    def test_settings_window_is_reused_while_open(self) -> None:
        self.ui.open_settings()
        first = self.ui.settings_window
        first.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        first.show()
        self.ui.open_settings()
        self.assertIs(self.ui.settings_window, first)
        first.close()
        self.ui.open_settings()
        self.assertIsNot(self.ui.settings_window, first)
        self.ui.settings_window.close()

    def test_arrange_keeps_windows_on_their_screen_and_modified_time(self) -> None:
        a, b = self.open_window("memo-0000"), self.open_window("memo-0001")
        before = a.memo_data["updated_at"]
        a.move(300, 300)
        b.move(300, 300)
        with mock.patch.object(self.ui, "_async_save_memos") as saved:
            self.ui.arrange_memos()
        self.assertEqual(len(saved.call_args[0][0]), 2)
        screen = _app.primaryScreen().availableGeometry()
        for w in (a, b):
            self.assertTrue(screen.contains(w.pos()), w.pos())
            self.assertEqual((w.memo_data["position_x"], w.memo_data["position_y"]), (w.x(), w.y()))
        self.assertNotEqual(a.pos(), b.pos())
        self.assertEqual(a.memo_data["updated_at"], before)          # 옮긴 것은 내용 수정이 아님

        a.toggle_rollup()
        self.assertTrue(a._is_rolled_up)
        self.assertFalse(a.content_container.isVisible())
        with mock.patch.object(self.ui, "_async_save_memos"):
            self.ui.arrange_rolled_up_memos()
        self.assertLessEqual(a.y() + a.height(), screen.bottom() + 1)
        a.toggle_rollup()
        self.assertFalse(a._is_rolled_up)
        self.assertTrue(a.content_container.isVisible())
        self.assertGreaterEqual(a.height(), 150)

    def test_wheel_does_not_change_memo_font_boxes(self) -> None:
        from PyQt6.QtCore import QPointF
        from PyQt6.QtGui import QWheelEvent
        w = self.open_window("memo-0000")
        for box in (w.font_box, w.size_box, w.code_lang_box):
            before = box.currentIndex()
            ev = QWheelEvent(QPointF(5, 5), QPointF(5, 5), QPoint(0, 0), QPoint(0, -120),
                             Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                             Qt.ScrollPhase.NoScrollPhase, False)
            _app.sendEvent(box, ev)
            self.assertEqual(box.currentIndex(), before)


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


    def test_tags_come_only_from_real_hashtags(self) -> None:
        self.sm.save_memo_locally({"id": "memo-code", "title": "c", "content": "#include <stdio.h>" + chr(10) + "#define X",
                                   "is_code_memo": True, "updated_at": "2026-01-09T00:00:00", "is_visible": False})
        self.sm.save_memo_locally({"id": "memo-tags", "title": "g", "content": "색 #FFFFFF 와 a#b 그리고 #회의 #todo",
                                   "updated_at": "2026-01-09T00:00:00", "is_visible": False})
        ex = self.explorer()
        ex.refresh()
        tags = [ex.tag_combo.itemText(i) for i in range(ex.tag_combo.count())]
        self.assertEqual(tags, ["#", "#tag0", "#tag1", "#tag2", "#todo", "#회의"])
        ex.tag_combo.setCurrentText("#회의")
        ex.refresh()
        self.assertEqual([m["id"] for m in ex.filtered_memos], ["memo-tags"])

    def test_favorite_column_uses_star_icons(self) -> None:
        ex = self.explorer()
        ex.refresh()
        header = ex.table.horizontalHeaderItem(1)
        self.assertEqual(header.text(), "★")
        row = self.row_of(ex, "memo-0000")
        btn = ex.table.cellWidget(row, 1).findChild(QPushButton)
        self.assertFalse(btn.icon().isNull())
        self.assertGreaterEqual(btn.width(), btn.iconSize().width() + 8)     # 아이콘 둘레에 여백이 있어 잘리지 않음
        for name in ("star_true.svg", "star_false.svg"):
            self.assertTrue((Path(__file__).resolve().parent.parent / "icons" / name).exists(), name)


class DesignStyleTest(UiTestCase):
    def _sheets(self, ex, win, w) -> list:
        return [ex.bg.styleSheet(), ex.table.styleSheet(), ex.pv.styleSheet(), ex.b_new.styleSheet(),
                win.styleSheet(), w.bg.styleSheet(), w.btn_bold.styleSheet()]

    def test_only_modern_and_neo_are_offered(self) -> None:
        win = sw.SettingsWindow(self.sm)
        self.assertEqual([win.ui_style_box.itemData(i) for i in range(win.ui_style_box.count())], ["modern", "neo"])
        self.assertEqual(win.ui_style_box.currentData(), "modern")

    def test_old_classic_setting_falls_back_to_modern(self) -> None:
        self.sm.settings["ui_style"] = "classic"
        win = sw.SettingsWindow(self.sm)
        self.assertEqual(win.ui_style_box.currentData(), "modern")
        ex = self.explorer()
        self.assertIn("Segoe UI", ex.bg.styleSheet())

    def test_switching_between_modern_and_neo(self) -> None:
        from ui.themes import DARK_THEMES, LIGHT_THEMES
        self.assertIn("mono", LIGHT_THEMES)
        self.assertIn("mono", DARK_THEMES)
        ex = self.explorer()
        ex.on_cell_click(0, 2)
        w = self.open_window("memo-0000")
        win = sw.SettingsWindow(self.sm)
        for sheet in self._sheets(ex, win, w):
            self.assertNotRegex(sheet, r"border-radius: [1-9]")
        self.assertEqual(ex.table.horizontalHeaderItem(3).text(), "수정일시")
        self.assertIn("Segoe UI", w.title_edit.styleSheet())
        modern_sheets = self._sheets(ex, win, w)[:4]
        modern_title = ex.title_label.styleSheet()

        win.ui_style_box.setCurrentIndex(win.ui_style_box.findData("neo"))
        self.assertEqual(win.light_theme_box.currentData(), "mono")     # 어울리는 색 테마를 함께 골라 줌
        self.assertEqual(win.dark_theme_box.currentData(), "mono")
        win.save()
        self.assertEqual(self.sm.settings["ui_style"], "neo")
        self.assertEqual(self.sm.settings["light_theme_mode"], "mono")
        self.assertIn(LIGHT_THEMES["mono"]["text"], ex.b_new.styleSheet())           # 주요 버튼은 잉크색
        self.assertIn("border-bottom: 2px solid", ex.btn_filter_all.styleSheet())   # 밑줄형 필터
        self.assertNotEqual(ex.title_label.styleSheet(), modern_title)
        for sheet in self._sheets(ex, win, w):
            self.assertNotRegex(sheet, r"border-radius: [1-9]")

        win.ui_style_box.setCurrentIndex(win.ui_style_box.findData("modern"))
        win.light_theme_box.setCurrentIndex(win.light_theme_box.findData("white"))
        win.save()
        self.assertEqual(self._sheets(ex, win, w)[:4], modern_sheets)
        self.assertEqual(ex.title_label.styleSheet(), modern_title)


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

    def test_lock_shortcut_cycles_through_states(self) -> None:
        w = self.open_window("memo-0000")
        w.text_edit.setPlainText("by shortcut")
        self.answers[:] = ["pw", "pw"]
        w.toggle_memo_lock()                                  # 일반 메모 → 암호 걸기
        self.assertTrue(self.disk("memo-0000")["is_locked"])
        w.toggle_memo_lock()                                  # 열린 암호 메모 → 잠그기
        self.assertTrue(w.memo_data.get("_locked"))
        self.answers[:] = ["pw"]
        w.toggle_memo_lock()                                  # 잠긴 메모 → 암호 입력
        self.assertEqual(w.text_edit.toPlainText(), "by shortcut")

    def test_change_password_while_locked_requires_old_password(self) -> None:
        w = self.lock()
        w.lock_now()
        self.answers[:] = ["wrong"]
        w.set_memo_password()
        self.assertIsNone(self.sm.unlock_memo("memo-0000", "wrong"))
        self.assertIn("top secret", self.sm.unlock_memo("memo-0000", "pw") or "")

    def test_explorer_manages_passwords_without_opening_the_memo(self) -> None:
        ex = self.explorer()
        for w in list(self.ui.memo_windows.values()):         # 창이 하나도 없는 상태에서 시작
            w._is_deleting = True
            w.close()
        self.ui.memo_windows.clear()
        memo = lambda: next(m for m in self.sm.load_local_memos() if m["id"] == "memo-0001")

        self.answers[:] = ["pw", "pw"]
        ex._lock_action(memo(), "set_memo_password")
        self.assertTrue(self.disk("memo-0001")["is_locked"])
        self.assertNotIn("body 1", self.raw("memo-0001"))
        self.assertFalse(self.ui.memo_windows["memo-0001"].isVisible())

        ex._lock_action(memo(), "lock_now")
        self.assertTrue(memo().get("_locked"))
        self.assertTrue(ex.table.item(self.row_of(ex, "memo-0001"), 2).text().startswith("🔒"))

        ex.table.setCurrentCell(self.row_of(ex, "memo-0001"), 2)
        self.answers[:] = ["pw"]
        ex._lock_action_on_current("toggle_memo_lock")       # 단축키: 잠금 해제
        self.assertIn("body 1", memo()["content"])

        ex._lock_action(memo(), "remove_memo_password")
        self.assertFalse(self.disk("memo-0001")["is_locked"])
        self.assertIn("body 1", self.disk("memo-0001")["content"])

    def test_explorer_menu_offers_actions_for_each_state(self) -> None:
        from PyQt6.QtWidgets import QMenu
        ex = self.explorer()

        def labels(memo: dict) -> list:
            menu = QMenu()
            ex._add_lock_menu(menu, memo)
            return [a.text() for a in menu.actions() if a.text()]

        plain = next(m for m in self.sm.load_local_memos() if m["id"] == "memo-0002")
        self.assertTrue(any("암호 걸기" in t for t in labels(plain)))
        w = self.lock("memo-0002")
        unlocked = next(m for m in self.sm.load_local_memos() if m["id"] == "memo-0002")
        texts = labels(unlocked)
        self.assertTrue(any("지금 잠그기" in t for t in texts) and any("암호 변경" in t for t in texts)
                        and any("암호 제거" in t for t in texts))
        w.lock_now()
        locked = next(m for m in self.sm.load_local_memos() if m["id"] == "memo-0002")
        self.assertTrue(any("잠금 해제" in t for t in labels(locked)))

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


    def test_wheel_does_not_change_options(self) -> None:
        from PyQt6.QtCore import QPointF
        from PyQt6.QtGui import QWheelEvent
        from PyQt6.QtWidgets import QAbstractSpinBox, QComboBox, QSlider
        win = sw.SettingsWindow(self.sm)
        targets = [w for kind in (QComboBox, QAbstractSpinBox, QSlider) for w in win.findChildren(kind)]
        self.assertGreater(len(targets), 8)

        def state(w):
            return w.currentIndex() if isinstance(w, QComboBox) else w.value()

        for w in targets:
            w.setFocus()                                   # 클릭해 둔 상태에서도 휠로는 바뀌지 않아야 함
            before = state(w)
            for delta in (-120, 120, -120):
                ev = QWheelEvent(QPointF(5, 5), QPointF(5, 5), QPoint(0, 0), QPoint(0, delta),
                                 Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                                 Qt.ScrollPhase.NoScrollPhase, False)
                _app.sendEvent(w, ev)
            self.assertEqual(state(w), before, type(w).__name__)
            self.assertEqual(w.focusPolicy(), Qt.FocusPolicy.StrongFocus)


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


class FormattingTest(UiTestCase):
    """메모 창의 서식 기능 (목록·들여쓰기·글꼴·저장 형식)."""

    def setUp(self) -> None:
        super().setUp()
        self.sm.save_memo_locally({"id": "memo-code", "title": "code", "content": "x", "is_code_memo": True,
                                   "code_lang": "PYTHON", "updated_at": "2026-01-09T00:00:00", "is_visible": False})
        self.w = self.open_window("memo-0000")
        self.te = self.w.text_edit

    def select(self, start: int, end: int, edit=None) -> None:
        edit = edit or self.te
        cur = edit.textCursor()
        cur.setPosition(start)
        cur.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        edit.setTextCursor(cur)

    def select_lines(self, first: int, last: int, edit=None) -> None:
        edit = edit or self.te
        doc = edit.document()
        last_block = doc.findBlockByNumber(last)
        self.select(doc.findBlockByNumber(first).position(), last_block.position() + last_block.length() - 1, edit)

    def at_line(self, line: int, edit=None) -> None:
        edit = edit or self.te
        pos = edit.document().findBlockByNumber(line).position()
        self.select(pos, pos, edit)

    def indents(self) -> list:
        doc = self.te.document()
        return [doc.findBlockByNumber(i).blockFormat().indent() for i in range(doc.blockCount())]

    def lists(self) -> list:
        doc = self.te.document()
        out = []
        for i in range(doc.blockCount()):
            block = doc.findBlockByNumber(i)
            lst = block.textList()
            if lst is None:
                out.append(None)
            else:
                kind = "disc" if lst.format().style() == QTextListFormat.Style.ListDisc else "num"
                out.append((kind, lst.format().indent(), lst.itemText(block)))
        return out

    def is_bold(self, pos: int) -> bool:
        cur = self.te.textCursor()
        cur.setPosition(pos)
        cur.setPosition(pos + 1, QTextCursor.MoveMode.KeepAnchor)
        return cur.charFormat().fontWeight() >= 600

    # 1) 글자 크기를 바꿔도 굵게·기울임이 유지
    def test_font_size_change_keeps_bold(self) -> None:
        self.te.setPlainText("bold word normal")
        self.select(0, 4)
        self.w.toggle_bold()
        self.assertTrue(self.is_bold(1))
        self.w.change_font_size("14")
        self.assertTrue(self.is_bold(1))
        self.assertFalse(self.is_bold(10))
        self.te.wheelEvent  # (Ctrl+휠도 같은 방식으로 크기만 바꿈)

    def test_bold_toggles_on_and_off(self) -> None:
        self.te.setPlainText("aaa bbb")
        self.select(0, 3)
        self.w.toggle_bold()
        self.assertTrue(self.is_bold(1))
        self.assertFalse(self.is_bold(5))
        self.select(0, 3)
        self.w.toggle_bold()
        self.assertFalse(self.is_bold(1))

    # 2) 코드 메모의 Tab 은 실제 공백
    def test_code_memo_tab_inserts_real_spaces(self) -> None:
        c = self.open_window("memo-code")
        ce = c.text_edit
        ce.setPlainText("def f():" + chr(10) + "return 1" + chr(10) + "pass")
        self.at_line(1, ce)
        ce.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Tab, Qt.KeyboardModifier.NoModifier, chr(9)))
        self.assertEqual(ce.toPlainText().split(chr(10))[1], "    return 1")
        self.select_lines(1, 2, ce)
        c.apply_indent()
        self.assertEqual(ce.toPlainText().split(chr(10)), ["def f():", "        return 1", "    pass"])
        self.select_lines(1, 2, ce)
        ce.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Backtab, Qt.KeyboardModifier.ShiftModifier))
        self.assertEqual(ce.toPlainText().split(chr(10)), ["def f():", "    return 1", "pass"])
        c.copy_all_content()
        self.assertIn("    return 1", _app.clipboard().text())

    # 3) 9) 여러 줄 들여쓰기는 줄마다 한 단계씩, 상한 8
    def test_multi_line_indent_keeps_relative_levels(self) -> None:
        self.te.setPlainText(chr(10).join(["a", "b", "c"]))
        self.at_line(1)
        self.w.apply_indent()
        self.w.apply_indent()
        self.select_lines(0, 2)
        self.w.apply_indent()
        self.assertEqual(self.indents(), [1, 3, 1])
        self.select_lines(0, 2)
        self.w.apply_outdent()
        self.assertEqual(self.indents(), [0, 2, 0])
        self.at_line(0)
        for _ in range(12):
            self.w.apply_indent()
        self.assertEqual(self.indents()[0], self.w.MAX_INDENT)

    # 4) 목록의 일부만 다른 종류로
    def test_list_style_changes_only_selected_lines(self) -> None:
        self.te.setPlainText(chr(10).join(["one", "two", "three"]))
        self.select_lines(0, 2)
        self.w.apply_number()
        self.assertEqual([x[0] for x in self.lists()], ["num", "num", "num"])
        self.at_line(1)
        self.w.apply_bullet()
        self.assertEqual([x[0] for x in self.lists()], ["num", "disc", "num"])
        self.at_line(1)
        self.w.apply_bullet()                       # 다시 누르면 그 줄만 목록 해제
        self.assertEqual([x and x[0] for x in self.lists()], ["num", None, "num"])

    def test_adjacent_lines_join_the_existing_list(self) -> None:
        self.te.setPlainText(chr(10).join(["one", "two", "three"]))
        self.at_line(0)
        self.w.apply_number()
        self.select_lines(1, 2)
        self.w.apply_number()
        self.assertEqual([x[2] for x in self.lists()], ["1.", "2.", "3."])

    # 5) 목록 항목의 Tab 은 하위 목록, Shift+Tab 은 원래 목록으로 복귀
    def test_tab_on_list_item_makes_a_sub_list(self) -> None:
        self.te.setPlainText(chr(10).join(["one", "two", "three", "four"]))
        self.select_lines(0, 3)
        self.w.apply_number()
        self.select_lines(1, 2)
        self.te.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Tab, Qt.KeyboardModifier.NoModifier, chr(9)))
        self.assertEqual(self.lists(), [("num", 1, "1."), ("num", 2, "1."), ("num", 2, "2."), ("num", 1, "2.")])
        self.assertEqual(self.indents(), [0, 0, 0, 0])
        self.select_lines(1, 2)
        self.w.apply_outdent()
        self.assertEqual([x[2] for x in self.lists()], ["1.", "2.", "3.", "4."])

    # 6) 선택 영역에만 글꼴을 바꾸면 메모 기본 글꼴은 그대로
    def test_partial_font_change_does_not_change_memo_default(self) -> None:
        from PyQt6.QtGui import QFont
        self.te.setPlainText("aaa bbb")
        before = self.w.memo_data.get("font_family")
        self.select(0, 3)
        self.w.change_font_family(QFont("Arial"))
        self.assertEqual(self.w.memo_data.get("font_family"), before)
        self.select(0, 0)
        self.w.change_font_family(QFont("Arial"))
        self.assertEqual(self.w.memo_data.get("font_family"), "Arial")

    # 7) 8) 버튼
    def test_toolbar_buttons_do_not_take_focus(self) -> None:
        for name in ("btn_bold", "btn_italic", "btn_underline", "btn_bullet", "btn_num", "btn_indent", "btn_outdent",
                     "btn_toggle_sub_fmt", "btn_fg_color", "btn_bg_color"):
            self.assertEqual(getattr(self.w, name).focusPolicy(), Qt.FocusPolicy.NoFocus, name)
        self.assertFalse(self.w.btn_indent.isCheckable())
        self.assertFalse(self.w.btn_outdent.isCheckable())
        self.assertTrue(self.w.btn_bold.isCheckable())

    def test_list_buttons_are_never_painted_as_active(self) -> None:
        self.te.setPlainText("item")
        for apply, btn in ((self.w.apply_bullet, self.w.btn_bullet), (self.w.apply_number, self.w.btn_num)):
            apply()
            self.w.update_toolbar_button_states()
            self.assertFalse(btn.isCheckable())
            self.assertFalse(btn.isChecked())
            self.assertIn("background: transparent", btn.styleSheet())

    # 저장 형식
    def test_plain_memo_is_stored_as_plain_text(self) -> None:
        self.te.setPlainText("hello <b>not a tag</b> & 1 < 2")
        self.w.manual_save()
        self.assertEqual(self.disk("memo-0000")["content"], "hello <b>not a tag</b> & 1 < 2")
        ex = self.explorer()
        ex.refresh()
        ex.on_cell_click(self.row_of(ex, "memo-0000"), 2)
        self.assertEqual(ex.pv.toPlainText(), "hello <b>not a tag</b> & 1 < 2")
        self.w.apply_data()                          # 다시 불러와도 글자 그대로
        self.assertEqual(self.te.toPlainText(), "hello <b>not a tag</b> & 1 < 2")

    def test_formatted_memo_is_stored_as_html_and_restored(self) -> None:
        self.te.setPlainText("bold rest")
        self.select(0, 4)
        self.w.toggle_bold()
        self.w.manual_save()
        self.assertTrue(self.disk("memo-0000")["content"].lstrip().startswith("<!DOCTYPE"))
        self.w.apply_data()
        self.assertTrue(self.is_bold(1))
        self.assertFalse(self.is_bold(6))

    def test_list_and_indent_count_as_formatting(self) -> None:
        self.te.setPlainText("item")
        self.w.apply_bullet()
        self.assertTrue(self.w._has_rich_formatting())
        self.w.apply_bullet()
        self.assertFalse(self.w._has_rich_formatting())
        self.w.apply_indent()
        self.assertTrue(self.w._has_rich_formatting())

    def test_code_memo_is_stored_as_plain_text_with_html_like_code_intact(self) -> None:
        c = self.open_window("memo-code")
        code = "<html><body>" + chr(10) + "    <p>List<int> x;</p>" + chr(10) + "</body></html>"
        c.text_edit.setPlainText(code)
        c.manual_save()
        self.assertEqual(self.disk("memo-code")["content"], code)
        c.apply_data()
        self.assertEqual(c.text_edit.toPlainText(), code)

    # 서식 조작은 바로 저장하지 않고 자동 저장에 맡김
    def test_formatting_does_not_save_immediately(self) -> None:
        self.te.setPlainText("text")
        self.w.manual_save()
        with mock.patch.object(self.sm, "save_memo_locally", wraps=self.sm.save_memo_locally) as spy:
            self.select(0, 4)
            self.w.toggle_bold()
            self.w.apply_bullet()
            self.w.apply_indent()
            self.assertEqual(spy.call_count, 0)
        self.assertTrue(self.w._auto_save_timer.isActive())
        self.w.close()
        self.assertTrue(self.disk("memo-0000")["content"].lstrip().startswith("<!DOCTYPE"))


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
