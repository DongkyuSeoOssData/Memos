"""메모 창의 저장: 고친 내용 자동 저장, 직접 저장, 제목 바꾸기.

(MemoWindow 에 섞어 쓰는 부분)
"""
from ui import modern_style
import re
import datetime
from utils.text_utils import clean_plain_text


class MemoSavingMixin:
    """메모 창의 저장."""

    def _mark_edited(self) -> None:
        """서식 변경 등으로 본문이 바뀌었음을 표시합니다. 저장은 자동 저장(마지막 입력 후 대기)에 맡깁니다."""
        if self.is_sealed():
            return
        # 본문 글자가 아니라 메모 속성(코드 테마, 기본 글꼴 등)만 바뀐 경우를 위해 표시해 둡니다.
        self._meta_dirty = True
        self._schedule_auto_save()
        self.restart_relock_timer()

    def update_content(self) -> None:
        if getattr(self, '_is_updating_from_explorer', False) or getattr(self, '_is_applying_data', False): return
        if self.is_sealed(): return
        self._schedule_auto_save()
        self.restart_relock_timer()

    def _schedule_auto_save(self) -> None:
        """마지막 입력 후 환경설정의 대기 시간이 지나면 저장하도록 예약합니다.

        입력이 이어지면 예약을 뒤로 미루되, 첫 미저장 입력 후 MAX_UNSAVED_SEC를 넘기지는 않습니다.
        """
        import time
        try:
            idle = int(self.memo_window_get_settings().get("auto_save_idle_sec", 60))
        except (TypeError, ValueError):
            idle = 60
        now = time.monotonic()
        if self._dirty_since is None or not self._auto_save_timer.isActive():
            self._dirty_since = now
        remaining_cap = self.MAX_UNSAVED_SEC - (now - self._dirty_since)
        delay = max(0.0, min(float(max(1, idle)), remaining_cap))
        self._auto_save_timer.start(int(delay * 1000))

    def flush_auto_save(self) -> None:
        """예약된 자동 저장이 남아 있으면 지금 바로 저장합니다. (닫기·숨기기·앱 종료 시)"""
        if self._auto_save_timer.isActive():
            self._auto_save_timer.stop()
            self.execute_auto_save()

    def execute_auto_save(self) -> None:
        self._dirty_since = None
        if self.is_sealed():
            # 잠긴 상태의 빈 편집기를 본문으로 저장하면 안 됩니다.
            return
        self.memo_data['content'] = self.current_content()
        # 수정일시는 본문을 실제로 고쳤을 때만 바꿉니다. (고친 것 없이 저장만 한 경우에는 그대로)
        # 본문은 그대로이고 속성만 바뀐 경우에는 다른 기기에 전해지도록 '속성 수정 시각'만 갱신합니다.
        document = self.text_edit.document()
        now = datetime.datetime.now().isoformat()
        if document.isModified():
            self.memo_data['updated_at'] = now
        elif getattr(self, '_meta_dirty', False):
            self.memo_data['meta_updated_at'] = now
        document.setModified(False)
        self._meta_dirty = False

        plain = clean_plain_text(self.memo_data['content'])

        if self.memo_data.get('is_draft'):
            if plain:
                self.memo_data['is_draft'] = False
                self.save_callback(self.memo_data)
                self.show_toast("✓ 저장됨")
        else:
            self.save_callback(self.memo_data)
            self.show_toast("✓ 저장됨")

    def manual_save(self) -> None:
        plain = clean_plain_text(self.text_edit.toHtml())
        if plain:
            self.memo_data['is_manually_saved'] = True
            self.memo_data['is_draft'] = False
            self._auto_save_timer.stop()
            self.execute_auto_save()
        else:
            # 내용이 없으면 draft 상태 유지, 저장은 수행하되 목록에는 추가 안되게 처리
            self._auto_save_timer.stop()
            self.execute_auto_save()

    def enable_rename(self) -> None:
        self.title_edit.setReadOnly(False)
        pal = self._memo_theme_palette()
        is_rolled = getattr(self, '_is_rolled_up', False)
        rolled_h = self._get_rolled_height()
        title_pt = max(8.0, min(13.0, rolled_h * 0.22)) if is_rolled else 12.0
        self.title_edit.setStyleSheet(f"border:1px solid {pal['accent']}; background:transparent; color:{pal['text']}; font-weight:bold; font-size:{title_pt}pt; border-radius:0px; font-family: {modern_style.UI_FONT};")
        self.title_edit.setFocus()
        self.title_edit.setCursorPosition(len(self.title_edit.text()))

    def handle_rename(self) -> None:
        self.title_edit.setReadOnly(True)
        self._do_title_save()

    def _do_title_save(self) -> None:
        nt = re.sub(r'[\\/*?:"<>|]', "", self.title_edit.text().strip())
        ot = self.memo_data.get('title','')
        if not nt or nt == ot:
            self.title_edit.setText(ot)
        else:
            if self.rename_callback(ot, nt, self.memo_data):
                self.memo_data['title'] = nt
                self.memo_data['updated_at'] = datetime.datetime.now().isoformat()     # 제목을 고친 것도 수정
                self.save_callback(self.memo_data)
            else:
                self.show_toast(f"'{nt}' 제목의 메모가 이미 있습니다.", warn=True)
                self.title_edit.setText(ot)

        is_rolled = getattr(self, '_is_rolled_up', False)
        rolled_h = self._get_rolled_height()
        title_pt = max(8.0, min(13.0, rolled_h * 0.22)) if is_rolled else 12.0
        self.title_edit.setStyleSheet(self._title_color_stylesheet(title_pt))
        self.title_edit.setCursorPosition(0)
        self.title_edit.deselect()
        if getattr(self, 'ui_manager', None) and self.ui_manager.explorer_window and self.ui_manager.explorer_window.isVisible():
            self.ui_manager.explorer_window.update_table()
