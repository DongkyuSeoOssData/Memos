"""본문 편집기의 키 처리: 여러 커서, 줄 옮기기, 코드 메모의 괄호 짝과 들여쓰기, Tab."""
import unittest

from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtGui import QKeyEvent, QTextCursor

# support 를 먼저 가져와야 합니다. (offscreen 설정과 프로젝트 경로)
import support

NONE = Qt.KeyboardModifier.NoModifier
ALT = Qt.KeyboardModifier.AltModifier
CTRL = Qt.KeyboardModifier.ControlModifier
SHIFT = Qt.KeyboardModifier.ShiftModifier


class EditorKeyTest(support.UiTestCase):
    def editor(self, text: str, code: bool = False, at: int = 0):
        memo_id = "memo-keys-code" if code else "memo-keys"
        self.sm.save_memo_locally({"id": memo_id, "title": "keys", "content": text, "is_code_memo": code,
                                   "updated_at": "2026-01-09T00:00:00", "is_visible": False})
        edit = self.open_window(memo_id).text_edit
        edit.setPlainText(text)
        self.put(edit, at)
        return edit

    def put(self, edit, position: int) -> None:
        cursor = edit.textCursor()
        cursor.setPosition(position)
        edit.setTextCursor(cursor)

    def press(self, edit, key, text: str = "", modifiers=NONE) -> None:
        edit.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, key, modifiers, text))

    # ── 줄 옮기기 ────────────────────────────────────────────────────────────
    def test_alt_arrows_move_the_line(self) -> None:
        edit = self.editor("one\ntwo\nthree", at=5)
        self.press(edit, Qt.Key.Key_Up, modifiers=ALT)
        self.assertEqual(edit.toPlainText(), "two\none\nthree")
        self.press(edit, Qt.Key.Key_Down, modifiers=ALT)
        self.assertEqual(edit.toPlainText(), "one\ntwo\nthree")
        self.put(edit, 0)
        self.press(edit, Qt.Key.Key_Up, modifiers=ALT)                 # 첫 줄은 더 올라가지 않음
        self.assertEqual(edit.toPlainText(), "one\ntwo\nthree")

    # ── 여러 커서 ────────────────────────────────────────────────────────────
    def test_extra_cursors_are_added_and_type_together(self) -> None:
        edit = self.editor("aa\nbb\ncc", at=0)
        self.press(edit, Qt.Key.Key_Down, modifiers=CTRL | ALT)
        self.press(edit, Qt.Key.Key_Down, modifiers=CTRL | ALT)
        self.assertEqual(len(edit.extra_cursors), 2)
        self.press(edit, Qt.Key.Key_X, "x")
        self.assertEqual(edit.toPlainText(), "xaa\nxbb\nxcc")
        self.press(edit, Qt.Key.Key_Backspace)
        self.assertEqual(edit.toPlainText(), "aa\nbb\ncc")
        self.press(edit, Qt.Key.Key_Delete)
        self.assertEqual(edit.toPlainText(), "a\nb\nc")

    def test_plain_ctrl_keys_are_not_typed_into_every_cursor(self) -> None:
        edit = self.editor("aa\nbb", at=0)
        self.press(edit, Qt.Key.Key_Down, modifiers=CTRL | ALT)
        self.press(edit, Qt.Key.Key_F, "f", CTRL)                      # 단축키로 쓰이는 조합
        self.assertEqual(edit.toPlainText(), "aa\nbb")

    def test_ordinary_typing_still_reaches_the_editor(self) -> None:
        edit = self.editor("ab", at=1)
        self.press(edit, Qt.Key.Key_X, "x")
        self.assertEqual(edit.toPlainText(), "axb")
        self.press(edit, Qt.Key.Key_ParenLeft, "(")                    # 일반 메모는 괄호 짝을 넣지 않음
        self.assertEqual(edit.toPlainText(), "ax(b")

    # ── 코드 메모 ────────────────────────────────────────────────────────────
    def test_code_memo_pairs_brackets(self) -> None:
        edit = self.editor("", code=True)
        self.press(edit, Qt.Key.Key_ParenLeft, "(")
        self.assertEqual(edit.toPlainText(), "()")
        self.assertEqual(edit.textCursor().position(), 1)
        self.press(edit, Qt.Key.Key_ParenRight, ")")                   # 이미 있는 닫는 괄호는 덮어씀
        self.assertEqual(edit.toPlainText(), "()")
        self.assertEqual(edit.textCursor().position(), 2)
        self.put(edit, 1)
        self.press(edit, Qt.Key.Key_Backspace)                         # 빈 짝은 함께 지움
        self.assertEqual(edit.toPlainText(), "")

    def test_code_memo_wraps_the_selection(self) -> None:
        edit = self.editor("abc", code=True)
        cursor = edit.textCursor()
        cursor.setPosition(0)
        cursor.setPosition(3, QTextCursor.MoveMode.KeepAnchor)
        edit.setTextCursor(cursor)
        self.press(edit, Qt.Key.Key_QuoteDbl, '"')
        self.assertEqual(edit.toPlainText(), '"abc"')

    def test_code_memo_enter_keeps_and_deepens_the_indent(self) -> None:
        edit = self.editor("    a = 1", code=True, at=9)
        self.press(edit, Qt.Key.Key_Return, "\r")
        self.assertEqual(edit.toPlainText(), "    a = 1\n    ")
        edit = self.editor("if x:", code=True, at=5)
        self.press(edit, Qt.Key.Key_Return, "\r")
        self.assertEqual(edit.toPlainText(), "if x:\n    ")
        edit = self.editor("f = {}", code=True, at=5)                  # { | } 사이
        self.press(edit, Qt.Key.Key_Return, "\r")
        self.assertEqual(edit.toPlainText(), "f = {\n    \n}")
        self.assertEqual(edit.textCursor().block().text(), "    ")

    def test_code_memo_other_keys_fall_through(self) -> None:
        edit = self.editor("ab", code=True, at=2)
        self.press(edit, Qt.Key.Key_X, "x")
        self.assertEqual(edit.toPlainText(), "abx")
        self.press(edit, Qt.Key.Key_Backspace)
        self.assertEqual(edit.toPlainText(), "ab")

    # ── Tab ──────────────────────────────────────────────────────────────────
    def test_tab_indents_and_shift_tab_outdents(self) -> None:
        edit = self.editor("line")
        calls = []
        edit.memo_window.apply_indent = lambda: calls.append("in")
        edit.memo_window.apply_outdent = lambda: calls.append("out")
        self.press(edit, Qt.Key.Key_Tab, "\t")
        self.press(edit, Qt.Key.Key_Backtab)
        self.press(edit, Qt.Key.Key_Tab, "\t", SHIFT)
        self.assertEqual(calls, ["in", "out", "out"])
        self.assertEqual(edit.toPlainText(), "line")

    def test_enter_keeps_the_block_indent(self) -> None:
        edit = self.editor("line", at=4)
        cursor = edit.textCursor()
        fmt = cursor.blockFormat()
        fmt.setIndent(2)
        cursor.setBlockFormat(fmt)
        self.press(edit, Qt.Key.Key_Return, "\r")
        self.assertEqual(edit.document().blockCount(), 2)
        self.assertEqual(edit.textCursor().blockFormat().indent(), 2)


if __name__ == "__main__":
    unittest.main()
