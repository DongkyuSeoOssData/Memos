"""메모 창: 글꼴·크기 칸, 여러 모니터에서 펴기."""
import unittest
from unittest import mock

from PyQt6.QtCore import QPoint

# support 를 먼저 가져와야 합니다. (offscreen 설정과 프로젝트 경로)
import support


class MemoFontBoxTest(support.UiTestCase):
    """글꼴과 글자 크기는 찾아서 고르거나 직접 적습니다."""

    def test_font_can_be_searched_and_size_typed(self) -> None:
        w = self.open_window("memo-0000")
        self.assertTrue(w.font_box.isEditable() and w.size_box.isEditable())
        if w.font_box.count() < 2:                                   # 화면 없는 시험 환경에는 글꼴 목록이 비어 있음
            w.font_box.addItems(["Alpha Sans", "Beta Mono"])
        families = [w.font_box.itemText(i) for i in range(w.font_box.count())]
        target = next((f for f in families if f != (w.memo_data.get("font_family") or "")), families[0])
        w.font_box.setEditText(target[:max(3, len(target) - 1)].upper())      # 이름의 일부만, 대소문자 달라도
        w.font_box.lineEdit().editingFinished.emit()
        self.assertIn(target[:3].lower(), w.memo_data["font_family"].lower())
        applied = w.memo_data["font_family"]
        w.font_box.setEditText("no such font zzz")
        w.font_box.lineEdit().editingFinished.emit()
        self.assertEqual((w.memo_data["font_family"], w.font_box.currentText()), (applied, applied))   # 없는 이름은 되돌림

        w.size_box.setEditText("17")
        w.size_box.lineEdit().editingFinished.emit()
        self.assertEqual(w.memo_data["font_size"], 17)
        w.size_box.setEditText("300")
        w.size_box.lineEdit().editingFinished.emit()
        self.assertEqual((w.memo_data["font_size"], w.size_box.currentText()), (17, "17"))

    def test_font_and_size_have_separate_dropdown_buttons(self) -> None:
        w = self.open_window("memo-0000")
        w.toggle_sub_fmt_panel()
        support.app.processEvents()
        for box, button in ((w.font_box, w.btn_font_drop), (w.size_box, w.btn_size_drop)):
            self.assertIn("drop-down { width: 0px", box.styleSheet())                   # 칸 안의 화살표는 없앰
            self.assertEqual(button.mapTo(w, QPoint(0, 0)).x(), box.mapTo(w, QPoint(0, 0)).x() + box.width())     # 칸 바로 오른쪽
            opened = []
            box.showPopup = lambda opened=opened: opened.append(True)
            button.clicked.disconnect()
            button.clicked.connect(lambda checked=False, b=box: b.showPopup())
            button.click()
            self.assertEqual(opened, [True])

    def test_dropdown_button_opens_a_list_you_can_type_into(self) -> None:
        w = self.open_window("memo-0000")
        w.toggle_sub_fmt_panel()
        if w.font_box.count() < 2:
            w.font_box.addItems(["Alpha Sans", "Beta Mono", "Beta Serif"])
        for box, button in ((w.font_box, w.btn_font_drop), (w.size_box, w.btn_size_drop)):
            finder = box.completer()
            shown = []
            finder.complete = lambda *a, shown=shown: shown.append(finder.completionPrefix())
            button.click()
            self.assertEqual(shown, [""])                            # 목록 전체를 펼침
            self.assertEqual(box.lineEdit().selectedText(), box.currentText())      # 바로 적으면 지금 글자를 대신함
            self.assertEqual(finder.completionMode(), finder.CompletionMode.PopupCompletion)
        # 목록이 떠 있는 동안 적으면 걸러짐
        finder = w.font_box.completer()
        finder.setCompletionPrefix("beta")
        names = [finder.completionModel().index(r, 0).data() for r in range(finder.completionModel().rowCount())]
        self.assertTrue(names and all("beta" in n.lower() for n in names), names)


class MemoMonitorTest(support.UiTestCase):
    """접은 메모를 펴면 기억해 둔 모니터의 자리로 돌아갑니다."""

    # ── 4. 다른 모니터에 기억해 둔 자리 ──
    def test_unrolling_goes_back_to_the_other_monitor(self) -> None:
        from PyQt6.QtCore import QRect
        left, right = QRect(0, 0, 1600, 900), QRect(1600, 0, 1600, 900)

        def screen_at(point):
            area = left if point.x() < 1600 else right
            return mock.Mock(availableGeometry=lambda: QRect(area))

        w = self.open_window("memo-0000")
        with mock.patch("ui.memo_drag.QApplication.screenAt", side_effect=screen_at):
            w.setGeometry(2000, 200, 400, 300)                       # 펼친 자리는 오른쪽 모니터
            w.toggle_rollup()
            w.move(100, 700)                                         # 접은 메모는 왼쪽 모니터로 옮겨 둠
            w.toggle_rollup()
            self.assertEqual((w.x(), w.y(), w.width(), w.height()), (2000, 200, 400, 300))
            w.toggle_rollup()
            self.assertEqual((w.x(), w.y()), (100, 700))


if __name__ == "__main__":
    unittest.main()
