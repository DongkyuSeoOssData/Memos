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
from PyQt6.QtGui import QIcon, QPixmap, QPainter
from PyQt6.QtSvg import QSvgRenderer
import threading

PASTEL_COLORS = ["#E0F2FE", "#DCFCE7", "#FEF9C3", "#FCE7F3", "#FFFFFF"]

from ui.themes import app_palette
from ui import modern_style
from core.defaults import DEFAULT_SHORTCUTS


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
        act_quit.triggered.connect(QApplication.quit)

        self._tray_menu = menu
        self.tray_icon.setContextMenu(self._tray_menu)
        self.register_global_hotkeys()

    def register_global_hotkeys(self) -> None:
        """전역 단축키를 (재)등록합니다. 등록된 조합은 이 앱만 받고 다른 프로그램에는 전달되지 않습니다."""
        self._hotkeys.unregister_all()

        shortcuts = {**DEFAULT_SHORTCUTS, **self.sync_manager.settings.get("shortcuts", {})}
        bindings = [
            ("new_memo",            self.create_empty_memo),
            ("new_code_memo",       self.create_code_memo),
            ("open_explorer",       self.toggle_explorer),
            ("toggle_all_memos",    self.toggle_all),
            ("arrange_rolled_memos",self.arrange_rolled_up_memos),
            ("arrange_all_memos",   self.arrange_memos),
        ]

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
        w.memo_data.update({'position_x': x, 'position_y': y})

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
                self.explorer_window.hide()
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
            self.explorer_window.hide()
        else:
            self.open_memo_explorer()

    def open_memo_explorer(self) -> None:
        if not self.explorer_window:
            self.explorer_window = MemoExplorerWindow(self)
        self.explorer_window.setWindowState(self.explorer_window.windowState() & ~Qt.WindowState.WindowMinimized | Qt.WindowState.WindowActive)
        self.explorer_window.show()
        self.enforce_z_order_layering()

    def open_settings(self) -> None:
        if self.settings_window and self.settings_window.isVisible():
            # 이미 열려 있으면 새로 만들지 않습니다. (고치던 값이 사라지지 않도록)
            self.settings_window.setWindowState(self.settings_window.windowState() & ~Qt.WindowState.WindowMinimized)
            self.settings_window.raise_()
            self.settings_window.activateWindow()
            return
        self.settings_window = SettingsWindow(self.sync_manager)
        self.settings_window.show()

    def show_all_memos(self) -> None:
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
        # 잠긴 암호 메모를 열었으면 바로 암호를 묻습니다.
        w = self.memo_windows.get(identifier)
        if w and w.isVisible() and w.memo_data.get('_locked'):
            QTimer.singleShot(0, w.prompt_unlock)

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