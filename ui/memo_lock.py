"""메모 창의 암호 잠금 기능 (암호 걸기·풀기·다시 잠그기·관리자 키 복구)."""
import datetime
from typing import Any

from PyQt6.QtWidgets import QFileDialog, QInputDialog, QLineEdit, QMessageBox


class MemoLockMixin:
    """MemoWindow 에 섞어 쓰는 암호 메모 기능. (memo_data, text_edit, ui_manager 등은 MemoWindow 의 것)"""

    # ── 암호 메모 ────────────────────────────────────────────────────────────
    def is_sealed(self) -> bool:
        """본문을 읽을 수 없는 상태(잠김 또는 손상)인지 여부. 이 상태에서는 본문을 저장하지 않습니다."""
        return bool(self.memo_data.get('_locked') or self.memo_data.get('_unreadable'))

    def _dlg_parent(self) -> Any:
        """암호 대화상자의 부모 창. 탐색기에서 호출하면 탐색기 위에 뜨도록 잠시 바꿔 답니다."""
        return getattr(self, '_dialog_parent', None) or self

    def toggle_memo_lock(self) -> None:
        """단축키용: 잠겨 있으면 암호를 묻고, 열려 있는 암호 메모면 잠그고, 일반 메모면 암호를 겁니다."""
        if self.memo_data.get('_locked'):
            self.prompt_unlock()
        elif self.memo_data.get('is_locked'):
            self.lock_now()
        elif not self.memo_data.get('_unreadable'):
            self.set_memo_password()

    def _sync_manager(self) -> Any:
        return self.ui_manager.sync_manager if getattr(self, 'ui_manager', None) else None

    def _refresh_explorer(self) -> None:
        ex = getattr(self.ui_manager, 'explorer_window', None) if getattr(self, 'ui_manager', None) else None
        if ex and ex.isVisible():
            ex.refresh()

    def _ask_password(self, label: str) -> str:
        from PyQt6.QtWidgets import QInputDialog
        text, ok = QInputDialog.getText(self._dlg_parent(), "암호 메모", label, QLineEdit.EchoMode.Password)
        return text if ok else ""

    def restart_relock_timer(self) -> None:
        self._relock_timer.stop()
        if not self.memo_data.get('is_locked') or self.is_sealed():
            return
        try:
            minutes = float(self.memo_window_get_settings().get("locked_memo_relock_min", 5))
        except (TypeError, ValueError):
            minutes = 5
        if minutes > 0:
            self._relock_timer.start(int(minutes * 60 * 1000))

    def prompt_unlock(self) -> None:
        sm = self._sync_manager()
        if not sm or not self.memo_data.get('_locked') or getattr(self, '_is_prompting', False):
            return
        self._is_prompting = True
        try:
            pwd = self._ask_password("이 메모의 암호를 입력하세요:")
            if not pwd:
                return
            plain = sm.unlock_memo(self.memo_data.get('id', ''), pwd)
            if plain is None:
                QMessageBox.warning(self._dlg_parent(), "암호 메모", "암호가 일치하지 않습니다.")
                return
            self.memo_data['content'] = plain
            self.memo_data.pop('_locked', None)
            self.apply_data()
            self.restart_relock_timer()
            self._refresh_explorer()
        finally:
            self._is_prompting = False

    def recover_with_master_key(self) -> None:
        """암호를 잊은 메모를 관리자 개인키 파일로 복구하고 새 암호를 설정합니다."""
        sm = self._sync_manager()
        if not sm or not self.memo_data.get('_locked'):
            return
        path, _ = QFileDialog.getOpenFileName(self._dlg_parent(), "관리자 개인키 파일 선택", "", "PEM 키 파일 (*.pem);;모든 파일 (*)")
        if not path:
            return
        try:
            with open(path, "rb") as f:
                pem = f.read()
        except OSError:
            QMessageBox.warning(self._dlg_parent(), "관리자 복구", "개인키 파일을 읽을 수 없습니다.")
            return
        passphrase = self._ask_password("개인키 파일의 암호를 입력하세요:")
        new_pwd = self._ask_password("이 메모에 새로 설정할 암호:")
        if not new_pwd:
            return
        if self._ask_password("새 암호를 한 번 더 입력하세요:") != new_pwd:
            QMessageBox.warning(self._dlg_parent(), "관리자 복구", "두 암호가 일치하지 않습니다.")
            return
        try:
            plain = sm.recover_memo_with_master(self.memo_data.get('id', ''), pem, passphrase, new_pwd)
        except ValueError as e:
            QMessageBox.warning(self._dlg_parent(), "관리자 복구", str(e))
            return
        self.memo_data['content'] = plain
        self.memo_data.pop('_locked', None)
        self.apply_data()
        self.restart_relock_timer()
        self.show_toast("🔓 복구 완료 · 새 암호 설정됨")
        self._refresh_explorer()

    def lock_now(self) -> None:
        """암호 메모를 저장한 뒤 다시 잠급니다. 본문은 메모리에서도 지웁니다."""
        sm = self._sync_manager()
        if not sm or not self.memo_data.get('is_locked') or self.is_sealed():
            return
        self._auto_save_timer.stop()
        self.execute_auto_save()
        self._relock_timer.stop()
        sm.relock_memo(self.memo_data.get('id', ''))
        self.memo_data['content'] = ""
        self.memo_data['_locked'] = True
        self.apply_data()
        self.show_toast("🔒 잠김")
        self._refresh_explorer()

    def set_memo_password(self) -> None:
        sm = self._sync_manager()
        if not sm or self.memo_data.get('_unreadable'):
            return
        if self.memo_data.get('_locked'):
            # 잠긴 상태에서는 먼저 현재 암호로 열어야 암호를 바꿀 수 있습니다.
            self.prompt_unlock()
            if self.is_sealed():
                return
        pwd = self._ask_password("새 암호를 입력하세요:")
        if not pwd:
            return
        if self._ask_password("확인을 위해 한 번 더 입력하세요:") != pwd:
            QMessageBox.warning(self._dlg_parent(), "암호 메모", "두 암호가 일치하지 않습니다.")
            return
        if QMessageBox.question(
            self._dlg_parent(), "암호 메모",
            "암호를 잊으면 이 메모의 내용은 복구할 수 없습니다.\n계속할까요?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        ) != QMessageBox.StandardButton.Yes:
            return
        self._auto_save_timer.stop()
        self._dirty_since = None
        self.memo_data['content'] = self.current_content()
        self.memo_data['updated_at'] = datetime.datetime.now().isoformat()
        if sm.set_memo_password(self.memo_data, pwd):
            self.show_toast("🔒 암호 설정됨")
            self.restart_relock_timer()
            self._refresh_explorer()
        else:
            QMessageBox.warning(self._dlg_parent(), "암호 메모", "암호를 설정하지 못했습니다.")

    def remove_memo_password(self) -> None:
        sm = self._sync_manager()
        if not sm or not self.memo_data.get('is_locked') or self.is_sealed():
            return
        if QMessageBox.question(
            self._dlg_parent(), "암호 메모", "이 메모의 암호를 없애고 일반 메모로 되돌릴까요?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        ) != QMessageBox.StandardButton.Yes:
            return
        self._auto_save_timer.stop()
        self._dirty_since = None
        self._relock_timer.stop()
        self.memo_data['content'] = self.current_content()
        self.memo_data['updated_at'] = datetime.datetime.now().isoformat()
        if sm.remove_memo_password(self.memo_data):
            self.show_toast("🔓 암호 제거됨")
            self._refresh_explorer()
