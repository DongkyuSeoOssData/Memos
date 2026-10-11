"""메모 창의 암호 잠금 기능 (암호 걸기·풀기·다시 잠그기·관리자 키 복구)."""
import datetime
from typing import Any

from PyQt6.QtWidgets import QFileDialog

from ui import themed_dialog


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

    def _ask_form(self, title: str, text: str, fields: list, ok_text: str = "확인", validate: Any = None,
                  danger: bool = False) -> Any:
        """암호 등을 입력받습니다. 메모 창 안에서 본문을 흐리게 가리고 묻고, 자리가 없으면 대화상자로 묻습니다.

        확인하면 입력한 값들을, 취소하면 None 을 돌려줍니다. validate 가 오류 문구를 돌려주면 닫지 않고 다시 묻습니다.
        """
        return themed_dialog.ask_form(self._dlg_parent(), title, text, fields, ok_text, validate, danger)

    def _warn(self, text: str) -> None:
        themed_dialog.toast(self._dlg_parent(), text, warn=True)

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

    def try_unlock(self, pwd: str) -> Any:
        """암호로 본문을 풀어 봅니다. 틀리면 오류 문구를, 맞으면 None 을 돌려줍니다. (맞으면 finish_unlock 으로 마무리)"""
        sm = self._sync_manager()
        if not sm or not self.memo_data.get('_locked'):
            return "잠긴 메모가 아닙니다."
        if not pwd:
            return "암호를 입력하세요."
        plain = sm.unlock_memo(self.memo_data.get('id', ''), pwd)
        if plain is None:
            return "암호가 일치하지 않습니다."
        self._opened_plain = plain
        return None

    def finish_unlock(self) -> None:
        """try_unlock 으로 푼 본문을 화면에 올립니다."""
        plain = self.__dict__.pop('_opened_plain', None)
        if plain is None:
            return
        self.memo_data['content'] = plain
        self.memo_data.pop('_locked', None)
        self.apply_data()
        self.restart_relock_timer()
        self._refresh_explorer()
        self.text_edit.setFocus()

    def prompt_unlock(self) -> None:
        """잠긴 메모의 암호를 묻습니다. 메모가 펼쳐져 있으면 본문 자리의 암호 칸에 커서를 두는 것으로 충분합니다."""
        sm = self._sync_manager()
        if not sm or not self.memo_data.get('_locked') or getattr(self, '_is_prompting', False):
            return
        if self._dlg_parent() is self and self.lock_overlay.focus_inline():
            return
        self._is_prompting = True
        try:
            if self._ask_form("🔒 암호 메모", "이 메모의 암호를 입력하세요.", [{"label": "암호", "password": True}],
                              "열기", validate=lambda values: self.try_unlock(values[0])) is None:
                return
            self.finish_unlock()
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
            self._warn("개인키 파일을 읽을 수 없습니다.")
            return
        recovered = {}

        def attempt(values: list) -> Any:
            passphrase, new_pwd, again = values
            if not new_pwd:
                return "새 암호를 입력하세요."
            if new_pwd != again:
                return "두 암호가 일치하지 않습니다."
            try:
                recovered['plain'] = sm.recover_memo_with_master(self.memo_data.get('id', ''), pem, passphrase, new_pwd)
            except ValueError as e:
                return str(e)
            return None

        fields = [{"label": "개인키 파일의 암호 (없으면 비워 둠)", "password": True},
                  {"label": "이 메모에 새로 설정할 암호", "password": True},
                  {"label": "새 암호 한 번 더", "password": True}]
        if self._ask_form("관리자 키로 복구", "", fields, "복구", validate=attempt) is None:
            return
        self.memo_data['content'] = recovered['plain']
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
        def check(values: list) -> Any:
            if not values[0]:
                return "암호를 입력하세요."
            return None if values[0] == values[1] else "두 암호가 일치하지 않습니다."

        changing = bool(self.memo_data.get('is_locked'))
        values = self._ask_form(
            "암호 변경" if changing else "🔒 암호 걸기", "암호를 잊으면 이 메모의 내용은 복구할 수 없습니다.",
            [{"label": "새 암호", "password": True}, {"label": "새 암호 한 번 더", "password": True}],
            "암호 변경" if changing else "암호 걸기", validate=check)
        if values is None:
            return
        pwd = values[0]
        self._auto_save_timer.stop()
        self._dirty_since = None
        self.memo_data['content'] = self.current_content()
        self.memo_data['updated_at'] = datetime.datetime.now().isoformat()
        if sm.set_memo_password(self.memo_data, pwd):
            self.refresh_lock_badge()                    # 접어 둔 메모면 바로 자물쇠가 보이게
            self.show_toast("🔒 암호 설정됨")
            self.restart_relock_timer()
            self._refresh_explorer()
        else:
            self._warn("암호를 설정하지 못했습니다.")

    def remove_memo_password(self) -> None:
        sm = self._sync_manager()
        if not sm or not self.memo_data.get('is_locked') or self.is_sealed():
            return
        if self._ask_form("암호 제거", "이 메모의 암호를 없애고 일반 메모로 되돌릴까요?", [], "암호 제거", danger=True) is None:
            return
        self._auto_save_timer.stop()
        self._dirty_since = None
        self._relock_timer.stop()
        self.memo_data['content'] = self.current_content()
        self.memo_data['updated_at'] = datetime.datetime.now().isoformat()
        if sm.remove_memo_password(self.memo_data):
            self.refresh_lock_badge()
            self.show_toast("🔓 암호 제거됨")
            self._refresh_explorer()
