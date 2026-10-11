"""앱 자체 모양의 창과 창 안에서 묻기, 색을 정하는 곳."""
import pathlib
import unittest

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QTextCursor
from PyQt6.QtTest import QTest

# support 를 먼저 가져와야 합니다. (offscreen 설정과 프로젝트 경로)
import support
from ui.dialogs import HistoryDialog
from ui.reminder_ui import ReminderDialog


class ThemedWindowTest(support.UiTestCase):
    """확인·입력·알림을 Windows 기본 창이 아니라 앱 자체 창과 토스트로 보여 줍니다."""

    def test_dialogs_have_their_own_title_bar(self) -> None:
        from ui.dialogs import ConflictDialog, FolderPickDialog
        from ui.themed_dialog import ColorDialog, ThemedDialog
        ex = self.explorer()
        dialogs = [ReminderDialog(ex, None, "t"), HistoryDialog(ex, "t", []), FolderPickDialog(ex, ["a"], {}),
                   ConflictDialog("t", "a", "b", ex), ColorDialog(ex, "색")]
        for d in dialogs:
            self.addCleanup(d.close)
            self.assertIsInstance(d, ThemedDialog)
            self.assertTrue(d.windowFlags() & Qt.WindowType.FramelessWindowHint, type(d).__name__)
            self.assertTrue(d.title_label.text())
            self.assertIn("ThemedDialog", d.styleSheet())

    def test_no_native_message_boxes_are_left(self) -> None:
        import pathlib
        for path in pathlib.Path(support.uim.__file__).parent.glob("*.py"):
            source = path.read_text(encoding="utf-8")
            for name in ("QMessageBox", "QInputDialog", "QColorDialog"):
                self.assertNotIn(name, source, path.name)

    def test_form_panel_keeps_asking_until_valid(self) -> None:
        from ui.input_panels import FormPanel
        got = []
        panel = FormPanel("t", "", [{"label": "a", "password": True}, {"label": "b", "password": True}],
                          validate=lambda v: None if v[0] == v[1] else "다릅니다")
        self.addCleanup(panel.close)
        panel.submitted.connect(got.append)
        panel.show()
        panel.inputs[0].setText("x")
        panel.inputs[1].setText("y")
        panel.submit()
        self.assertEqual(got, [])
        self.assertTrue(panel.error.isVisible())
        self.assertIn("다릅니다", panel.error.text())
        panel.inputs[1].setText("x")
        QTest.keyClick(panel.inputs[1], Qt.Key.Key_Return)             # 마지막 칸에서 Enter = 확인
        self.assertEqual(got, [["x", "x"]])

    def test_color_dialog(self) -> None:
        from ui.themed_dialog import ColorDialog
        d = ColorDialog(None, "색", "#112233")
        self.addCleanup(d.close)
        self.assertEqual(d.color().name(), "#112233")
        d.swatches[9].click()
        self.assertEqual(d.color().name().upper(), "#FF0000")
        d.code.setText("nope")
        self.assertIsNone(d.color())
        self.assertFalse(d.ok_button.isEnabled())

    def test_settings_window_reports_with_its_own_toast(self) -> None:
        win = support.sw.SettingsWindow(self.sm)
        self.addCleanup(win.close)
        win.show()
        win.save()
        self.assertTrue(win.toast.isVisible())
        self.assertIn("저장", win.toast.toolTip())
        win.url_input.setText("not a url")
        win.test_gas_url()
        self.assertTrue(win.toast.toolTip().startswith("⚠"))
        self.assertEqual(self.warnings, [])                          # 창을 따로 띄우지 않음

    def test_folder_display_option_is_on_the_general_tab(self) -> None:
        win = support.sw.SettingsWindow(self.sm)
        self.addCleanup(win.close)
        general = win.tabs.widget(0)
        self.assertEqual(win.tabs.tabText(0).strip(), "일반 설정")
        self.assertTrue(general.isAncestorOf(win.folder_ui_box))

    def test_duplicate_title_is_a_toast_in_the_memo(self) -> None:
        w = self.open_window("memo-0000")
        w.show_toast("안내")
        self.assertEqual(w.toast_label.text(), "안내")
        w.show_toast("문제", warn=True)
        self.assertEqual(w.toast_label.text(), "⚠ 문제")


