"""메모 탐색기에서 고른 메모에 하는 일: 우클릭 메뉴, 암호 걸기·잠그기, 알림과 예약된 알림 목록, 이전 내용, 삭제 방지, 색, 본문 복사.

(MemoExplorerWindow 에 섞어 쓰는 부분)
"""
from ui.dialogs import HistoryDialog
from ui.reminder_ui import ask_reminder
from ui.reminder_list import ask_reminder_list
from core import reminders
from ui import modern_style, themed_dialog
import datetime
import re
from typing import Dict, Any
from PyQt6.QtWidgets import QMenu, QApplication
from PyQt6.QtCore import Qt, QPoint
from utils.text_utils import clean_plain_text


class ExplorerActionsMixin:
    """탐색기에서 메모에 하는 일."""

    # ── 암호 메모 관리 ───────────────────────────────────────────────────────
    def _lock_action(self, memo: Dict[str, Any], action: str) -> None:
        """선택한 메모에 암호 관련 동작을 수행합니다. (메모 창의 기능을 그대로 사용, 창은 띄우지 않음)"""
        memo_id = memo.get('id', '')
        if not memo_id or self.is_trash_mode:
            return
        w = self.ui_manager.memo_windows.get(memo_id)
        if w is None:
            fresh = next((x for x in self.ui_manager.sync_manager.load_local_memos() if x.get('id') == memo_id), None)
            if not fresh:
                return
            self.ui_manager.create_new_memo(fresh, show_on_create=False)
            w = self.ui_manager.memo_windows.get(memo_id)
        if w is None:
            return
        w._dialog_parent = self
        try:
            getattr(w, action)()
        finally:
            w._dialog_parent = None
        self.pv.clear()
        self.refresh()

    def _lock_action_on_current(self, action: str) -> None:
        r = self.table.currentRow()
        item = self.table.item(r, 2) if r >= 0 else None
        memo = item.data(Qt.ItemDataRole.UserRole) if item else None
        if memo:
            self._lock_action(memo, action)
        else:
            self.show_toast("먼저 목록에서 메모를 선택하세요.")

    def _add_lock_menu(self, menu: Any, m: Dict[str, Any]) -> None:
        if m.get('_unreadable'):
            return
        sc = self.ui_manager.sync_manager.settings.get("shortcuts", {})
        def _label(text: str, key: str) -> str:
            return f"{text} ({sc[key]})" if sc.get(key) else text

        menu.addSeparator()
        if m.get('_locked'):
            menu.addAction(_label("🔓 잠금 해제 (암호 입력)", "toggle_memo_lock")).triggered.connect(
                lambda: self._lock_action(m, "prompt_unlock"))
            if self.ui_manager.sync_manager.memo_has_master_recovery(m.get('id', '')):
                menu.addAction("관리자 키로 복구…").triggered.connect(
                    lambda: self._lock_action(m, "recover_with_master_key"))
        elif m.get('is_locked'):
            menu.addAction(_label("🔒 지금 잠그기", "toggle_memo_lock")).triggered.connect(
                lambda: self._lock_action(m, "lock_now"))
            menu.addAction(_label("암호 변경", "set_memo_password")).triggered.connect(
                lambda: self._lock_action(m, "set_memo_password"))
            menu.addAction("암호 제거 (일반 메모로)").triggered.connect(
                lambda: self._lock_action(m, "remove_memo_password"))
        else:
            menu.addAction(_label("🔒 이 메모에 암호 걸기", "set_memo_password")).triggered.connect(
                lambda: self._lock_action(m, "set_memo_password"))

    def show_table_context_menu(self, pos: QPoint) -> None:
        item = self.table.itemAt(pos)
        if not item: return
        r = item.row()
        m_item = self.table.item(r, 2)
        if not m_item: return
        m = m_item.data(Qt.ItemDataRole.UserRole)
        if not m: return

        theme = self.ui_manager.sync_manager.settings.get('app_theme', 'white')
        is_dark = (theme == "dark")
        menu = QMenu(self)
        menu.setStyleSheet(modern_style.menu_qss(self.ui_manager.sync_manager.settings))

        act_open = menu.addAction("메모 열기")
        if hasattr(self.ui_manager, 'get_theme_icon'):
            act_open.setIcon(self.ui_manager.get_theme_icon("memo.svg", is_dark))
        act_open.triggered.connect(lambda: self.ui_manager.show_specific_memo(m.get('id')))

        sc_open = self.ui_manager.sync_manager.settings.get("shortcuts", {}).get("open_all_memos", "")
        act_open_all = menu.addAction("메모 열기 (폴더 골라서)…" + (f" ({sc_open})" if sc_open else ""))
        if hasattr(self.ui_manager, 'get_theme_icon'):
            act_open_all.setIcon(self.ui_manager.get_theme_icon("memo.svg", is_dark))
        act_open_all.triggered.connect(self.ui_manager.open_all_memos)

        sc_rename = self.ui_manager.sync_manager.settings.get("shortcuts", {}).get("rename", "F2")
        menu.addAction("제목 바꾸기…" + (f" ({sc_rename})" if sc_rename else "")).triggered.connect(lambda: self.rename_memo(m))

        fav_text = "즐겨찾기 해제" if m.get('is_favorite') else "즐겨찾기 등록"
        act_fav = menu.addAction(fav_text)
        if hasattr(self.ui_manager, 'get_theme_icon'):
            act_fav.setIcon(self.favorite_icon(bool(m.get('is_favorite'))))
        act_fav.triggered.connect(lambda: self.toggle_fav(m))

        prot_text = "삭제 방지 해제" if m.get('is_protected') else "삭제 방지 설정"
        act_prot = menu.addAction(prot_text)
        if hasattr(self.ui_manager, 'get_theme_icon'):
            act_prot.setIcon(self.ui_manager.get_theme_icon("lock_open.svg" if m.get('is_protected') else "lock_close.svg", is_dark))
        act_prot.triggered.connect(lambda: self.toggle_protect(m))
        self._add_lock_menu(menu, m)

        menu.addSeparator()
        has_reminder = bool(reminders.normalize(m.get('reminder')))
        menu.addAction("⏰ 알림 바꾸기…" if has_reminder else "⏰ 알림 설정…").triggered.connect(lambda: self.edit_reminder(m))
        menu.addAction("이전 내용 보기…").triggered.connect(lambda: self.show_history(m))
        self._add_folder_menu(menu, m)
        cm = menu.addMenu("메모 색상 변경")
        if hasattr(self.ui_manager, 'get_theme_icon'):
            cm.setIcon(self.ui_manager.get_theme_icon("colorpalette_89189.svg", is_dark))
        for n, c in {"다크그레이": "#2E3440", "하늘색": "#E0F2FE", "연두색": "#DCFCE7", "노란색": "#FEF9C3", "분홍색": "#FCE7F3", "흰색": "#FFFFFF"}.items():
            cm.addAction(n).triggered.connect(lambda checked, memo=m, code=c: self.change_memo_color(memo, code))

        act_copy = menu.addAction("본문 내용 복사")
        if hasattr(self.ui_manager, 'get_theme_icon'):
            act_copy.setIcon(self.ui_manager.get_theme_icon("font.svg", is_dark))
        act_copy.triggered.connect(lambda: self.copy_memo_text(m))

        menu.addSeparator()
        # 여러 줄을 골라 놓고(체크하거나 Ctrl·Shift 로 선택) 그중 하나에서 삭제를 누르면 고른 메모를 모두 지웁니다.
        picked = self.picked_memos()
        several = len(picked) > 1 and any(p.get('id') == m.get('id') for p in picked)
        act_del = menu.addAction(f"선택한 {len(picked)}개 삭제 (휴지통)" if several else "삭제 (휴지통)")
        if hasattr(self.ui_manager, 'get_theme_icon'):
            act_del.setIcon(self.ui_manager.get_theme_icon("trashbucket.svg", is_dark, override_color="#FF453A"))
        act_del.triggered.connect(self.del_checked if several else (lambda: self.delete_single_memo(m)))

        menu.exec(self.table.viewport().mapToGlobal(pos))

    def rename_memo(self, memo: Dict[str, Any]) -> None:
        """메모의 제목을 바꿉니다. 메모 창이 열려 있으면 그 창의 제목 칸으로 바꿔, 창이 들고 있는 데이터와 어긋나지 않게 합니다."""
        old = str(memo.get('title', ''))
        text, ok = themed_dialog.ask_text(self, "제목 바꾸기", "새 제목", text=old)
        new = re.sub(r'[\\/*?:"<>|]', "", str(text).strip()) if ok else ""
        if not new or new == old:
            return
        w = self.ui_manager.memo_windows.get(memo.get('id', ''))
        if w:
            w.title_edit.setText(new)
            w._do_title_save()
        else:
            target = next((m for m in self.ui_manager.sync_manager.load_local_memos() if m.get('id') == memo.get('id')), None)
            if target is None or not self.ui_manager.sync_manager.rename_memo_locally(old, new, target):
                self.show_toast("제목을 바꾸지 못했습니다.", warn=True)
                return
            target['updated_at'] = datetime.datetime.now().isoformat()     # 제목을 고친 것도 수정 (메모 창과 같게)
            self.ui_manager.sync_manager.save_memo_locally(target)
        self.show_toast(f"제목을 '{new}'(으)로 바꿨습니다")
        self.refresh()

    def rename_current(self) -> None:
        """목록에서 고른 메모의 제목을 바꿉니다. (탐색기에서 F2)"""
        if self.is_trash_mode or self.table.currentRow() < 0:
            return
        item = self.table.item(self.table.currentRow(), 2)
        memo = item.data(Qt.ItemDataRole.UserRole) if item else None
        if memo:
            self.rename_memo(memo)

    # ── 알림 · 변경 기록 ─────────────────────────────────────────────────────
    def edit_reminder(self, memo: Dict[str, Any]) -> None:
        """메모의 알림을 걸거나 풉니다. 메모 창이 열려 있으면 그 창이 들고 있는 데이터에 반영합니다."""
        w = self.ui_manager.memo_windows.get(memo.get('id', ''))
        target = w.memo_data if w else memo
        changed, reminder = ask_reminder(self, target.get('reminder'), str(target.get('title', '')))
        if not changed:
            return
        self.ui_manager.sync_manager.set_reminder(target, reminder)
        if w:
            w.refresh_reminder_badge()
        self.show_toast("⏰ " + reminders.describe(reminder) if reminder else "알림을 해제했습니다")
        self.refresh()

    def update_reminder_button(self) -> None:
        """예약된 알림 버튼 옆의 개수와 풍선 도움말을 지금의 알림 목록에 맞춥니다."""
        count = len(self.ui_manager.sync_manager.reminders)
        self.btn_reminders.setText(f" {count}" if count else "")
        self.btn_reminders.setToolTip(f"예약된 알림 {count}개 보기" if count else "예약된 알림 보기 (지금은 없음)")

    def show_reminder_list(self) -> None:
        """예약된 알림 목록을 엽니다. 미루기·건너뛰기·해제는 목록 안에서 하고, 메모 열기와 알림 바꾸기는 여기서 이어받습니다."""
        while self.isVisible():
            action = ask_reminder_list(self, self.ui_manager)
            if not action:
                break
            kind, memo_id = action
            if kind == "open":
                self.ui_manager.show_specific_memo(memo_id)
                break
            memo = self.ui_manager.memo_for(memo_id)
            if memo is not None:
                self.edit_reminder(memo)        # 바꾸고 나면 목록으로 돌아옴
        self.update_reminder_button()

    def show_history(self, memo: Dict[str, Any]) -> None:
        """메모의 이전 내용을 보여 주고, 고른 내용으로 되돌립니다."""
        memo_id = memo.get('id', '')
        sm = self.ui_manager.sync_manager
        w = self.ui_manager.memo_windows.get(memo_id)
        if w:
            w.flush_auto_save()
        dialog = HistoryDialog(self, str(memo.get('title', '')), sm.list_history(memo_id),
                               reveal=lambda index, password: sm.read_history_text(memo_id, index, password),
                               check=lambda index, password: sm.restore_problem(memo_id, index, password))
        if (dialog.exec() and dialog.chosen_index is not None
                and sm.restore_history(memo_id, dialog.chosen_index, dialog.chosen_password)):
            self.ui_manager.reload_pulled_memos([memo_id])
            self.pv.clear()
            self.show_toast("이전 내용으로 되돌렸습니다")
            self.refresh()

    def _save_memo_meta(self, memo: Dict[str, Any], **changes: Any) -> None:
        """즐겨찾기·고정·색상 같은 메모 속성을 저장합니다.

        메모 창이 열려 있으면 창이 들고 있는 데이터에도 같이 반영합니다.
        (그렇지 않으면 창이 다음에 저장할 때 예전 값으로 되돌려 버립니다)
        """
        # 수정일시(본문을 고친 시각)는 건드리지 않고, 다른 기기에 전해지도록 '속성 수정 시각'만 갱신합니다.
        changes.setdefault('meta_updated_at', datetime.datetime.now().isoformat())
        memo.update(changes)
        w = self.ui_manager.memo_windows.get(memo.get('id', ''))
        if w:
            w.memo_data.update(changes)
            self.ui_manager.sync_manager.save_memo_locally(w.memo_data)
        else:
            self.ui_manager.sync_manager.save_memo_locally(memo)

    def toggle_protect(self, memo: Dict[str, Any]) -> None:
        self._save_memo_meta(memo, is_protected=not memo.get('is_protected', False))
        self.show_toast(f"{'🔒 삭제 방지 설정됨' if memo['is_protected'] else '🔓 삭제 방지 해제됨'}")
        self.refresh()

    def change_memo_color(self, memo: Dict[str, Any], color_hex: str) -> None:
        self._save_memo_meta(memo, bg_color=color_hex)
        memo_id = memo.get('id')
        if memo_id and memo_id in self.ui_manager.memo_windows:
            self.ui_manager.memo_windows[memo_id].apply_look()
        self.refresh()

    def copy_memo_text(self, memo: Dict[str, Any]) -> None:
        if memo.get('_locked') or memo.get('_unreadable'):
            self.show_toast("🔒 잠긴 메모는 복사할 수 없습니다.")
            return
        if memo.get('is_locked'):
            self.show_toast("🔒 암호 메모는 메모 창에서 복사하세요.")
            return
        raw_cnt = memo.get('content', '')
        text = clean_plain_text(raw_cnt)
        QApplication.clipboard().setText(text)
        self.show_toast("본문 내용이 클립보드에 복사되었습니다.")
