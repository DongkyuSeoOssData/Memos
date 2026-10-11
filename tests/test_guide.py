"""사용 안내 메모."""
import datetime as dt
import unittest
from unittest import mock

from PyQt6.QtCore import Qt

# support 를 먼저 가져와야 합니다. (offscreen 설정과 프로젝트 경로)
import support
from ui import checklist

D = dt.datetime


class GuideMemoTest(support.UiTestCase):
    """처음 실행할 때 사용 안내 메모를 남깁니다."""

    def test_first_run_leaves_guide_memos(self) -> None:
        from core import guide
        for path in self.memo_dir.glob("*.json"):
            path.unlink()
        self.ui.show_all_memos()
        memos = {m["id"]: m for m in self.sm.load_local_memos()}
        self.assertEqual(sorted(memos), ["guide-explorer", "guide-memo", "guide-settings"])
        self.assertTrue(all(m["folder"] == guide.FOLDER and m["content"].strip() for m in memos.values()))
        self.assertIn(guide.FOLDER, self.sm.settings["folders"])
        self.assertTrue(self.sm.settings["guide_memos_made"])
        self.assertEqual(list(self.ui.memo_windows), ["guide-memo"])           # 첫 안내만 화면에 띄움
        ex = self.explorer()
        ex.refresh()
        self.assertEqual(ex.table.item(0, 2).data(Qt.ItemDataRole.UserRole)["id"], "guide-memo")     # ①이 맨 위

        # 읽고 지운 뒤에는 다시 만들지 않음
        for w in list(self.ui.memo_windows.values()):
            w._is_deleting = True
            w.close()
        self.ui.memo_windows.clear()
        for path in self.memo_dir.glob("*.json"):
            path.unlink()
        self.ui.show_all_memos()
        self.assertFalse(any(m["id"].startswith("guide-") for m in self.sm.load_local_memos()))
        # 트레이 메뉴로는 다시 만들 수 있음
        self.ui.remake_guide_memos()
        self.assertEqual(len([m for m in self.sm.load_local_memos() if m["id"].startswith("guide-")]), 3)
        self.assertIn("guide-memo", self.ui.memo_windows)

    def test_existing_users_do_not_get_guides(self) -> None:
        self.assertFalse(any(m["id"].startswith("guide-") for m in self.sm.load_local_memos()))
        self.assertNotIn("guide_memos_made", self.sm.settings)

    def test_guide_checklist_is_usable(self) -> None:
        from core import guide
        self.assertEqual(checklist.progress(guide.MEMO_GUIDE)[1], 4)
        for memo in guide.build(D(2026, 1, 1)):
            self.assertTrue(support.smm.is_safe_memo_id(memo["id"]) if hasattr(support.smm, "is_safe_memo_id") else True)

    # ── 8. 동기화를 쓰는 PC 에서는 안내 메모를 자동으로 만들지 않음 ──
    def test_guides_are_not_auto_made_on_a_pc_joining_sync(self) -> None:
        for path in self.memo_dir.glob("*.json"):
            path.unlink()
        self.sm.settings.update({"use_sync": True, "drive_folder_id": "https://example.invalid/exec"})
        with mock.patch.object(self.sm, "check_remote_if_stale"), mock.patch.object(self.sm, "_start_sync", create=True):
            self.ui.show_all_memos()
        self.assertFalse(any(m["id"].startswith("guide-") for m in self.sm.load_local_memos()))


if __name__ == "__main__":
    unittest.main()
