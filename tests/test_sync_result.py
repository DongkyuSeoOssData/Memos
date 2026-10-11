"""동기화 결과 알리기: 동기화 쪽은 결과만 넘기고, 어떻게 보여 줄지는 화면 쪽이 정합니다."""
import unittest

# support 를 먼저 가져와야 합니다. (offscreen 설정과 프로젝트 경로)
import support
from core.sync_worker import SYNC_CHANGED, SYNC_NOT_DONE, SYNC_UNCHANGED


class SyncResultTest(support.UiTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.tray = []
        self.ui.tray_icon.showMessage = lambda *a, **k: self.tray.append(a)
        self.shown = []
        real = self.ui.show_sync_result
        self.ui.show_sync_result = lambda *a: (self.shown.append(a), real(*a))[1]

    def watch(self, explorer):
        seen = {"toasts": [], "refreshes": 0}
        explorer.show_toast = lambda text, *a, **k: seen["toasts"].append(text)
        real_refresh = explorer.refresh

        def refresh(*a, **k):
            seen["refreshes"] += 1
            return real_refresh(*a, **k)

        explorer.refresh = refresh
        return seen

    def test_completed_sync_toasts_and_refreshes_the_open_explorer(self) -> None:
        seen = self.watch(self.explorer())
        self.sm.on_sync_finished(True, "동기화 완료 (가져오기 1개 / 업로드 0개)", SYNC_CHANGED)
        self.assertEqual(seen["toasts"], ["동기화 완료 (가져오기 1개 / 업로드 0개)"])
        self.assertEqual(seen["refreshes"], 1)
        self.assertEqual(self.tray, [])

    def test_refresh_does_not_depend_on_the_wording(self) -> None:
        seen = self.watch(self.explorer())
        self.sm.on_sync_finished(True, "다 됐습니다", SYNC_CHANGED)
        self.assertEqual(seen["refreshes"], 1)
        self.sm.on_sync_finished(True, "동기화 완료처럼 보이는 문구", SYNC_NOT_DONE)       # 문구가 아니라 결과 값으로 판단
        self.assertEqual(seen["refreshes"], 1)

    def test_failure_goes_to_the_tray_when_the_explorer_is_hidden(self) -> None:
        explorer = self.explorer()
        seen = self.watch(explorer)
        explorer.hide()
        self.sm.on_sync_finished(False, "동기화 치명적 오류: x", SYNC_NOT_DONE)
        self.assertEqual(seen["toasts"], [])
        self.assertEqual(len(self.tray), 1)
        self.assertEqual(self.tray[0][1], "동기화 치명적 오류: x")
        self.assertEqual(seen["refreshes"], 0)
        self.sm.on_sync_finished(True, "동기화 완료 (변경사항 없음)", SYNC_UNCHANGED)   # 성공은 트레이로 알리지 않음
        self.assertEqual(len(self.tray), 1)

    def test_quiet_check_with_nothing_changed_says_nothing(self) -> None:
        self.watch(self.explorer())
        self.sm._last_sync_quiet = True
        self.sm.on_sync_finished(True, "동기화 완료 (변경사항 없음)", SYNC_UNCHANGED)
        self.assertEqual(self.shown, [])
        self.sm.on_sync_finished(True, "동기화 완료 (가져오기 2개 / 업로드 0개)", SYNC_CHANGED)
        self.assertEqual(len(self.shown), 1)
        self.sm._last_sync_quiet = False
        self.sm.on_sync_finished(True, "동기화 완료 (변경사항 없음)", SYNC_UNCHANGED)   # 직접 누른 동기화는 알림
        self.assertEqual(len(self.shown), 2)

    def test_local_mode_notice_is_shown_without_a_refresh(self) -> None:
        seen = self.watch(self.explorer())
        self.sm.on_sync_finished(True, "로컬 모드로 작동 중입니다. (동기화 OFF)")
        self.assertEqual(len(seen["toasts"]), 1)
        self.assertEqual(seen["refreshes"], 0)


if __name__ == "__main__":
    unittest.main()
