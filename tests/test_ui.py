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

from PyQt6.QtCore import QPoint, QRect, Qt
from PyQt6.QtGui import QKeyEvent, QTextCursor, QTextListFormat
from PyQt6.QtCore import QEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QDialog, QFileDialog, QInputDialog, QLabel, QMessageBox, QPushButton

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

import core.sync_manager as smm
import ui.settings_window as sw
import ui.screen_bounds as screen_bounds
import ui.ui_manager as uim
import ui.overlay as overlay
import ui.themed_dialog as themed_dialog
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


class StartupTest(UiTestCase):
    def test_starts_without_login_and_registers_hotkeys(self) -> None:
        self.assertEqual(len(self.ui.memo_windows), 0)     # 숨겨 둔 메모는 창을 미리 만들지 않음
        self.assertEqual(len(self.ui._hotkeys.registered), 7)


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

    def test_settings_panel_is_reused_while_open(self) -> None:
        self.ui.open_settings()
        first = self.ui.settings_window
        self.assertTrue(first.isVisible())
        self.ui.open_settings()
        self.assertIs(self.ui.settings_window, first)             # 이미 열려 있으면 새로 만들지 않음 (고치던 값 유지)
        self.ui.explorer_window.close_settings_panel()
        self.assertIsNone(self.ui.settings_window)
        self.ui.open_settings()
        self.assertIsNot(self.ui.settings_window, first)
        self.ui.explorer_window.close_settings_panel()

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


class ModifiedTimeTest(UiTestCase):
    """수정일시(updated_at)는 본문·제목을 실제로 고쳤을 때만 바뀝니다."""

    def type_into(self, w, text: str) -> None:
        cursor = w.text_edit.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(text)                      # 사용자가 친 것과 같은 편집

    def test_saving_without_changes_keeps_modified_time(self) -> None:
        w = self.open_window("memo-0000")
        before = self.disk("memo-0000")["updated_at"]
        w.manual_save()                              # Ctrl+S 만 누름
        w.toggle_rollup()
        w.toggle_rollup()
        w.apply_data()
        w.manual_save()
        w.close()
        self.assertEqual(self.disk("memo-0000")["updated_at"], before)

    def test_editing_text_updates_modified_time(self) -> None:
        w = self.open_window("memo-0000")
        before = self.disk("memo-0000")["updated_at"]
        self.type_into(w, " more")
        w.apply_data()                               # 저장 전에 화면이 다시 그려져도(테마 변경 등) '고침'이 유지됨
        w.manual_save()
        after = self.disk("memo-0000")
        self.assertIn("more", after["content"])
        self.assertGreater(after["updated_at"], before)

        w.manual_save()                              # 그 뒤 고친 것 없이 다시 저장
        self.assertEqual(self.disk("memo-0000")["updated_at"], after["updated_at"])

    def test_formatting_counts_as_an_edit_but_meta_changes_do_not(self) -> None:
        w = self.open_window("memo-0000")
        before = self.disk("memo-0000")["updated_at"]
        w.memo_data["code_theme"] = "light"
        w._mark_edited()                             # 속성만 바뀜
        w.manual_save()
        saved = self.disk("memo-0000")
        self.assertEqual(saved["updated_at"], before)
        self.assertGreater(saved["meta_updated_at"], before)

        w.text_edit.selectAll()
        w.toggle_bold()
        w.manual_save()
        self.assertGreater(self.disk("memo-0000")["updated_at"], before)

    def test_explorer_actions_keep_modified_time(self) -> None:
        ex = self.explorer()
        ex.refresh()
        before = self.disk("memo-0001")["updated_at"]
        memo = lambda: next(m for m in self.sm.load_local_memos() if m["id"] == "memo-0001")
        ex.toggle_fav(memo())
        ex.change_memo_color(memo(), "#DCFCE7")
        ex.move_memos_to_folder(memo(), "업무")
        ex.on_cell_click(self.row_of(ex, "memo-0001"), 2)        # 미리보기에 띄우기만 함
        ex._flush_preview_save()
        saved = self.disk("memo-0001")
        self.assertEqual(saved["updated_at"], before)
        self.assertEqual((saved["is_favorite"], saved["bg_color"], saved["folder"]), (True, "#DCFCE7", "업무"))
        self.assertGreater(saved["meta_updated_at"], before)

        ex.table.setCurrentCell(self.row_of(ex, "memo-0001"), 2)
        ex.on_cell_click(self.row_of(ex, "memo-0001"), 2)
        ex.pv.setPlainText(ex.pv.toPlainText() + " edited in preview")
        ex._flush_preview_save()
        self.assertGreater(self.disk("memo-0001")["updated_at"], before)

    def test_renaming_updates_modified_time(self) -> None:
        w = self.open_window("memo-0000")
        before = self.disk("memo-0000")["updated_at"]
        w.title_edit.setText("renamed")
        w._do_title_save()
        saved = self.disk("memo-0000")
        self.assertEqual(saved["title"], "renamed")
        self.assertGreater(saved["updated_at"], before)


