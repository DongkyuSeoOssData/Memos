"""이전 내용: 기록 남기기와 되돌리기, 암호 메모의 기록, 이전 내용 화면."""
import datetime as dt
import json
import pathlib
import unittest
from unittest import mock

from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtTest import QTest

# support 를 먼저 가져와야 합니다. (offscreen 설정과 프로젝트 경로)
import support
from core import reminders
from ui.dialogs import HistoryDialog

D = dt.datetime


class HistoryTest(support.UiTestCase):
    def test_saving_new_content_keeps_the_old_one(self) -> None:
        memo = next(m for m in self.sm.load_local_memos() if m["id"] == "memo-0000")
        memo["content"] = "second"
        self.sm.save_memo_locally(memo)
        history = self.sm.list_history("memo-0000")
        self.assertEqual([h["text"] for h in history], ["body 0 #tag0"])

        # 연달아 저장한 것은 쌓지 않음 (10분 간격)
        memo["content"] = "third"
        self.sm.save_memo_locally(memo)
        self.assertEqual(len(self.sm.list_history("memo-0000")), 1)

    def test_meta_only_saves_do_not_add_history(self) -> None:
        memo = next(m for m in self.sm.load_local_memos() if m["id"] == "memo-0001")
        memo["is_favorite"] = True
        self.sm.save_memo_locally(memo)
        self.sm.set_reminder(memo, reminders.make(D(2030, 1, 1, 9, 0)))
        self.assertEqual(self.sm.list_history("memo-0001"), [])

    def test_restore_brings_back_the_content_and_can_be_undone(self) -> None:
        memo = next(m for m in self.sm.load_local_memos() if m["id"] == "memo-0000")
        memo["content"], memo["title"] = "second", "new title"
        self.sm.save_memo_locally(memo)
        index = self.sm.list_history("memo-0000")[0]["index"]
        self.assertTrue(self.sm.restore_history("memo-0000", index))
        self.assertEqual(self.disk("memo-0000")["title"], "t0")
        restored = next(m for m in self.sm.load_local_memos() if m["id"] == "memo-0000")
        self.assertEqual(restored["content"], "body 0 #tag0")
        self.assertEqual(self.sm.list_history("memo-0000")[0]["text"], "second")     # 되돌리기 직전 내용도 남음
        self.assertFalse(self.sm.restore_history("memo-0000", 99))

    def test_history_is_capped_and_removed_with_the_memo(self) -> None:
        memo = next(m for m in self.sm.load_local_memos() if m["id"] == "memo-0002")
        with mock.patch.object(self.sm, "HISTORY_MIN_GAP_SEC", 0):
            for i in range(self.sm.HISTORY_KEEP + 5):
                memo["content"] = f"v{i}"
                self.sm.save_memo_locally(memo)
        self.assertEqual(len(self.sm.list_history("memo-0002")), self.sm.HISTORY_KEEP)
        self.assertTrue((self.memo_dir / "history_bin" / "memo-0002.json").exists())
        self.sm.delete_memo_locally("memo-0002")
        self.sm.empty_trash_locally()
        self.assertFalse((self.memo_dir / "history_bin" / "memo-0002.json").exists())

    def test_history_folder_is_not_listed_as_memos(self) -> None:
        memo = next(m for m in self.sm.load_local_memos() if m["id"] == "memo-0000")
        memo["content"] = "second"
        self.sm.save_memo_locally(memo)
        self.assertEqual(len(self.sm.load_local_memos()), 3)

    def test_history_opens_beside_the_memo_and_restores(self) -> None:
        from PyQt6.QtCore import QTimer
        w = self.open_window("memo-0000")
        w.text_edit.setPlainText("rewritten")
        w.text_edit.document().setModified(True)
        w.execute_auto_save()
        seen = {}

        def steps() -> None:
            side = w.side_panel()
            view = side.panel
            seen["visible"] = side.isVisible()
            seen["attached"] = abs(side.x() - (w.bg.mapToGlobal(QPoint(0, 0)).x() + w.bg.width() - 1)) <= 1      # 메모 오른쪽에 붙음
            seen["same_color"] = w.memo_bg_color().lower() in side.styleSheet().lower()
            seen["tall_enough"] = side.height() >= 460
            view.list.setCurrentRow(0)
            view._restore()

        QTimer.singleShot(0, steps)
        w.show_history()
        self.assertEqual(seen, {"visible": True, "attached": True, "same_color": True, "tall_enough": True})
        self.assertEqual(w.text_edit.toPlainText(), "body 0 #tag0")
        self.assertEqual(self.sm.list_history("memo-0000")[0]["text"], "rewritten")
        self.assertFalse(w.side_panel().isVisible())

    def test_history_panel_closes_with_the_memo(self) -> None:
        from PyQt6.QtCore import QTimer
        w = self.open_window("memo-0000")
        QTimer.singleShot(0, w.hide)                                 # 메모를 숨기면 옆 패널도 닫히고 기다림이 끝남
        w.show_history()
        self.assertFalse(w.side_panel().isVisible())
        self.assertEqual(w.text_edit.toPlainText(), "body 0 #tag0")

    def test_dialog_with_no_history(self) -> None:
        d = HistoryDialog(None, "t", [])
        self.assertFalse(d.restore_button.isEnabled())
        d.close()


