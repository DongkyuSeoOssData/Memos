"""환경설정: 탐색기 옆 패널로 열기, 저장하지 않은 변경, 설정 표, 화면 구성, 단축키 범위."""
import pathlib
import unittest
from unittest import mock

from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtWidgets import QLabel

# support 를 먼저 가져와야 합니다. (offscreen 설정과 프로젝트 경로)
import support


class SettingsPanelTest(support.UiTestCase):
    """환경설정은 탐색기 옆에 붙는 패널로 열립니다."""

    def test_settings_opens_as_a_panel_inside_the_explorer(self) -> None:
        ex = self.explorer()
        ex.move(300, 200)
        ex.resize(700, 600)
        support.app.processEvents()
        before = ex.geometry()
        content = ex.content_width()
        table_left = ex.table.mapToGlobal(QPoint(0, 0)).x()
        self.ui.open_settings()
        support.app.processEvents()
        panel = self.ui.settings_window
        self.assertIs(panel, ex.settings_panel)
        self.assertIs(panel.window(), ex)                            # 따로 뜬 창이 아니라 탐색기 창의 일부
        self.assertTrue(ex.bg.isAncestorOf(panel) and panel.isVisible())
        extra = ex.SETTINGS_WIDTH + ex.SIDEBAR_GAP
        self.assertEqual((ex.x(), ex.y(), ex.width(), ex.height()), (before.x(), before.y(), before.width() + extra, before.height()))
        self.assertEqual(ex.content_width(), content)                # 탐색기 본래 영역의 크기와 자리는 그대로
        self.assertEqual(ex.table.mapToGlobal(QPoint(0, 0)).x(), table_left)
        self.assertGreater(panel.mapTo(ex, QPoint(0, 0)).x(), ex.table.mapTo(ex, QPoint(0, 0)).x())     # 오른쪽에 붙음
        self.assertTrue(panel.btn_win_min.isHidden() and panel.grip.isHidden())
        self.assertIn("border: none", panel.styleSheet())

        panel.btn_win_close.click()                                  # 패널의 닫기는 패널만 닫음
        support.app.processEvents()
        self.assertTrue(ex.isVisible())
        self.assertIsNone(ex.settings_panel)
        self.assertEqual(ex.geometry(), before)

    def test_settings_panel_goes_left_when_there_is_no_room_on_the_right(self) -> None:
        ex = self.explorer()
        ex.resize(700, 600)
        ex.move(4000 - ex.width(), 200)
        support.app.processEvents()
        right_edge = ex.x() + ex.width()
        table_left = ex.table.mapToGlobal(QPoint(0, 0)).x()
        self.ui.open_settings()
        support.app.processEvents()
        panel = ex.settings_panel
        self.assertEqual(ex._settings_side, "left")
        self.assertEqual(ex.x() + ex.width(), right_edge)            # 오른쪽 끝은 그대로, 왼쪽으로 늘어남
        self.assertEqual(ex.table.mapToGlobal(QPoint(0, 0)).x(), table_left)
        self.assertLess(panel.mapTo(ex, QPoint(0, 0)).x(), ex.table.mapTo(ex, QPoint(0, 0)).x())
        ex.close_settings_panel()
        self.assertEqual(ex.x() + ex.width(), right_edge)

    def test_settings_panel_closes_with_the_explorer_and_is_not_saved_into_its_size(self) -> None:
        ex = self.explorer()
        ex.move(300, 200)
        ex.resize(700, 600)
        support.app.processEvents()
        self.ui.open_settings()
        ex.close()
        support.app.processEvents()
        self.assertIsNone(ex.settings_panel)
        self.assertIsNone(self.ui.settings_window)
        self.assertEqual(self.sm.settings["explorer_geom"][2:], [700, 600])     # 패널 너비가 탐색기 크기로 저장되지 않음
        ex.show()
        self.assertEqual(ex.width(), 700)

        self.ui.open_settings()
        ex.hide()                                                    # Alt+W 로 숨겨도 닫힘
        support.app.processEvents()
        self.assertIsNone(ex.settings_panel)

    def test_opening_settings_from_the_tray_brings_up_the_explorer(self) -> None:
        self.assertIsNone(self.ui.explorer_window)
        self.ui.open_settings()                                      # 탐색기가 닫혀 있어도
        ex = self.ui.explorer_window
        self.assertTrue(ex.isVisible() and ex.settings_open())       # 탐색기와 함께 열림

    def test_saving_in_the_panel_keeps_it_open_and_the_size_right(self) -> None:
        ex = self.explorer()
        ex.resize(700, 600)
        support.app.processEvents()
        self.ui.open_settings()
        panel = ex.settings_panel
        content = ex.content_width()
        panel.save()
        support.app.processEvents()
        self.assertIs(ex.settings_panel, panel)
        self.assertTrue(panel.isVisible() and panel.toast.isVisible())
        self.assertEqual(ex.content_width(), content)
        self.assertEqual(ex.width(), content + ex.SETTINGS_WIDTH + ex.SIDEBAR_GAP)

    def test_folder_sidebar_and_settings_panel_work_together(self) -> None:
        self.sm.save_settings({"folder_ui": "sidebar", "folder_sidebar_open": True})
        ex = self.explorer()
        ex.resize(ex.width(), 600)
        ex.move(900, 200)
        ex.refresh()
        support.app.processEvents()
        content, sidebar = ex.content_width(), ex._sidebar_extra
        self.assertGreater(sidebar, 0)
        self.ui.open_settings()
        self.assertEqual(ex.content_width(), content)
        self.assertEqual(ex.width(), content + sidebar + ex.SETTINGS_WIDTH + ex.SIDEBAR_GAP)
        ex.toggle_folder_sidebar()                                   # 패널이 열린 채로 사이드바를 접어도
        self.assertEqual(ex.content_width(), content)
        self.assertTrue(ex.settings_open())
        ex.close_settings_panel()
        self.assertEqual(ex.width(), content)

    def test_explorer_has_a_settings_button_above_the_preview(self) -> None:
        ex = self.explorer()
        support.app.processEvents()
        self.assertFalse(ex.btn_settings.icon().isNull())
        self.assertLess(ex.btn_settings.mapTo(ex, QPoint(0, 0)).y(), ex.pv.mapTo(ex, QPoint(0, 0)).y())
        ex.btn_settings.click()
        self.assertTrue(ex.settings_open() and self.ui.settings_window.isVisible())

    def test_settings_button_sits_left_of_the_title_and_toggles(self) -> None:
        ex = self.explorer()
        support.app.processEvents()
        title = next(label for label in ex.findChildren(QLabel) if label.text() == "미리보기")
        self.assertLess(ex.btn_settings.mapTo(ex, QPoint(0, 0)).x(), title.mapTo(ex, QPoint(0, 0)).x())
        ex.btn_settings.click()
        self.assertTrue(ex.settings_open())
        ex.btn_settings.click()                                      # 열려 있을 때 누르면 닫힘
        self.assertFalse(ex.settings_open())
        ex.btn_settings.click()
        self.assertTrue(ex.settings_open() and self.ui.settings_window.isVisible())


