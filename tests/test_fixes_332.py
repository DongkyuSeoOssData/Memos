"""3.3.2 에서 고친 것: 저장 실패 알림, 빈 메모 자동 삭제의 범위, 암호를 바꾸거나 없앨 때 지금 암호 확인."""
import unittest
from unittest import mock

# support 를 먼저 가져와야 합니다. (offscreen 설정과 프로젝트 경로)
import support


class SaveFailureTest(support.UiTestCase):
    def typing(self, memo_id: str = "memo-0000"):
        w = self.open_window(memo_id)
        w.text_edit.setPlainText("precious text")
        w.text_edit.document().setModified(True)
        w._schedule_auto_save()
        self.toasts = []
        w.show_toast = lambda text, warn=False: self.toasts.append((text, warn))
        return w

    def broken_disk(self):
        return mock.patch.object(self.sm, "save_memo_locally", return_value=False)

    def test_failed_save_is_not_reported_as_saved(self) -> None:
        w = self.typing()
        with self.broken_disk():
            self.assertFalse(w.flush_auto_save())
        self.assertEqual(len(self.toasts), 1)
        self.assertTrue(self.toasts[0][1])                            # 경고
        self.assertIn("저장하지 못했습니다", self.toasts[0][0])
        self.assertTrue(w.text_edit.document().isModified())          # 아직 저장되지 않은 것으로 남음
        self.assertTrue(w._auto_save_timer.isActive())                # 조금 뒤에 다시 시도
        self.assertTrue(w.flush_auto_save())                          # 디스크가 돌아오면 저장됨
        self.assertEqual(self.toasts[-1], ("✓ 저장됨", False))
        self.assertIn("precious text", self.disk("memo-0000")["content"])

    def test_closing_is_held_back_once_when_the_save_fails(self) -> None:
        w = self.typing()
        with self.broken_disk():
            w.close()
            self.assertTrue(w.isVisible())                            # 한 번은 닫지 않고 알림
            self.assertIn("닫지 않았습니다", self.toasts[-1][0])
            self.assertEqual(w.text_edit.toPlainText(), "precious text")
            w.close()                                                 # 한 번 더 닫으면 닫힘
            self.assertFalse(w.isVisible())

    def test_auto_lock_waits_when_the_save_fails(self) -> None:
        w = self.open_window("memo-0000")
        self.answers[:] = ["pw12", "pw12"]
        w.set_memo_password()
        w.text_edit.setPlainText("secret draft")
        w.text_edit.document().setModified(True)
        w._schedule_auto_save()
        with self.broken_disk():
            w.lock_now()
        self.assertFalse(w.is_sealed())                               # 잠그지 않음 (잠그면 본문이 메모리에서도 지워짐)
        self.assertEqual(w.text_edit.toPlainText(), "secret draft")
        self.assertIn("저장하지 못해 잠그지 않았습니다.", self.warnings)
        w.lock_now()                                                  # 저장이 되면 잠김
        self.assertTrue(w.is_sealed())

    def test_blank_new_memo_is_not_a_failed_save(self) -> None:
        self.ui.create_empty_memo()
        w = next(w for w in self.ui.memo_windows.values() if w.memo_data.get("is_draft"))
        self.assertTrue(self.ui.notify_save(w.memo_data))
        self.assertTrue(w.execute_auto_save())


class EmptyMemoOnCloseTest(support.UiTestCase):
    def test_saved_memo_survives_being_emptied_and_closed(self) -> None:
        w = self.open_window("memo-0000")
        w.text_edit.setPlainText("")
        w.text_edit.document().setModified(True)
        w._schedule_auto_save()
        w.close()
        self.assertTrue((self.memo_dir / "memo-0000.json").exists())  # 휴지통으로 가지 않음
        self.assertFalse((self.sm.trash_path / "memo-0000.json").exists())
        self.assertEqual(self.disk("memo-0000")["content"], "")

    def test_untouched_new_memo_is_still_cleaned_up(self) -> None:
        self.ui.create_empty_memo()
        w = next(w for w in self.ui.memo_windows.values() if w.memo_data.get("is_draft"))
        memo_id = w.memo_data["id"]
        w.close()
        self.assertNotIn(memo_id, self.ui.memo_windows)
        self.assertFalse((self.memo_dir / f"{memo_id}.json").exists())


class CurrentPasswordTest(support.UiTestCase):
    def locked(self):
        w = self.open_window("memo-0000")
        self.answers[:] = ["old1", "old1"]
        w.set_memo_password()
        self.warnings.clear()
        return w

    def test_changing_needs_the_current_password(self) -> None:
        w = self.locked()
        self.answers[:] = ["wrong", "new1", "new1"]
        w.set_memo_password()
        self.assertIn("지금 암호가 일치하지 않습니다.", self.warnings)
        self.assertTrue(self.sm.check_memo_password("memo-0000", "old1"))       # 그대로
        self.answers[:] = ["old1", "new1", "new1"]
        w.set_memo_password()
        self.assertTrue(self.sm.check_memo_password("memo-0000", "new1"))
        self.assertFalse(self.sm.check_memo_password("memo-0000", "old1"))

    def test_removing_needs_the_current_password(self) -> None:
        w = self.locked()
        self.answers[:] = ["wrong"]
        w.remove_memo_password()
        self.assertTrue(self.disk("memo-0000")["is_locked"])
        self.assertIn("암호가 일치하지 않습니다.", self.warnings)
        self.answers[:] = ["old1"]
        w.remove_memo_password()
        self.assertFalse(self.disk("memo-0000")["is_locked"])

    def test_failed_removal_is_reported(self) -> None:
        w = self.locked()
        self.answers[:] = ["old1"]
        with mock.patch.object(self.sm, "remove_memo_password", return_value=False):
            w.remove_memo_password()
        self.assertIn("암호를 없애지 못했습니다.", self.warnings)

    def test_first_password_asks_only_for_the_new_one(self) -> None:
        w = self.open_window("memo-0001")
        self.answers[:] = ["pw12", "pw12"]
        w.set_memo_password()
        self.assertEqual(self.answers, [])
        self.assertTrue(self.sm.check_memo_password("memo-0001", "pw12"))
        self.assertFalse(self.sm.check_memo_password("memo-0001", ""))
        self.assertFalse(self.sm.check_memo_password("memo-0002", "pw12"))      # 암호 메모가 아님


if __name__ == "__main__":
    unittest.main()