class InWindowPromptTest(support.UiTestCase):
    """확인·입력·색 고르기는 부른 창(메모·탐색기) 안에서 합니다."""

    def test_confirm_and_name_input_happen_inside_the_explorer(self) -> None:
        from PyQt6.QtCore import QTimer
        from ui import themed_dialog
        ex = self.explorer()
        ex.resize(720, 640)
        support.app.processEvents()
        seen = {}

        def press(which: str) -> None:
            overlay = ex.inline_overlay
            seen[which] = overlay.isVisible() and overlay.panel is not None
            (overlay.panel.ok_button if which != "no" else overlay.panel.cancel_button).click()

        confirm = self.real["confirm"]
        QTimer.singleShot(0, lambda: press("yes"))
        self.assertTrue(confirm(ex, "삭제", "지울까요?", ok_text="삭제", danger=True))
        QTimer.singleShot(0, lambda: press("no"))
        self.assertFalse(confirm(ex, "삭제", "지울까요?"))
        self.assertEqual(seen, {"yes": True, "no": True})
        self.assertTrue(ex.inline_overlay.isHidden())

        def type_name() -> None:
            panel = ex.inline_overlay.panel
            panel.inputs[0].setText("업무/새폴더")
            panel.submit()

        QTimer.singleShot(0, type_name)
        self.assertEqual(self.real["ask_form"](ex, "새 폴더", "", [{"label": "폴더 이름"}]), ["업무/새폴더"])
        self.assertIsNotNone(support.overlay.NO_HOST)

    def test_color_is_picked_inside_the_memo(self) -> None:
        from PyQt6.QtCore import QTimer
        w = self.open_window("memo-0000")
        w.resize(380, 460)
        support.app.processEvents()
        w.text_edit.setPlainText("mark me")
        w.text_edit.selectAll()
        seen = {}

        def steps() -> None:
            panel = w.lock_overlay.panel
            seen["inside"] = w.lock_overlay.isVisible() and w.lock_overlay.isAncestorOf(panel)
            panel.code.setText("#12AB34")
            panel.submit()

        QTimer.singleShot(0, steps)
        w.choose_bg_color()                                          # 형광펜 '사용자 지정 색'
        self.assertEqual(seen, {"inside": True})
        probe = QTextCursor(w.text_edit.document())
        probe.setPosition(3)
        self.assertEqual(probe.charFormat().background().color().name().upper(), "#12AB34")

        QTimer.singleShot(0, lambda: w.lock_overlay.panel.cancel_button.click())
        w.choose_fg_color()                                          # 취소하면 그대로
        self.assertTrue(w.lock_overlay.isHidden())

    # ── 그 밖에 ──
    def test_side_panel_is_removed_with_the_memo(self) -> None:
        w = self.open_window("memo-0000")
        panel = w.side_panel()
        w.close()
        support.app.processEvents()
        self.assertIsNone(w._side_panel)
        with self.assertRaises(RuntimeError):                        # 패널 창도 없어짐
            panel.isVisible()


class ColorSourceTest(support.UiTestCase):
    """색은 modern_style 한곳에서 정하고, 화면의 각 부분은 거기서 받아 씁니다."""

    def colors_of(self, memo_id: str, ui_style: str, bg: str) -> dict:
        from ui import modern_style
        self.sm.settings["ui_style"] = ui_style
        w = self.open_window(memo_id)
        w.memo_data["bg_color"] = bg
        return modern_style.memo_colors(w)

    def test_memo_colors_follow_the_memo_and_the_design_style(self) -> None:
        from ui import modern_style
        light = self.colors_of("memo-0000", "modern", "#FEF9C3")
        self.assertEqual((light["bg"], light["dark"], light["neo"]), ("#FEF9C3", False, False))
        self.assertEqual((light["strong"], light["on_strong"]), (light["accent"], "#FFFFFF"))      # Modern: 강조색
        neo_light = self.colors_of("memo-0000", "neo", "#FEF9C3")
        self.assertEqual((neo_light["strong"], neo_light["on_strong"]), (neo_light["ink"], "#FFFFFF"))   # Neo: 흑백
        neo_dark = self.colors_of("memo-0000", "neo", "#2E3440")
        self.assertEqual((neo_dark["dark"], neo_dark["strong"], neo_dark["on_strong"]), (True, neo_dark["ink"], "#1C1C1E"))
        self.assertNotEqual(neo_dark["field"], neo_light["field"])
        self.assertEqual(modern_style.check_colors(neo_dark),
                         {"ink": neo_dark["ink"], "fill": neo_dark["ink"], "tick": "#1C1C1E", "dark": True})
        self.assertEqual(modern_style.check_colors(light)["fill"], light["accent"])

    def test_app_colors_follow_the_app_theme(self) -> None:
        from ui import modern_style
        modern = modern_style.app_colors({"ui_style": "modern", "app_theme": "white"})
        neo = modern_style.app_colors({"ui_style": "neo", "app_theme": "dark"})
        self.assertEqual((modern["neo"], modern["dark"], modern["strong"]), (False, False, modern["accent"]))
        self.assertEqual((neo["neo"], neo["dark"], neo["strong"], neo["on_strong"]), (True, True, neo["ink"], neo["bg"]))

    def test_every_part_takes_its_colors_from_the_one_source(self) -> None:
        from ui import modern_style
        for style in ("modern", "neo"):
            self.sm.settings["ui_style"] = style
            w = self.open_window("memo-0000")
            colors = modern_style.memo_colors(w)
            self.assertEqual(w.text_edit._check_colors(), modern_style.check_colors(colors))       # 본문의 체크 상자
            w.lock_overlay.apply_style()
            self.assertIn(colors["strong"], w.lock_overlay.styleSheet())                           # 암호 입력 가림막
            panel = w.side_panel()
            panel.apply_style()
            self.assertIn(colors["bg"], panel.styleSheet())                                        # 메모 옆 패널
            self.assertIn(colors["edge"], panel.styleSheet())
            ex = self.explorer()
            self.assertEqual(ex._preview_check_colors(),                                           # 탐색기 미리보기
                             modern_style.check_colors(modern_style.app_colors(self.sm.settings)))

    def test_no_screen_decides_colors_on_its_own(self) -> None:
        folder = pathlib.Path(support.uim.__file__).parent
        for path in folder.glob("*.py"):
            if path.name in ("modern_style.py", "neo_style.py", "themes.py"):
                continue
            source = path.read_text(encoding="utf-8")
            self.assertNotRegex(source, r"modern_style\._[a-z]", path.name)       # 스타일 모듈의 내부 함수를 직접 쓰지 않음
            self.assertNotIn("is_neo(", source, path.name)                         # 디자인 스타일을 직접 가르지 않음


if __name__ == "__main__":
    unittest.main()
