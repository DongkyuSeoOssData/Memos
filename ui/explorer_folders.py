"""메모 탐색기의 폴더 화면.

폴더를 고르는 세 가지 화면(탭 줄·사이드바·드롭다운)을 채우고, 폴더를 만들고·이름을 바꾸고·지우고·순서를 바꾸며,
메모를 폴더로 옮깁니다. (MemoExplorerWindow 에 섞어 쓰는 부분. 화면의 위젯과 상태는 MemoExplorerWindow 의 것)
"""
from ui.dialogs import FolderPickDialog
from ui import themed_dialog
from ui import modern_style
from core import folders
from typing import List, Dict, Any, Optional
from PyQt6.QtWidgets import QPushButton, QMenu, QDialog, QListWidgetItem
from PyQt6.QtCore import Qt, QPoint


class ExplorerFoldersMixin:
    """탐색기의 폴더 기능."""

    FOLDER_ACTIONS = {"/new": "＋ 새 폴더…", "/rename": "이름 바꾸기…", "/delete": "폴더 삭제…",
                      "/delete_many": "여러 폴더 삭제…"}

    def _saved_folders(self) -> List[str]:
        return list(self.ui_manager.sync_manager.settings.get("folders", []) or [])

    def _is_real_folder(self) -> bool:
        return self.current_folder not in (folders.ALL, folders.UNFILED)

    def folder_ui_mode(self) -> str:
        mode = self.ui_manager.sync_manager.settings.get("folder_ui", "tabs")
        return mode if mode in folders.UI_MODES else "tabs"

    def apply_folder_ui_mode(self) -> None:
        """환경설정에서 고른 방식의 폴더 화면만 보이게 합니다."""
        mode = self.folder_ui_mode()
        sidebar_open = bool(self.ui_manager.sync_manager.settings.get("folder_sidebar_open", True))
        self.folder_combo.setVisible(mode == "dropdown")
        self.folder_tabs.setVisible(mode == "tabs")
        self.btn_folder.setVisible(mode == "sidebar")
        show_list = mode == "sidebar" and sidebar_open
        self.folder_list.setVisible(show_list)
        self._set_sidebar_extra(self.SIDEBAR_WIDTH + self.SIDEBAR_GAP if show_list else 0)
        if not self.is_size_fixed():
            self._apply_minimum_size()

    def toggle_folder_sidebar(self) -> None:
        is_open = bool(self.ui_manager.sync_manager.settings.get("folder_sidebar_open", True))
        self.ui_manager.sync_manager.save_settings({"folder_sidebar_open": not is_open})
        self.apply_folder_ui_mode()

    def _folder_title(self, path: str) -> str:
        return {folders.ALL: "전체 메모", folders.UNFILED: "미분류"}.get(path, path)

    def _rebuild_folder_ui(self, memos: List[Dict[str, Any]]) -> None:
        """폴더 고르는 화면(탭 줄·사이드바·드롭다운)을 지금의 폴더 목록으로 다시 채웁니다."""
        names = folders.all_folders(self._saved_folders(), memos)
        if self._is_real_folder() and self.current_folder not in names:
            self.current_folder = folders.ALL
        counts = folders.counts(memos)
        self._fill_folder_combo(names)
        self._fill_folder_tabs(names)
        self._fill_folder_list(names, counts)
        self._fit_header()
        self.apply_folder_ui_mode()

    def _fill_folder_combo(self, names: List[str]) -> None:
        """드롭다운: 맨 위에 '새 폴더', 그다음 '전체 메모', 그 아래 폴더(탭·사이드바에서 정한 순서), 미분류, 관리 메뉴."""
        combo = self.folder_combo
        combo.blockSignals(True)
        combo.clear()
        combo.addItem(self.FOLDER_ACTIONS["/new"], "/new")
        combo.addItem("전체 메모", folders.ALL)
        for path in names:
            combo.addItem("　" * folders.depth(path) + folders.leaf(path), path)
            combo.setItemData(combo.count() - 1, path, Qt.ItemDataRole.ToolTipRole)
        combo.addItem("미분류", folders.UNFILED)
        if names:
            combo.insertSeparator(combo.count())
            for key in ("/rename", "/delete") if self._is_real_folder() else ():
                combo.addItem(self.FOLDER_ACTIONS[key], key)
            combo.addItem(self.FOLDER_ACTIONS["/delete_many"], "/delete_many")
        combo.setCurrentIndex(max(0, combo.findData(self.current_folder)))
        combo.blockSignals(False)

    def _make_folder_tab(self, label: str, path: str, selected: bool, sub: bool = False) -> QPushButton:
        btn = QPushButton(label)
        btn.setFixedHeight(28 if sub else 32)
        btn.setCheckable(path != "/new")
        btn.setChecked(selected)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setProperty("folder_path", path)
        btn.setProperty("sub_tab", sub)
        btn.setToolTip("새 폴더" if path == "/new" else self._folder_title(path))
        btn.clicked.connect(lambda checked, target=path: self._on_folder_data(target))
        if path not in (folders.ALL, folders.UNFILED, "/new"):
            btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            btn.customContextMenuRequested.connect(
                lambda pos, target=path, b=btn: self._show_folder_menu(target, b.mapToGlobal(pos)))
        return btn

    def _fill_folder_tabs(self, names: List[str]) -> None:
        current_top = folders.top(self.current_folder) if self._is_real_folder() else self.current_folder
        tops = [p for p in names if folders.depth(p) == 0]
        row = [("전체 메모", folders.ALL)] + [(p, p) for p in tops] + [("미분류", folders.UNFILED), ("＋", "/new")]
        top_buttons = [self._make_folder_tab(label, path, current_top == path) for label, path in row]

        # 하위 폴더가 있는 폴더를 고른 경우에만 둘째 줄을 채웁니다.
        children = [p for p in names if self._is_real_folder() and p.startswith(current_top + folders.SEP)]
        sub_row = ([("전체", current_top)] + [(p[len(current_top) + 1:], p) for p in children]) if children else []
        sub_buttons = [self._make_folder_tab(label, path, self.current_folder == path, sub=True) for label, path in sub_row]

        self.folder_tab_buttons = top_buttons + sub_buttons
        # 버튼 너비는 모양(스타일)이 입혀진 뒤에 정해지므로, 먼저 모양을 입히고 줄에 넣습니다.
        modern_style.apply_explorer_folders(self)
        self.folder_tab_strip.set_tabs(top_buttons, [p for _, p in row], tops, keep_visible=current_top)
        self.folder_subtab_strip.set_tabs(sub_buttons, [p for _, p in sub_row], children, keep_visible=self.current_folder)
        self.folder_subtab_strip.setVisible(bool(sub_buttons))

    def _fill_folder_list(self, names: List[str], counts: Dict[str, int]) -> None:
        lst = self.folder_list
        lst.blockSignals(True)
        lst.clear()
        rows = [(folders.ALL, "전체 메모")] + [(p, "　" * folders.depth(p) + folders.leaf(p)) for p in names] \
            + [(folders.UNFILED, "미분류")]
        for path, label in rows:
            item = QListWidgetItem(f"{label}  ({counts.get(path, 0)})")
            item.setData(Qt.ItemDataRole.UserRole, path)
            item.setToolTip(self._folder_title(path))
            if path in (folders.ALL, folders.UNFILED):
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsDragEnabled)      # 폴더만 끌어 옮길 수 있음
            lst.addItem(item)
            if path == self.current_folder:
                lst.setCurrentItem(item)
        new_item = QListWidgetItem("＋ 새 폴더…")
        new_item.setData(Qt.ItemDataRole.UserRole, "/new")
        new_item.setFlags(new_item.flags() & ~Qt.ItemFlag.ItemIsDragEnabled)
        lst.addItem(new_item)
        lst.blockSignals(False)

    # ── 폴더 순서 (탭·사이드바에서 끌어서 바꾸며, 드롭다운에도 같은 순서가 쓰입니다) ──
    def _folder_names(self) -> List[str]:
        return folders.all_folders(self._saved_folders(), self.ui_manager.sync_manager.load_local_memos())

    def _save_folder_order(self, names: List[str]) -> None:
        self.ui_manager.sync_manager.save_settings({"folders": folders.arrange(names)})
        self.refresh()

    def move_folder(self, path: Any, before: Any) -> None:
        """path 폴더를 before 폴더 앞으로 옮깁니다. before 가 None 이면 같은 단계의 맨 뒤로."""
        names = self._folder_names()
        if path in names and path != before:
            self._save_folder_order(folders.reorder(names, path, before))

    def _on_sidebar_reordered(self) -> None:
        """사이드바에서 항목을 끌어 놓은 뒤: 화면에 놓인 순서대로 저장합니다."""
        order = [self.folder_list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.folder_list.count())]
        self._save_folder_order([p for p in order if isinstance(p, str) and not p.startswith(folders.SEP) and p])

    def _show_sidebar_menu(self, pos: QPoint) -> None:
        item = self.folder_list.itemAt(pos)
        path = item.data(Qt.ItemDataRole.UserRole) if item else None
        if isinstance(path, str) and path not in (folders.ALL, folders.UNFILED, "/new"):
            self._show_folder_menu(path, self.folder_list.viewport().mapToGlobal(pos))

    def _show_folder_menu(self, path: str, global_pos: QPoint) -> None:
        """폴더(탭·목록 항목)를 우클릭했을 때: 하위 폴더 만들기 / 이름 바꾸기 / 삭제."""
        menu = QMenu(self)
        menu.setStyleSheet(modern_style.menu_qss(self.ui_manager.sync_manager.settings))
        for key, label in (("/new", "여기에 하위 폴더 만들기…"), ("/rename", "이름 바꾸기…"), ("/delete", "폴더 삭제…")):
            menu.addAction(label).triggered.connect(lambda checked, k=key: self._run_folder_action(path, k))
        menu.addSeparator()
        menu.addAction("여러 폴더 삭제…").triggered.connect(lambda: self.pick_and_delete_folders([path]))
        menu.exec(global_pos)

    def _run_folder_action(self, path: str, key: str) -> None:
        self.current_folder = path
        self._on_folder_data(key)

    def _on_folder_picked(self, index: int) -> None:
        self._on_folder_data(self.folder_combo.itemData(index))

    def _on_folder_data(self, data: Any) -> None:
        """폴더 화면에서 무언가를 골랐을 때. 폴더 경로면 그 폴더로, '/new' 같은 값이면 관리 동작을 합니다."""
        if data == "/new":
            self.new_folder()
        elif data == "/rename":
            self.rename_folder()
        elif data == "/delete":
            self.delete_folder()
        elif data == "/delete_many":
            self.pick_and_delete_folders([self.current_folder] if self._is_real_folder() else [])
            return
        elif isinstance(data, str):
            self.select_folder(data)
            return
        self.refresh()      # 관리 동작 뒤: 폴더 화면을 다시 채우며 선택 표시를 맞춤

    def select_folder(self, path: str) -> None:
        self.current_folder = path
        self.current_page = 1
        self.ui_manager.sync_manager.save_settings({"explorer_folder": path})
        self.refresh()

    def _ask_folder_name(self, title: str, text: str = "") -> str:
        name, ok = themed_dialog.ask_text(self, title, "폴더 이름", text,
                                          hint="하위 폴더는 '업무/프로젝트A'처럼 / 로 구분해서 적습니다.")
        return folders.normalize(name) if ok else ""

    def new_folder(self) -> None:
        name = self._ask_folder_name("새 폴더", self.current_folder + folders.SEP if self._is_real_folder() else "")
        if not name:
            return
        saved = self._saved_folders()
        if name not in saved:
            self.ui_manager.sync_manager.save_settings({"folders": saved + [name]})
        self.current_folder = name
        self.ui_manager.sync_manager.save_settings({"explorer_folder": name})
        self.show_toast(f"'{name}' 폴더를 만들었습니다")

    def _memos_in(self, path: str) -> List[Dict[str, Any]]:
        return [m for m in self.ui_manager.sync_manager.load_local_memos() if folders.contains(path, folders.folder_of(m))]

    def _move_to_folder(self, memo: Dict[str, Any], path: str) -> None:
        self._save_memo_meta(memo, folder=path)

    def rename_folder(self) -> None:
        old = self.current_folder
        if not self._is_real_folder():
            return
        new = self._ask_folder_name("폴더 이름 바꾸기", old)
        if not new or new == old:
            return
        for memo in self._memos_in(old):
            self._move_to_folder(memo, folders.moved(folders.folder_of(memo), old, new))
        renamed = [folders.moved(p, old, new) for p in self._saved_folders()]
        self.ui_manager.sync_manager.save_settings({"folders": list(dict.fromkeys(renamed + [new])), "explorer_folder": new})
        self.current_folder = new
        self.show_toast(f"폴더 이름을 '{new}'(으)로 바꿨습니다")

    def delete_folder(self) -> None:
        if self._is_real_folder():
            self.delete_folders([self.current_folder])

    def pick_and_delete_folders(self, preselect: List[str]) -> None:
        """폴더 목록에서 여러 개를 체크해 한 번에 삭제합니다. preselect 는 미리 체크해 둘 폴더."""
        memos = self.ui_manager.sync_manager.load_local_memos()
        names = folders.all_folders(self._saved_folders(), memos)
        dialog = FolderPickDialog(self, names, folders.counts(memos), preselect)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.delete_folders(dialog.selected())
        else:
            self.refresh()

    def delete_folders(self, paths: List[str]) -> bool:
        """폴더들을(하위 폴더 포함) 삭제합니다. 메모는 지우지 않고 미분류로 옮깁니다. 삭제했으면 True."""
        names = self._folder_names()
        # 상위 폴더가 함께 골라졌으면 하위 폴더는 따로 처리할 필요가 없습니다.
        picked = [p for p in dict.fromkeys(paths) if p in names]
        tops = [p for p in picked if not any(other != p and folders.contains(other, p) for other in picked)]
        if not tops:
            return False
        doomed = lambda path: any(folders.contains(top, path) for top in tops)
        inside = [m for m in self.ui_manager.sync_manager.load_local_memos() if doomed(folders.folder_of(m))]
        label = f"'{tops[0]}' 폴더" if len(tops) == 1 else f"폴더 {len(tops)}개"
        # 여러 개를 지울 때는 어떤 폴더인지 한 줄씩 보여 줍니다.
        listing = "" if len(tops) == 1 else "\n" + "\n".join(f"  • {p}" for p in tops) + "\n"
        question = (f"{label}를 삭제할까요?{listing}\n"
                    f"메모는 지워지지 않고 미분류로 옮겨집니다. (옮겨질 메모 {len(inside)}개)")
        if not themed_dialog.confirm(self, "폴더 삭제", question, ok_text="폴더 삭제", danger=True):
            return False
        for memo in inside:
            self._move_to_folder(memo, "")
        changes: Dict[str, Any] = {"folders": [p for p in self._saved_folders() if not doomed(folders.normalize(p))]}
        if self._is_real_folder() and doomed(self.current_folder):
            # 보고 있던 폴더가 사라졌으면 전체 메모로
            self.current_folder = folders.ALL
            changes["explorer_folder"] = folders.ALL
        self.ui_manager.sync_manager.save_settings(changes)
        self.show_toast(f"{label}를 삭제했습니다 (메모 {len(inside)}개는 미분류로)")
        self.refresh()
        return True

    def move_memos_to_folder(self, clicked: Dict[str, Any], path: Optional[str]) -> None:
        """우클릭한 메모(체크해 둔 메모가 있으면 그것들도 함께)를 폴더로 옮깁니다. path 가 None 이면 새 폴더를 물어봅니다."""
        if path is None:
            path = self._ask_folder_name("새 폴더로 이동")
            if not path:
                return
            saved = self._saved_folders()
            if path not in saved:
                self.ui_manager.sync_manager.save_settings({"folders": saved + [path]})
        targets = {m.get('id'): m for m in self._checked_memos() + [clicked] if m}
        for memo in targets.values():
            self._move_to_folder(memo, path)
        self.show_toast(f"메모 {len(targets)}개를 '{path or '미분류'}'(으)로 옮겼습니다")
        self.clear_checks()
        self.refresh()

    def _add_folder_menu(self, menu: Any, m: Dict[str, Any]) -> None:
        sub = menu.addMenu("폴더로 이동")
        current = folders.folder_of(m)
        names = folders.all_folders(self._saved_folders(), self.ui_manager.sync_manager.load_local_memos())
        for path, label in [("", "미분류")] + [(p, "　" * folders.depth(p) + folders.leaf(p)) for p in names]:
            act = sub.addAction(("✓ " if path == current else "　") + label)
            act.triggered.connect(lambda checked, target=path: self.move_memos_to_folder(m, target))
        sub.addSeparator()
        sub.addAction("＋ 새 폴더로…").triggered.connect(lambda: self.move_memos_to_folder(m, None))
