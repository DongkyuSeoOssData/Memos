from PyQt6.QtCore import QMetaObject, QObject, pyqtSlot

from ui.memo_window import MemoWindow
from ui.memo_explorer import MemoExplorerWindow
from ui.settings_window import SettingsWindow
from ui.dialogs import PasswordSetupDialog, PasswordLoginDialog, OTPRescueDialog, ConflictDialog
import sys
import re
import random
import datetime
import math
import uuid
import json
from pathlib import Path
from typing import List, Dict, Any, Optional, Union
from PyQt6.QtWidgets import (
    QWidget, QTextEdit, QVBoxLayout, QHBoxLayout, QGridLayout, QPushButton, 
    QLineEdit, QMenu, QSystemTrayIcon, QApplication, QMessageBox, 
    QLabel, QComboBox, QCheckBox, QFileDialog, QTableWidget, 
    QTableWidgetItem, QHeaderView, QDialog, QDialogButtonBox,
    QGraphicsDropShadowEffect, QFrame, QSizeGrip, QFontComboBox,
    QColorDialog, QTabWidget, QKeySequenceEdit, QGroupBox, QFormLayout,
    QScrollArea, QSlider, QSpinBox, QWidgetAction
)
from PyQt6.QtCore import Qt, QPoint, QSize, QTimer, QEvent, QRect, QByteArray
from PyQt6.QtGui import (
    QIcon, QAction, QColor, QShortcut, QKeySequence, QFont, QFontDatabase,
    QPixmap, QPainter, QTextListFormat, QTextCursor, QTextCharFormat, QPalette, QTextDocument,
    QSyntaxHighlighter, QCursor
)
from PyQt6.QtSvg import QSvgRenderer
import os
import threading
from utils.text_utils import convert_eng_kor_smart
from utils.text_utils import clean_plain_text

try:
    import keyboard
except Exception:
    # 외부 패키지 필요: pip install keyboard
    keyboard = None

PASTEL_COLORS = ["#E0F2FE", "#DCFCE7", "#FEF9C3", "#FCE7F3", "#FFFFFF"]

from ui.themes import LIGHT_THEMES, DARK_THEMES


