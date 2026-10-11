"""암호 메모의 화면: 메모 안에서 암호 묻기, 잠긴 메모의 크기, 접고 펴기, 잠금 표시."""
import unittest
from unittest import mock

from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtTest import QTest

# support 를 먼저 가져와야 합니다. (offscreen 설정과 프로젝트 경로)
import support


class LockOverlayTest(support.UiTestCase):
    """암호는 따로 창을 띄우지 않고 메모 창 안에서 묻습니다."""

    def setUp(self) -> None:
        super().setUp()
        self.real_ask = self.real_form_ask
        self.w = self.open_window("memo-0000")
        self.w.resize(360, 380)
        support.app.processEvents()

    def drive(self, steps) -> None:
        """입력 묶음이 뜨면 steps(panel) 을 실행합니다. (입력을 기다리는 동안 실행되도록 예약)"""
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(0, lambda: steps(self.w.lock_overlay.panel))

    def test_setting_a_password_happens_inside_the_memo(self) -> None:
        seen = {}

        def steps(panel) -> None:
            seen["overlay"] = self.w.lock_overlay.isVisible()
            seen["blurred"] = self.w.text_edit.graphicsEffect() is not None
            seen["parent"] = self.w.lock_overlay.isAncestorOf(panel)
            panel.inputs[0].setText("pw12")
            panel.inputs[1].setText("nope")
            panel.submit()
            seen["error"] = panel.error.text()
            panel.inputs[1].setText("pw12")
            panel.submit()

        self.drive(steps)
        with mock.patch.object(support.themed_dialog, "ask_form", self.real_ask):
            self.w.set_memo_password()
        self.assertEqual(seen, {"overlay": True, "blurred": True, "parent": True, "error": "⚠ 두 암호가 일치하지 않습니다."})
        self.assertTrue(self.disk("memo-0000")["is_locked"])
        self.assertIsNone(self.w.text_edit.graphicsEffect())         # 끝나면 흐림을 걷음
        self.assertTrue(self.w.lock_overlay.isHidden())

    def test_locked_memo_shows_a_password_box_in_the_middle_and_unlocks_in_place(self) -> None:
        self.answers[:] = ["pw12", "pw12"]
        self.w.set_memo_password()
        self.w.lock_now()
        overlay = self.w.lock_overlay
        panel = overlay.unlock_panel
        self.assertTrue(overlay.isVisible() and panel.isVisible())
        self.assertEqual(overlay.geometry().size(), self.w.text_edit.size())
        support.app.processEvents()
        self.assertLessEqual(abs(panel.geometry().center().x() - overlay.rect().center().x()), 1)     # 한가운데
        self.assertLessEqual(abs(panel.geometry().center().y() - overlay.rect().center().y()), 1)
        self.assertIsNone(panel.cancel_button)

        panel.inputs[0].setText("wrong")
        QTest.keyClick(panel.inputs[0], Qt.Key.Key_Return)
        self.assertEqual(panel.error.text(), "⚠ 암호가 일치하지 않습니다.")
        self.assertTrue(self.w.memo_data.get("_locked"))
        panel.inputs[0].setText("pw12")
        QTest.keyClick(panel.inputs[0], Qt.Key.Key_Return)
        self.assertFalse(self.w.memo_data.get("_locked"))
        self.assertTrue(overlay.isHidden())
        self.assertIsNone(overlay.unlock_panel)
        self.assertEqual(self.w.text_edit.toPlainText(), "body 0 #tag0")

    def test_opening_a_locked_memo_from_the_explorer_never_pops_a_prompt(self) -> None:
        self.answers[:] = ["pw12", "pw12"]
        self.w.set_memo_password()
        self.w.lock_now()
        asked = []
        with mock.patch.object(support.themed_dialog, "ask_form", lambda *a, **k: asked.append(a)):
            # 펼친 메모: 암호 칸이 있는 화면으로 열림
            self.w.hide()
            self.ui.show_specific_memo("memo-0000")
            support.app.processEvents()
            self.assertTrue(self.w.isVisible() and self.w.lock_overlay.unlock_panel.isVisible())
            # 접은 메모: 접힌 그대로 열리고 아무것도 묻지 않음. 펼치면 암호 칸이 나타남
            self.w.toggle_rollup()
            self.w.hide()
            self.ui.show_specific_memo("memo-0000")
            support.app.processEvents()
            self.assertTrue(self.w.isVisible() and self.w._is_rolled_up)
            self.assertTrue(self.w.lock_overlay.isHidden())
            self.w.toggle_rollup()
            self.assertTrue(self.w.lock_overlay.unlock_panel.isVisible())
        self.assertEqual(asked, [])
        self.assertTrue(self.w.memo_data.get("_locked"))

    def test_cancel_leaves_everything_as_it_was(self) -> None:
        self.drive(lambda panel: panel.cancel_button.click())
        with mock.patch.object(support.themed_dialog, "ask_form", self.real_ask):
            self.w.set_memo_password()
        self.assertFalse(self.disk("memo-0000").get("is_locked"))
        self.assertTrue(self.w.lock_overlay.isHidden())
        self.assertIsNone(self.w.text_edit.graphicsEffect())

    def test_tiny_memo_asks_beside_itself(self) -> None:
        from PyQt6.QtCore import QTimer
        self.w.resize(200, 150)
        support.app.processEvents()
        seen = {}

        def steps() -> None:
            side = self.w.side_panel()
            seen["beside"] = side.isVisible() and side.panel is not None
            side.panel.inputs[0].setText("pw12")
            side.panel.inputs[1].setText("pw12")
            side.panel.submit()

        QTimer.singleShot(0, steps)
        with mock.patch.object(support.themed_dialog, "ask_form", self.real_ask):
            self.w.set_memo_password()
        self.assertEqual(seen, {"beside": True})
        self.assertTrue(self.disk("memo-0000")["is_locked"])

    def test_password_form_is_centered(self) -> None:
        seen = {}

        def steps(panel) -> None:
            overlay = self.w.lock_overlay
            support.app.processEvents()
            seen["dx"] = abs(panel.geometry().center().x() - overlay.rect().center().x()) <= 1
            seen["dy"] = abs(panel.geometry().center().y() - overlay.rect().center().y()) <= 1
            panel.cancel_button.click()

        self.drive(steps)
        with mock.patch.object(support.themed_dialog, "ask_form", self.real_ask):
            self.w.set_memo_password()
        self.assertEqual(seen, {"dx": True, "dy": True})

    def test_rolled_or_tiny_memo_cannot_host_the_form(self) -> None:
        overlay = self.w.lock_overlay
        self.assertTrue(overlay.can_host(230, 220))
        self.w.toggle_rollup()
        self.assertFalse(overlay.can_host(230, 100))                 # 접힌 메모는 대화상자로 묻음
        self.w.toggle_rollup()
        self.w.resize(200, 150)
        support.app.processEvents()
        self.assertFalse(overlay.can_host(230, 220))

    def test_locked_overlay_hides_while_rolled_up(self) -> None:
        self.answers[:] = ["pw12", "pw12"]
        self.w.set_memo_password()
        self.w.lock_now()
        self.w.toggle_rollup()
        self.assertTrue(self.w.lock_overlay.isHidden())
        self.w.toggle_rollup()
        self.assertTrue(self.w.lock_overlay.isVisible())