class RolledStackTest(UiTestCase):
    """접은 메모가 한 줄로 쌓여 있을 때 그중 하나를 펴면, 나머지를 가리지 않게 쌓인 줄 옆에 펼쳐집니다."""

    AREA = QRect(0, 0, 1600, 900)

    def setUp(self) -> None:
        super().setUp()
        screen = mock.Mock(availableGeometry=lambda: QRect(self.AREA))
        patcher = mock.patch("ui.memo_window.QApplication.screenAt", return_value=screen)
        patcher.start()
        self.addCleanup(patcher.stop)

    def rolled(self, memo_id: str, x: int, y: int):
        w = self.open_window(memo_id)
        w.setGeometry(x, y, 300, 300)
        w.toggle_rollup()
        w.move(x, y)
        self.assertTrue(w._is_rolled_up)
        return w

    def test_stacked_on_the_left_opens_to_the_right_and_returns(self) -> None:
        a = self.rolled("memo-0000", 0, 700)
        b = self.rolled("memo-0001", 0, 700 + a.height())
        slot = (a.x(), a.y())
        a.toggle_rollup()                                         # 펴기
        self.assertFalse(a._is_rolled_up)
        self.assertEqual(a.x(), b.x() + b.width())                # 쌓인 줄의 오른쪽에 펼쳐짐
        self.assertFalse(a.geometry().intersects(b.geometry()))   # 남은 접은 메모를 가리지 않음
        a.toggle_rollup()                                         # 옮기지 않고 다시 접으면
        self.assertEqual((a.x(), a.y()), slot)                    # 원래 쌓여 있던 자리로

    def test_stacked_on_the_right_opens_to_the_left(self) -> None:
        a = self.rolled("memo-0000", 1300, 700)
        b = self.rolled("memo-0001", 1300, 700 + a.height())
        a.toggle_rollup()
        self.assertEqual(a.x() + a.width(), b.x())
        self.assertFalse(a.geometry().intersects(b.geometry()))

    def test_single_rolled_memo_opens_in_place(self) -> None:
        a = self.rolled("memo-0000", 0, 700)
        a.toggle_rollup()
        self.assertEqual(a.x(), 0)                                # 쌓인 줄이 아니면 제자리에서 펼침

    def test_rolling_up_always_returns_to_the_rolled_spot(self) -> None:
        a = self.rolled("memo-0000", 0, 700)
        self.rolled("memo-0001", 0, 700 + a.height())
        slot = (a.x(), a.y(), a.width())
        a.toggle_rollup()
        a.move(800, 200)                                          # 펼친 뒤 다른 곳으로 옮기고 크기도 바꿈
        a.resize(520, 410)
        a.toggle_rollup()
        self.assertEqual((a.x(), a.y(), a.width()), slot)         # 접으면 접힌 상태로 기억해 둔 자리와 너비로
        a.toggle_rollup()
        self.assertEqual((a.x(), a.y(), a.width(), a.height()), (800, 200, 520, 410))     # 펴면 펼친 상태의 자리와 크기로

    def test_rolled_and_unrolled_sizes_do_not_affect_each_other(self) -> None:
        a = self.open_window("memo-0000")
        a.setGeometry(500, 300, 400, 320)
        a.toggle_rollup()
        a.resize(250, a.height())                                 # 접은 메모의 너비를 줄임
        a.move(900, 600)
        a.toggle_rollup()
        self.assertEqual((a.x(), a.y(), a.width(), a.height()), (500, 300, 400, 320))     # 펼친 크기는 그대로
        a.resize(640, 480)                                        # 펼친 메모를 키워도
        a.toggle_rollup()
        self.assertEqual((a.x(), a.y(), a.width()), (900, 600, 250))                      # 접은 메모의 너비와 자리는 그대로
        saved = a.memo_data
        self.assertEqual((saved["rolled_position_x"], saved["rolled_position_y"], saved["rolled_width"]), (900, 600, 250))
        self.assertEqual((saved["position_x"], saved["position_y"], saved["unrolled_width"], saved["unrolled_height"]),
                         (500, 300, 640, 480))

    def test_geometry_survives_closing_and_reopening(self) -> None:
        a = self.open_window("memo-0000")
        a.setGeometry(500, 300, 400, 320)
        a.toggle_rollup()
        a.resize(260, a.height())
        a.move(900, 600)
        a.close()
        saved = self.disk("memo-0000")
        self.assertEqual((saved["rolled_position_x"], saved["rolled_position_y"], saved["rolled_width"]), (900, 600, 260))
        self.assertEqual((saved["position_x"], saved["position_y"], saved["unrolled_width"], saved["unrolled_height"]),
                         (500, 300, 400, 320))
        b = self.open_window("memo-0000")
        self.assertEqual((b._is_rolled_up, b.x(), b.y(), b.width()), (True, 900, 600, 260))
        b.toggle_rollup()
        self.assertEqual((b.x(), b.y(), b.width(), b.height()), (500, 300, 400, 320))


