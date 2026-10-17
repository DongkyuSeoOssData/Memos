"""3.8.0 에서 바꾼 것: 할 일을 마친 뒤 체크 풀기, 미리보기 접기, 앱 글꼴. (위치 고정은 test_geometry · test_ui 의 FoldPlacementTest)"""
import unittest
from unittest import mock

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

# support 를 먼저 가져와야 합니다. (offscreen 설정과 프로젝트 경로)
import support
from ui import modern_style


class ChecksAreClearedAfterActionsTest(support.UiTestCase):
    def check(self, ex, *memo_ids: str) -> None:
        for memo_id in memo_ids:
            ex.table.item(self.row_of(ex, memo_id), 0).setCheckState(Qt.CheckState.Checked)

    def checked(self, ex) -> list:
        ex._remember_checked()
        return sorted(ex._checked_ids)

    def test_move_to_folder(self) -> None:
        ex = self.explorer()
        self.check(ex, "memo-0000", "memo-0001")
        memo = ex.table.item(self.row_of(ex, "memo-0000"), 2).data(Qt.ItemDataRole.UserRole)
        ex.move_memos_to_folder(memo, "work")
        self.assertEqual(self.disk("memo-0001")["folder"], "work")
        self.assertEqual(self.checked(ex), [])

    def test_delete_with_a_protected_memo_left_over(self) -> None:
        ex = self.explorer()
        memo = ex.table.item(self.row_of(ex, "memo-0002"), 2).data(Qt.ItemDataRole.UserRole)
        ex.toggle_protect(memo)
        self.check(ex, "memo-0000", "memo-0002")
        ex.del_checked()
        self.assertFalse((self.memo_dir / "memo-0000.json").exists())
        self.assertTrue((self.memo_dir / "memo-0002.json").exists())       # 삭제 방지라 남은 메모도
        self.assertEqual(self.checked(ex), [])                             # 체크는 풀림

    def test_cancelled_delete_keeps_the_checks(self) -> None:
        ex = self.explorer()
        self.check(ex, "memo-0000")
        self.confirm_answer = False
        ex.del_checked()
        self.assertEqual(self.checked(ex), ["memo-0000"])

    def test_restore_from_trash(self) -> None:
        ex = self.explorer()
        self.check(ex, "memo-0000")
        ex.del_checked()
        ex.t_btn.setChecked(True)
        ex.toggle_trash()
        self.check(ex, "memo-0000")
        ex.res_checked()
        self.assertTrue((self.memo_dir / "memo-0000.json").exists())
        self.assertEqual(self.checked(ex), [])


class PreviewFoldTest(support.UiTestCase):
    def test_fold_shrinks_the_window_by_the_preview_and_is_remembered(self) -> None:
        ex = self.explorer()
        ex.resize(ex.width(), ex.minimumHeight() + 150)            # 너비는 그대로 (너비에 따라 글자 크기가 바뀜)
        support.app.processEvents()
        height, table = ex.height(), ex.table.height()
        preview = ex.pv.height()
        self.assertTrue(ex.preview_open())
        ex.btn_preview_fold.click()
        support.app.processEvents()
        self.assertFalse(ex.preview_open())
        self.assertEqual(ex.table.height(), table)                         # 목록 칸은 그대로 (10개)
        self.assertEqual(ex.height(), height - preview)                  # 창이 미리보기만큼 줄어듦
        self.assertFalse(self.sm.settings["explorer_preview_open"])
        self.assertEqual(ex.btn_preview_fold.text(), "미리보기 ▸")         # 제목째로 접고 펴는 버튼
        ex.btn_preview_fold.click()
        support.app.processEvents()
        self.assertEqual(ex.btn_preview_fold.text(), "미리보기 ▾")
        self.assertEqual((ex.height(), ex.pv.height()), (height, preview))  # 펴면 원래대로
        ex.btn_preview_fold.click()
        ex.close()
        self.ui.explorer_window = None
        again = self.explorer()                                            # 다시 열어도 접힌 채
        self.assertFalse(again.preview_open())

    def test_fixed_size_explorer_also_folds(self) -> None:
        ex = self.explorer()
        self.sm.settings["explorer_fixed_size"] = True
        self.sm.settings["explorer_geom"] = [10, 10, ex.content_width(), ex.minimumHeight() + 100]
        ex.apply_size_settings()
        height = ex.height()
        ex.toggle_preview()
        self.assertLess(ex.height(), height)
        self.assertEqual(ex.minimumHeight(), ex.maximumHeight())          # 줄어든 크기로 다시 고정
        self.assertEqual(self.sm.settings["explorer_geom"][3], ex.height())
        ex.toggle_preview()
        self.assertEqual(ex.height(), height)


