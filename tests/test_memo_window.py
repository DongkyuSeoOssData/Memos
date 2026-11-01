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


class FontSizeChangeTest(support.UiTestCase):
    """Ctrl+휠이나 크기 칸으로 글자 크기를 바꿀 때 불릿·번호·체크 상자도 같이 맞습니다."""

    def wheel(self, w, times: int, up: bool = True) -> None:
        from PyQt6.QtCore import QPoint, Qt
        event = mock.Mock()
        event.angleDelta.return_value = QPoint(0, 120 if up else -120)
        with mock.patch("ui.memo_editor.QApplication.keyboardModifiers", return_value=Qt.KeyboardModifier.ControlModifier):
            for _ in range(times):
                w.text_edit.wheelEvent(event)

    def memo_with_list(self):
        from PyQt6.QtGui import QTextCursor, QTextListFormat
        w = self.open_window("memo-0000")
        w.text_edit.setPlainText("first" + chr(10) + "second" + chr(10) + "☐ todo")
        cursor = QTextCursor(w.text_edit.document())
        cursor.movePosition(QTextCursor.MoveOperation.NextBlock, QTextCursor.MoveMode.KeepAnchor)
        cursor.createList(QTextListFormat.Style.ListDecimal)              # 첫 줄부터 목록
        return w

    def test_list_marker_has_room_and_follows_the_size(self) -> None:
        from PyQt6.QtGui import QFontMetricsF
        w = self.memo_with_list()
        document = w.text_edit.document()
        w.text_edit.fit_list_indent()
        normal = document.indentWidth()
        self.assertGreaterEqual(normal, QFontMetricsF(w.text_edit.font()).horizontalAdvance("0."))
        self.wheel(w, 30)
        size = w.memo_data["font_size"]
        self.assertGreater(size, 30)
        wide = document.indentWidth()
        self.assertGreaterEqual(wide, QFontMetricsF(w.text_edit.font()).horizontalAdvance("00."))     # 번호가 잘리지 않을 폭
        self.assertEqual(document.firstBlock().charFormat().fontPointSize(), size)     # 첫 줄의 번호도 같은 크기
        self.assertGreater(wide, normal)
        self.wheel(w, 30, up=False)
        self.assertEqual(document.indentWidth(), normal)                    # 줄이면 폭도 돌아옴

    def test_two_digit_numbers_get_room(self) -> None:
        from PyQt6.QtGui import QFontMetricsF, QTextCursor, QTextListFormat
        w = self.open_window("memo-0000")
        document = w.text_edit.document()
        w.text_edit.setPlainText("one")
        QTextCursor(document).createList(QTextListFormat.Style.ListDecimal)
        one_digit = document.indentWidth()
        cursor = QTextCursor(document)
        cursor.movePosition(QTextCursor.MoveOperation.End)
        for n in range(12):
            cursor.insertBlock()
            cursor.insertText("x")
        self.assertEqual(document.lastBlock().textList().count(), 13)
        self.assertGreaterEqual(document.indentWidth(), one_digit)
        expected = int(QFontMetricsF(w.text_edit.font()).horizontalAdvance("00. ")) + 1
        self.assertEqual(document.indentWidth(), max(w.text_edit.MIN_INDENT_WIDTH, expected))

    def test_memo_without_a_list_keeps_the_default_indent(self) -> None:
        w = self.open_window("memo-0000")
        w.change_font_size("48")
        self.assertEqual(w.text_edit.document().indentWidth(), w.text_edit.MIN_INDENT_WIDTH)

    def test_size_box_does_the_same(self) -> None:
        w = self.memo_with_list()
        w.change_font_size("40")
        document = w.text_edit.document()
        self.assertEqual(document.firstBlock().charFormat().fontPointSize(), 40)
        self.assertGreater(document.indentWidth(), w.text_edit.MIN_INDENT_WIDTH)

    def test_indent_is_fitted_when_a_big_memo_is_opened(self) -> None:
        w = self.memo_with_list()
        w.change_font_size("40")
        w.manual_save()
        w.close()
        again = self.open_window("memo-0000")
        self.assertGreater(again.text_edit.document().indentWidth(), again.text_edit.MIN_INDENT_WIDTH)

    def test_changing_size_keeps_bold(self) -> None:
        from PyQt6.QtGui import QTextCursor
        w = self.open_window("memo-0000")
        w.text_edit.selectAll()
        w.toggle_bold()
        self.wheel(w, 3)
        cursor = QTextCursor(w.text_edit.document())
        cursor.setPosition(1)
        self.assertGreaterEqual(cursor.charFormat().fontWeight(), 600)
        self.assertEqual(cursor.charFormat().fontPointSize(), w.memo_data["font_size"])

    def test_check_box_follows_the_size(self) -> None:
        w = self.memo_with_list()
        marks = w.text_edit.check_marks
        block = w.text_edit.document().lastBlock()
        small = marks.box_rect(block, 0)
        self.wheel(w, 40)
        big = marks.box_rect(block, 0)
        self.assertGreater(big.height(), small.height())
        self.assertLessEqual(big.width(), marks.glyph_cell(block, 0).width())     # 뒤 글자에 겹치지 않음
        w.text_edit.viewport().grab()                                       # 그리기까지 오류 없이