class _GlobalHotkeyDispatcher(QObject):
    def __init__(self, ui_manager: 'UIManager') -> None:
        super().__init__()
        self.ui_manager = ui_manager

    @pyqtSlot()
    def trigger_create_empty_memo(self) -> None:
        self.ui_manager.create_empty_memo()

    @pyqtSlot()
    def trigger_create_code_memo(self) -> None:
        self.ui_manager.create_code_memo()

    @pyqtSlot()
    def trigger_open_memo_explorer(self) -> None:
        self.ui_manager.open_memo_explorer()

    @pyqtSlot()
    def trigger_toggle_explorer(self) -> None:
        """탐색기 창을 토글합니다 (켜기/숨기기)."""
        self.ui_manager.toggle_explorer()

    @pyqtSlot()
    def trigger_toggle_all(self) -> None:
        self.ui_manager.toggle_all()

    @pyqtSlot()
    def trigger_arrange_rolled_memos(self) -> None:
        self.ui_manager.arrange_rolled_up_memos()

    @pyqtSlot()
    def trigger_arrange_all_memos(self) -> None:
        self.ui_manager.arrange_memos()


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
        self._global_hotkey_handles: List[Any] = []
        self._hotkey_dispatcher = _GlobalHotkeyDispatcher(self)
        self.sync_manager.set_ui_manager(self)
        self.setup_tray()
    
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
        
        s = self.sync_manager.settings.get("shortcuts", {})
        
        act_new = menu.addAction(self._fmt_sc("새 메모", s.get('new_memo', 'Ctrl+N')))
        act_new.setIcon(self.get_theme_icon("memo.svg", is_dark))
        act_new.triggered.connect(self.create_empty_memo)

        act_code = menu.addAction(self._fmt_sc("새 코드 메모", s.get('new_code_memo', 'Ctrl+Shift+N')))
        act_code.setIcon(self.get_theme_icon("codememo.svg", is_dark))
        act_code.triggered.connect(self.create_code_memo)

        act_arr_r = menu.addAction(self._fmt_sc("접은 메모 정렬", s.get('arrange_rolled_memos', 'Ctrl+Alt+R')))
        act_arr_r.setIcon(self.get_theme_icon("정렬1.svg", is_dark))
        act_arr_r.triggered.connect(self.arrange_rolled_up_memos)

        act_exp = menu.addAction(self._fmt_sc("메모 탐색기", s.get('open_explorer', 'Ctrl+E')))
        act_exp.setIcon(self.get_theme_icon("memo.svg", is_dark))
        act_exp.triggered.connect(self.open_memo_explorer)

        act_arr_a = menu.addAction(self._fmt_sc("펼친 메모 정렬", s.get('arrange_all_memos', 'Ctrl+Alt+A')))
        act_arr_a.setIcon(self.get_theme_icon("정렬2.svg", is_dark))
        act_arr_a.triggered.connect(self.arrange_memos)

        act_sync = menu.addAction("지금 동기화")
        act_sync.setIcon(self.get_theme_icon("cloude.svg", is_dark))
        act_sync.triggered.connect(self.sync_manager.sync_push)
        
        title_toggle = "모두 숨기기" if self._all_visible else "모두 보이기"
        self.toggle_action = menu.addAction(self._fmt_sc(title_toggle, s.get('toggle_all_memos', 'Ctrl+Shift+H')))
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

    def _normalize_keyboard_hotkey(self, shortcut: str) -> str:
        normalized = shortcut.strip().replace(" ", "")
        replacements = {
            "Ctrl": "ctrl",
            "Shift": "shift",
            "Alt": "alt",
            "Win": "windows",
            "Meta": "windows",
        }
        for old, new in replacements.items():
            normalized = normalized.replace(old, new)
            normalized = normalized.replace(old.lower(), new)
        return normalized.lower()

    def _invoke_hotkey(self, method_name: str) -> None:
        QMetaObject.invokeMethod(self._hotkey_dispatcher, method_name, Qt.ConnectionType.QueuedConnection)

    def _clear_global_hotkeys(self) -> None:
        if keyboard is None:
            return
        while self._global_hotkey_handles:
            handle = self._global_hotkey_handles.pop()
            try:
                keyboard.remove_hotkey(handle)
            except Exception:
                pass

    def register_global_hotkeys(self) -> None:
        self._clear_global_hotkeys()
        if keyboard is None:
            return

        shortcuts = self.sync_manager.settings.get("shortcuts", {})
        bindings = [
            ("new_memo",            "trigger_create_empty_memo"),
            ("new_code_memo",       "trigger_create_code_memo"),
            ("open_explorer",       "trigger_toggle_explorer"),
            ("toggle_all_memos",    "trigger_toggle_all"),
            ("arrange_rolled_memos","trigger_arrange_rolled_memos"),
            ("arrange_all_memos",   "trigger_arrange_all_memos"),
        ]

        for shortcut_key, method_name in bindings:
            shortcut = shortcuts.get(shortcut_key, "")
            if not shortcut:
                continue
            key_combo = self._normalize_keyboard_hotkey(shortcut)
            try:
                handle = keyboard.add_hotkey(key_combo, lambda name=method_name: self._invoke_hotkey(name), suppress=False)
                self._global_hotkey_handles.append(handle)
            except Exception as exc:
                self.sync_manager.log_error(f"글로벌 단축키 등록 실패 ({shortcut_key}: {key_combo}): {exc}", exc)

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
                    w.memo_data['updated_at'] = datetime.now().isoformat()
                    self.sync_manager.save_memo_locally(w.memo_data)
                except Exception:
                    pass
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
        if not self.ensure_unlocked():
            return
        if not self.explorer_window:
            self.explorer_window = MemoExplorerWindow(self)
        self.explorer_window.setWindowState(self.explorer_window.windowState() & ~Qt.WindowState.WindowMinimized | Qt.WindowState.WindowActive)
        self.explorer_window.show()
        self.enforce_z_order_layering()

    def open_settings(self) -> None:
        self.settings_window = SettingsWindow(self.sync_manager)
        self.settings_window.show()

    def ensure_unlocked(self) -> bool:
        if not self.sync_manager.has_vault():
            dlg = PasswordSetupDialog()
            if dlg.exec() == QDialog.DialogCode.Accepted:
                ok = self.sync_manager.create_vault(dlg.password)
                if ok:
                    self.sync_manager.save_remembered_password(dlg.password, dlg.remember)
                return ok
            else:
                return False
                
        if self.sync_manager.is_unlocked():
            return True
            
        if self.sync_manager.try_auto_login():
            return True

        dlg = PasswordLoginDialog(self.sync_manager)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            return True
        else:
            return False
        
    def show_all_memos(self) -> None:
        if not self.ensure_unlocked():
            QMessageBox.warning(None, "잠금 해제 실패", "비밀번호 인증이 완료되지 않아 메모를 로드할 수 없습니다.")
            return

        ms = self.sync_manager.load_local_memos()
        if not ms:
            self.create_empty_memo()
        else:
            for m in ms:
                self.create_new_memo(m, show_on_create=m.get('is_visible', True))
            self.enforce_z_order_layering()
                
    def show_specific_memo(self, identifier: str) -> None:
        if not self.ensure_unlocked(): return
        target_win = None
        if identifier in self.memo_windows:
            target_win = self.memo_windows[identifier]
        else:
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
        else:
            for m in self.sync_manager.load_local_memos():
                if m.get('id') == identifier or m.get('title') == identifier: 
                    m['is_visible'] = True
                    self.sync_manager.save_memo_locally(m)
                    self.create_new_memo(m, show_on_create=True)
                    break
                    
    def create_empty_memo(self) -> None:
        if not self.ensure_unlocked(): return
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
        if not self.ensure_unlocked(): return
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

    def notify_save(self, m: Dict[str, Any]) -> None: 
        self.sync_manager.save_memo_locally(m)
        if self.explorer_window and self.explorer_window.isVisible():
            self.explorer_window.refresh()
            
    def on_close(self, w: MemoWindow) -> None:
        memo_id = w.memo_data.get('id')
        if memo_id and memo_id in self.memo_windows:
            self.memo_windows.pop(memo_id)

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