class ScreenBoundsTest(UiTestCase):
    """탐색기와 환경설정 창은 화면(작업 영역) 밖으로 나가지 않고 화면보다 커지지 않습니다."""

    AREA = QRect(100, 50, 1000, 700)

    def setUp(self) -> None:
        super().setUp()
        patcher = mock.patch.object(screen_bounds, "work_area", lambda widget, at=None: QRect(self.AREA))
        patcher.start()
        self.addCleanup(patcher.stop)

    def inside(self, w) -> bool:
        # 탐색기는 창 둘레에 투명한 여백이 있어, 눈에 보이는 테두리(그 여백을 뺀 영역)가 화면 안에 있으면 됩니다.
        m = getattr(w, "EDGE_MARGIN", 0)
        return self.AREA.contains(w.frameGeometry().adjusted(m, m, -m, -m))

    def visible(self, w) -> QRect:
        m = getattr(w, "EDGE_MARGIN", 0)
        return w.frameGeometry().adjusted(m, m, -m, -m)

    def test_clamp_rules(self) -> None:
        a = self.AREA
        self.assertEqual(screen_bounds.clamp_position(a, -500, -500, 300, 200), (100, 50))
        self.assertEqual(screen_bounds.clamp_position(a, 5000, 5000, 300, 200), (800, 550))
        self.assertEqual(screen_bounds.clamp_position(a, 400, 300, 300, 200), (400, 300))
        self.assertEqual(screen_bounds.clamp_position(a, 400, 300, 2000, 2000), (100, 50))   # 화면보다 크면 왼쪽 위에 맞춤

    def test_snap_rules(self) -> None:
        a = self.AREA                                            # x 100..1100, y 50..750
        snap = screen_bounds.snap_to_edges
        self.assertEqual(snap(a, 110, 300, 300, 200), (100, 300))            # 왼쪽 가장자리에 붙음
        self.assertEqual(snap(a, 790, 300, 300, 200), (800, 300))            # 오른쪽
        self.assertEqual(snap(a, 400, 40, 300, 200), (400, 50))              # 위
        self.assertEqual(snap(a, 400, 560, 300, 200), (400, 550))            # 아래
        self.assertEqual(snap(a, 108, 545, 300, 200), (100, 550))            # 모서리
        self.assertEqual(snap(a, 130, 300, 300, 200), (130, 300))            # 멀면 그대로

    def drag(self, w, start: QPoint, to: QPoint) -> None:
        press = mock.Mock(button=lambda: Qt.MouseButton.LeftButton,
                          globalPosition=lambda: mock.Mock(toPoint=lambda: QPoint(start)),
                          position=lambda: mock.Mock(y=lambda: 5, toPoint=lambda: QPoint(5, 5)))
        move = mock.Mock(globalPosition=lambda: mock.Mock(toPoint=lambda: QPoint(to)))
        w.mousePressEvent(press)
        w.mouseMoveEvent(move)

    def test_explorer_sticks_to_the_edge_and_comes_off_again(self) -> None:
        ex = self.explorer()
        ex.setGeometry(400, 100, 600, 500)
        m = ex.EDGE_MARGIN
        self.drag(ex, QPoint(500, 120), QPoint(195, 120))                     # 보이는 테두리가 왼쪽 끝 10px 앞까지
        self.assertEqual(self.visible(ex).left(), 100)                        # 보이는 테두리가 화면 끝에 딱 붙음
        self.assertEqual(ex.x(), 100 - m)                                     # 창의 투명한 여백은 화면 밖으로
        ex.mouseMoveEvent(mock.Mock(globalPosition=lambda: mock.Mock(toPoint=lambda: QPoint(260, 120))))
        self.assertEqual(ex.x(), 160)                                         # 더 끌면 자연스럽게 떨어짐
        ex.mouseMoveEvent(mock.Mock(globalPosition=lambda: mock.Mock(toPoint=lambda: QPoint(500, 60))))
        self.assertEqual(self.visible(ex).top(), 50)                          # 위쪽 가장자리에도 붙음
        ex._old_pos = None

    def test_memo_window_sticks_to_screen_edges(self) -> None:
        w = self.open_window("memo-0000")
        w.setGeometry(400, 300, 300, 200)
        with mock.patch("ui.memo_window.QApplication.screenAt", return_value=mock.Mock(availableGeometry=lambda: QRect(self.AREA))):
            self.drag(w, QPoint(450, 310), QPoint(840, 310))                  # 오른쪽 가장자리 근처로 (x=790)
            self.assertEqual(w.x(), 800)
            self.drag(w, QPoint(850, 310), QPoint(550, 310))
            self.assertEqual(w.x(), 500)                                      # 멀어지면 붙지 않음
        w._old_pos = None

    def test_explorer_stays_inside_and_is_not_larger_than_the_screen(self) -> None:
        ex = self.explorer()
        ex.setGeometry(-300, -200, 760, 620)
        ex._limit_to_screen()
        self.assertTrue(self.inside(ex), ex.geometry())
        self.assertEqual((ex.maximumWidth(), ex.maximumHeight()), (1030, 730))     # 보이는 부분이 화면 크기까지
        ex.setGeometry(-300, 100, 760, 620)
        ex._limit_to_screen()
        self.assertEqual(self.visible(ex).left(), self.AREA.left())                # 보이는 테두리가 화면 끝에 딱 닿음

        ex.setMaximumSize(16777215, 16777215)
        ex.setGeometry(900, 600, 2500, 1800)                     # 화면보다 큰 크기
        ex._limit_to_screen()
        self.assertTrue(ex.width() <= 1030 and ex.height() <= 730, ex.size())
        self.assertTrue(self.inside(ex), ex.geometry())

        # 끌어서 옮길 때도 화면 밖으로 나가지 않음
        ex.resize(760, 620)
        ex._old_pos = QPoint(500, 300)
        move = mock.Mock(globalPosition=lambda: mock.Mock(toPoint=lambda: QPoint(5000, 4000)))
        ex.mouseMoveEvent(move)
        self.assertTrue(self.inside(ex), ex.geometry())
        shown = self.visible(ex)
        self.assertEqual((shown.x() + shown.width(), shown.y() + shown.height()), (1100, 750))   # 오른쪽 아래 끝까지 붙음
        ex._old_pos = None

    def test_fixed_size_explorer_is_still_kept_on_screen(self) -> None:
        self.sm.save_settings({"explorer_fixed_size": True, "explorer_geom": [3000, 3000, 760, 620]})
        ex = self.explorer()
        ex.move(3000, 3000)
        ex.apply_size_settings()
        self.assertEqual((ex.width(), ex.height()), (760, 620))
        self.assertTrue(self.inside(ex), ex.geometry())

    def test_settings_window_is_frameless_and_snaps_like_the_explorer(self) -> None:
        win = sw.SettingsWindow(self.sm)
        self.assertTrue(win.windowFlags() & Qt.WindowType.FramelessWindowHint)     # Windows 기본 제목 줄을 쓰지 않음
        self.assertEqual(win.title_label.text(), "환경설정")
        self.assertFalse(win.btn_win_close.icon().isNull())
        win.setGeometry(400, 100, 600, 500)
        self.drag(win, QPoint(500, 110), QPoint(210, 110))
        self.assertEqual(win.x(), 100)                                            # 화면 왼쪽 끝에 딱 붙음 (투명 여백이 없는 창)
        win.mouseMoveEvent(mock.Mock(globalPosition=lambda: mock.Mock(toPoint=lambda: QPoint(5000, 5000))))
        self.assertEqual((win.x() + win.width(), win.y() + win.height()), (1100, 750))   # 화면 밖으로 나가지 않음
        win.mouseReleaseEvent(mock.Mock())
        self.assertIsNone(win._drag_start_cursor)
        closed = []
        win.closeEvent = lambda e: closed.append(True)
        win.btn_win_close.click()
        self.assertTrue(closed)

    def test_settings_window_stays_inside(self) -> None:
        win = sw.SettingsWindow(self.sm)
        win.setGeometry(-400, 2000, 3000, 2500)
        win._limit_to_screen()
        self.assertTrue(self.inside(win), win.geometry())
        self.assertLessEqual(win.width(), 1000)
        self.assertLessEqual(win.height(), 700)
        self.assertEqual((win.spin_explorer_width.maximum(), win.spin_explorer_height.maximum()), (1000, 700))


