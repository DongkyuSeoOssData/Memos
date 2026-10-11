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


class QuitKeepsMemosTest(support.UiTestCase):
    """앱을 끝낼 때 닫히는 메모는 숨김으로 저장하지 않습니다. (다시 켜면 떠 있던 메모가 다시 뜸)"""

    def test_memos_open_at_quit_come_back_after_restart(self) -> None:
        rolled = self.open_window("memo-0000")
        rolled.toggle_rollup()
        rolled.move(10, 500)
        opened = self.open_window("memo-0001")
        closed = self.open_window("memo-0002")
        closed.close()                                                # 사용자가 직접 닫은 메모
        support.app.processEvents()
        self.ui.quitting = True                                       # 트레이의 '종료'
        for w in (rolled, opened):
            w.close()                                                 # Qt 가 끝내면서 창을 닫음
        self.assertTrue(self.disk("memo-0000")["is_visible"])
        self.assertTrue(self.disk("memo-0001")["is_visible"])
        self.assertFalse(self.disk("memo-0002")["is_visible"])        # 직접 닫은 것은 숨김 그대로
        self.assertTrue(self.disk("memo-0000")["is_rolled_up"])       # 접힌 상태와 자리도 기억
        self.assertEqual(self.disk("memo-0000")["rolled_position_x"], 10)

        again = support.uim.UIManager(self.sm)                        # 다시 켬
        self.addCleanup(lambda: [w.close() for w in list(again.memo_windows.values())])
        again.show_all_memos()
        self.assertIn("memo-0000", again.memo_windows)
        self.assertIn("memo-0001", again.memo_windows)
        self.assertNotIn("memo-0002", again.memo_windows)
        self.assertTrue(again.memo_windows["memo-0000"]._is_rolled_up)
        self.assertTrue(again.memo_windows["memo-0000"].isVisible())

    def test_quit_sets_the_flag_before_closing(self) -> None:
        with mock.patch.object(support.uim.QApplication, "quit") as quit_app:
            self.ui.quit_app()
        self.assertTrue(self.ui.quitting)
        quit_app.assert_called_once()


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
