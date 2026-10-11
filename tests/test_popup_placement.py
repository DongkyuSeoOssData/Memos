"""알림 창을 띄울 자리(모니터와 모서리)와, 미리보기에서 고친 내용의 저장 실패 알림."""
import unittest
from unittest import mock

from PyQt6.QtCore import QRect
from PyQt6.QtGui import QGuiApplication

# support 를 먼저 가져와야 합니다. (offscreen 설정과 프로젝트 경로)
import support
from ui import reminder_ui
from ui.reminder_ui import POPUP_GAP, POPUP_MARGIN, ReminderPopup, popup_position, popup_screen

AREA = QRect(1920, 0, 1600, 900)            # 두 번째 모니터의 작업 영역
SIZE = (340, 150)
PAST = {"at": "2020-01-01T09:00:00", "repeat": "none"}


class PopupPositionTest(unittest.TestCase):
    def test_each_corner(self) -> None:
        right = AREA.left() + AREA.width() - SIZE[0] - POPUP_MARGIN
        left = AREA.left() + POPUP_MARGIN
        top = AREA.top() + POPUP_MARGIN
        bottom = AREA.top() + AREA.height() - SIZE[1] - POPUP_MARGIN
        self.assertEqual(popup_position(AREA, SIZE, "bottom_right"), (right, bottom))
        self.assertEqual(popup_position(AREA, SIZE, "bottom_left"), (left, bottom))
        self.assertEqual(popup_position(AREA, SIZE, "top_right"), (right, top))
        self.assertEqual(popup_position(AREA, SIZE, "top_left"), (left, top))
        self.assertEqual(popup_position(AREA, SIZE, "nonsense"), (right, bottom))       # 모르는 값은 기본 자리

    def test_stacks_away_from_the_corner(self) -> None:
        step = SIZE[1] + POPUP_GAP
        _, first = popup_position(AREA, SIZE, "bottom_right")
        self.assertEqual(popup_position(AREA, SIZE, "bottom_right", step)[1], first - step)      # 아래 모서리는 위로
        _, first = popup_position(AREA, SIZE, "top_left")
        self.assertEqual(popup_position(AREA, SIZE, "top_left", step)[1], first + step)          # 위 모서리는 아래로

    def test_never_leaves_the_screen(self) -> None:
        step = SIZE[1] + POPUP_GAP
        for corner, _ in reminder_ui.POPUP_CORNERS:
            for count in range(30):
                x, y = popup_position(AREA, SIZE, corner, step * count)
                self.assertGreaterEqual(y, AREA.top(), (corner, count))
                self.assertLessEqual(y + SIZE[1], AREA.top() + AREA.height(), (corner, count))
                self.assertGreaterEqual(x, AREA.left())
                self.assertLessEqual(x + SIZE[0], AREA.left() + AREA.width())
        # 자리가 없으면 모서리에서 다시 시작
        self.assertEqual(popup_position(AREA, SIZE, "top_left", step * 30), popup_position(AREA, SIZE, "top_left"))