class ListSizeTest(support.UiTestCase):
    def test_list_shows_ten_memos_without_scrolling(self) -> None:
        for i in range(3, 25):
            self.sm.save_memo_locally({"id": f"memo-{i:04d}", "title": f"t{i}", "content": "x",
                                       "updated_at": "2026-02-01T00:00:00", "is_visible": False})
        ex = self.explorer()
        ex.resize(ex.width(), 400)                                         # 작게 줄여도
        support.app.processEvents()
        self.assertEqual(ex.table.rowCount(), 10)
        self.assertEqual(ex.table.verticalScrollBar().maximum(), 0)       # 10개가 스크롤 없이 다 보임
        table = ex.table.height()
        ex.resize(ex.width(), ex.height() + 200)                          # 키우면 미리보기가 커지고 목록은 그대로
        support.app.processEvents()
        self.assertEqual(ex.table.height(), table)

    def test_default_size(self) -> None:
        self.assertNotIn("explorer_geom", self.sm.settings)
        from PyQt6.QtGui import QGuiApplication
        ex = self.explorer()
        area = QGuiApplication.primaryScreen().availableGeometry()        # 모니터가 작으면 그 안으로
        self.assertEqual(ex.content_width(), min(ex.DEFAULT_SIZE[0], area.width()))
        self.assertEqual(ex.height(), max(min(ex.DEFAULT_SIZE[1], area.height()), ex.minimumHeight()))


class PagingTest(support.UiTestCase):
    def test_first_and_last_page_buttons(self) -> None:
        for i in range(3, 35):
            self.sm.save_memo_locally({"id": f"memo-{i:04d}", "title": f"t{i}", "content": "x",
                                       "updated_at": "2026-02-01T00:00:00", "is_visible": False})
        ex = self.explorer()
        self.assertEqual(ex.page_count(), 4)                               # 35개 → 4쪽
        self.assertFalse(ex.btn_last_page.icon().isNull())
        ex.btn_last_page.click()
        self.assertEqual((ex.current_page, ex.table.rowCount()), (4, 5))
        self.assertEqual(ex.p_l.text(), "4 / 4")
        ex.btn_first_page.click()
        self.assertEqual((ex.current_page, ex.table.rowCount()), (1, 10))


class OpenByFolderTest(support.UiTestCase):
    def setUp(self) -> None:
        super().setUp()
        for i in range(3, 8):
            self.sm.save_memo_locally({"id": f"memo-{i:04d}", "title": f"w{i}", "content": "x", "folder": "업무",
                                       "updated_at": f"2026-03-0{i}T00:00:00", "is_visible": False})

    def open_with(self, folder, order=None):
        asked = {}

        def fake_ask(parent, entries):
            asked["entries"] = entries
            return folder

        self.choice_answer = order
        with mock.patch("ui.ui_manager.ask_folder_to_open", fake_ask):
            self.ui.open_all_memos()
        return asked["entries"]

    def test_lists_all_unfiled_and_folders_with_counts(self) -> None:
        entries = self.open_with(None)                                     # 취소
        self.assertEqual(entries[0][1:], ("전체", 8))
        self.assertEqual(entries[1][1:], ("미분류", 3))
        self.assertIn(("업무", 5), [(e[1].strip("　"), e[2]) for e in entries])
        self.assertEqual(self.ui.memo_windows, {})                         # 취소하면 아무것도 열지 않음

    def test_opens_only_that_folder(self) -> None:
        self.open_with("업무")
        self.assertEqual(sorted(self.ui.memo_windows), [f"memo-{i:04d}" for i in range(3, 8)])

    def test_more_than_the_batch_asks_which_end_to_open(self) -> None:
        with mock.patch.object(support.uim.UIManager, "OPEN_BATCH", 2):
            self.open_with("업무", order="oldest")
            self.assertEqual(sorted(self.ui.memo_windows), ["memo-0003", "memo-0004"])
            self.assertIn("메모 열기", self.choices_asked)
            for w in list(self.ui.memo_windows.values()):
                w.close()
            self.open_with("업무", order="newest")
            self.assertEqual(sorted(w for w, win in self.ui.memo_windows.items() if win.isVisible()), ["memo-0006", "memo-0007"])
            before = set(self.ui.memo_windows)
            self.open_with(folders_all := "", order=None)                  # 많은데 취소
            self.assertEqual(set(self.ui.memo_windows), before)