class LockedHistoryTest(support.UiTestCase):
    """암호 메모의 내용은 변경 기록에도 평문으로 남지 않고, 되돌려도 잠금 상태가 바뀌지 않습니다."""

    SECRET = "body 0 #tag0"

    def history_file(self, memo_id: str = "memo-0000") -> pathlib.Path:
        return self.memo_dir / "history_bin" / f"{memo_id}.json"

    def edit(self, w, text: str) -> None:
        with mock.patch.object(self.sm, "HISTORY_MIN_GAP_SEC", 0):
            w.text_edit.setPlainText(text)
            w.text_edit.document().setModified(True)
            w.execute_auto_save()

    def lock(self, memo_id: str = "memo-0000", password: str = "pw12"):
        w = self.open_window(memo_id)
        self.answers[:] = [password, password]
        w.set_memo_password()
        return w

    def test_setting_a_password_leaves_no_plaintext_in_the_history(self) -> None:
        w = self.open_window("memo-0000")
        self.edit(w, "second version")                               # 암호를 걸기 전에 쌓인 평문 기록
        self.assertIn(self.SECRET, self.history_file().read_text(encoding="utf-8"))
        self.answers[:] = ["pw12", "pw12"]
        w.set_memo_password()
        raw = self.history_file().read_text(encoding="utf-8")
        self.assertNotIn(self.SECRET, raw)                           # 예전 기록도
        self.assertNotIn("second version", raw)                      # 암호를 걸기 직전의 내용도 평문으로 남지 않음
        entries = self.sm.list_history("memo-0000")
        self.assertTrue(entries and all(e["locked"] and e["text"] == "" for e in entries))
        self.edit(w, "third version")                                # 잠긴 뒤에 쌓이는 기록도 암호문
        self.assertNotIn("second version", self.history_file().read_text(encoding="utf-8"))

    def test_history_opens_with_the_memo_key_or_the_password(self) -> None:
        w = self.lock()
        self.edit(w, "second version")
        index = self.sm.list_history("memo-0000")[-1]["index"]
        self.assertEqual(self.sm.read_history_text("memo-0000", index), self.SECRET)          # 메모가 열려 있으면 바로 보임
        w.lock_now()
        self.assertIsNone(self.sm.read_history_text("memo-0000", index))                      # 잠그면 암호가 필요
        self.assertIsNone(self.sm.read_history_text("memo-0000", index, "wrong"))
        self.assertEqual(self.sm.read_history_text("memo-0000", index, "pw12"), self.SECRET)

    def test_changing_the_password_reseals_the_history(self) -> None:
        w = self.lock()
        self.edit(w, "second version")
        self.answers[:] = ["pw12", "new-pw", "new-pw"]               # 지금 암호, 새 암호 두 번
        w.set_memo_password()                                        # 암호 변경
        w.lock_now()
        for entry in self.sm.list_history("memo-0000"):
            self.assertIsNone(self.sm.read_history_text("memo-0000", entry["index"], "pw12"), entry)       # 예전 암호로는 안 열림
            self.assertIsNotNone(self.sm.read_history_text("memo-0000", entry["index"], "new-pw"), entry)  # 새 암호 하나로 다 열림

    def test_removing_the_password_opens_the_history_again(self) -> None:
        w = self.lock()
        self.edit(w, "second version")
        self.answers[:] = ["pw12"]                                   # 지금 암호
        w.remove_memo_password()
        entries = self.sm.list_history("memo-0000")
        self.assertTrue(entries and all(not e["locked"] for e in entries))
        self.assertIn(self.SECRET, [e["text"] for e in entries])

    def test_plaintext_left_by_older_versions_is_sealed_on_unlock(self) -> None:
        w = self.lock()
        w.lock_now()
        self.history_file().parent.mkdir(parents=True, exist_ok=True)
        self.history_file().write_text(json.dumps([{                 # 예전 버전이 남긴 평문 기록
            "saved_at": "2026-01-01T00:00:00", "reason": "", "title": "t0", "content": "left in the clear",
            "updated_at": "", "is_locked": False}]), encoding="utf-8")
        w.lock_overlay.unlock_panel.inputs[0].setText("pw12")
        w.lock_overlay.unlock_panel.submit()                         # 잠금을 푸는 순간
        self.assertNotIn("left in the clear", self.history_file().read_text(encoding="utf-8"))
        self.assertEqual(self.sm.read_history_text("memo-0000", 0), "left in the clear")

    def test_restoring_keeps_the_memo_locked_with_its_current_password(self) -> None:
        w = self.open_window("memo-0000")
        self.edit(w, "second version")                               # 기록 0: 평문이었던 처음 내용
        self.answers[:] = ["pw12", "pw12"]
        w.set_memo_password()
        self.assertEqual(self.sm.restore_problem("memo-0000", 0), "")
        self.assertTrue(self.sm.restore_history("memo-0000", 0))
        self.ui.reload_pulled_memos(["memo-0000"])
        saved = self.disk("memo-0000")
        self.assertTrue(saved["is_locked"] and isinstance(saved["content"], dict))       # 여전히 암호 메모
        self.assertNotIn(self.SECRET, self.raw("memo-0000"))
        w.lock_now()
        self.answers[:] = ["pw12"]
        w.prompt_unlock()                                            # 지금 암호 그대로 열림
        self.assertEqual(w.text_edit.toPlainText(), self.SECRET)

    def test_locked_memo_must_be_unlocked_before_restoring(self) -> None:
        w = self.lock()
        self.edit(w, "second version")
        w.lock_now()
        before = self.raw("memo-0000")
        self.assertIn("잠금", self.sm.restore_problem("memo-0000", 0, "pw12"))
        self.assertFalse(self.sm.restore_history("memo-0000", 0, "pw12"))
        self.assertEqual(self.raw("memo-0000"), before)

    def test_history_under_another_password_needs_that_password(self) -> None:
        w = self.lock()
        crypto = self.sm.crypto
        salt = crypto.new_salt()
        foreign = crypto.encrypt_locked("old secret", crypto.derive_key("other-pw", salt), salt)
        self.history_file().parent.mkdir(parents=True, exist_ok=True)
        self.history_file().write_text(json.dumps([{
            "saved_at": "2026-01-01T00:00:00", "reason": "", "title": "old", "content": foreign,
            "updated_at": "", "is_locked": True}]), encoding="utf-8")
        self.assertIn("다른 암호", self.sm.restore_problem("memo-0000", 0))
        self.assertIn("일치하지", self.sm.restore_problem("memo-0000", 0, "nope"))
        self.assertFalse(self.sm.restore_history("memo-0000", 0, "nope"))
        self.assertTrue(self.sm.restore_history("memo-0000", 0, "other-pw"))
        self.ui.reload_pulled_memos(["memo-0000"])
        w.lock_now()
        self.answers[:] = ["pw12"]                                   # 되돌린 뒤에도 메모의 암호는 지금 것
        w.prompt_unlock()
        self.assertEqual((w.text_edit.toPlainText(), w.memo_data["title"]), ("old secret", "old"))

    def test_plain_memo_stays_plain_when_restoring_a_locked_entry(self) -> None:
        crypto = self.sm.crypto
        salt = crypto.new_salt()
        sealed = crypto.encrypt_locked("was secret once", crypto.derive_key("other-pw", salt), salt)
        self.history_file("memo-0001").parent.mkdir(parents=True, exist_ok=True)
        self.history_file("memo-0001").write_text(json.dumps([{
            "saved_at": "2026-01-01T00:00:00", "reason": "", "title": "t1", "content": sealed,
            "updated_at": "", "is_locked": True}]), encoding="utf-8")
        self.assertFalse(self.sm.restore_history("memo-0001", 0))
        self.assertTrue(self.sm.restore_history("memo-0001", 0, "other-pw"))
        saved = self.disk("memo-0001")
        self.assertEqual((saved["content"], saved["is_locked"]), ("was secret once", False))

    def test_history_screen_shows_and_checks_before_restoring(self) -> None:
        from ui.dialogs import HistoryView
        w = self.lock()
        self.edit(w, "second version")
        w.lock_now()
        entries = self.sm.list_history("memo-0000")
        view = HistoryView("t", entries,
                           reveal=lambda index, pwd: self.sm.read_history_text("memo-0000", index, pwd),
                           check=lambda index, pwd: self.sm.restore_problem("memo-0000", index, pwd))
        self.addCleanup(view.close)
        view.show()
        got = []
        view.submitted.connect(got.append)
        view.list.setCurrentRow(len(entries) - 1)
        self.assertTrue(view.unlock_row.isVisible())                 # 잠긴 메모: 암호를 넣어야 내용이 보임
        self.assertNotIn(self.SECRET, view.preview.toPlainText())
        view.password_edit.setText("wrong")
        view.unlock_button.click()
        self.assertTrue(view.unlock_error.isVisible())
        view.password_edit.setText("pw12")
        QTest.keyClick(view.password_edit, Qt.Key.Key_Return)
        self.assertEqual(view.preview.toPlainText(), self.SECRET)
        self.assertFalse(view.unlock_row.isVisible())
        view.restore_button.click()                                  # 메모가 잠겨 있으면 되돌리지 않고 이유를 알림
        self.assertEqual(got, [])
        self.assertIn("잠금", view.unlock_error.text())

        self.answers[:] = ["pw12"]
        w.prompt_unlock()
        view.restore_button.click()                                  # 잠금을 푼 뒤에는 되돌려짐
        self.assertEqual(got, [entries[-1]["index"]])

    def test_open_memo_shows_its_locked_history_without_asking(self) -> None:
        from ui.dialogs import HistoryView
        w = self.lock()
        self.edit(w, "second version")
        entries = self.sm.list_history("memo-0000")
        view = HistoryView("t", entries, reveal=lambda index, pwd: self.sm.read_history_text("memo-0000", index, pwd))
        self.addCleanup(view.close)
        view.show()
        view.list.setCurrentRow(len(entries) - 1)
        self.assertFalse(view.unlock_row.isVisible())
        self.assertEqual(view.preview.toPlainText(), self.SECRET)