class UnsavedSettingsTest(support.UiTestCase):
    """환경설정에서 바꾸고 저장하지 않은 채 닫으려 하면 저장할지 묻습니다."""

    def setUp(self) -> None:
        super().setUp()
        self.ex = self.explorer()
        self.ex.resize(720, 640)
        self.ui.open_settings()
        self.panel = self.ex.settings_panel
        support.app.processEvents()

    def change(self) -> None:
        self.panel.spin_relock_min.setValue(self.panel.spin_relock_min.value() + 3)

    def test_untouched_settings_close_without_asking(self) -> None:
        self.assertFalse(self.panel.is_dirty())
        self.assertNotIn("●", self.panel.sb.text())
        self.ex.move(self.ex.x() + 40, self.ex.y() + 30)             # 탐색기를 옮기는 것은 설정을 바꾼 것이 아님
        self.assertFalse(self.panel.is_dirty())
        self.panel.btn_win_close.click()
        self.assertEqual(self.choices_asked, [])
        self.assertFalse(self.ex.settings_open())

    def test_changing_marks_the_save_button_and_reverting_clears_it(self) -> None:
        before = self.panel.spin_relock_min.value()
        self.change()
        self.assertTrue(self.panel.is_dirty())
        self.assertIn("●", self.panel.sb.text())
        self.panel.spin_relock_min.setValue(before)                   # 되돌리면 바뀐 것이 없는 것으로
        self.assertFalse(self.panel.is_dirty())
        self.assertNotIn("●", self.panel.sb.text())
        for toggle in (self.panel.cb_global_hotkeys, self.panel.cb_default_pin):
            toggle.setChecked(not toggle.isChecked())
            self.assertTrue(self.panel.is_dirty())
            toggle.setChecked(not toggle.isChecked())
        self.panel.url_input.setText("https://example.invalid/x")
        self.assertIn("●", self.panel.sb.text())

    def test_saving_clears_the_mark(self) -> None:
        self.change()
        self.panel.save()
        self.assertFalse(self.panel.is_dirty())
        self.assertNotIn("●", self.panel.sb.text())
        self.panel.btn_win_close.click()
        self.assertEqual(self.choices_asked, [])

    def test_cancel_keeps_everything_open(self) -> None:
        self.change()
        self.choice_answer = None
        value = self.panel.spin_relock_min.value()
        self.panel.btn_win_close.click()                             # 패널의 닫기
        self.ex.btn_settings.click()                                 # 톱니바퀴
        self.ui.toggle_explorer()                                    # Alt+W
        self.ex.close()                                              # 탐색기 닫기
        support.app.processEvents()
        self.assertEqual(len(self.choices_asked), 4)
        self.assertTrue(self.ex.isVisible() and self.ex.settings_open())
        self.assertEqual(self.panel.spin_relock_min.value(), value)   # 고치던 값도 그대로

    def test_save_and_close(self) -> None:
        self.change()
        wanted = self.panel.spin_relock_min.value()
        self.choice_answer = "save"
        self.ex.close()
        support.app.processEvents()
        self.assertEqual(self.choices_asked, ["저장하지 않은 변경이 있습니다"])
        self.assertFalse(self.ex.isVisible())
        self.assertEqual(self.sm.settings["locked_memo_relock_min"], wanted)

    def test_discard_and_close(self) -> None:
        before = self.sm.settings.get("locked_memo_relock_min", 5)
        self.change()
        self.choice_answer = "discard"
        self.ui.toggle_explorer()
        support.app.processEvents()
        self.assertFalse(self.ex.isVisible())
        self.assertEqual(self.sm.settings.get("locked_memo_relock_min", 5), before)
        self.assertEqual(len(self.choices_asked), 1)

    def test_quitting_asks_too(self) -> None:
        self.change()
        with mock.patch.object(support.uim.QApplication, "quit") as quit_app:
            self.choice_answer = None
            self.ui.quit_app()
            quit_app.assert_not_called()                             # 취소하면 끝내지 않음
            self.choice_answer = "save"
            wanted = self.panel.spin_relock_min.value()
            self.ui.quit_app()
            quit_app.assert_called_once()
        self.assertEqual(self.sm.settings["locked_memo_relock_min"], wanted)

    def test_quitting_with_nothing_changed_does_not_ask(self) -> None:
        with mock.patch.object(support.uim.QApplication, "quit") as quit_app:
            self.ui.quit_app()
            quit_app.assert_called_once()
        self.assertEqual(self.choices_asked, [])

    def test_the_question_is_shown_inside_the_explorer(self) -> None:
        from PyQt6.QtCore import QTimer
        self.change()
        seen = {}

        def press() -> None:
            overlay = self.ex.inline_overlay
            seen["inside"] = overlay.isVisible() and overlay.isAncestorOf(overlay.panel)
            seen["buttons"] = [b.text() for b in overlay.panel.buttons.values()]
            overlay.panel.buttons[None].click()                      # 취소

        QTimer.singleShot(0, press)
        with mock.patch.object(support.themed_dialog, "choose", self.real_choose):
            closed = self.ex.ask_and_close_settings_panel()
        self.assertEqual(seen, {"inside": True, "buttons": ["저장하고 닫기", "저장 안 함", "취소"]})
        self.assertFalse(closed)
        self.assertTrue(self.ex.settings_open())


