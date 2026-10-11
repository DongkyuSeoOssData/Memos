"""빠른 검색."""
import unittest

from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest

# support 를 먼저 가져와야 합니다. (offscreen 설정과 프로젝트 경로)
import support
from ui.quick_search import QuickSearch


class QuickSearchTest(support.UiTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.sm.save_memo_locally({"id": "memo-0009", "title": "회의 body", "content": "분기 계획", "folder": "업무",
                                   "updated_at": "2026-02-01T00:00:00", "is_visible": False})
        self.qs = QuickSearch(self.ui)
        self.addCleanup(self.qs.close)
        self.qs.popup()

    def ids(self, query: str) -> list:
        return [m["id"] for m in self.qs.search(query)]

    def test_empty_query_lists_recent_first(self) -> None:
        self.assertEqual(self.ids(""), ["memo-0009", "memo-0002", "memo-0001", "memo-0000"])

    def test_title_matches_come_before_body_matches(self) -> None:
        self.assertEqual(self.ids("body"), ["memo-0009", "memo-0002", "memo-0001", "memo-0000"])
        self.assertEqual(self.ids("BODY tag1"), ["memo-0001"])
        self.assertEqual(self.ids("업무"), ["memo-0009"])            # 폴더 이름으로도 찾음
        self.assertEqual(self.ids("없는말"), [])

    def test_typing_and_enter_opens_the_memo(self) -> None:
        QTest.keyClicks(self.qs.input, "tag1")
        self.assertEqual(self.qs.results.count(), 1)
        QTest.keyClick(self.qs.input, Qt.Key.Key_Return)
        self.assertFalse(self.qs.isVisible())
        self.assertIn("memo-0001", self.ui.memo_windows)

    def test_arrows_move_and_escape_closes(self) -> None:
        QTest.keyClick(self.qs.input, Qt.Key.Key_Down)
        self.assertEqual(self.qs.results.currentRow(), 1)
        QTest.keyClick(self.qs.input, Qt.Key.Key_Up)
        QTest.keyClick(self.qs.input, Qt.Key.Key_Up)
        self.assertEqual(self.qs.results.currentRow(), 3)            # 처음에서 위로 가면 끝으로
        QTest.keyClick(self.qs.input, Qt.Key.Key_Escape)
        self.assertFalse(self.qs.isVisible())

    def test_locked_memo_content_is_not_searched(self) -> None:
        w = self.open_window("memo-0000")
        self.answers[:] = ["pw12", "pw12"]
        w.set_memo_password()
        w.lock_now()
        self.qs.popup()
        self.assertNotIn("memo-0000", self.ids("tag0"))
        self.assertIn("memo-0000", self.ids("t0"))                   # 제목으로는 찾음

    def test_tray_and_hotkey_toggle(self) -> None:
        self.ui.toggle_quick_search()
        self.assertTrue(self.ui.quick_search.isVisible())
        self.ui.toggle_quick_search()
        self.assertFalse(self.ui.quick_search.isVisible())


class QuickSearchPrivacyTest(support.UiTestCase):
    """암호 메모의 내용은 풀려 있어도 검색에 나오지 않습니다."""

    def test_quick_search_hides_unlocked_password_memo_text(self) -> None:
        w = self.open_window("memo-0000")
        self.answers[:] = ["pw12", "pw12"]
        w.set_memo_password()                                        # 암호 메모지만 지금은 열려 있음
        qs = QuickSearch(self.ui)
        self.addCleanup(qs.close)
        qs.popup()
        self.assertNotIn("memo-0000", [m["id"] for m in qs.search("tag0")])      # 내용으로는 찾지 않음
        self.assertIn("memo-0000", [m["id"] for m in qs.search("t0")])           # 제목으로는 찾음
        qs.input.setText("t0")
        text = " ".join(qs.results.item(i).text() for i in range(qs.results.count()))
        self.assertNotIn("body 0", text)


if __name__ == "__main__":
    unittest.main()