class HistoryViewTest(support.UiTestCase):
    """이전 내용 화면의 구성."""

    def test_history_shows_titles_first_and_body_on_click(self) -> None:
        from ui.dialogs import HistoryView
        entries = [{"index": 1, "saved_at": "2026-10-11T08:29:00", "reason": "", "title": "둘째", "locked": False, "text": "second body"},
                   {"index": 0, "saved_at": "2026-10-10T07:00:00", "reason": "", "title": "첫째", "locked": True, "text": ""}]
        view = HistoryView("메모", entries)
        self.addCleanup(view.close)
        view.show()
        changed = []
        view.layout_changed.connect(lambda: changed.append(True))
        self.assertTrue(view.detail.isHidden())                      # 처음에는 목록만
        self.assertEqual(view.list.item(0).text(), "10.11 08:29" + chr(10) + "둘째")
        self.assertIn("암호 메모", view.list.item(1).text())
        view.list.setCurrentRow(0)
        self.assertFalse(view.detail.isHidden())                     # 고르면 오른쪽에 본문이 펼쳐짐
        self.assertEqual((view.preview.toPlainText(), changed), ("second body", [True]))
        self.assertGreater(view.detail.mapTo(view, QPoint(0, 0)).x(), view.list.mapTo(view, QPoint(0, 0)).x() + view.list.width() - 1)
        got = []
        view.submitted.connect(got.append)
        view.restore_button.click()
        self.assertEqual(got, [1])

        empty = HistoryView("메모", [])
        self.addCleanup(empty.close)
        self.assertFalse(empty.restore_button.isEnabled())
        empty.list.setCurrentRow(0)
        self.assertTrue(empty.detail.isHidden())


if __name__ == "__main__":
    unittest.main()