class SettingsFieldTableTest(support.UiTestCase):
    """칸 하나가 설정값 하나와 그대로 짝지어지는 설정은 표(FIELDS) 하나로 불러오고 모읍니다."""

    def window(self, **saved):
        self.sm.settings.update(saved)
        win = support.sw.SettingsWindow(self.sm)
        self.addCleanup(win.close)
        return win

    def test_every_field_is_loaded_and_collected(self) -> None:
        win = self.window()
        keys = [key for key, _, _ in win.FIELDS]
        self.assertEqual(len(keys), len(set(keys)))
        got = win.collect()
        for key, name, default in win.FIELDS:
            self.assertTrue(hasattr(win, name), name)
            self.assertEqual(got[key], self.sm.settings.get(key, default), key)     # 저장된 값이 없으면 기본값
        self.assertFalse(win.is_dirty())

    def test_saved_values_round_trip(self) -> None:
        saved = {"use_sync": True, "drive_folder_id": "https://x/exec", "locked_memo_relock_min": 9, "default_font_size": 14,
                 "auto_eng_kor_convert": False, "default_memo_width": 410, "default_rolled_height": 60, "ui_style": "neo",
                 "auto_save_idle_sec": 300, "explorer_fixed_size": True, "folder_ui": "sidebar", "global_hotkeys": False}
        win = self.window(**saved)
        got = win.collect()
        self.assertEqual({key: got[key] for key in saved}, saved)
        self.assertFalse(win.is_dirty())
        win.spin_relock_min.setValue(3)
        self.assertTrue(win.is_dirty())
        self.assertEqual(win.collect()["locked_memo_relock_min"], 3)

    def test_unknown_saved_choice_falls_back_to_the_default(self) -> None:
        got = self.window(ui_style="zzz", auto_save_idle_sec=7, folder_ui="zzz", dark_theme_mode="zzz").collect()
        self.assertEqual((got["ui_style"], got["auto_save_idle_sec"], got["folder_ui"], got["dark_theme_mode"]),
                         ("modern", 60, "tabs", "dark"))