class FirstRunStyleTest(unittest.TestCase):
    def test_new_pc_starts_with_neo_and_old_pc_keeps_its_look(self) -> None:
        import json
        import tempfile
        from pathlib import Path
        import core.sync_manager as smm
        from drive_api import DriveAPI
        with tempfile.TemporaryDirectory() as folder:
            home = Path(folder)
            with mock.patch.object(Path, "home", return_value=home):
                fresh = smm.SyncManager(DriveAPI())
                self.assertEqual((fresh.settings["ui_style"], fresh.settings["light_theme_mode"], fresh.settings["dark_theme_mode"]),
                                 ("neo", "mono", "mono"))
                fresh.sync_timer.stop()
                (home / ".memoit_custom" / "settings.json").write_text(json.dumps({"use_sync": False}), encoding="utf-8")
                old = smm.SyncManager(DriveAPI())                          # 예전 설정 파일 (디자인을 고른 적 없음)
                self.assertEqual((old.settings["ui_style"], old.settings["light_theme_mode"], old.settings["dark_theme_mode"]),
                                 ("modern", "white", "dark"))
                old.sync_timer.stop()


class RenameFromMenusTest(support.UiTestCase):
    def test_memo_window_menu_offers_rename_with_its_shortcut(self) -> None:
        from PyQt6.QtCore import QPoint
        from PyQt6.QtWidgets import QMenu
        w = self.open_window("memo-0000")
        texts = []
        with mock.patch.object(QMenu, "exec", lambda menu, *args: texts.extend(act.text() for act in menu.actions())):
            w.text_edit.customContextMenuRequested.emit(QPoint(0, 0))
        self.assertIn("제목 바꾸기 (F2)", texts)
        w.enable_rename()
        self.assertFalse(w.title_edit.isReadOnly())

    def test_explorer_renames_closed_and_open_memos(self) -> None:
        ex = self.explorer()
        memo = ex.table.item(self.row_of(ex, "memo-0001"), 2).data(Qt.ItemDataRole.UserRole)
        self.answers[:] = ["새 제목/이" + chr(92) + "름"]
        ex.rename_memo(memo)
        self.assertEqual(self.disk("memo-0001")["title"], "새 제목이름")      # 파일 이름에 못 쓰는 글자는 뺌
        self.assertGreater(self.disk("memo-0001")["updated_at"], "2026-01-02T00:00:00")
        w = self.open_window("memo-0002")
        ex.table.setCurrentCell(self.row_of(ex, "memo-0002"), 2)
        self.answers[:] = ["열린 메모"]
        ex.rename_current()                                                # 탐색기에서 F2
        self.assertEqual(w.title_edit.text(), "열린 메모")
        self.assertEqual(self.disk("memo-0002")["title"], "열린 메모")
        self.answers[:] = []
        ex.rename_current()                                                # 취소하면 그대로
        self.assertEqual(self.disk("memo-0002")["title"], "열린 메모")
        self.assertEqual(ex._rename_key.key().toString(), "F2")


class AppFontTest(support.UiTestCase):
    def tearDown(self) -> None:
        modern_style.set_app_font(modern_style.DEFAULT_APP_FONT)
        super().tearDown()

    def test_default_is_d2coding_with_a_hangul_fallback(self) -> None:
        self.assertEqual(self.sm.settings["app_font_family"], "D2Coding")
        self.assertEqual(modern_style.UI_FONT, "'D2Coding', 'Malgun Gothic', sans-serif")
        self.assertEqual(modern_style.app_qfont(10).families(), ["D2Coding", "Malgun Gothic"])
        ex = self.explorer()
        self.assertEqual(ex.font().families()[:2], ["D2Coding", "Malgun Gothic"])

    def test_changing_the_font_redraws_every_window(self) -> None:
        ex = self.explorer()
        w = self.open_window("memo-0000")
        win = support.sw.SettingsWindow(self.sm)
        self.assertIn("app_font_family", win.collect())                   # 환경설정 저장에 들어감
        # (시험 환경에는 설치된 글꼴이 없어 목록에서 고를 수 없으므로, 저장된 뒤의 적용만 봅니다)
        self.sm.save_settings({"app_font_family": "Test Font"})
        self.ui.apply_settings_to_windows()
        self.assertIn("'Test Font', 'Malgun Gothic'", ex.bg.styleSheet())
        self.assertEqual(ex.font().families()[0], "Test Font")
        self.assertIn("'Test Font'", w.title_edit.styleSheet())
        self.assertEqual(QApplication.font().families()[0], "Test Font")  # 메뉴·풍선 도움말 등

    def test_app_font_stays_on_this_pc(self) -> None:
        from core import shared_settings
        self.assertNotIn("app_font_family", shared_settings.SHARED_KEYS)

    def test_missing_font_is_announced(self) -> None:
        self.sm.settings["app_font_family"] = "No Such Font 123"
        win = support.sw.SettingsWindow(self.sm)
        self.assertFalse(win.app_font_note.isHidden())
        with mock.patch.object(modern_style, "font_installed", return_value=True):
            win.load()
        self.assertTrue(win.app_font_note.isHidden())


if __name__ == "__main__":
    unittest.main()
