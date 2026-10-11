from PyQt6.QtCore import QMetaObject

from ui.memo_window import MemoWindow
from ui.memo_explorer import MemoExplorerWindow
from ui.settings_window import SettingsWindow
from ui.global_hotkeys import GlobalHotkeys
import sys
import re
import random
import datetime
import uuid
from pathlib import Path
from typing import List, Dict, Any, Optional
from PyQt6.QtWidgets import QMenu, QSystemTrayIcon, QApplication
from PyQt6.QtCore import Qt, QTimer, QByteArray
from PyQt6.QtGui import QIcon, QKeySequence, QPixmap, QPainter, QShortcut
from PyQt6.QtSvg import QSvgRenderer
import threading

PASTEL_COLORS = ["#E0F2FE", "#DCFCE7", "#FEF9C3", "#FCE7F3", "#FFFFFF"]

from ui.themes import app_palette
from ui import modern_style
from core.defaults import DEFAULT_SHORTCUTS
from core import folders, guide, reminders
from ui.quick_search import QuickSearch
from ui import themed_dialog
from ui.reminder_ui import ReminderPopup
from utils.text_utils import clean_plain_text


class UIManager:
    """
    iOS 울트라 미니멀 화이트 & 블랙 트레이 및 창 레이어링 배치 관리자
    """
    def __init__(self, sm: Any) -> None:
        self.sync_manager = sm
        self.memo_windows: Dict[str, MemoWindow] = {}
        self._all_visible: bool = True
        self.explorer_window: Optional[MemoExplorerWindow] = None
        self.settings_window: Optional['SettingsWindow'] = None
        self._cascade_count: int = 0
        self._hotkeys = GlobalHotkeys()
        # (아이콘 파일, 색, 화면 배율) → 그려 둔 아이콘. 같은 아이콘을 쓸 때마다 SVG를 다시 읽고 그리지 않습니다.
        self._icon_cache: Dict[tuple, QIcon] = {}
        themed_dialog.use_settings(lambda: self.sync_manager.settings, self._save_dialog_settings)
        reminders.set_ampm(not self.sync_manager.settings.get("time_24h", False))
        self.quick_search: Optional[QuickSearch] = None
        # 알림: 가장 가까운 알림 시각에 맞춰 한 번만 깨어나는 타이머 (주기적으로 훑지 않음)
        self._reminder_popups: List[ReminderPopup] = []
        self._reminder_timer = QTimer()
        self._reminder_timer.setSingleShot(True)
        self._reminder_timer.timeout.connect(self.check_reminders)
        self.sync_manager.reminders_changed.connect(self.schedule_reminders)
        self.schedule_reminders()               # 이미 읽어 둔 알림이 있으면 바로 예약
        self.sync_manager.set_ui_manager(self)
        self.setup_tray()
        app = QApplication.instance()
        if app:
            app.aboutToQuit.connect(self.flush_pending_saves)

    def flush_pending_saves(self) -> None:
        """앱 종료 직전, 자동 저장 주기를 기다리던 입력을 모두 저장합니다."""
        for w in list(self.memo_windows.values()):
            try:
                w.flush_auto_save()
            except Exception as e:
                self.sync_manager.log_error(f"종료 시 메모 저장 실패: {e}", e)
        if self.explorer_window:
            self.explorer_window._flush_preview_save()
        self._hotkeys.unregister_all()

    def get_theme_icon(self, svg_name: str, is_dark: Optional[bool] = None, override_color: Optional[str] = None) -> QIcon:
        if getattr(sys, 'frozen', False):
            base_dir = Path(getattr(sys, '_MEIPASS', Path(__file__).parent.parent))
        else:
            base_dir = Path(__file__).parent.parent

        if override_color:
            target_color = override_color
        else:
            if is_dark is None:
                is_dark = self.sync_manager.settings.get("app_theme", "white") == "dark"
            # 아이콘 색은 고른 색 테마에서 가져오되, 밝기(is_dark)는 호출한 쪽이 정한 값을 따릅니다.
            pal, _ = app_palette({**self.sync_manager.settings, "app_theme": "dark" if is_dark else "white"})
            target_color = pal["icon"]
            if is_dark and svg_name in ["rollup.svg", "maximize.svg"]:
                target_color = "#FFFFFF"

        screen = QApplication.primaryScreen()
        scale = max(1.0, float(screen.devicePixelRatio())) if screen else 1.0
        cache_key = (svg_name, target_color, scale)
        cached = self._icon_cache.get(cache_key)
        if cached is not None:
            return cached

        svg_path = base_dir / "icons" / svg_name
        if not svg_path.exists():
            svg_path = Path("icons") / svg_name
        if not svg_path.exists():
            return QIcon()
        try:
            with open(svg_path, "r", encoding="utf-8") as f:
                svg_data = f.read()

            svg_data = re.sub(r'stroke="[^"]+"', f'stroke="{target_color}"', svg_data)
            if re.search(r'fill="#[0-9a-fA-F]{3,6}"', svg_data):
                svg_data = re.sub(r'fill="#[0-9a-fA-F]{3,6}"', f'fill="{target_color}"', svg_data)
            elif "stroke=" not in svg_data:
                svg_data = re.sub(r'<path(?![^>]*(?:stroke="none"|fill="none"))', f'<path fill="{target_color}" ', svg_data)

            renderer = QSvgRenderer(QByteArray(svg_data.encode('utf-8')))
            # 화면 배율만큼 크게 그려 두어야 고배율(125%·150%…) 화면에서 흐려지지 않습니다.
            side = round(24 * scale)
            pixmap = QPixmap(side, side)
            pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            renderer.render(painter)
            painter.end()
            pixmap.setDevicePixelRatio(scale)
            icon = QIcon(pixmap)
            self._icon_cache[cache_key] = icon
            return icon
        except Exception:
            return QIcon()

    def setup_tray(self) -> None:
        if getattr(sys, 'frozen', False):
            base_dir = Path(getattr(sys, '_MEIPASS', Path(__file__).parent.parent))
        else:
            base_dir = Path(__file__).parent.parent

        icon_path = base_dir / "icons" / "memo.ico"
        if not icon_path.exists():
            icon_path = Path("icons") / "memo.ico"

        self.tray_icon = QSystemTrayIcon(QIcon(str(icon_path)))
        self.tray_icon.activated.connect(self.on_tray_activated)
        self.update_tray_menu()
        self.tray_icon.show()

    def _fmt_sc(self, title: str, sc: str) -> str:
        return f"{title} ({sc})" if sc else title

    def update_tray_menu(self) -> None:
        menu = QMenu()
        theme = self.sync_manager.settings.get('app_theme', 'white')
        is_dark = (theme == "dark")
        menu.setStyleSheet(modern_style.menu_qss(self.sync_manager.settings))

        s = {**DEFAULT_SHORTCUTS, **self.sync_manager.settings.get("shortcuts", {})}

        act_new = menu.addAction(self._fmt_sc("새 메모", s['new_memo']))
        act_new.setIcon(self.get_theme_icon("memo.svg", is_dark))
        act_new.triggered.connect(self.create_empty_memo)

        act_code = menu.addAction(self._fmt_sc("새 코드 메모", s['new_code_memo']))
        act_code.setIcon(self.get_theme_icon("codememo.svg", is_dark))
        act_code.triggered.connect(self.create_code_memo)

        act_arr_r = menu.addAction(self._fmt_sc("접은 메모 정렬", s['arrange_rolled_memos']))
        act_arr_r.setIcon(self.get_theme_icon("정렬1.svg", is_dark))
        act_arr_r.triggered.connect(self.arrange_rolled_up_memos)

        act_find = menu.addAction(self._fmt_sc("빠른 검색", s['quick_search']))
        act_find.setIcon(self.get_theme_icon("search.svg", is_dark))
        act_find.triggered.connect(self.toggle_quick_search)

        act_exp = menu.addAction(self._fmt_sc("메모 탐색기", s['open_explorer']))
        act_exp.setIcon(self.get_theme_icon("memo.svg", is_dark))
        act_exp.triggered.connect(self.open_memo_explorer)

        act_arr_a = menu.addAction(self._fmt_sc("펼친 메모 정렬", s['arrange_all_memos']))
        act_arr_a.setIcon(self.get_theme_icon("정렬2.svg", is_dark))
        act_arr_a.triggered.connect(self.arrange_memos)

        act_sync = menu.addAction("지금 동기화")
        act_sync.setIcon(self.get_theme_icon("cloude.svg", is_dark))
        act_sync.triggered.connect(self.sync_manager.sync_all)

        title_toggle = "모두 숨기기" if self._all_visible else "모두 보이기"
        self.toggle_action = menu.addAction(self._fmt_sc(title_toggle, s['toggle_all_memos']))
        self.toggle_action.setIcon(self.get_theme_icon("minimize.svg", is_dark))
        self.toggle_action.triggered.connect(self.toggle_all)

        menu.addSeparator()
        act_set = menu.addAction("환경설정")
        act_set.setIcon(self.get_theme_icon("setting.svg", is_dark))
        act_set.triggered.connect(self.open_settings)

        menu.addSeparator()
        act_quit = menu.addAction("종료")
        act_quit.setIcon(self.get_theme_icon("close.svg", is_dark, override_color="#FF453A"))
        act_quit.triggered.connect(self.quit_app)

        self._tray_menu = menu
        self.tray_icon.setContextMenu(self._tray_menu)
        self.register_global_hotkeys()

    def apply_settings_to_windows(self, reload_settings_window: bool = False) -> None:
        """설정이 바뀐 뒤(환경설정 저장, 다른 기기에서 받은 공유 설정) 열려 있는 모든 창에 바로 반영합니다."""
        settings = self.sync_manager.settings
        self.update_tray_menu()                 # 트레이 메뉴의 단축키 표시와 전역 단축키 재등록

        if self.settings_window and self.settings_window.isVisible():
            if reload_settings_window:
                self.settings_window.load()     # 화면의 값이 예전 것이면 저장할 때 되돌려 버리므로 새 값으로 채움
            self.settings_window.apply_theme_style()

        explorer = self.explorer_window
        if explorer:
            explorer.apply_size_settings()
            explorer.apply_theme_style()
            explorer.update_filter_buttons()
            explorer.refresh()                  # 폴더 목록·표시 방식 포함

        rolled_h = max(36, int(settings.get('default_rolled_height', 53)))
        for w in list(self.memo_windows.values()):
            w.apply_data()
            w.rebind_shortcuts()
            if w._is_rolled_up:
                # 접힌 메모의 높이 설정이 바뀌었으면 바로 맞춥니다.
                w.memo_data['rolled_height'] = rolled_h
                w.setMinimumSize(0, 0)
                w.setMaximumSize(16777215, 16777215)
                w.resize(w.width(), rolled_h)
                w.setMinimumHeight(rolled_h)
                w.setMaximumHeight(rolled_h)
                w._apply_rolled_ui(rolled_h)

    def make_guide_memos(self) -> None:
        """사용 안내 메모(메모 창·탐색기·환경설정)를 만듭니다. 이미 있는 안내 메모는 그대로 둡니다."""
        existing = {m.get('id') for m in self.sync_manager.load_local_memos()}
        made = 0
        for memo in guide.build(datetime.datetime.now()):
            if memo["id"] not in existing:
                self.sync_manager.save_memo_locally(memo)
                made += 1
        changes: Dict[str, Any] = {"guide_memos_made": True}
        saved = list(self.sync_manager.settings.get("folders", []) or [])
        if made and guide.FOLDER not in saved:
            changes["folders"] = saved + [guide.FOLDER]
        self.sync_manager.save_settings(changes)

    def remake_guide_memos(self) -> None:
        """환경설정의 '사용 안내 메모 만들기': 안내 메모를 다시 만들어 첫 번째 안내를 엽니다."""
        self.make_guide_memos()
        self.show_specific_memo(guide.GUIDES[0][0])
        if self.explorer_window and self.explorer_window.isVisible():
            self.explorer_window.refresh()

    def _save_dialog_settings(self, changes: Dict[str, Any]) -> None:
        """대화상자 안에서 바꾼 선택을 기억합니다. 시간 표기를 바꿨으면 알림 시각을 보여 주는 곳들도 맞춥니다."""
        self.sync_manager.save_settings(changes)
        if "time_24h" in changes:
            reminders.set_ampm(not changes["time_24h"])
            for w in self.memo_windows.values():
                w.refresh_reminder_badge()
            if self.explorer_window and self.explorer_window.isVisible():
                self.explorer_window.refresh()

    # ── 빠른 검색 ────────────────────────────────────────────────────────────
    def toggle_quick_search(self) -> None:
        if self.quick_search is None:
            self.quick_search = QuickSearch(self)
        self.quick_search.toggle()

    # ── 알림 ─────────────────────────────────────────────────────────────────
    MAX_REMINDER_WAIT_MS = 60 * 60 * 1000       # PC 절전·시계 변경에 대비해 길어도 1시간마다는 다시 계산

    def schedule_reminders(self) -> None:
        """가장 가까운 알림 시각에 맞춰 타이머를 겁니다. 알림이 하나도 없으면 타이머를 끕니다."""
        due = [d for d in (reminders.due_at(r) for r in self.sync_manager.reminders.values()) if d is not None]
        if not due:
            self._reminder_timer.stop()
            return
        wait_ms = int((min(due) - datetime.datetime.now()).total_seconds() * 1000) + 300
        self._reminder_timer.start(max(0, min(wait_ms, self.MAX_REMINDER_WAIT_MS)))

    def check_reminders(self) -> None:
        """시각이 된 알림을 울립니다. (앱이 꺼져 있던 동안 지나간 알림도 여기서 한 번 울립니다)"""
        now = datetime.datetime.now()
        for memo_id, reminder in list(self.sync_manager.reminders.items()):
            due = reminders.due_at(reminder)
            if due is not None and due <= now:
                self.fire_reminder(memo_id, reminder, now)
        self.schedule_reminders()

    def _memo_for(self, memo_id: str) -> Optional[Dict[str, Any]]:
        """메모 데이터. 창이 열려 있으면 창이 들고 있는 것을 써서, 창이 나중에 예전 값으로 덮어쓰지 않게 합니다."""
        if memo_id in self.memo_windows:
            return self.memo_windows[memo_id].memo_data
        return next((m for m in self.sync_manager.load_local_memos() if m.get('id') == memo_id), None)

    def fire_reminder(self, memo_id: str, reminder: Dict[str, Any], now: datetime.datetime) -> None:
        memo = self._memo_for(memo_id)
        if memo is None:
            self.sync_manager.reminders.pop(memo_id, None)
            return
        # 반복 알림이면 다음 시각으로 넘기고, 한 번짜리면 풉니다.
        self.sync_manager.set_reminder(memo, reminders.following(reminder, now))
        if memo_id in self.memo_windows:
            self.memo_windows[memo_id].refresh_reminder_badge()

        title = str(memo.get('title', '')) or "(제목 없음)"
        # 암호 메모는 지금 열려 있더라도 알림 창에 내용을 보이지 않습니다. (암호를 풀어야 보이는 내용)
        sealed = memo.get('is_locked') or memo.get('_locked') or memo.get('_unreadable')
        detail = "🔒 암호 메모" if sealed else " ".join(clean_plain_text(memo.get('content', '')).split())[:120]
        late = (now - (reminders.due_at(reminder) or now)).total_seconds() > 120
        self._reminder_popups = [p for p in self._reminder_popups if self._still_open(p)]
        popup = ReminderPopup(self.sync_manager.settings, memo_id, title,
                              ("(지나간 알림) " if late else "") + detail,
                              self.show_specific_memo, self.snooze_reminder, slot=len(self._reminder_popups))
        self._reminder_popups.append(popup)
        popup.show()
        if self.explorer_window and self.explorer_window.isVisible():
            self.explorer_window.refresh()

    @staticmethod
    def _still_open(popup: Any) -> bool:
        try:
            return popup.isVisible()
        except RuntimeError:            # 닫혀서 이미 지워진 창
            return False

    def snooze_reminder(self, memo_id: str, minutes: int) -> None:
        """알림을 잠시 뒤로 미룹니다. 반복 알림의 원래 일정은 그대로 유지됩니다."""
        memo = self._memo_for(memo_id)
        if memo is None:
            return
        self.sync_manager.set_reminder(memo, reminders.snoozed(memo.get('reminder'), minutes, datetime.datetime.now()))
        if memo_id in self.memo_windows:
            self.memo_windows[memo_id].refresh_reminder_badge()
        if self.explorer_window and self.explorer_window.isVisible():
            self.explorer_window.refresh()

    def register_global_hotkeys(self) -> None:
        """새 메모·탐색기 열기 같은 단축키를 (재)등록합니다.

        환경설정의 '다른 프로그램을 쓰는 중에도 단축키 받기'가
          켜져 있으면: 전역 단축키로 등록합니다. 어디서나 동작하지만 그 조합은 이 앱만 받고 다른 프로그램에는 전달되지 않습니다.
          꺼져 있으면: 메모 탐색기나 메모 창이 앞에 있을 때만 동작합니다. 다른 프로그램은 그 조합을 그대로 쓸 수 있습니다.
        """
        self._hotkeys.unregister_all()
        for shortcut in getattr(self, '_app_shortcuts', []):
            shortcut.setEnabled(False)
            shortcut.deleteLater()
        self._app_shortcuts: List[QShortcut] = []

        shortcuts = {**DEFAULT_SHORTCUTS, **self.sync_manager.settings.get("shortcuts", {})}
        bindings = [
            ("new_memo",            self.create_empty_memo),
            ("new_code_memo",       self.create_code_memo),
            ("open_explorer",       self.toggle_explorer),
            ("toggle_all_memos",    self.toggle_all),
            ("arrange_rolled_memos",self.arrange_rolled_up_memos),
            ("arrange_all_memos",   self.arrange_memos),
            ("quick_search",        self.toggle_quick_search),
        ]

        if not self.sync_manager.settings.get("global_hotkeys", True):
            app = QApplication.instance()
            for shortcut_key, callback in bindings:
                sequence = shortcuts.get(shortcut_key, "")
                if not sequence:
                    continue
                shortcut = QShortcut(QKeySequence(sequence), app)
                shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)      # 이 앱의 창이 앞에 있을 때만
                shortcut.activated.connect(callback)
                self._app_shortcuts.append(shortcut)
            return

        failed = []
        for shortcut_key, callback in bindings:
            shortcut = shortcuts.get(shortcut_key, "")
            if not shortcut:
                continue
            if not self._hotkeys.register(shortcut, callback):
                failed.append(shortcut)
        if failed:
            msg = f"전역 단축키 등록 실패: {', '.join(failed)} (다른 프로그램이 사용 중이거나 지원하지 않는 조합)"
            self.sync_manager.log_error(msg)
            if hasattr(self, 'tray_icon'):
                self.tray_icon.showMessage("Memos 단축키", msg, QSystemTrayIcon.MessageIcon.Warning, 4000)

    def enforce_z_order_layering(self) -> None:
        for w in self.memo_windows.values():
            if w.isVisible() and w._is_rolled_up:
                w.raise_()

        for w in self.memo_windows.values():
            if w.isVisible() and not w._is_rolled_up:
                w.raise_()

        if self.explorer_window and self.explorer_window.isVisible():
            self.explorer_window.raise_()
            self.explorer_window.activateWindow()

    def _async_save_memos(self, memos_list: list) -> None:
        def _task():
            for w in memos_list:
                try:
                    # 창을 옮긴 것은 내용 수정이 아니므로 수정 시각은 그대로 둡니다.
                    self.sync_manager.save_memo_locally(w.memo_data)
                except Exception as e:
                    self.sync_manager.log_error(f"정렬 후 메모 저장 실패: {e}", e)
            if self.explorer_window and self.explorer_window.isVisible():
                QMetaObject.invokeMethod(self.explorer_window, "refresh", Qt.ConnectionType.QueuedConnection)
        import threading
        threading.Thread(target=_task, daemon=True).start()

    def _by_screen(self, windows: list) -> list:
        """창들을 지금 놓여 있는 모니터별로 묶습니다. → [(그 모니터의 작업 영역, [창…]), …]"""
        groups: Dict[Any, list] = {}
        for w in windows:
            screen = QApplication.screenAt(w.geometry().center()) or QApplication.primaryScreen()
            groups.setdefault(screen, []).append(w)
        return [(screen.availableGeometry(), ws) for screen, ws in groups.items()]

    @staticmethod
    def _place(w: Any, x: int, y: int) -> None:
        w.move(x, y)
        w.remember_geometry()               # 접은 메모는 접힌 자리로, 펼친 메모는 펼친 자리로 기억

    def _toast(self, text: str) -> None:
        if self.explorer_window and self.explorer_window.isVisible():
            self.explorer_window.show_toast(text)

    def arrange_rolled_up_memos(self) -> None:
        """접은 메모를 각자 놓여 있는 모니터의 아래쪽에 쌓습니다. (일반: 왼쪽, 코드: 오른쪽)"""
        rolled = [w for w in self.memo_windows.values() if w.isVisible() and w._is_rolled_up]
        if not rolled:
            self._toast("접혀 있는 메모가 없습니다.")
            return

        for screen, windows in self._by_screen(rolled):
            for is_code in (False, True):
                group = [w for w in windows if bool(w.memo_data.get('is_code_memo')) == is_code]
                for idx, w in enumerate(group):
                    col, row = idx // 12, idx % 12
                    x = screen.right() - (col + 1) * w.width() if is_code else screen.left() + col * w.width()
                    y = screen.bottom() - (row + 1) * w.height()
                    self._place(w,
                                max(screen.left(), min(x, screen.right() - w.width())),
                                max(screen.top(), min(y, screen.bottom() - w.height())))

        self._async_save_memos(rolled)
        self.enforce_z_order_layering()
        code_cnt = sum(1 for w in rolled if w.memo_data.get('is_code_memo'))
        self._toast(f"🧱 접은 메모 정렬 완료 (일반:좌하단 {len(rolled) - code_cnt}개 | 코드:우하단 {code_cnt}개)")

    def arrange_memos(self) -> None:
        """펼친 메모를 각자 놓여 있는 모니터 안에서 바둑판으로 놓습니다. (일반: 왼쪽 절반, 코드: 오른쪽 절반)"""
        opened = [w for w in self.memo_windows.values() if w.isVisible() and not w._is_rolled_up]
        if not opened:
            self._toast("⚠️ 펼쳐진 메모가 없습니다.")
            return

        for screen, windows in self._by_screen(opened):
            center_x = screen.x() + screen.width() // 2
            # (창 목록, 시작 x, 줄바꿈 기준 x)
            halves = (
                ([w for w in windows if not w.memo_data.get('is_code_memo')], screen.x() + 20, center_x - 10),
                ([w for w in windows if w.memo_data.get('is_code_memo')], center_x + 10, screen.right() - 20),
            )
            for group, start_x, limit_x in halves:
                x, y, row_h = start_x, screen.y() + 20, 0
                for w in group:
                    if x + w.width() > limit_x:
                        x, y, row_h = start_x, y + row_h + 20, 0
                    self._place(w, max(screen.left(), min(x, screen.right() - w.width() - 10)), y)
                    x += w.width() + 20
                    row_h = max(row_h, w.height())

        self._async_save_memos(opened)
        self.enforce_z_order_layering()
        code_cnt = sum(1 for w in opened if w.memo_data.get('is_code_memo'))
        self._toast(f"📐 펼친 메모 정렬 완료 (일반: {len(opened) - code_cnt}개 | 코드: {code_cnt}개)")

    def on_tray_activated(self, reason: Any = None) -> None:
        try:
            val = reason.value if hasattr(reason, 'value') else int(reason)
        except Exception:
            val = 3

        if val in (2, 3):
            if self.explorer_window and self.explorer_window.isVisible():
                self.explorer_window.request_hide()
            else:
                self.open_memo_explorer()

    def toggle_all(self) -> None:
        for w in self.memo_windows.values():
            if self._all_visible:
                w.hide()
            else:
                w.show()
        if not self._all_visible:
            self.enforce_z_order_layering()
        self.toggle_action.setText("모두 보이기" if self._all_visible else "모두 숨기기")
        self._all_visible = not self._all_visible

    def open_all_memos(self) -> None:
        """모든 메모를 저장된 위치에 켭니다."""
        memos = self.sync_manager.load_local_memos()
        for m in memos:
            if not m.get('is_deleted', False):
                memo_id = m['id']
                if memo_id in self.memo_windows:
                    w = self.memo_windows[memo_id]
                    w.memo_data['is_visible'] = True
                    w.show()
                else:
                    m['is_visible'] = True
                    self.create_new_memo(m, show_on_create=True)
        self.enforce_z_order_layering()

    def toggle_explorer(self) -> None:
        """메모 탐색기를 토글합니다. 보이면 숨기고, 숨어있으면 열어서 포커스를 줍니다."""
        if self.explorer_window and self.explorer_window.isVisible():
            self.explorer_window.request_hide()      # 환경설정에 저장하지 않은 변경이 있으면 먼저 물음
        else:
            self.open_memo_explorer()

    def open_memo_explorer(self) -> None:
        if not self.explorer_window:
            self.explorer_window = MemoExplorerWindow(self)
        self.explorer_window.setWindowState(self.explorer_window.windowState() & ~Qt.WindowState.WindowMinimized | Qt.WindowState.WindowActive)
        self.explorer_window.show()
        self.enforce_z_order_layering()
        # 탐색기를 열 때, 한동안 확인하지 않았다면 다른 기기의 변경을 받아 옵니다.
        self.sync_manager.check_remote_if_stale()

    def open_settings(self) -> None:
        """환경설정을 엽니다. 따로 창을 띄우지 않고 메모 탐색기 옆에 패널로 엽니다. (탐색기가 닫혀 있으면 함께 엶)"""
        self.open_memo_explorer()
        explorer = self.explorer_window
        explorer.open_settings_panel()          # 이미 열려 있으면 그대로 둠 (고치던 값이 사라지지 않도록)
        self.settings_window = explorer.settings_panel
        explorer.raise_()
        explorer.activateWindow()

    def toggle_settings(self) -> None:
        """환경설정이 열려 있으면 닫고, 닫혀 있으면 엽니다. (탐색기의 환경설정 버튼)"""
        explorer = self.explorer_window
        if explorer and explorer.isVisible() and explorer.settings_open():
            explorer.ask_and_close_settings_panel()
        else:
            self.open_settings()

    def quit_app(self) -> None:
        """앱을 끝냅니다. 환경설정에 저장하지 않은 변경이 있으면 먼저 묻고, 취소하면 끝내지 않습니다."""
        explorer = self.explorer_window
        if explorer and explorer.settings_open() and explorer.settings_panel.is_dirty():
            self.open_memo_explorer()                # 묻는 화면이 보이도록 탐색기를 앞으로
            if not explorer.settle_unsaved_settings():
                return
            explorer.close_settings_panel()
        QApplication.quit()

    def show_all_memos(self) -> None:
        ms = self.sync_manager.load_local_memos()
        if not ms and not self.sync_manager.settings.get("guide_memos_made"):
            # 처음 실행: 빈 메모 대신 사용 안내 메모를 만들어 둡니다. (읽고 지우면 됨)
            self.make_guide_memos()
            ms = self.sync_manager.load_local_memos()
        if not ms:
            self.create_empty_memo()
        else:
            # 숨겨 둔 메모는 창을 만들지 않고, 탐색기 등에서 열 때 만듭니다. (시작 시간·메모리 절약)
            for m in ms:
                if m.get('is_visible', True):
                    self.create_new_memo(m, show_on_create=True)
            self.enforce_z_order_layering()

    def show_specific_memo(self, identifier: str) -> None:
        self._show_specific_memo(identifier)
        # 잠긴 암호 메모는 접힌 것은 접힌 대로, 펼친 것은 펼친 대로 엽니다. 따로 암호를 묻지 않고,
        # 펼쳐진 메모라면 본문 자리의 암호 칸에 커서만 둡니다. (접힌 메모는 펼쳤을 때 그 칸이 나타남)
        w = self.memo_windows.get(identifier)
        if w and w.isVisible() and w.memo_data.get('_locked'):
            QTimer.singleShot(0, w.lock_overlay.focus_inline)

    def _show_specific_memo(self, identifier: str) -> None:
        target_win = None
        if identifier in self.memo_windows:
            target_win = self.memo_windows[identifier]
        else:
            # identifier가 id 형식(UUID 또는 숫자)이 아닐 때만 title로 탐색
            # UUID 포맷(하이픈 포함) 또는 순수 숫자면 id 탐색에만 한정
            looks_like_id = (
                len(identifier) > 10 and '-' in identifier  # UUID 패턴
            ) or identifier.isdigit()  # 숫자 id 패턴
            if not looks_like_id:
                for w in self.memo_windows.values():
                    if w.memo_data.get('title') == identifier:
                        target_win = w
                        break

        if target_win:
            target_win.memo_data['is_visible'] = True
            self.notify_save(target_win.memo_data)
            target_win.show()
            target_win.raise_()
            target_win.activateWindow()
            # 가시적 하이라이트: 메모 테두리를 일시적으로 강조
            self._flash_memo_window(target_win)
        else:
            for m in self.sync_manager.load_local_memos():
                if m.get('id') == identifier or (not identifier.replace('-','').isalnum() and m.get('title') == identifier):
                    m['is_visible'] = True
                    self.sync_manager.save_memo_locally(m)
                    self.create_new_memo(m, show_on_create=True)
                    break


    def create_empty_memo(self) -> None:
        self._create_blank_memo(is_code=False)

    def create_code_memo(self) -> None:
        self._create_blank_memo(is_code=True)
        if self.explorer_window and self.explorer_window.isVisible():
            self.explorer_window.refresh()

    def _unused_title(self, base_title: str) -> str:
        """'새 메모', '새 메모 2' … 중 아직 쓰이지 않은 제목. (창이 닫혀 있는 메모의 제목도 피함)"""
        taken = {w.memo_data.get('title', '') for w in self.memo_windows.values()}
        taken.update(m.get('title', '') for m in self.sync_manager.load_local_memos())
        title, idx = base_title, 1
        while title in taken:
            idx += 1
            title = f"{base_title} {idx}"
        return title

    def _create_blank_memo(self, is_code: bool) -> None:
        cfg = self.sync_manager.settings
        step = self._cascade_count % 12
        self._cascade_count += 1
        origin = 80 if is_code else 60

        memo_data = {
            'id': str(uuid.uuid4()),
            'title': self._unused_title("코드 메모" if is_code else "새 메모"),
            'content': '',
            'font_size': 11,
            'opacity': float(cfg.get('default_memo_opacity', 1.0)),
            'is_pinned': cfg.get('default_is_pinned', False),
            'is_visible': True,
            'is_code_memo': is_code,
            'position_x': origin + step * 35,
            'position_y': origin + step * 35,
            'is_draft': True,
            'is_manually_saved': False,
            'updated_at': datetime.datetime.now().isoformat(),
        }
        if is_code:
            code_theme = cfg.get('default_code_theme', 'dark')
            memo_data.update({
                'bg_color': '#2E3440' if code_theme == 'dark' else '#FFFFFF',
                'font_family': cfg.get('default_code_font_family', 'D2Coding'),
                'code_lang': cfg.get('default_code_lang', 'JSON'),
                'code_theme': code_theme,
                'width': cfg.get('default_code_memo_width', cfg.get('default_memo_width', 350) * 2),
                'height': cfg.get('default_code_memo_height', cfg.get('default_memo_height', 380)),
                'show_line_numbers': cfg.get('default_code_line_numbers', True),
                'show_line_bg': cfg.get('default_code_line_bg', False),
            })
        else:
            color = cfg.get('default_memo_color', '#FFFFFF')
            if color == "random":
                color = random.choice(["#E0F2FE", "#DCFCE7", "#FEF9C3", "#FCE7F3", "#FFFFFF"])
            memo_data.update({
                'bg_color': color,
                'font_family': cfg.get('default_font_family', 'D2Coding'),
                'width': cfg.get('default_memo_width', 350),
                'height': cfg.get('default_memo_height', 380),
                'show_line_numbers': cfg.get('default_gen_line_numbers', cfg.get('default_show_line_numbers', False)),
                'show_line_bg': cfg.get('default_gen_line_bg', cfg.get('default_show_line_bg', False)),
            })
        # 탐색기에서 폴더를 골라 둔 상태라면 새 메모도 그 폴더에 넣습니다.
        ex = self.explorer_window
        if ex and ex.current_folder not in (folders.ALL, folders.UNFILED):
            memo_data['folder'] = ex.current_folder
        self.create_new_memo(memo_data, show_on_create=True)

    def resolve_memo_overlap(self, memo_win: 'MemoWindow') -> None:
        """메모 익스플로러나 로드 시 다른 메모와 좌표 겹침이 있으면 계단식 오프셋을 부여합니다."""
        rect = memo_win.geometry()
        screen = (QApplication.screenAt(rect.center()) or QApplication.primaryScreen()).availableGeometry()

        offset_step = 35
        max_attempts = 15
        attempt = 0

        current_x = rect.x()
        current_y = rect.y()

        while attempt < max_attempts:
            has_overlap = False
            for other_id, other_win in self.memo_windows.items():
                if other_win is memo_win or not other_win.isVisible():
                    continue

                if abs(other_win.x() - current_x) < 15 and abs(other_win.y() - current_y) < 15:
                    has_overlap = True
                    break

            if not has_overlap:
                break

            current_x += offset_step
            current_y += offset_step

            if current_x + rect.width() > screen.right() - 20:
                current_x = screen.left() + 40
            if current_y + rect.height() > screen.bottom() - 20:
                current_y = screen.top() + 40

            attempt += 1

        if current_x != rect.x() or current_y != rect.y():
            memo_win.move(current_x, current_y)
            memo_win.memo_data.update({'position_x': current_x, 'position_y': current_y})
            memo_win.save_callback(memo_win.memo_data)

    def create_new_memo(self, m: Dict[str, Any], show_on_create: bool = False) -> None:
        memo_id = m.get('id')
        if not memo_id:
            memo_id = str(uuid.uuid4())
            m['id'] = memo_id

        if memo_id in self.memo_windows:
            w = self.memo_windows[memo_id]
            w.memo_data = m
            w.apply_data()
            if show_on_create:
                self.resolve_memo_overlap(w)
                w.show()
                w.raise_()
        else:
            w = MemoWindow(m, self.notify_save, self.delete_memo, self.sync_manager.rename_memo_locally, self.on_close)
            self.memo_windows[memo_id] = w
            if show_on_create:
                self.resolve_memo_overlap(w)
                w.show()

    def close_memo_window_by_id(self, memo_id: str, is_deleting: bool = False) -> None:
        if memo_id in self.memo_windows:
            w = self.memo_windows.pop(memo_id)
            if is_deleting:
                w._is_deleting = True
            w.close()

    def reload_pulled_memos(self, memo_ids: List[str]) -> None:
        """동기화로 디스크 내용이 바뀐 메모 중 열려 있는 창을 새 내용으로 갱신합니다."""
        open_ids = [i for i in memo_ids if i in self.memo_windows]
        if not open_ids:
            return
        fresh = {m.get('id'): m for m in self.sync_manager.load_local_memos()}
        for memo_id in open_ids:
            w = self.memo_windows[memo_id]
            m = fresh.get(memo_id)
            # 입력 중(자동저장 대기)인 창은 건드리지 않습니다. 곧 저장되는 사용자 입력이 우선합니다.
            if not m or w._auto_save_timer.isActive():
                continue
            m['is_visible'] = w.memo_data.get('is_visible', m.get('is_visible', True))
            w.memo_data = m
            w.apply_data()

    def notify_save(self, m: Dict[str, Any]) -> None:
        self.sync_manager.save_memo_locally(m)
        if self.explorer_window and self.explorer_window.isVisible():
            self.explorer_window.refresh()

    def on_close(self, w: MemoWindow) -> None:
        memo_id = w.memo_data.get('id')
        if memo_id and memo_id in self.memo_windows:
            self.memo_windows.pop(memo_id)

    def _flash_memo_window(self, target_win: 'MemoWindow') -> None:
        """탐색기 더블클릭 시 해당 메모창을 가시적으로 강조합니다.

        연속 클릭 시 플래시가 중첩되지 않도록 플래그를 사용하며,
        original_style을 호출 시점에 고정하여 클로저 캡처 문제를 방지합니다.
        """
        try:
            # 이미 플래시 진행 중이면 무시 (중복 클릭 방지)
            if getattr(target_win, '_is_flashing', False):
                return
            target_win._is_flashing = True

            # 원본 스타일을 호출 시점에 스냅샷
            original_style = target_win.bg.styleSheet()
            flash_style = original_style + " QWidget#MemoBackground { border: 3px solid #007AFF; }"

            def _apply_flash():
                if target_win.isVisible():
                    target_win.bg.setStyleSheet(flash_style)

            def _restore(is_final=False):
                if target_win.isVisible():
                    target_win.bg.setStyleSheet(original_style)
                if is_final:
                    target_win._is_flashing = False

            _apply_flash()
            QTimer.singleShot(300, _restore)
            QTimer.singleShot(550, _apply_flash)
            QTimer.singleShot(850, lambda: _restore(is_final=True))
        except Exception:
            if hasattr(target_win, '_is_flashing'):
                target_win._is_flashing = False



    def delete_memo(self, w: MemoWindow) -> None:

        memo_id = w.memo_data.get('id', '')
        title = w.memo_data.get('title', '')
        w._is_deleting = True
        if memo_id and memo_id in self.memo_windows:
            self.memo_windows.pop(memo_id)
        w.close()
        if memo_id:
            self.sync_manager.delete_memo_locally(memo_id, title=title)
            self.sync_manager.delete_memos_cloud([memo_id])
        if self.explorer_window and self.explorer_window.isVisible():
            self.explorer_window.refresh()