class SettingsLayoutTest(support.UiTestCase):
    """환경설정 화면의 구성과 세부 동작."""

    def test_quick_choice_rows_are_stacked(self) -> None:
        win = support.sw.SettingsWindow(self.sm)
        self.addCleanup(win.close)
        win.show()
        support.app.processEvents()
        tops = [spin.mapTo(win, QPoint(0, 0)).y() for spin in win.quick_minute_spins]
        lefts = {spin.mapTo(win, QPoint(0, 0)).x() for spin in win.quick_minute_spins}
        self.assertEqual(tops, sorted(set(tops)))                    # 한 줄에 하나씩 아래로
        self.assertEqual(len(lefts), 1)

    def test_guide_button_lives_in_settings_not_in_the_tray(self) -> None:
        win = support.sw.SettingsWindow(self.sm)
        self.addCleanup(win.close)
        self.assertTrue(win.tabs.widget(0).isAncestorOf(win.btn_make_guide))
        win.btn_make_guide.click()
        self.assertEqual(len([m for m in self.sm.load_local_memos() if m["id"].startswith("guide-")]), 3)
        self.assertIn("guide-memo", self.ui.memo_windows)
        menu = self.ui.tray_icon.contextMenu()
        self.assertFalse(any("사용 안내" in action.text() for action in menu.actions()))

    def test_sync_tab_links_to_the_setup_guide(self) -> None:
        win = support.sw.SettingsWindow(self.sm)
        self.addCleanup(win.close)
        self.assertTrue(win.tabs.widget(1).isAncestorOf(win.btn_sync_guide))
        opened = []
        with mock.patch.object(support.sw.QDesktopServices, "openUrl", staticmethod(lambda url: opened.append(url.toString()))):
            win.btn_sync_guide.click()
        self.assertEqual(len(opened), 1)
        self.assertTrue(opened[0].startswith("https://github.com/DongkyuSeoOssData/Memos"))
        readme = (pathlib.Path(support.sw.__file__).parent.parent / "README.md").read_text(encoding="utf-8")
        self.assertIn("### 설정 방법", readme)                        # 링크가 가리키는 대목이 README 에 있음
        self.assertTrue(support.sw.SYNC_GUIDE_URL.endswith("#설정-방법"))
        for needed in ("mobile/Code.gs", "mobile/Index.html", "ACCESS_TOKEN", "웹 앱 URL"):
            self.assertIn(needed, readme)

    def test_settings_layout_details(self) -> None:
        win = support.sw.SettingsWindow(self.sm)
        self.addCleanup(win.close)
        win.show()
        support.app.processEvents()
        general = win.tabs.widget(0)
        tops = {name: getattr(win, name).mapTo(general, QPoint(0, 0)).y() for name in ("folder_ui_box", "spin_relock_min", "btn_make_guide")}
        self.assertLess(tops["folder_ui_box"], tops["spin_relock_min"])          # 폴더 표시 방식이 맨 위
        self.assertLess(tops["spin_relock_min"], tops["btn_make_guide"])
        texts = " ".join(label.text() for label in win.findChildren(QLabel))
        self.assertIn("단축키 설정", texts)
        self.assertNotIn("종]", texts)

    def test_duplicate_shortcut_clears_the_other_one(self) -> None:
        from PyQt6.QtGui import QKeySequence
        win = support.sw.SettingsWindow(self.sm)
        self.addCleanup(win.close)
        win.show()
        edits = {win.shortcut_table.item(r, 0).data(Qt.ItemDataRole.UserRole): win.shortcut_table.cellWidget(r, 1)
                 for r in range(win.shortcut_table.rowCount())}
        taken = edits["open_explorer"].keySequence().toString()
        edits["new_memo"].setKeySequence(QKeySequence(taken))
        cleared = win._resolve_shortcut_conflict(edits["new_memo"])
        self.assertEqual(len(cleared), 1)
        self.assertEqual(edits["open_explorer"].keySequence().toString(), "")            # 겹친 쪽을 비움
        self.assertEqual(edits["new_memo"].keySequence().toString(), taken)
        self.assertTrue(win.toast.isVisible() and win.toast.toolTip().startswith("⚠"))
        win.save()
        self.assertEqual((self.sm.settings["shortcuts"]["new_memo"], self.sm.settings["shortcuts"]["open_explorer"]), (taken, ""))
        self.assertEqual(win._resolve_shortcut_conflict(edits["new_memo"]), [])            # 겹치는 것이 없으면 그대로

    # ── 6. 다른 기기에서 받은 설정이 고치던 값을 덮지 않음 ──
    def test_incoming_settings_do_not_overwrite_unsaved_edits(self) -> None:
        self.explorer()
        self.ui.open_settings()
        panel = self.ui.settings_window
        before = panel.spin_relock_min.value()
        panel.spin_relock_min.setValue(before + 7)
        self.sm.settings["locked_memo_relock_min"] = before + 1      # 다른 기기에서 받은 값
        self.ui.apply_settings_to_windows(reload_settings_window=True)
        self.assertEqual(panel.spin_relock_min.value(), before + 7)  # 고치던 값이 그대로
        self.assertTrue(panel.is_dirty())
        self.assertTrue(panel.toast.isVisible() and panel.toast.toolTip().startswith("⚠"))

        panel.spin_relock_min.setValue(before)
        panel.mark_clean()
        self.sm.settings["locked_memo_relock_min"] = before + 2
        self.ui.apply_settings_to_windows(reload_settings_window=True)
        self.assertEqual(panel.spin_relock_min.value(), before + 2)  # 고치던 것이 없으면 새 값으로 채움