class FolderTest(UiTestCase):
    """탐색기의 폴더: 고른 폴더의 메모만 목록·태그·검색에 나타납니다."""

    def setUp(self) -> None:
        super().setUp()
        from core import folders
        self.folders = folders
        # memo-0000 → 업무, memo-0001 → 업무/프로젝트A, memo-0002 → 개인 (본문에 #tag0, #tag1, #tag2)
        for memo_id, folder in (("memo-0000", "업무"), ("memo-0001", "업무/프로젝트A"), ("memo-0002", "개인")):
            memo = self.disk(memo_id)
            memo["folder"] = folder
            self.sm.save_memo_locally(memo)
        self.sm.save_memo_locally({"id": "memo-none", "title": "loose", "content": "no folder #free",
                                   "updated_at": "2026-01-09T00:00:00", "is_visible": False})
        self.ex = self.explorer()
        self.ex.refresh()

    def ids(self) -> list:
        return sorted(m["id"] for m in self.ex.filtered_memos)

    def combo_items(self) -> list:
        c = self.ex.folder_combo
        return [(c.itemText(i).strip("　"), c.itemData(i)) for i in range(c.count()) if c.itemData(i) is not None]

    def tags(self) -> list:
        c = self.ex.tag_combo
        return [c.itemText(i) for i in range(c.count())]

    def test_dropdown_lists_new_folder_then_all_then_folders(self) -> None:
        items = self.combo_items()
        self.assertEqual([d for _, d in items],
                         ["/new", self.folders.ALL, "개인", "업무", "업무/프로젝트A", self.folders.UNFILED, "/delete_many"])
        self.assertEqual(items[1][0], "전체 메모")
        self.assertEqual(self.ex.folder_combo.itemText(4), "　프로젝트A")       # 하위 폴더는 들여쓰기
        self.assertEqual(self.ex.folder_combo.currentData(), self.folders.ALL)
        self.assertEqual(len(self.ids()), 4)

    def folder_order(self) -> list:
        return [d for _, d in self.combo_items() if not str(d).startswith("/") and d]

    def test_new_folders_keep_creation_order(self) -> None:
        for name in ("zeta", "alpha"):
            self.answers[:] = [name]
            self.ex.new_folder()
            self.ex.refresh()
        self.assertEqual(self.folder_order(), ["개인", "업무", "업무/프로젝트A", "zeta", "alpha"])   # 이름순이 아니라 만든 순서

    def test_reordering_applies_to_tabs_sidebar_and_dropdown(self) -> None:
        self.ex.move_folder("업무", "개인")                                      # 탭을 끌어 '개인' 앞에 놓은 것과 같음
        self.assertEqual(self.folder_order(), ["업무", "업무/프로젝트A", "개인"])  # 하위 폴더는 함께 따라감
        tops = [b.property("folder_path") for b in self.ex.folder_tab_buttons if not b.property("sub_tab")]
        self.assertEqual(tops, [self.folders.ALL, "업무", "개인", self.folders.UNFILED, "/new"])
        listed = [self.ex.folder_list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.ex.folder_list.count())]
        self.assertEqual(listed, [self.folders.ALL, "업무", "업무/프로젝트A", "개인", self.folders.UNFILED, "/new"])
        self.assertEqual(self.sm.settings["folders"], ["업무", "업무/프로젝트A", "개인"])   # 순서를 기억

        self.ex.move_folder("업무", None)                                        # 맨 뒤로
        self.assertEqual(self.folder_order(), ["개인", "업무", "업무/프로젝트A"])

        # 사이드바에서 항목을 끌어 놓은 경우: 화면에 놓인 순서대로 저장
        lst = self.ex.folder_list
        row = next(i for i in range(lst.count()) if lst.item(i).data(Qt.ItemDataRole.UserRole) == "업무")
        lst.insertItem(1, lst.takeItem(row))
        self.ex._on_sidebar_reordered()
        self.assertEqual(self.folder_order(), ["업무", "업무/프로젝트A", "개인"])

        # 하위 폴더끼리의 순서
        self.answers[:] = ["업무/회의록"]
        self.ex.new_folder()
        self.ex.refresh()
        self.ex.move_folder("업무/회의록", "업무/프로젝트A")
        self.assertEqual(self.folder_order(), ["업무", "업무/회의록", "업무/프로젝트A", "개인"])

    def test_tab_strip_pages_whole_buttons_when_it_overflows(self) -> None:
        for i in range(8):
            self.answers[:] = [f"폴더이름이긴것{i}"]
            self.ex.new_folder()
        self.ex.select_folder(self.folders.ALL)
        strip = self.ex.folder_tab_strip
        keys = [b.property("folder_path") for b in strip.tabs]
        self.assertEqual(len(keys), 13)

        strip.setFixedWidth(4000)
        strip.relayout()
        self.assertTrue(strip.btn_prev.isHidden() and strip.btn_next.isHidden())  # 다 들어가면 < > 없음
        self.assertEqual(strip.visible_keys(), keys)

        strip.setFixedWidth(420)
        strip.relayout()
        self.assertFalse(strip.btn_next.isHidden())
        first_page = strip.visible_keys()
        self.assertEqual(first_page, keys[:len(first_page)])
        self.assertTrue(0 < len(first_page) < len(keys))
        self.assertFalse(strip.btn_prev.isEnabled())
        shown_width = sum(b.sizeHint().width() for b in strip.tabs if not b.isHidden())
        self.assertLessEqual(shown_width, 420)                                    # 보이는 버튼은 잘리지 않음

        seen = list(first_page)
        for _ in range(20):
            if not strip.btn_next.isEnabled():
                break
            strip.btn_next.click()
            seen += [k for k in strip.visible_keys() if k not in seen]
        self.assertEqual(seen, keys)                                              # 넘기다 보면 모두 나옴
        self.assertEqual(strip.visible_keys()[-1], "/new")
        strip.btn_prev.click()
        self.assertTrue(strip.btn_next.isEnabled())

        self.ex.select_folder("폴더이름이긴것7")                                   # 고른 폴더는 보이는 쪽으로
        strip = self.ex.folder_tab_strip
        strip.setFixedWidth(420)
        strip.relayout("폴더이름이긴것7")
        self.assertIn("폴더이름이긴것7", strip.visible_keys())

    def test_sidebar_panel_is_added_on_the_left_without_moving_anything(self) -> None:
        ex = self.ex
        ex.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        ex.setGeometry(600, 100, 760, 620)
        ex.show()
        self.sm.save_settings({"folder_ui": "sidebar", "folder_sidebar_open": False})
        ex.refresh()
        _app.processEvents()
        watched = (ex.btn_folder, ex.title_label, ex.btn_app_theme, ex.btn_win_close, ex.table, ex.b_new, ex.pv)
        where = lambda: [(w.mapTo(ex, QPoint(0, 0)).x() + ex.x(), w.mapTo(ex, QPoint(0, 0)).y(), w.width(), w.height()) for w in watched]
        before = where()

        ex.btn_folder.click()                                                     # 폴더 목록 열기
        _app.processEvents()
        self.assertEqual(where(), before)                                         # 버튼·제목·표가 화면에서 제자리, 같은 크기
        list_left = ex.folder_list.mapTo(ex, QPoint(0, 0)).x() + ex.x()
        self.assertLess(list_left + ex.folder_list.width(), before[0][0])         # 목록은 그 왼쪽에 덧붙음
        self.assertGreater(ex.folder_list.height(), ex.table.height())            # 위에서 아래까지 세로로 길게

        ex.btn_folder.click()
        _app.processEvents()
        self.assertEqual(where(), before)

    def test_header_layout(self) -> None:
        """왼쪽에 [폴더][라이트/다크], 정가운데에 Memos, 오른쪽 끝에 창 버튼."""
        ex = self.ex
        ex.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        ex.setGeometry(100, 100, 900, 620)
        ex.show()
        x_of = lambda w: w.mapTo(ex.bg, QPoint(0, 0)).x()
        for mode in ("tabs", "sidebar", "dropdown"):
            self.sm.save_settings({"folder_ui": mode, "folder_sidebar_open": False})
            ex.refresh()
            _app.processEvents()
            title_center = x_of(ex.title_label) + ex.title_label.width() / 2
            self.assertLessEqual(abs(title_center - ex.bg.width() / 2), 2, mode)             # Memos 는 정가운데
            left_group = [w for w in (ex.btn_folder, ex.folder_combo, ex.btn_app_theme) if not w.isHidden()]
            self.assertEqual(x_of(left_group[0]), x_of(ex.table), mode)                       # 왼쪽 묶음은 왼쪽 끝에서 시작
            self.assertIs(left_group[-1], ex.btn_app_theme)                                   # 폴더 다음에 라이트/다크
            for a, b in zip(left_group, left_group[1:]):
                self.assertLess(x_of(a) + a.width(), x_of(b) + 1, mode)
            self.assertLess(x_of(ex.btn_app_theme) + ex.btn_app_theme.width(), x_of(ex.title_label), mode)
            self.assertEqual(x_of(ex.btn_win_close) + ex.btn_win_close.width(), x_of(ex.table) + ex.table.width(), mode)

    def test_sidebar_adds_width_on_the_left_and_keeps_explorer_size(self) -> None:
        ex = self.ex
        ex.setGeometry(600, 100, 760, 620)
        font_before, content_before = ex.ui_font_pt, ex.content_width()
        self.sm.save_settings({"folder_ui": "sidebar", "folder_sidebar_open": True})
        ex.refresh()
        extra = ex.SIDEBAR_WIDTH + ex.SIDEBAR_GAP
        self.assertEqual((ex.width(), ex.x()), (760 + extra, 600 - extra))        # 왼쪽으로 늘어남
        self.assertEqual(ex.content_width(), content_before)                      # 탐색기 본래 너비는 그대로
        self.assertEqual(ex.ui_font_pt, font_before)                              # 글자 크기도 그대로

        ex.btn_folder.click()                                                     # 닫으면 원래대로
        self.assertEqual((ex.width(), ex.x(), ex.ui_font_pt), (760, 600, font_before))
        ex.btn_folder.click()
        ex.close()
        self.assertEqual(self.sm.settings["explorer_geom"], [600, 100, 760, 620]) # 저장되는 크기는 본래 크기

    def test_selecting_a_folder_filters_list_tags_and_search(self) -> None:
        self.ex.select_folder("업무")
        self.assertEqual(self.ids(), ["memo-0000", "memo-0001"])                 # 하위 폴더 포함
        self.assertEqual(self.tags(), ["#", "#tag0", "#tag1"])                   # 태그도 그 폴더 것만
        self.assertIn("총 2개", self.ex.stat_label.text())
        self.ex.select_folder("업무/프로젝트A")
        self.assertEqual(self.ids(), ["memo-0001"])
        self.ex.select_folder(self.folders.UNFILED)
        self.assertEqual(self.ids(), ["memo-none"])
        self.assertEqual(self.tags(), ["#", "#free"])

        self.ex.select_folder("업무")
        self.ex.s_type.setCurrentIndex(1)                                        # 내용 검색
        self.ex.s_in.setText("body 2")                                           # '개인' 폴더의 메모
        self.ex.refresh()
        self.assertEqual(self.ids(), [])
        self.ex.s_in.setText("body 1")
        self.ex.refresh()
        self.assertEqual(self.ids(), ["memo-0001"])
        self.ex.s_in.setText("")

        self.assertEqual(self.sm.settings["explorer_folder"], "업무")           # 다음에 열 때도 같은 폴더
        self.ex.select_folder(self.folders.ALL)
        self.assertEqual(len(self.ids()), 4)

    def test_move_memos_with_the_context_menu_action(self) -> None:
        before = self.disk("memo-0002")["updated_at"]
        self.ex.move_memos_to_folder(self.disk("memo-0002"), "업무")
        moved = self.disk("memo-0002")
        self.assertEqual(moved["folder"], "업무")
        self.assertEqual(moved["updated_at"], before)                             # 수정일시는 그대로
        self.assertGreater(moved["meta_updated_at"], before)                      # 다른 기기에는 이 값으로 전해짐
        self.ex.move_memos_to_folder(self.disk("memo-0002"), "")
        self.assertEqual(self.disk("memo-0002")["folder"], "")

        self.answers[:] = [" 업무 / 회의록 "]
        self.ex.move_memos_to_folder(self.disk("memo-none"), None)               # 새 폴더로 이동
        self.assertEqual(self.disk("memo-none")["folder"], "업무/회의록")
        self.assertIn("업무/회의록", self.sm.settings["folders"])

        # 체크해 둔 메모가 있으면 함께 옮김
        self.ex.select_folder(self.folders.ALL)
        for r in range(self.ex.table.rowCount()):
            if self.ex.table.item(r, 2).data(Qt.ItemDataRole.UserRole)["id"] in ("memo-0000", "memo-0001"):
                self.ex.table.item(r, 0).setCheckState(Qt.CheckState.Checked)
        self.ex.move_memos_to_folder(self.disk("memo-0002"), "개인")
        self.assertEqual([self.disk(i)["folder"] for i in ("memo-0000", "memo-0001", "memo-0002")], ["개인"] * 3)

    def test_open_window_keeps_the_new_folder(self) -> None:
        w = self.open_window("memo-0002")
        self.ex.move_memos_to_folder(self.disk("memo-0002"), "업무")
        w.text_edit.setPlainText("edited after move")
        w.manual_save()
        self.assertEqual(self.disk("memo-0002")["folder"], "업무")              # 창이 예전 폴더로 되돌리지 않음

    def test_new_memo_goes_into_the_selected_folder(self) -> None:
        self.ex.select_folder("업무/프로젝트A")
        self.ui.create_empty_memo()
        new = next(w for w in self.ui.memo_windows.values() if w.memo_data.get("is_draft"))
        self.assertEqual(new.memo_data["folder"], "업무/프로젝트A")
        self.ex.select_folder(self.folders.ALL)
        self.ui.create_code_memo()
        code = next(w for w in self.ui.memo_windows.values() if w.memo_data.get("is_code_memo"))
        self.assertNotIn("folder", code.memo_data)

    def test_new_rename_and_delete_folder(self) -> None:
        self.answers[:] = ["개인/여행"]
        self.ex.new_folder()
        self.ex.refresh()
        self.assertIn("개인/여행", [d for _, d in self.combo_items()])           # 메모가 없어도 목록에 남음
        self.assertEqual(self.ex.current_folder, "개인/여행")

        self.ex.select_folder("업무")
        self.answers[:] = ["회사"]
        self.ex.rename_folder()
        self.ex.refresh()
        self.assertEqual(self.disk("memo-0000")["folder"], "회사")
        self.assertEqual(self.disk("memo-0001")["folder"], "회사/프로젝트A")    # 하위 폴더도 함께
        self.assertEqual(self.ex.current_folder, "회사")
        self.assertNotIn("업무", [d for _, d in self.combo_items()])

        self.ex.delete_folder()
        self.ex.refresh()
        self.assertEqual(self.disk("memo-0000")["folder"], "")
        self.assertEqual(self.disk("memo-0001")["folder"], "")
        self.assertTrue((self.memo_dir / "memo-0000.json").exists())              # 메모는 지워지지 않음
        self.assertEqual(self.ex.current_folder, self.folders.ALL)
        self.assertNotIn("회사", [d for _, d in self.combo_items()])

    def tab(self, path: str):
        return next(b for b in self.ex.folder_tab_buttons if b.property("folder_path") == path)

    def shown(self) -> dict:
        ex = self.ex
        return {"tabs": not ex.folder_tabs.isHidden(), "list": not ex.folder_list.isHidden(),
                "button": not ex.btn_folder.isHidden(), "combo": not ex.folder_combo.isHidden()}

    def test_three_ways_to_pick_a_folder(self) -> None:
        only = lambda **on: {**{"tabs": False, "list": False, "button": False, "combo": False}, **on}
        self.assertEqual(self.sm.settings["folder_ui"], "tabs")                  # 기본은 탭 줄
        self.assertEqual(self.shown(), only(tabs=True))

        win = sw.SettingsWindow(self.sm)
        self.assertEqual([win.folder_ui_box.itemData(i) for i in range(win.folder_ui_box.count())],
                         ["tabs", "sidebar", "dropdown"])
        for mode, expected in (("sidebar", only(list=True, button=True)), ("dropdown", only(combo=True)),
                               ("tabs", only(tabs=True))):
            win.folder_ui_box.setCurrentIndex(win.folder_ui_box.findData(mode))
            win.save()
            self.assertEqual(self.sm.settings["folder_ui"], mode)
            self.assertEqual(self.shown(), expected, mode)

    def test_tab_row_selects_folders_and_shows_subfolders(self) -> None:
        top = [b.property("folder_path") for b in self.ex.folder_tab_buttons if not b.property("sub_tab")]
        self.assertEqual(top, [self.folders.ALL, "개인", "업무", self.folders.UNFILED, "/new"])
        self.assertTrue(self.tab(self.folders.ALL).isChecked())
        self.assertFalse(any(b.property("sub_tab") for b in self.ex.folder_tab_buttons))   # 하위 폴더 줄 없음

        self.tab("업무").click()
        self.assertEqual(self.ids(), ["memo-0000", "memo-0001"])
        subs = [(b.text(), b.property("folder_path"), b.isChecked()) for b in self.ex.folder_tab_buttons if b.property("sub_tab")]
        self.assertEqual(subs, [("전체", "업무", True), ("프로젝트A", "업무/프로젝트A", False)])
        self.tab("업무/프로젝트A").click()
        self.assertEqual(self.ids(), ["memo-0001"])
        self.assertTrue(self.tab("업무").isChecked())                             # 윗줄은 상위 폴더가 선택된 채
        self.tab("개인").click()
        self.assertFalse(any(b.property("sub_tab") for b in self.ex.folder_tab_buttons))

        self.answers[:] = ["개인/여행"]
        self.tab("/new").click()
        self.assertEqual(self.ex.current_folder, "개인/여행")

    def test_sidebar_button_shows_current_folder_and_toggles_the_list(self) -> None:
        self.sm.save_settings({"folder_ui": "sidebar"})
        self.ex.refresh()
        self.assertEqual(self.ex.btn_folder.text().strip(), "전체 메모")
        self.assertFalse(self.ex.btn_folder.icon().isNull())
        rows = [self.ex.folder_list.item(i) for i in range(self.ex.folder_list.count())]
        self.assertEqual([r.data(Qt.ItemDataRole.UserRole) for r in rows],
                         [self.folders.ALL, "개인", "업무", "업무/프로젝트A", self.folders.UNFILED, "/new"])
        self.assertIn("(2)", rows[2].text())                                      # 하위 폴더의 메모까지 센 개수
        self.assertIn("(4)", rows[0].text())

        self.ex.folder_list.itemClicked.emit(rows[3])
        self.assertEqual(self.ids(), ["memo-0001"])
        # 버튼에 지금 폴더 이름. 자리가 모자라면 줄여(…) 보여 주고, 온전한 이름은 풍선 도움말에 둡니다.
        self.assertTrue(self.ex.btn_folder.toolTip().startswith("업무/프로젝트A"))
        self.assertTrue(self.ex.btn_folder.text().strip().startswith("업무"))
        self.assertEqual(self.ex.folder_list.currentItem().data(Qt.ItemDataRole.UserRole), "업무/프로젝트A")

        self.ex.btn_folder.click()                                                # 목록 닫기
        self.assertTrue(self.ex.folder_list.isHidden())
        self.assertFalse(self.ex.btn_folder.isHidden())
        self.assertFalse(self.sm.settings["folder_sidebar_open"])
        self.ex.btn_folder.click()
        self.assertFalse(self.ex.folder_list.isHidden())

    def test_settings_from_another_device_update_open_windows(self) -> None:
        w = self.open_window("memo-0000")
        win = sw.SettingsWindow(self.sm)
        self.ui.settings_window = win
        win.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        win.show()
        self.sm.apply_remote_settings({"updated_at": "2099-01-01T00:00:00", "settings": {
            "ui_style": "neo", "folder_ui": "sidebar", "folders": ["업무", "개인", "새폴더"],
            "shortcuts": {"toggle_rollup": "Ctrl+Alt+M"}}})
        self.assertEqual(self.folder_order(), ["업무", "업무/프로젝트A", "개인", "새폴더"])   # 폴더 목록과 순서
        self.assertFalse(self.ex.btn_folder.isHidden())                                       # 폴더 표시 방식
        self.assertIn("border-bottom: 2px solid", self.ex.btn_filter_all.styleSheet())        # 디자인 스타일
        self.assertEqual(win.ui_style_box.currentData(), "neo")                               # 열려 있던 환경설정 화면도 새 값
        self.assertEqual(win.folder_ui_box.currentData(), "sidebar")
        self.assertEqual(self.sm.settings["shortcuts"]["toggle_rollup"], "Ctrl+Alt+M")
        self.assertTrue(w.isVisible())
        win.close()

    def test_delete_several_folders_at_once(self) -> None:
        for name in ("여행", "독서", "개인/일기"):
            self.answers[:] = [name]
            self.ex.new_folder()
        self.ex.select_folder("업무/프로젝트A")
        # 상위(업무)와 그 하위를 함께 고르고, 없는 폴더도 섞여 있음
        self.assertTrue(self.ex.delete_folders(["업무", "업무/프로젝트A", "여행", "없는폴더"]))
        self.assertEqual(self.folder_order(), ["개인", "개인/일기", "독서"])
        self.assertEqual([self.disk(i)["folder"] for i in ("memo-0000", "memo-0001", "memo-0002")], ["", "", "개인"])
        self.assertTrue((self.memo_dir / "memo-0000.json").exists())              # 메모는 지워지지 않음
        self.assertEqual(self.ex.current_folder, self.folders.ALL)                # 보던 폴더가 사라지면 전체로
        self.assertEqual(self.sm.settings["folders"], ["개인", "독서", "개인/일기"])

        self.ex.select_folder("개인")
        self.assertTrue(self.ex.delete_folders(["독서"]))
        self.assertEqual(self.ex.current_folder, "개인")                  # 다른 폴더를 지우면 보던 폴더 유지
        self.assertFalse(self.ex.delete_folders([]))
        self.assertFalse(self.ex.delete_folders(["없는폴더"]))

    def test_folder_pick_dialog(self) -> None:
        from ui.dialogs import FolderPickDialog
        names = ["개인", "업무", "업무/A", "업무/A/깊이", "여행"]
        dlg = FolderPickDialog(self.ex, names, {"업무": 3}, preselect=["여행"])
        ok = dlg.buttons.button(dlg.buttons.StandardButton.Ok)
        self.assertEqual(dlg.selected(), ["여행"])
        self.assertIn("(3)", dlg.list.item(1).text())
        dlg.list.item(1).setCheckState(Qt.CheckState.Checked)                     # 상위를 고르면 하위도 함께
        self.assertEqual(dlg.selected(), ["업무", "업무/A", "업무/A/깊이", "여행"])
        dlg._set_all(Qt.CheckState.Unchecked)
        self.assertEqual(dlg.selected(), [])
        self.assertFalse(ok.isEnabled())                                          # 고른 것이 없으면 삭제 버튼 꺼짐
        dlg._set_all(Qt.CheckState.Checked)
        self.assertEqual(dlg.selected(), names)
        self.assertTrue(ok.isEnabled())

        # 창에서 고른 것이 그대로 삭제됨
        with mock.patch.object(FolderPickDialog, "exec", lambda d: (d._set_all(Qt.CheckState.Checked), QDialog.DialogCode.Accepted)[1]):
            self.ex.pick_and_delete_folders([])
        self.assertEqual(self.folder_order(), [])
        self.assertEqual(self.disk("memo-0001")["folder"], "")

    def test_management_entries_depend_on_selection(self) -> None:
        actions = lambda: [d for _, d in self.combo_items() if str(d).startswith("/") and d != self.folders.UNFILED]
        self.assertEqual(actions(), ["/new", "/delete_many"])
        self.ex.select_folder("개인")
        self.assertEqual(actions(), ["/new", "/rename", "/delete", "/delete_many"])          # 새 폴더는 맨 위, 나머지는 맨 아래
        self.assertEqual(self.combo_items()[0][1], "/new")
        self.answers[:] = []                                                      # 이름 입력을 취소
        self.ex._on_folder_picked(self.ex.folder_combo.findData("/new"))
        self.assertEqual(self.ex.folder_combo.currentData(), "개인")             # 선택 표시는 원래 폴더로


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