class LockedFirstFoldTest(support.UiTestCase):
    """잠긴 메모를 접고 펴도 접은 메모의 크기는 암호 입력용 크기에 끌려가지 않습니다."""

    def locked(self, memo_id: str, width: int = 500):
        w = self.open_window(memo_id)
        w.setGeometry(100, 100, width, 400)
        self.answers[:] = ["pw12", "pw12"]
        w.set_memo_password()
        w.lock_now()
        self.assertEqual((w.width(), w.height()), w.LOCKED_SIZE)
        return w

    def unlock(self, w) -> None:
        w.lock_overlay.unlock_panel.inputs[0].setText("pw12")
        w.lock_overlay.unlock_panel.submit()

    def test_first_fold_of_a_locked_memo_uses_its_real_width(self) -> None:
        w = self.locked("memo-0000")                                 # 한 번도 접은 적 없는 메모를 잠근 뒤
        w.toggle_rollup()
        support.app.processEvents()
        self.assertEqual(w.width(), 500)                             # 암호 입력용 너비(340)가 아니라 메모 본래의 너비로 접힘
        spot = (w.x(), w.y(), w.width())
        for _ in range(3):
            w.toggle_rollup()
            support.app.processEvents()
            self.assertEqual((w.width(), w.height()), w.LOCKED_SIZE)
            w.toggle_rollup()
            support.app.processEvents()
            self.assertEqual((w.x(), w.y(), w.width()), spot)
        w.toggle_rollup()
        self.unlock(w)
        self.assertEqual((w.width(), w.height()), (500, 400))
        w.toggle_rollup()
        self.assertEqual((w.x(), w.y(), w.width()), spot)            # 암호를 푼 뒤에도 같은 자리·같은 너비
        self.assertEqual(w.memo_data["rolled_width"], 500)

    def test_first_fold_lands_where_an_unlocked_memo_would(self) -> None:
        plain = self.open_window("memo-0001")
        plain.setGeometry(100, 100, 500, 400)
        plain.toggle_rollup()
        locked = self.locked("memo-0000")
        locked.toggle_rollup()
        self.assertEqual((locked.x(), locked.y(), locked.width()), (plain.x(), plain.y(), plain.width()))

    def test_reopening_a_rolled_locked_memo_keeps_its_width(self) -> None:
        w = self.locked("memo-0000")
        w.toggle_rollup()
        w.resize(280, w.height())
        w.close()
        w = self.open_window("memo-0000")
        self.assertEqual((w._is_rolled_up, w.width()), (True, 280))
        w.toggle_rollup()
        w.close()
        w = self.open_window("memo-0000")                            # 잠긴 채 펼쳐진 상태로 다시 열림
        self.assertEqual((w.width(), w.height()), w.LOCKED_SIZE)
        w.toggle_rollup()
        self.assertEqual(w.width(), 280)
        saved = self.disk("memo-0000")
        self.assertEqual((saved["unrolled_width"], saved["unrolled_height"]), (500, 400))