class ComboColorTest(support.UiTestCase):
    """언어 칸과 펼친 목록의 색을 윈도우 설정이 아니라 메모 색으로 정합니다. (어떤 PC에서는 글자가 안 보이던 문제)"""

    @staticmethod
    def luminance(code: str) -> float:
        from PyQt6.QtGui import QColor
        color = QColor(code)

        def part(value: int) -> float:
            value /= 255
            return value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4

        return 0.2126 * part(color.red()) + 0.7152 * part(color.green()) + 0.0722 * part(color.blue())

    def test_list_and_box_colors_are_set_for_every_design_and_memo_color(self) -> None:
        from ui import modern_style
        cases = [{"is_code_memo": True, "code_theme": theme} for theme in ("dark", "light")]
        cases += [{"is_code_memo": False, "bg_color": color} for color in ("#2E3440", "#E0F2FE", "#DCFCE7", "#FEF9C3", "#FCE7F3", "#FFFFFF")]
        w = self.open_window("memo-0000")
        for style in ("modern", "neo"):
            self.sm.settings["ui_style"] = style
            for case in cases:
                w.memo_data.update(case)
                w.apply_data()
                _, _, background = modern_style.memo_tone(w)
                ink = w._memo_theme_palette()["text"]
                sheet = w.code_lang_box.styleSheet()
                self.assertIn(f"QComboBox QAbstractItemView {{ background-color: {background}; color: {ink};", sheet, (style, case))
                self.assertIn(f"QComboBox {{ background-color: {background}; color: {ink}; }}", sheet)
                bright, dim = sorted((self.luminance(ink), self.luminance(background)), reverse=True)
                self.assertGreaterEqual((bright + 0.05) / (dim + 0.05), 4.5, (style, case))     # 글자가 읽히는 대비


class MemoMonitorTest(support.UiTestCase):
    """펼친 위치를 다른 모니터에 고정해 두면, 접은 메모를 어느 모니터에서 펴든 그 자리로 갑니다."""

    def test_pin_on_the_other_monitor(self) -> None:
        from PyQt6.QtCore import QRect
        left, right = QRect(0, 0, 1600, 900), QRect(1600, 0, 1600, 900)

        def screen_at(point):
            area = left if point.x() < 1600 else right
            return mock.Mock(availableGeometry=lambda: QRect(area), geometry=lambda: QRect(area))

        w = self.open_window("memo-0000")
        with mock.patch("ui.memo_drag.QApplication.screenAt", side_effect=screen_at), \
                mock.patch("ui.memo_rollup.MemoRollupMixin._screen_layout", return_value=[left.getRect(), right.getRect()]):
            w.setGeometry(2000, 200, 400, 300)                       # 펼친 자리는 오른쪽 모니터
            w.pin_position()
            w.toggle_rollup()
            w.move(100, 700)                                         # 접은 메모는 왼쪽 모니터로 옮겨 둠
            w.toggle_rollup()
            self.assertEqual((w.x(), w.y(), w.width(), w.height()), (2000, 200, 400, 300))


if __name__ == "__main__":
    unittest.main()