class HotkeyScopeTest(support.UiTestCase):
    def test_global_by_default(self) -> None:
        self.assertEqual(len(self.ui._hotkeys.registered), 7)
        self.assertEqual(self.ui._app_shortcuts, [])

    def test_app_only_mode_leaves_the_keys_to_other_programs(self) -> None:
        self.sm.save_settings({"global_hotkeys": False})
        self.ui.register_global_hotkeys()
        self.assertEqual(self.ui._hotkeys.registered, [])            # 전역으로는 아무것도 잡지 않음
        shortcuts = self.ui._app_shortcuts
        self.assertEqual(len(shortcuts), 7)
        self.assertTrue(all(s.context() == Qt.ShortcutContext.ApplicationShortcut for s in shortcuts))
        keys = {s.key().toString() for s in shortcuts}
        self.assertIn("Alt+W", keys)
        self.assertIn("Alt+Q", keys)
        opener = next(s for s in shortcuts if s.key().toString() == "Alt+W")
        opener.activated.emit()                                      # 앱 창이 앞에 있을 때 눌린 것처럼
        self.assertTrue(self.ui.explorer_window.isVisible())

        self.ui.register_global_hotkeys()                            # 다시 걸어도 겹쳐 쌓이지 않음
        self.assertEqual(len(self.ui._app_shortcuts), 7)
        self.sm.save_settings({"global_hotkeys": True})
        self.ui.register_global_hotkeys()
        self.assertEqual((len(self.ui._hotkeys.registered), self.ui._app_shortcuts), (7, []))

    def test_cleared_shortcut_is_skipped_in_both_modes(self) -> None:
        shortcuts = dict(self.sm.settings.get("shortcuts", {}), open_explorer="")
        self.sm.save_settings({"shortcuts": shortcuts, "global_hotkeys": False})
        self.ui.register_global_hotkeys()
        self.assertEqual(len(self.ui._app_shortcuts), 6)

    def test_option_is_on_the_shortcut_tab_and_applies_on_save(self) -> None:
        win = support.sw.SettingsWindow(self.sm)
        self.addCleanup(win.close)
        self.assertTrue(win.tabs.widget(3).isAncestorOf(win.cb_global_hotkeys))
        self.assertTrue(win.cb_global_hotkeys.isChecked())
        win.cb_global_hotkeys.setChecked(False)
        win.save()
        self.assertFalse(self.sm.settings["global_hotkeys"])
        self.assertEqual((self.ui._hotkeys.registered, len(self.ui._app_shortcuts)), ([], 7))
        again = support.sw.SettingsWindow(self.sm)
        self.addCleanup(again.close)
        self.assertFalse(again.cb_global_hotkeys.isChecked())


if __name__ == "__main__":
    unittest.main()