class LockedMemoSizeTest(support.UiTestCase):
    """잠긴 메모는 암호 입력용 크기로 뜨고, 접은 너비와 본래 크기는 그대로입니다."""

    def test_locked_memo_opens_small_and_grows_back_after_the_password(self) -> None:
        w = self.open_window("memo-0000")
        w.setGeometry(200, 150, 520, 430)
        self.answers[:] = ["pw12", "pw12"]
        w.set_memo_password()
        self.assertEqual((w.width(), w.height()), (520, 430))        # 암호를 걸기만 해서는 그대로
        w.lock_now()
        self.assertEqual((w.width(), w.height()), w.LOCKED_SIZE)     # 잠기면 암호 입력용 크기로
        self.assertEqual((w.x(), w.y()), (200, 150))
        self.assertTrue(w.lock_overlay.unlock_panel.isVisible())
        self.assertGreaterEqual(w.text_edit.height(), w.lock_overlay.unlock_panel.sizeHint().height())    # 암호 칸이 잘리지 않음
        w.resize(300, 260)                                           # 잠긴 채로 크기를 바꿔도 메모의 크기로 기억하지 않음
        w.close()
        saved = self.disk("memo-0000")
        self.assertEqual((saved["unrolled_width"], saved["unrolled_height"], saved["width"], saved["height"]), (520, 430, 520, 430))

        w = self.open_window("memo-0000")
        self.assertEqual((w.width(), w.height()), w.LOCKED_SIZE)
        w.lock_overlay.unlock_panel.inputs[0].setText("pw12")
        w.lock_overlay.unlock_panel.submit()
        self.assertFalse(w.memo_data.get("_locked"))
        self.assertEqual((w.width(), w.height()), (520, 430))        # 암호를 넣으면 원래 크기로

    def test_locked_rolled_memo_unrolls_small(self) -> None:
        w = self.open_window("memo-0000")
        w.setGeometry(200, 150, 520, 430)
        self.answers[:] = ["pw12", "pw12"]
        w.set_memo_password()
        w.lock_now()
        w.toggle_rollup()
        w.toggle_rollup()
        self.assertEqual((w.width(), w.height()), w.LOCKED_SIZE)
        self.assertEqual(w.memo_data["unrolled_width"], 520)

    def test_rolled_password_memo_shows_a_lock(self) -> None:
        w = self.open_window("memo-0000")
        self.assertTrue(w.lbl_lock.isHidden())
        self.answers[:] = ["pw12", "pw12"]
        w.set_memo_password()
        self.assertTrue(w.lbl_lock.isHidden())                       # 펼쳐져 있을 때는 본문 쪽에서 알 수 있음
        w.toggle_rollup()
        self.assertFalse(w.lbl_lock.isHidden())
        w.toggle_rollup()
        self.assertTrue(w.lbl_lock.isHidden())

    def test_lock_badge_sits_at_the_left_of_the_title(self) -> None:
        w = self.open_window("memo-0000")
        self.answers[:] = ["pw12", "pw12"]
        w.set_memo_password()
        w.toggle_rollup()
        support.app.processEvents()
        self.assertFalse(w.lbl_lock.isHidden())
        self.assertEqual(w.lbl_lock.mapTo(w, QPoint(0, 0)).x(), w.title_edit.mapTo(w, QPoint(0, 0)).x())    # 제목 칸의 왼쪽 끝
        self.assertEqual(w.title_edit.textMargins().left(), w.LOCK_BADGE_WIDTH)                              # 제목 글자는 그 오른쪽부터
        w.toggle_rollup()
        self.assertTrue(w.lbl_lock.isHidden())
        self.assertEqual(w.title_edit.textMargins().left(), 0)

    def test_adding_a_password_never_widens_a_rolled_memo(self) -> None:
        w = self.open_window("memo-0000")
        w.setGeometry(100, 100, 500, 400)
        w.toggle_rollup()
        w.resize(10, w.height())                                     # 줄일 수 있는 데까지 좁게 접어 둔 메모
        support.app.processEvents()
        narrowest, needed = w.width(), w.minimumSizeHint().width()
        self.assertLess(narrowest, 500)
        self.answers[:] = ["pw12", "pw12"]
        w.set_memo_password()                                        # 접힌 채로 암호를 걸면
        support.app.processEvents()
        self.assertFalse(w.lbl_lock.isHidden())                      # 자물쇠가 바로 보이고
        self.assertEqual((w.width(), w.minimumSizeHint().width()), (narrowest, needed))      # 너비는 그대로
        w.lock_now()
        support.app.processEvents()
        self.assertEqual((w.width(), w.minimumSizeHint().width(), w.memo_data["rolled_width"]), (narrowest, needed, narrowest))
        self.answers[:] = ["pw12"]
        w.prompt_unlock()
        self.answers[:] = ["pw12"]                                   # 지금 암호
        w.remove_memo_password()                                     # 암호를 없애면 자물쇠도 사라지고 너비는 그대로
        support.app.processEvents()
        self.assertTrue(w.lbl_lock.isHidden())
        self.assertEqual(w.width(), narrowest)

    def test_locked_memo_keeps_its_rolled_width_and_shows_the_password_box_when_opened(self) -> None:
        w = self.open_window("memo-0000")
        w.setGeometry(200, 150, 520, 430)
        self.answers[:] = ["pw12", "pw12"]
        w.set_memo_password()
        w.toggle_rollup()
        w.resize(410, w.height())                                    # 접은 메모의 너비를 정해 둠
        w.move(300, 400)
        w.lock_now()
        self.assertEqual((w.x(), w.y(), w.width()), (300, 400, 410))
        for _ in range(3):                                           # 폈다 접기를 되풀이해도 접은 크기는 그대로
            w.toggle_rollup()
            support.app.processEvents()
            self.assertEqual((w.width(), w.height()), w.LOCKED_SIZE)
            overlay, panel = w.lock_overlay, w.lock_overlay.unlock_panel
            self.assertTrue(overlay.isVisible() and panel.isVisible())
            self.assertEqual(overlay.geometry().size(), w.text_edit.size())
            self.assertTrue(overlay.rect().contains(panel.geometry()), (overlay.rect(), panel.geometry()))      # 암호 칸이 잘리지 않고
            self.assertLessEqual(abs(panel.geometry().center().x() - overlay.rect().center().x()), 1)           # 한가운데
            self.assertLessEqual(abs(panel.geometry().center().y() - overlay.rect().center().y()), 1)
            w.toggle_rollup()
            self.assertEqual((w.x(), w.y(), w.width()), (300, 400, 410))
        w.toggle_rollup()
        w.lock_overlay.unlock_panel.inputs[0].setText("pw12")
        w.lock_overlay.unlock_panel.submit()
        self.assertEqual((w.width(), w.height()), (520, 430))        # 암호를 풀면 원래 크기
        w.toggle_rollup()
        self.assertEqual(w.width(), 410)


if __name__ == "__main__":
    unittest.main()
