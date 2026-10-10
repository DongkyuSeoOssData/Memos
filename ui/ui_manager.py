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
from PyQt6.QtWidgets import QWidget, QMenu, QSystemTrayIcon, QApplication
from PyQt6.QtCore import Qt, QTimer, QByteArray
from PyQt6.QtGui import QIcon, QPixmap, QPainter
from PyQt6.QtSvg import QSvgRenderer
import threading

PASTEL_COLORS = ["#E0F2FE", "#DCFCE7", "#FEF9C3", "#FCE7F3", "#FFFFFF"]

from ui.themes import LIGHT_THEMES, DARK_THEMES
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
            
        svg_path = base_dir / "icons" / svg_name
        if not svg_path.exists():
            svg_path = Path("icons") / svg_name
        if not svg_path.exists():
            return QIcon()
        try:
            with open(svg_path, "r", encoding="utf-8") as f:
                svg_data = f.read()
            if override_color:
                target_color = override_color
            else:
                if is_dark is None:
                    theme = self.sync_manager.settings.get("app_theme", "white")
                    is_dark = (theme == "dark")
                if is_dark:
                    mode = self.sync_manager.settings.get("dark_theme_mode", "dark")
                    target_color = DARK_THEMES.get(mode, DARK_THEMES["dark"])["icon"]
                    if svg_name in ["rollup.svg", "maximize.svg"]:
                        target_color = "#FFFFFF"
                else:
                    mode = self.sync_manager.settings.get("light_theme_mode", "white")
                    target_color = LIGHT_THEMES.get(mode, LIGHT_THEMES["white"])["icon"]
            
            svg_data = re.sub(r'stroke="[^"]+"', f'stroke="{target_color}"', svg_data)
            if re.search(r'fill="#[0-9a-fA-F]{3,6}"', svg_data):
                svg_data = re.sub(r'fill="#[0-9a-fA-F]{3,6}"', f'fill="{target_color}"', svg_data)
            elif "stroke=" not in svg_data:
                svg_data = re.sub(r'<path(?![^>]*(?:stroke="none"|fill="none"))', f'<path fill="{target_color}" ', svg_data)
                
            renderer = QSvgRenderer(QByteArray(svg_data.encode('utf-8')))
            pixmap = QPixmap(24, 24)
            pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            renderer.render(painter)
            painter.end()
            return QIcon(pixmap)
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
        if is_dark:
            mode = self.sync_manager.settings.get("dark_theme_mode", "dark")
            pal = DARK_THEMES.get(mode, DARK_THEMES["dark"])
        else:
            mode = self.sync_manager.settings.get("light_theme_mode", "white")
            pal = LIGHT_THEMES.get(mode, LIGHT_THEMES["white"])

        menu.setStyleSheet(f"QMenu {{ background: {pal['card']}; color: {pal['text']}; border: 1px solid {pal['border']}; border-radius: 10px; padding: 4px; }} QMenu::item:selected {{ background-color: {pal['accent']}; color: white; border-radius: 6px; }}")
        
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
                    w.memo_data['updated_at'] = datetime.datetime.now().isoformat()
                    self.sync_manager.save_memo_locally(w.memo_data)
                except Exception as e:
                    self.sync_manager.log_error(f"정렬 후 메모 저장 실패: {e}", e)
            if self.explorer_window and self.explorer_window.isVisible():
                QMetaObject.invokeMethod(self.explorer_window, "refresh", Qt.ConnectionType.QueuedConnection)
        import threading
        threading.Thread(target=_task, daemon=True).start()

    def arrange_rolled_up_memos(self) -> None:
        screen = QApplication.primaryScreen().availableGeometry()
        rolled_gen = [w for w in self.memo_windows.values() if w.isVisible() and w._is_rolled_up and not w.memo_data.get('is_code_memo')]
        rolled_code = [w for w in self.memo_windows.values() if w.isVisible() and w._is_rolled_up and w.memo_data.get('is_code_memo')]
        
        if not rolled_gen and not rolled_code:
            if self.explorer_window and self.explorer_window.isVisible():
                self.explorer_window.show_toast("접혀 있는 메모가 없습니다.")
            return

        left_base_x = screen.left()
        right_base_x = screen.right()

        for idx, w in enumerate(rolled_gen):
            w_h = w.height()
            w_w = w.width()
            col = idx // 12
            row = idx % 12
            target_x = left_base_x + (col * w_w)
            target_y = screen.bottom() - ((row + 1) * w_h)
            target_x = max(screen.left(), min(target_x, screen.right() - w_w))
            target_y = max(screen.top(), min(target_y, screen.bottom() - w_h))
            w.move(target_x, target_y)
            w.memo_data.update({'position_x': target_x, 'position_y': target_y})

        for idx, w in enumerate(rolled_code):
            w_h = w.height()
            w_w = w.width()
            col = idx // 12
            row = idx % 12
            target_x = right_base_x - ((col + 1) * w_w)
            target_y = screen.bottom() - ((row + 1) * w_h)
            target_x = max(screen.left(), min(target_x, screen.right() - w_w))
            target_y = max(screen.top(), min(target_y, screen.bottom() - w_h))
            w.move(target_x, target_y)
            w.memo_data.update({'position_x': target_x, 'position_y': target_y})
            
        self._async_save_memos(rolled_gen + rolled_code)
        self.enforce_z_order_layering()
        if self.explorer_window and self.explorer_window.isVisible():
            self.explorer_window.show_toast(f"🧱 접은 메모 정렬 완료 (일반:좌하단 {len(rolled_gen)}개 | 코드:우하단 {len(rolled_code)}개)")

    def arrange_memos(self) -> None:
        screen = QApplication.primaryScreen().availableGeometry()
        center_x = screen.x() + (screen.width() // 2)
        
        gen_memos = [w for w in self.memo_windows.values() if w.isVisible() and not w._is_rolled_up and not w.memo_data.get('is_code_memo')]
        code_memos = [w for w in self.memo_windows.values() if w.isVisible() and not w._is_rolled_up and w.memo_data.get('is_code_memo')]

        if not gen_memos and not code_memos:
            if self.explorer_window and self.explorer_window.isVisible():
                self.explorer_window.show_toast("⚠️ 펼쳐진 메모가 없습니다.")
            return

        gx, gy = screen.x() + 20, screen.y() + 20
        g_max_h = 0
        for idx, w in enumerate(gen_memos):
            w_width = w.width()
            w_height = w.height()
            if gx + w_width > center_x - 10:
                gx = screen.x() + 20
                gy += g_max_h + 20
                g_max_h = 0
            target_x = max(screen.left(), min(gx, screen.right() - w_width - 10))
            w.move(target_x, gy)
            w.memo_data.update({'position_x': target_x, 'position_y': gy})
            gx += w_width + 20
            g_max_h = max(g_max_h, w_height)

        cx, cy = center_x + 10, screen.y() + 20
        c_max_h = 0
        for idx, w in enumerate(code_memos):
            w_width = w.width()
            w_height = w.height()
            if cx + w_width > screen.right() - 20:
                cx = center_x + 10
                cy += c_max_h + 20
                c_max_h = 0
            target_x = max(screen.left(), min(cx, screen.right() - w_width - 10))
            w.move(target_x, cy)
            w.memo_data.update({'position_x': target_x, 'position_y': cy})
            cx += w_width + 20
            c_max_h = max(c_max_h, w_height)

        self._async_save_memos(gen_memos + code_memos)
        self.enforce_z_order_layering()
        if self.explorer_window and self.explorer_window.isVisible():
            self.explorer_window.show_toast(f"📐 펼친 메모 정렬 완료 (일반: {len(gen_memos)}개 | 코드: {len(code_memos)}개)")

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
        self.settings_window = SettingsWindow(self.sync_manager)
        self.settings_window.show()

    def show_all_memos(self) -> None:
        ms = self.sync_manager.load_local_memos()
        if not ms:
            self.create_empty_memo()
        else:
            for m in ms:
                self.create_new_memo(m, show_on_create=m.get('is_visible', True))
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
        memo_id = str(uuid.uuid4())
        
        cfg = getattr(self.sync_manager, 'settings', {})
        default_ln = cfg.get('default_gen_line_numbers', cfg.get('default_show_line_numbers', False))
        default_bg = cfg.get('default_gen_line_bg', cfg.get('default_show_line_bg', False))
        default_font = cfg.get('default_font_family', 'D2Coding')
        default_pin = cfg.get('default_is_pinned', False)
        default_opacity = float(cfg.get('default_memo_opacity', 1.0))
        
        existing_titles = [w.memo_data.get('title', '') for w in self.memo_windows.values()]
        
        base_title = "새 메모"
        title = base_title
        idx = 1
        while title in existing_titles:
            idx += 1
            title = f"{base_title} {idx}"
            
        step = (self._cascade_count % 12)
        pos_x = 60 + (step * 35)
        pos_y = 60 + (step * 35)
        self._cascade_count += 1
        
        default_color = cfg.get('default_memo_color', '#FFFFFF')
        if default_color == "random":
            default_color = random.choice(["#E0F2FE", "#DCFCE7", "#FEF9C3", "#FCE7F3", "#FFFFFF"])

        default_w = cfg.get('default_memo_width', 350)
        default_h = cfg.get('default_memo_height', 380)

        memo_data = {
            'id': memo_id,
            'title': title,
            'content': '',
            'bg_color': default_color,
            'font_size': 11,
            'font_family': default_font,
            'opacity': default_opacity,
            'is_pinned': default_pin,
            'is_visible': True,
            'is_code_memo': False,
            'position_x': pos_x,
            'position_y': pos_y,
            'width': default_w,
            'height': default_h,
            'show_line_numbers': default_ln,
            'show_line_bg': default_bg,
            'is_draft': True,
            'is_manually_saved': False,
            'updated_at': datetime.datetime.now().isoformat()
        }
        
        self.create_new_memo(memo_data, show_on_create=True)

    def create_code_memo(self) -> None:
        memo_id = str(uuid.uuid4())
        cfg = getattr(self.sync_manager, 'settings', {})
        default_code_lang = cfg.get('default_code_lang', 'JSON')
        default_code_font = cfg.get('default_code_font_family', 'D2Coding')
        default_code_theme = cfg.get('default_code_theme', 'dark')
        
        default_code_ln = cfg.get('default_code_line_numbers', True)
        default_code_bg = cfg.get('default_code_line_bg', False)
        default_opacity = float(cfg.get('default_memo_opacity', 1.0))
        
        default_w = cfg.get('default_code_memo_width', cfg.get('default_memo_width', 350) * 2)
        default_h = cfg.get('default_code_memo_height', cfg.get('default_memo_height', 380))
        
        existing_titles = [w.memo_data.get('title', '') for w in self.memo_windows.values()]
        
        base_title = "코드 메모"
        title = base_title
        idx = 1
        while title in existing_titles:
            idx += 1
            title = f"{base_title} {idx}"
            
        step = (self._cascade_count % 12)
        pos_x = 80 + (step * 35)
        pos_y = 80 + (step * 35)
        self._cascade_count += 1
        
        memo_data = {
            'id': memo_id,
            'title': title,
            'content': '',
            'bg_color': '#2E3440' if default_code_theme == 'dark' else '#FFFFFF',
            'font_size': 11,
            'font_family': default_code_font,
            'opacity': default_opacity,
            'is_pinned': cfg.get('default_is_pinned', False),
            'is_visible': True,
            'is_code_memo': True,
            'code_lang': default_code_lang,
            'code_theme': default_code_theme,
            'position_x': pos_x,
            'position_y': pos_y,
            'width': default_w,
            'height': default_h,
            'show_line_numbers': default_code_ln,
            'show_line_bg': default_code_bg,
            'is_draft': True,
            'is_manually_saved': False,
            'updated_at': datetime.datetime.now().isoformat()
        }
        
        self.create_new_memo(memo_data, show_on_create=True)
        if self.explorer_window and self.explorer_window.isVisible():
            self.explorer_window.refresh()
        
    def resolve_memo_overlap(self, memo_win: 'MemoWindow') -> None:
        """메모 익스플로러나 로드 시 다른 메모와 좌표 겹침이 있으면 계단식 오프셋을 부여합니다."""
        screen = QApplication.primaryScreen().availableGeometry()
        rect = memo_win.geometry()
        
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

    def close_memo_window(self, identifier: str) -> None:
        if identifier in self.memo_windows:
            self.memo_windows[identifier].close()
        else:
            for w in list(self.memo_windows.values()):
                if w.memo_data.get('title') == identifier:
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