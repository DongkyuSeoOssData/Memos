from ui.memo_editor import CodeHighlighter
from ui.themes import memo_palette
from ui import modern_style
from core import reminders
from ui import memo_geometry
from ui.reminder_ui import ask_reminder
from ui.dialogs import pick_history
from ui.side_panel import SidePanel
from ui.memo_lock import MemoLockMixin
from ui.memo_format import MemoFormatMixin
from typing import Dict, Any, Optional
from PyQt6.QtWidgets import QWidget, QLabel
from PyQt6.QtCore import Qt, QPoint, QTimer, QEvent
from PyQt6.QtGui import QColor, QShortcut, QKeySequence, QCursor
from utils.text_utils import clean_plain_text
from ui.memo_rollup import MemoRollupMixin
from ui.memo_saving import MemoSavingMixin
from ui.memo_find import MemoFindMixin
from ui.memo_menu import MemoMenuMixin
from ui.memo_layout import MemoLayoutMixin
from ui.memo_apply import MemoApplyMixin
from ui.memo_drag import MemoDragMixin
from ui.memo_code import MemoCodeMixin


class MemoWindow(MemoLayoutMixin, MemoApplyMixin, MemoDragMixin, MemoCodeMixin, MemoRollupMixin, MemoSavingMixin, MemoFindMixin, MemoMenuMixin, MemoLockMixin, MemoFormatMixin, QWidget):
    """
    개별 메모장 창 클래스:
    - 옵션 2: 애플 모던 사이버/네온 핀 뱃지 (📍 / 📌)
    - 윈도우 스타일 우상단 제어 버튼 (─ 최소화 / □ 최대화 / ✕ 닫기)
    - 100% 정상 작동하는 최대화/복원 (toggle_maximize)
    - 기본 100% 불투명 솔리드 상태 (opacity: 1.0)
    """
    def __init__(self, m: Dict[str, Any], sc: Any, dc: Any, rc: Any, cc: Any) -> None:
        super().__init__()
        self.memo_data = m
        self.save_callback = sc
        self.delete_callback = dc
        self.rename_callback = rc
        self.close_callback = cc
        self.ui_manager = getattr(cc, '__self__', None)
        self._old_pos: Optional[QPoint] = None
        self._is_updating_from_explorer: bool = False
        self._is_rolled_up: bool = m.get('is_rolled_up', False)
        self._normal_height: int = m.get('height', 400)

        self._auto_save_timer = QTimer(self)
        self._auto_save_timer.setSingleShot(True)
        self._auto_save_timer.timeout.connect(self.execute_auto_save)
        self._dirty_since: Optional[float] = None

        # 암호 메모: 마지막 입력 후 일정 시간이 지나면 다시 잠급니다.
        self._relock_timer = QTimer(self)
        self._relock_timer.setSingleShot(True)
        self._relock_timer.timeout.connect(self.lock_now)

        self.highlighter: Optional[CodeHighlighter] = None

        self.toast_label = QLabel(self)
        self.toast_label.hide()
        self.toast_timer = QTimer(self)
        self.toast_timer.setSingleShot(True)
        self.toast_timer.timeout.connect(self.toast_label.hide)

        self.setup_ui()
        self.apply_data()
        self.bind_shortcuts()

        self.setMouseTracking(True)
        self.text_edit.setMouseTracking(True)
        self.text_edit.cursorPositionChanged.connect(self.update_toolbar_button_states)

        self._is_deleting = False
        self._title_save_timer = QTimer(self)
        self._title_save_timer.setSingleShot(True)
        self._title_save_timer.timeout.connect(self._do_title_save)

        self._wheel_save_timer = QTimer(self)
        self._wheel_save_timer.setSingleShot(True)
        self._wheel_save_timer.timeout.connect(lambda: self.save_callback(self.memo_data))

    def bind_shortcuts(self) -> None:
        # 기존 QShortcut 키를 비워 무력화 (rebind 시 중복 등록 방지)
        for _sc in self.findChildren(QShortcut):
            _sc.setEnabled(False)
            _sc.setKey(QKeySequence())
            _sc.deleteLater()

        s_cfg = self.memo_window_get_settings().get("shortcuts", {})

        QShortcut(QKeySequence(s_cfg.get("save", "Ctrl+S")), self).activated.connect(self.manual_save)
        QShortcut(QKeySequence(s_cfg.get("search", "Ctrl+F")), self).activated.connect(self.show_search_only)
        QShortcut(QKeySequence(s_cfg.get("replace", "Ctrl+H")), self).activated.connect(self.show_search_and_replace)
        QShortcut(QKeySequence(s_cfg.get("rename", "F2")), self).activated.connect(self.enable_rename)
        QShortcut(QKeySequence(s_cfg.get("eng_kor_convert", "Alt+E")), self).activated.connect(self.convert_selected_eng_kor)
        QShortcut(QKeySequence(s_cfg.get("toggle_fmt_bar", "Alt+T")), self).activated.connect(self.toggle_sub_fmt_panel)
        QShortcut(QKeySequence(s_cfg.get("copy_all", "Alt+C")), self).activated.connect(self.copy_all_content)
        QShortcut(QKeySequence(s_cfg.get("format_code", "Alt+F")), self).activated.connect(self.prettify_code)

        QShortcut(QKeySequence(s_cfg.get("toggle_pin", "Alt+P")), self).activated.connect(self.toggle_pin)
        QShortcut(QKeySequence(s_cfg.get("toggle_rollup", "Alt+M")), self).activated.connect(self.toggle_rollup)
        QShortcut(QKeySequence(s_cfg.get("delete_memo", "Alt+D")), self).activated.connect(self.request_delete)
        QShortcut(QKeySequence(s_cfg.get("toggle_code_theme", "Alt+L")), self).activated.connect(self.toggle_code_theme)
        QShortcut(QKeySequence(s_cfg.get("toggle_line_numbers", "Alt+G")), self).activated.connect(self.toggle_line_numbers)
        QShortcut(QKeySequence(s_cfg.get("toggle_line_bg",      "Alt+B")), self).activated.connect(self.toggle_line_bg)

        if getattr(self, 'ui_manager', None):
            # 글로벌 단축키(keyboard 훅)와 중복 방지를 위해 로컬 QShortcut에서는 제외함
            # open_all_memos는 전역 단축키가 아니므로 로컬로 유지
            QShortcut(QKeySequence(s_cfg.get("open_all_memos", "Alt+O")), self).activated.connect(self.ui_manager.open_all_memos)

        QShortcut(QKeySequence(s_cfg.get("toggle_memo_lock", "Ctrl+L")), self).activated.connect(self.toggle_memo_lock)
        QShortcut(QKeySequence(s_cfg.get("set_memo_password", "Ctrl+Shift+L")), self).activated.connect(self.set_memo_password)
        QShortcut(QKeySequence(s_cfg.get("toggle_checklist", "Alt+K")), self).activated.connect(self.toggle_checklist)
        QShortcut(QKeySequence(s_cfg.get("set_reminder", "Ctrl+R")), self).activated.connect(self.edit_reminder)
        QShortcut(QKeySequence(s_cfg.get("show_history", "Ctrl+Shift+H")), self).activated.connect(self.show_history)

        QShortcut(QKeySequence("Esc"), self).activated.connect(self.close)

    def rebind_shortcuts(self) -> None:
        """설정 변경 후 단축키를 새 설정으로 재등록합니다."""
        self.bind_shortcuts()

    def memo_window_get_settings(self) -> Dict[str, Any]:
        return self.ui_manager.sync_manager.settings if getattr(self, 'ui_manager', None) else {}

    def memo_bg_color(self) -> str:
        """일반 메모의 바탕색."""
        bg_color = self.memo_data.get('bg_color', '#FFFFFF')
        return '#FFFFFF' if bg_color == 'random' else bg_color

    def is_dark_bg(self) -> bool:
        """메모 바탕이 어두운지 여부. (글자·아이콘을 밝게 그려야 하는지)"""
        if self.memo_data.get('is_code_memo', False):
            return self.memo_data.get('code_theme', 'dark') == 'dark'
        color = QColor(self.memo_bg_color())
        if not color.isValid():
            return False
        return (0.299 * color.red() + 0.587 * color.green() + 0.114 * color.blue()) / 255.0 < 0.5

    def _memo_theme_palette(self) -> Dict[str, Any]:
        return memo_palette(self.is_dark_bg())

    def show_toast(self, text: str, warn: bool = False) -> None:
        self.toast_label.setText(("⚠ " + text) if warn else text)
        self.toast_label.adjustSize()
        x = self.width() - self.toast_label.width() - 15
        y = self.height() - (self.fmt_bar.geometry().height() if hasattr(self, 'fmt_bar') else 35) - self.toast_label.height() - 20
        self.toast_label.move(max(10, x), max(10, y))
        self.toast_label.show()
        self.toast_label.raise_()
        self.toast_timer.start(3000 if warn else 1500)


    LOCK_BADGE_WIDTH = 20

    def refresh_lock_badge(self) -> None:
        """접어 둔 암호 메모의 제목 왼쪽에 자물쇠를 보입니다. (제목 글자는 그만큼 오른쪽에서 시작)"""
        show = bool(self.memo_data.get('is_locked')) and self._is_rolled_up
        self.title_edit.setTextMargins(self.LOCK_BADGE_WIDTH if show else 0, 0, 0, 0)
        if show:
            self.lbl_lock.setFont(self.title_edit.font())
            self.lbl_lock.setGeometry(0, 0, self.LOCK_BADGE_WIDTH, self.title_edit.height())
        self.lbl_lock.setVisible(show)

    def side_panel(self) -> SidePanel:
        """이 메모 옆에 붙는 패널. (알림 설정·이전 내용처럼 메모 안에 다 들어가지 않는 화면을 띄우는 곳)"""
        if getattr(self, '_side_panel', None) is None:
            self._side_panel = SidePanel(self)
        return self._side_panel

    # ── 체크리스트 진행 표시 ──────────────────────────────────────────────────
    def refresh_progress(self) -> None:
        """제목 줄의 진행 표시('☐ 3/5', 다 끝내면 '☑ 5/5')를 지금 본문에 맞춥니다. 체크리스트가 없거나 잠긴 메모면 숨깁니다."""
        text = "" if self.is_sealed() else self.text_edit.check_marks.progress_label()
        if text != self.lbl_progress.text() or self.lbl_progress.isHidden() == bool(text):
            ink = self._memo_theme_palette()['text']
            self.lbl_progress.setStyleSheet(
                f"color: {ink}; background: {modern_style.rgba(ink, 0.10)}; padding: 1px 6px; font-size: 8.5pt; "
                f"font-weight: 700; font-family: {modern_style.UI_FONT};")
            self.lbl_progress.setText(text)
            self.lbl_progress.setVisible(bool(text))

    # ── 알림 ─────────────────────────────────────────────────────────────────
    def refresh_reminder_badge(self) -> None:
        """서식 줄 오른쪽의 알림 표시를 지금 알림에 맞춥니다."""
        text = reminders.describe(self.memo_data.get('reminder'))
        self.btn_reminder.setToolTip("알림: " + text + " (눌러서 바꾸기)" if text else "")
        self.btn_reminder.setVisible(bool(text) and not self._is_rolled_up)
        if not text:
            self.btn_reminder.setText("")
            return
        # 메모 폭에 들어가는 가장 자세한 표기를 고릅니다. (좁은 메모에서는 시계만)
        due = reminders.due_at(self.memo_data.get('reminder'))
        used = sum(item.widget().width() + self.fmt_bar.spacing() for item in map(self.fmt_bar.itemAt, range(self.fmt_bar.count()))
                   if item.widget() and item.widget() is not self.btn_reminder and not item.widget().isHidden())
        room = self.bg.width() - used - 36
        metrics = self.btn_reminder.fontMetrics()
        choices = ("⏰ " + text, f"⏰ {due.month}.{due.day:02d} {due.hour:02d}:{due.minute:02d}", f"⏰ {due.month}.{due.day:02d}", "⏰")
        label = next((c for c in choices if metrics.horizontalAdvance(c) + 18 <= room), choices[-1])
        self.btn_reminder.setText(label)
        self.btn_reminder.setFixedWidth(metrics.horizontalAdvance(label) + 18)

    def edit_reminder(self) -> None:
        """알림 설정 창을 띄워 이 메모의 알림을 걸거나 풉니다."""
        sm = self._sync_manager()
        if not sm:
            return
        changed, reminder = ask_reminder(self._dlg_parent(), self.memo_data.get('reminder'), str(self.memo_data.get('title', '')))
        if not changed:
            return
        sm.set_reminder(self.memo_data, reminder)
        self.refresh_reminder_badge()
        self._refresh_explorer()
        self.show_toast("⏰ " + reminders.describe(reminder) if reminder else "알림을 해제했습니다")

    # ── 변경 기록 ────────────────────────────────────────────────────────────
    def show_history(self) -> None:
        """이전 내용을 보여 주고, 고른 내용으로 되돌립니다."""
        sm = self._sync_manager()
        memo_id = self.memo_data.get('id', '')
        if not sm or not memo_id:
            return
        self.flush_auto_save()                  # 지금 치던 내용도 기록에 남도록 먼저 저장
        chosen = pick_history(self._dlg_parent(), str(self.memo_data.get('title', '')), sm.list_history(memo_id),
                              reveal=lambda index, password: sm.read_history_text(memo_id, index, password),
                              check=lambda index, password: sm.restore_problem(memo_id, index, password))
        if chosen is not None and sm.restore_history(memo_id, chosen[0], chosen[1]):
            self.ui_manager.reload_pulled_memos([memo_id])
            self._refresh_explorer()
            self.show_toast("이전 내용으로 되돌렸습니다")

    def toggle_maximize(self) -> None:
        """100% 정상 작동하는 최대화/복원 토글"""
        if self.isMaximized():
            self.showNormal()
            self.btn_max.setText("")
            self.btn_max.setToolTip("최대화")
        else:
            self.showMaximized()
            self.btn_max.setText("")
            self.btn_max.setToolTip("복원")


    def toggle_sub_fmt_panel(self) -> None:
        is_vis = self.sub_fmt_widget.isVisible()
        self.sub_fmt_widget.setVisible(not is_vis)
        self.btn_toggle_sub_fmt.setText("Aa ▾" if not is_vis else "Aa ▴")      # 위로 열리고(▴) 아래로 닫힘(▾)
        if is_vis:
            self.title_edit.deselect()
            self.text_edit.setFocus()                   # 닫으면 본문으로 돌아감


    def mouseDoubleClickEvent(self, e: Any) -> None:
        if e.button() == Qt.MouseButton.LeftButton:
            if self._is_rolled_up or e.position().y() <= 53:
                self.toggle_rollup()
                e.accept()
                return
        super().mouseDoubleClickEvent(e)

    def eventFilter(self, obj: Any, event: Any) -> bool:
        if hasattr(self, 'title_edit') and obj == self.title_edit:
            if event.type() == QEvent.Type.MouseButtonDblClick and event.button() == Qt.MouseButton.LeftButton:
                self.toggle_rollup()
                return True

            if not self.title_edit.isReadOnly():
                if event.type() == QEvent.Type.FocusOut:
                    self.handle_rename()
            else:
                if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                    self.mousePressEvent(event)
                    return True
                elif event.type() == QEvent.Type.MouseMove:
                    self.mouseMoveEvent(event)
                    return True
                elif event.type() == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
                    self.mouseReleaseEvent(event)
                    return True

        return super().eventFilter(obj, event)


    def resizeEvent(self, event: Any) -> None:
        super().resizeEvent(event)
        if hasattr(self, 'lock_overlay'):
            self.lock_overlay.refresh()                    # 접거나 펼 때 보이기/숨기기
            self.refresh_lock_badge()
            if not self.lock_overlay.isHidden():
                self.lock_overlay.sync_geometry()
        if hasattr(self, 'btn_reminder') and not self.btn_reminder.isHidden():
            self.refresh_reminder_badge()
        if hasattr(self, 'grip'):
            # 📌 접힌 메모와 동일하게 메모 안쪽에 딱 알맞게 안착 (삐져나옴 방지)
            if self._is_rolled_up:
                self.grip.move(self.width() - 18, self.height() - 18)
            else:
                self.grip.move(self.width() - 20, self.height() - 20)
            self.grip.resize(12, 12)

        # 📌 접힌 상태에서 맞닿아 있을 때만 12px 스냅 멈춤 & 15px 이상 끌면 이탈하여 가로 자유 조절
        applying = getattr(self, '_applying_geometry', False)
        if self._is_rolled_up:
            if not applying:
                self.memo_data['rolled_width'] = self.width()
            rolled_h = self._get_rolled_height()
            if self.height() != rolled_h:
                self.resize(self.width(), rolled_h)
                return  # resize()가 또 resizeEvent를 발생시키므로 이번 이벤트는 여기서 종료
            # 접힌 상태이면 버튼·타이틀 크기를 항상 재보정 (외부 resize/스케일 변경 대응)
            self._apply_rolled_ui(rolled_h)
            target_win = self.find_snap_target_memo()
            if target_win:
                target_w = target_win.width()
                mouse_x = QCursor.pos().x()

                if getattr(self, '_sticky_snap_origin', None):
                    start_mouse_x, snap_w = self._sticky_snap_origin
                    if abs(mouse_x - start_mouse_x) > 15:
                        self._sticky_snap_origin = None  # 15px 이상 당기면 자석 이탈!
                    else:
                        self.resize(snap_w, rolled_h)
                        return

                if not getattr(self, '_sticky_snap_origin', None):
                    if abs(self.width() - target_w) <= 12:
                        self.resize(target_w, rolled_h)
                        self._sticky_snap_origin = (mouse_x, target_w)
            else:
                self._sticky_snap_origin = None
        elif not applying and not self.is_locked_compact():
            self.memo_data['unrolled_width'] = self.width()
            self.memo_data['unrolled_height'] = self.height()
            self.memo_data['width'] = self.width()
            self.memo_data['height'] = self.height()


    # ── 위치와 크기 기억 ─────────────────────────────────────────────────────
    # 어디에 어떤 크기로 놓을지의 규칙은 ui/memo_geometry.py 에 있습니다. (창 없이 숫자만으로 따질 수 있게 따로 둠)
    # 여기서는 지금 창의 상태를 넘겨주고, 돌려받은 자리에 창을 놓습니다.
    LOCKED_SIZE = memo_geometry.LOCKED_SIZE


    # 쉬지 않고 계속 입력하는 동안에도 최소한 이 간격으로는 저장합니다.
    MAX_UNSAVED_SEC = 600


    def hideEvent(self, e: Any) -> None:
        if hasattr(self, 'lock_overlay'):
            self.lock_overlay.cancel()                     # 암호를 묻던 중이면 취소
        if not getattr(self, '_is_deleting', False):
            self.flush_auto_save()
        super().hideEvent(e)


    def closeEvent(self, e: Any) -> None:
        if (not getattr(self, '_is_deleting', False) and not getattr(self, '_close_warned', False)
                and self.flush_auto_save() is False):
            # 쓴 글을 저장하지 못한 채 닫히면 그대로 사라지므로, 한 번은 닫지 않고 알립니다.
            self._close_warned = True
            self.show_toast("저장하지 못해 닫지 않았습니다 · 한 번 더 닫으면 저장하지 않고 닫습니다", warn=True)
            e.ignore()
            return
        panel = getattr(self, '_side_panel', None)
        if panel is not None:                               # 옆에 붙여 연 패널(알림 설정·이전 내용)도 함께 정리
            self._side_panel = None
            panel.cancel()
            panel.hide()
            panel.deleteLater()
        if getattr(self, '_is_deleting', False):
            self._auto_save_timer.stop()
        else:
            # 아직 저장되지 않은 입력을 닫기 전에 반영
            self.flush_auto_save()
        if hasattr(self, '_title_save_timer'):
            self._title_save_timer.stop()

        if getattr(self, '_is_deleting', False):
            super().closeEvent(e)
            return

        if self.memo_data.get('is_code_memo', False):
            plain_text = self.text_edit.toPlainText().strip()
        else:
            plain_text = clean_plain_text(self.text_edit.toHtml()).strip()

        # 아무것도 적지 않고 닫는 새 메모만 치웁니다. 한 번이라도 저장된 메모는 글을 다 지우고 닫아도 남깁니다.
        is_empty_draft = (
            (not plain_text)
            and bool(self.memo_data.get('is_draft'))
            and (not self.memo_data.get('is_manually_saved', False))
            and not self.memo_data.get('is_locked')
            and not self.is_sealed()
        )

        if is_empty_draft:
            self.delete_callback(self)
        else:
            if plain_text and self.memo_data.get('is_draft'):
                self.memo_data['is_draft'] = False
                self.save_callback(self.memo_data)

            self.remember_geometry()
            self.memo_data['is_rolled_up'] = self._is_rolled_up

            # 사용자가 닫은 메모는 숨긴 것으로 기억합니다. 앱을 끝내느라 닫히는 경우는 그대로 두어,
            # 다시 켰을 때 떠 있던 메모가 제자리에 다시 뜨게 합니다.
            if not getattr(getattr(self, 'ui_manager', None), 'quitting', False):
                self.memo_data['is_visible'] = False
            self.save_callback(self.memo_data)
            self.close_callback(self)
            # 창을 닫으면 암호 메모의 키도 메모리에서 지웁니다.
            self._relock_timer.stop()
            sm = self._sync_manager()
            if sm and self.memo_data.get('is_locked'):
                sm.relock_memo(self.memo_data.get('id', ''))
        super().closeEvent(e)


    def toggle_pin(self) -> None:
        self.memo_data['is_pinned'] = not self.memo_data.get('is_pinned', False)
        self.apply_look()
        self.save_callback(self.memo_data)