class PopupScreenTest(support.UiTestCase):
    def test_unknown_or_missing_monitor_falls_back_to_the_main_one(self) -> None:
        main = QGuiApplication.primaryScreen()
        self.assertIs(popup_screen({}), main)
        self.assertIs(popup_screen({"reminder_popup_screen": ""}), main)
        self.assertIs(popup_screen({"reminder_popup_screen": "no-such-monitor"}), main)
        self.assertIs(popup_screen({"reminder_popup_screen": main.name()}), main)

    def test_chosen_monitor_is_used(self) -> None:
        other = mock.Mock()
        other.name.return_value = "SECOND"
        other.availableGeometry.return_value = AREA
        with mock.patch.object(reminder_ui.QGuiApplication, "screens", return_value=[QGuiApplication.primaryScreen(), other]):
            settings = {**self.sm.settings, "reminder_popup_screen": "SECOND", "reminder_popup_corner": "top_left"}
            self.assertIs(popup_screen(settings), other)
            popup = ReminderPopup(settings, "memo-0000", "title", "detail", lambda i: None, lambda i, m: None)
            self.addCleanup(popup.close)
            self.assertEqual((popup.x(), popup.y()), (AREA.left() + POPUP_MARGIN, AREA.top() + POPUP_MARGIN))

    def test_popups_from_the_app_follow_the_setting_and_stack(self) -> None:
        self.sm.settings["reminder_popup_corner"] = "top_right"
        for memo_id in ("memo-0000", "memo-0001"):
            memo = next(m for m in self.sm.load_local_memos() if m["id"] == memo_id)
            self.sm.set_reminder(memo, dict(PAST))
        support.app.processEvents()
        self.ui.check_reminders()
        self.ui._reminder_timer.stop()
        first, second = self.ui._reminder_popups
        area = QGuiApplication.primaryScreen().availableGeometry()
        self.assertEqual(first.y(), area.top() + POPUP_MARGIN)
        self.assertEqual(second.y(), first.y() + first.height() + POPUP_GAP)
        self.assertEqual(first.x(), area.left() + area.width() - first.width() - POPUP_MARGIN)
        for popup in (first, second):
            popup.close()


class PopupSettingTest(support.UiTestCase):
    def window(self, **saved):
        self.sm.settings.update(saved)
        win = support.sw.SettingsWindow(self.sm)
        self.addCleanup(win.close)
        return win

    def test_defaults_and_round_trip(self) -> None:
        win = self.window()
        got = win.collect()
        self.assertEqual((got["reminder_popup_screen"], got["reminder_popup_corner"]), ("", "bottom_right"))
        self.assertEqual(win.popup_screen_box.itemText(0), "주 모니터")
        self.assertEqual(win.popup_corner_box.count(), 4)
        win.popup_corner_box.setCurrentIndex(win.popup_corner_box.findData("top_left"))
        self.assertTrue(win.is_dirty())
        win.save()
        self.assertEqual(self.sm.settings["reminder_popup_corner"], "top_left")
        self.assertEqual(self.window().collect()["reminder_popup_corner"], "top_left")

    def test_connected_monitors_are_listed_by_name(self) -> None:
        win = self.window()
        names = [win.popup_screen_box.itemData(i) for i in range(win.popup_screen_box.count())]
        self.assertEqual(names, [""] + [s.name() for s in QGuiApplication.screens()])

    def test_unplugged_monitor_choice_is_kept(self) -> None:
        win = self.window(reminder_popup_screen="OLD-MONITOR")
        self.assertEqual(win.collect()["reminder_popup_screen"], "OLD-MONITOR")        # 다른 설정을 저장해도 사라지지 않음
        self.assertIn("연결되지 않은 모니터", win.popup_screen_box.currentText())
        self.assertFalse(win.is_dirty())

    def test_placement_is_a_per_pc_setting(self) -> None:
        shared = support.smm.shared_settings.SHARED_KEYS
        self.assertNotIn("reminder_popup_screen", shared)
        self.assertNotIn("reminder_popup_corner", shared)


class PreviewSaveFailureTest(support.UiTestCase):
    def test_failed_preview_save_is_reported_and_retried(self) -> None:
        ex = self.explorer()
        row = self.row_of(ex, "memo-0000")
        ex.table.selectRow(row)
        ex.on_cell_click(row, 2)
        ex.pv.setPlainText("edited in the preview")
        self.assertIsNotNone(ex._pending_preview_memo)
        self.warnings.clear()
        told = []
        ex.show_toast = lambda text, warn=False: told.append((text, warn))
        with mock.patch.object(self.sm, "save_memo_locally", return_value=False):
            ex._flush_preview_save()
        self.assertEqual(len(told), 1)
        self.assertTrue(told[0][1])
        self.assertIn("저장하지 못했습니다", told[0][0])
        self.assertTrue(ex._preview_save_timer.isActive())            # 조금 뒤에 다시 시도
        ex._flush_preview_save()
        self.assertEqual(len(told), 1)
        self.assertIn("edited in the preview", self.disk("memo-0000")["content"])


if __name__ == "__main__":
    unittest.main()
