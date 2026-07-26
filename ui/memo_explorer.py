from ui.dialogs import ConflictDialog
from ui.ui_utils import apply_ios_shadow
from ui.themes import LIGHT_THEMES, DARK_THEMES
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
from core.sync_manager import convert_eng_kor_smart
from utils.text_utils import clean_plain_text

class MemoExplorerWindow(QWidget):
    """
    iOS 울트라 미니멀 화이트 & 블랙 탐색기:
    - 윈도우 우측 창 제어 버튼 (─, □/❐, ✕) & 100% 정상 작동하는 최대화/복원
    - 실시간 라이트 / 다크 모드 전환 지원
    """
    def __init__(self, ui_manager: Any) -> None:
        super().__init__()
        self.ui_manager = ui_manager
        self.current_page: int = 1
        self.items_per_page: int = 10
        self.filtered_memos: List[Dict[str, Any]] = []
        self.filter_mode: str = "ALL"
        self.is_trash_mode: bool = False
        self._old_pos: Optional[QPoint] = None
        self._is_loading_preview: bool = False
        self.init_ui()
        self.apply_theme_style()
        self.bind_global_shortcuts()

    def bind_global_shortcuts(self) -> None:
        s_cfg = self.ui_manager.sync_manager.settings.get("shortcuts", {})
        QShortcut(QKeySequence(s_cfg.get("new_memo", "Ctrl+N")), self).activated.connect(self.ui_manager.create_empty_memo)
        QShortcut(QKeySequence(s_cfg.get("new_code_memo", "Ctrl+Shift+N")), self).activated.connect(self.ui_manager.create_code_memo)
        QShortcut(QKeySequence(s_cfg.get("arrange_rolled_memos", "Ctrl+Alt+R")), self).activated.connect(self.ui_manager.arrange_rolled_up_memos)
        QShortcut(QKeySequence(s_cfg.get("arrange_all_memos", "Ctrl+Alt+A")), self).activated.connect(self.ui_manager.arrange_memos)
        QShortcut(QKeySequence("Esc"), self).activated.connect(self.close)

    def keyPressEvent(self, e: Any) -> None:
        if e.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.del_checked()
            e.accept()
            return
        super().keyPressEvent(e)

    def init_ui(self) -> None:
        self.setWindowTitle("Memos Explorer")
        geom = self.ui_manager.sync_manager.settings.get('explorer_geom')
        if geom and len(geom) == 4:
            self.setGeometry(geom[0], geom[1], geom[2], geom[3])
        else:
            self.resize(1060, 860)
            
        self.is_pinned = self.ui_manager.sync_manager.settings.get('explorer_is_pinned', True)
        f = Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowSystemMenuHint | Qt.WindowType.WindowMinimizeButtonHint
        if self.is_pinned:
            f = f | Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(f)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        main_l = QVBoxLayout(self)
        main_l.setContentsMargins(15, 15, 15, 15)
        
        self.bg = QFrame()
        self.bg.setObjectName("ExplorerBg")
        bg_l = QVBoxLayout(self.bg)
        bg_l.setContentsMargins(20, 20, 20, 20)
        main_l.addWidget(self.bg)
        apply_ios_shadow(self.bg)
        
        # 📌 상단 헤더: 좌측 제목 & 우측 윈도우 스타일 컨트롤 버튼 (─, □, ✕)
        ctrl = QHBoxLayout()
        
        title_l = QLabel("Memos")
        title_l.setStyleSheet("font-size: 14pt; border: none; font-weight: 700; letter-spacing: -0.5px; font-family: 'SF Pro Display', 'Pretendard', sans-serif;")
        ctrl.addWidget(title_l)

        self.btn_app_theme = QPushButton("")
        self.btn_app_theme.setFixedSize(100, 30)
        self.btn_app_theme.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_app_theme.clicked.connect(self.toggle_app_theme)

        self.toast = QLabel("")
        self.toast.setStyleSheet("color: #0A84FF; font-weight: bold; font-size: 10.5pt; margin-left: 15px;")
        self.toast.hide()

        ctrl.addWidget(self.btn_app_theme)
        ctrl.addWidget(self.toast)
        ctrl.addStretch()

        # 윈도우 스타일 우상단 제어 버튼 (📌 고정 / ─ 최소화 / □ 최대화 / ✕ 닫기)
        self.btn_win_pin   = QPushButton("")
        self.btn_win_min   = QPushButton("")
        self.btn_win_max   = QPushButton("")
        self.btn_win_close = QPushButton("")

        for b_item, tip in [(self.btn_win_pin, "화면 고정 토글"), (self.btn_win_min, "최소화"), (self.btn_win_max, "최대화"), (self.btn_win_close, "닫기")]:
            b_item.setFixedSize(32, 28)
            b_item.setCursor(Qt.CursorShape.PointingHandCursor)
            b_item.setToolTip(tip)
            ctrl.addWidget(b_item)

        self.btn_win_pin.clicked.connect(self.toggle_explorer_pin)
        self.btn_win_min.clicked.connect(self.showMinimized)
        self.btn_win_max.clicked.connect(self.toggle_maximize)
        self.btn_win_close.clicked.connect(self.close)

        bg_l.addLayout(ctrl)

        filter_layout = QHBoxLayout()
        self.btn_filter_all  = QPushButton(" 전체")
        self.btn_filter_gen  = QPushButton(" 일반")
        self.btn_filter_code = QPushButton(" 코드")
        
        for fb in [self.btn_filter_all, self.btn_filter_gen, self.btn_filter_code]:
            fb.setFixedHeight(34)
            fb.setCheckable(True)
            fb.setCursor(Qt.CursorShape.PointingHandCursor)
            filter_layout.addWidget(fb)
            
        self.btn_filter_all.clicked.connect(lambda: self.set_filter_mode("ALL"))
        self.btn_filter_gen.clicked.connect(lambda: self.set_filter_mode("GENERAL"))
        self.btn_filter_code.clicked.connect(lambda: self.set_filter_mode("CODE"))
        self.update_filter_buttons()
        
        filter_layout.addStretch()
        
        self.btn_arrange_rolled = QPushButton(" 접은 메모 정렬")
        self.btn_arrange_memos  = QPushButton(" 펼친 메모 정렬")
        
        for ab in [self.btn_arrange_rolled, self.btn_arrange_memos]:
            ab.setFixedHeight(34)
            ab.setCursor(Qt.CursorShape.PointingHandCursor)
            filter_layout.addWidget(ab)
            
        self.btn_arrange_rolled.clicked.connect(self.ui_manager.arrange_rolled_up_memos)
        self.btn_arrange_memos.clicked.connect(self.ui_manager.arrange_memos)
        
        bg_l.addLayout(filter_layout)

        sh_l = QHBoxLayout()
        self.s_type = QComboBox()
        self.s_type.addItems(["제목 검색", "본문 검색"])
        self.s_type.setFixedHeight(36)
        
        self.tag_combo = QComboBox()
        self.tag_combo.addItem("#  태그 필터")
        self.tag_combo.setFixedHeight(36)
        self.tag_combo.currentIndexChanged.connect(self.on_search)
        
        self.s_in = QLineEdit()
        self.s_in.setPlaceholderText("검색어를 입력하세요...")
        self.s_in.setFixedHeight(36)
        self.s_in.textChanged.connect(self.on_search)

        self.t_btn = QPushButton("⊘  휴지통")
        self.t_btn.setCheckable(True)
        self.t_btn.setFixedHeight(36)
        self.t_btn.clicked.connect(self.toggle_trash)
        
        sh_l.addWidget(self.s_type)
        sh_l.addWidget(self.tag_combo)
        sh_l.addWidget(self.s_in)
        sh_l.addWidget(self.t_btn)
        bg_l.addLayout(sh_l)
        
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["선택", "♡", "구분 / 제목", "수정일시", "삭제 방지"])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.cellClicked.connect(self.on_cell_click)
        self.table.cellDoubleClicked.connect(self.on_cell_double_click)
        self.table.itemSelectionChanged.connect(self.sync_selection_and_checkboxes)
        self.table.setTextElideMode(Qt.TextElideMode.ElideRight)
        
        self.table.verticalHeader().setVisible(False)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_table_context_menu)
        self.table.setFocusPolicy(Qt.FocusPolicy.StrongFocus) 
        
        h = self.table.horizontalHeader()
        h.setSectionsMovable(False)
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(0, 50)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(1, 50)
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(3, 140)
        h.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(4, 105)
        h.sectionClicked.connect(self.on_header_click)
        bg_l.addWidget(self.table)
        
        pg_l = QHBoxLayout()
        self.p_b = QPushButton("‹")
        self.p_b.setFixedSize(30, 30)
        self.p_b.clicked.connect(self.go_prev)

        self.p_l = QLabel("1 / 1")
        self.p_l.setStyleSheet("font-weight: bold; margin: 0 16px; font-size: 10pt;")

        self.n_b = QPushButton("›")
        self.n_b.setFixedSize(30, 30)
        self.n_b.clicked.connect(self.go_next)
        
        pg_l.addStretch()
        pg_l.addWidget(self.p_b)
        pg_l.addWidget(self.p_l)
        pg_l.addWidget(self.n_b)
        pg_l.addStretch()
        bg_l.addLayout(pg_l)
        
        bg_l.addWidget(QLabel("미리보기"))
        self.pv = QTextEdit()
        self.pv.setFixedHeight(120)
        self.pv.setReadOnly(False) 
        bg_l.addWidget(self.pv)
        self.pv.textChanged.connect(self.on_preview_changed)
        
        self.stat_label = QLabel("총 0개")
        self.stat_label.setStyleSheet("font-size: 9pt; font-weight: bold; color: #8E8E93; margin-top: 4px;")
        bg_l.addWidget(self.stat_label)

        self.btn_box = QWidget()
        self.btn_l = QHBoxLayout(self.btn_box)
        self.btn_l.setContentsMargins(0, 10, 0, 0)
        bg_l.addWidget(self.btn_box)
        
        self.setup_btns()
        self.refresh()
        
        self.grip = QSizeGrip(self)

    def toggle_maximize(self) -> None:
        """100% 정상 작동하는 윈도우 최대화/복원 기능"""
        if self.isMaximized():
            self.showNormal()
            self.btn_win_max.setText("")
            self.btn_win_max.setToolTip("최대화")
        else:
            self.showMaximized()
            self.btn_win_max.setText("")
            self.btn_win_max.setToolTip("복원")

    def toggle_app_theme(self) -> None:
        cur = self.ui_manager.sync_manager.settings.get('app_theme', 'white')
        new_theme = "dark" if cur == "white" else "white"
        self.ui_manager.sync_manager.settings['app_theme'] = new_theme
        self.ui_manager.sync_manager.save_settings(self.ui_manager.sync_manager.settings)
        
        self.apply_theme_style()
        self.update_filter_buttons()
        self.update_table() 
        
        if self.ui_manager.settings_window and self.ui_manager.settings_window.isVisible():
            self.ui_manager.settings_window.apply_theme_style()

    def toggle_explorer_pin(self) -> None:
        self.is_pinned = not getattr(self, 'is_pinned', False)
        self.ui_manager.sync_manager.settings['explorer_is_pinned'] = self.is_pinned
        self.ui_manager.sync_manager.save_settings(self.ui_manager.sync_manager.settings)
        f = self.windowFlags()
        if self.isVisible() and sys.platform == 'win32':
            import ctypes
            hwnd = int(self.winId())
            HWND_TOPMOST = -1
            HWND_NOTOPMOST = -2
            SWP_NOMOVE = 0x0002
            SWP_NOSIZE = 0x0001
            flag = HWND_TOPMOST if self.is_pinned else HWND_NOTOPMOST
            ctypes.windll.user32.SetWindowPos(hwnd, flag, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE)
            
            if self.is_pinned:
                self.show_toast("📌 메모 탐색기 화면 고정 켜짐")
            else:
                self.show_toast("📍 메모 탐색기 화면 고정 해제됨")
        else:
            if self.is_pinned:
                self.setWindowFlags(f | Qt.WindowType.WindowStaysOnTopHint)
                self.show_toast("📌 메모 탐색기 화면 고정 켜짐")
            else:
                self.setWindowFlags(f & ~Qt.WindowType.WindowStaysOnTopHint)
                self.show_toast("📍 메모 탐색기 화면 고정 해제됨")
            self.show()
        self.update_icons()

    def update_icons(self) -> None:
        if not hasattr(self.ui_manager, 'get_theme_icon'): return
        theme = self.ui_manager.sync_manager.settings.get('app_theme', 'white')
        is_dark = (theme == 'dark')
        self.btn_win_pin.setText("")
        self.btn_win_min.setText("")
        self.btn_win_max.setText("")
        self.btn_win_close.setText("")
        is_pinned = getattr(self, 'is_pinned', False)
        if is_pinned:
            self.btn_win_pin.setStyleSheet("QPushButton { background: #0A84FF; color: white; border: none; border-radius: 6px; } QPushButton:hover { background: #007AFF; }")
            self.btn_win_pin.setIcon(self.ui_manager.get_theme_icon("pin_icon_True.svg", is_dark, override_color="#FFFFFF"))
        else:
            win_btn_style = "QPushButton { background: transparent; color: #FFFFFF; font-weight: bold; border: none; border-radius: 6px; } QPushButton:hover { background: rgba(255, 255, 255, 0.15); }" if is_dark else "QPushButton { background: transparent; color: #000000; font-weight: bold; border: none; border-radius: 6px; } QPushButton:hover { background: rgba(0, 0, 0, 0.08); }"
            self.btn_win_pin.setStyleSheet(win_btn_style)
            self.btn_win_pin.setIcon(self.ui_manager.get_theme_icon("pin_icon_False.svg", is_dark))
        self.btn_app_theme.setIcon(self.ui_manager.get_theme_icon("litemode.svg" if is_dark else "darkmod.svg", is_dark))
        self.btn_win_min.setIcon(self.ui_manager.get_theme_icon("minimize.svg", is_dark))
        self.btn_win_max.setIcon(self.ui_manager.get_theme_icon("maximize.svg", is_dark))
        self.btn_win_close.setIcon(self.ui_manager.get_theme_icon("close.svg", is_dark, override_color="#FF453A"))
        self.btn_filter_all.setIcon(self.ui_manager.get_theme_icon("total.svg", is_dark))
        self.btn_filter_gen.setIcon(self.ui_manager.get_theme_icon("memo.svg", is_dark))
        self.btn_filter_code.setIcon(self.ui_manager.get_theme_icon("codememo.svg", is_dark))
        self.btn_arrange_rolled.setIcon(self.ui_manager.get_theme_icon("정렬1.svg", is_dark))
        self.btn_arrange_memos.setIcon(self.ui_manager.get_theme_icon("정렬2.svg", is_dark))
        self.t_btn.setIcon(self.ui_manager.get_theme_icon("trashbucket.svg", is_dark))
        self.p_b.setText("")
        self.n_b.setText("")
        self.p_b.setIcon(self.ui_manager.get_theme_icon("arrow left.svg", is_dark))
        self.n_b.setIcon(self.ui_manager.get_theme_icon("arrow right.svg", is_dark))
        self.b_new.setIcon(self.ui_manager.get_theme_icon("pluse.svg", is_dark))
        self.b_new_code.setIcon(self.ui_manager.get_theme_icon("codememo.svg", is_dark))
        self.b_ref.setIcon(self.ui_manager.get_theme_icon("restart-icon.svg", is_dark))
        self.b_sync.setIcon(self.ui_manager.get_theme_icon("cloude.svg", is_dark))
        self.b_del.setIcon(self.ui_manager.get_theme_icon("minus.svg", is_dark))
        self.b_res.setIcon(self.ui_manager.get_theme_icon("restart-icon.svg", is_dark))
        self.b_empty_trash.setIcon(self.ui_manager.get_theme_icon("trashbucket.svg", is_dark))

    def apply_theme_style(self) -> None:
        """iOS 울트라 미니멀 화이트 & 블랙 양방향 스타일시트"""
        self.update_icons()
        theme = self.ui_manager.sync_manager.settings.get('app_theme', 'white')
        is_dark = (theme == "dark")
        
        self.btn_app_theme.setText(" 라이트" if is_dark else " 다크")
        
        win_btn_style_dark = "QPushButton { background: transparent; color: #FFFFFF; font-weight: bold; border: none; border-radius: 6px; } QPushButton:hover { background: rgba(255, 255, 255, 0.15); }"
        win_btn_style_light = "QPushButton { background: transparent; color: #000000; font-weight: bold; border: none; border-radius: 6px; } QPushButton:hover { background: rgba(0, 0, 0, 0.08); }"
        close_btn_style = "QPushButton { background: transparent; color: #FF453A; font-weight: bold; border: none; border-radius: 6px; } QPushButton:hover { background: #FF453A; color: white; }"

        if is_dark:
            mode = self.ui_manager.sync_manager.settings.get("dark_theme_mode", "dark")
            pal = DARK_THEMES.get(mode, DARK_THEMES["dark"])
            self.bg.setStyleSheet(f"""
                QFrame#ExplorerBg {{
                    background-color: {pal['bg']};
                    border: 1px solid {pal['border']};
                    border-radius: 0px;
                }}
                QLabel {{
                    color: {pal['text']};
                    font-family: 'SF Pro Display', 'Pretendard', sans-serif;
                }}
                QPushButton {{
                    font-family: 'SF Pro Display', 'Pretendard', sans-serif;
                    color: {pal['text']};
                    border-radius: 0px;
                }}
                QLineEdit, QComboBox {{
                    padding: 8px 14px;
                    border: 1px solid {pal['border']};
                    border-radius: 0px;
                    color: {pal['text']};
                    background-color: {pal['input']};
                    selection-background-color: {pal['accent']};
                }}
                QLineEdit:focus, QComboBox:focus {{
                    border: 1.5px solid {pal['accent']};
                    background-color: {pal['card']};
                }}
                QComboBox QAbstractItemView {{
                    background-color: {pal['input']};
                    color: {pal['text']};
                    selection-background-color: {pal['accent']};
                    selection-color: white;
                    border: 1px solid {pal['border']};
                }}
            """)
            self.table.setStyleSheet(f"""
                QTableWidget {{
                    border: none;
                    border-radius: 0px;
                    background-color: {pal['card']};
                    color: {pal['text']};
                    outline: none;
                    gridline-color: transparent;
                    font-family: 'SF Pro Display', 'Pretendard', sans-serif;
                    font-size: 9.5pt;
                }}
                QTableWidget::item {{
                    border: none;
                    border-bottom: 1px solid {pal['border']};
                    color: {pal['text']};
                    padding: 4px 8px;
                    background-color: transparent;
                }}
                QTableWidget::item:alternate {{
                    background-color: rgba(255, 255, 255, 0.025);
                }}
                QTableWidget::item:selected {{
                    background-color: rgba(10, 132, 255, 0.28);
                    color: #FFFFFF;
                    font-weight: bold;
                    border-bottom: 1px solid rgba(10, 132, 255, 0.5);
                }}
                QHeaderView {{
                    background-color: transparent;
                    border: none;
                }}
                QHeaderView::section {{
                    background-color: {pal['input']};
                    color: {pal['accent']};
                    font-weight: 600;
                    font-size: 8.5pt;
                    font-family: 'SF Pro Display', 'Pretendard', sans-serif;
                    border: none;
                    border-bottom: 1px solid {pal['border']};
                    padding: 8px 10px;
                    letter-spacing: 0.3px;
                    text-transform: uppercase;
                }}
                QTableWidget::indicator {{
                    width: 18px;
                    height: 18px;
                    margin-left: 12px;
                    border-radius: 5px;
                }}
                QTableWidget::indicator:unchecked {{
                    border: 1.5px solid rgba(255,255,255,0.25);
                    background: transparent;
                    border-radius: 5px;
                }}
                QTableWidget::indicator:checked {{
                    background: {pal['accent']};
                    border: 1.5px solid {pal['accent']};
                    border-radius: 5px;
                }}
                QTableCornerButton::section {{
                    background-color: {pal['input']};
                    border: none;
                }}
                QScrollBar:vertical {{
                    width: 6px;
                    background: transparent;
                    margin: 4px 2px 4px 0;
                }}
                QScrollBar::handle:vertical {{
                    background: rgba(255,255,255,0.18);
                    border-radius: 3px;
                    min-height: 24px;
                }}
                QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
            """)
            self.table.setAlternatingRowColors(True)
            self.pv.setStyleSheet(f"""
                background-color: {pal['input']};
                border: 1px solid {pal['border']};
                border-radius: 12px; padding: 12px;
                color: {pal['text']}; font-size: 10pt;
                font-family: 'SF Pro Display', 'Pretendard', sans-serif;
            """)

            btn_base = f"""
                QPushButton {{
                    padding: 8px 16px;
                    background-color: {pal['input']};
                    border: 1px solid {pal['border']};
                    border-radius: 12px;
                    color: {pal['text']};
                    font-weight: bold;
                    font-size: 9.5pt;
                }}
                QPushButton:hover {{
                    background-color: rgba(255,255,255,0.12);
                    border-color: rgba(255,255,255,0.25);
                }}
            """
            self.b_new.setStyleSheet(btn_base)
            self.b_new_code.setStyleSheet(btn_base)
            self.b_ref.setStyleSheet(btn_base)
            self.b_sync.setStyleSheet(btn_base)
            self.b_res.setStyleSheet(btn_base)
            self.btn_app_theme.setStyleSheet(f"""
                padding: 0 14px; border: 1.5px solid {pal['accent']}; border-radius: 14px;
                font-weight: bold; background: rgba(10,132,255,0.15); color: {pal['accent']};
            """)
            self.btn_arrange_rolled.setStyleSheet(f"""
                padding: 6px 14px; background: rgba(10,132,255,0.12);
                border: 1px solid rgba(10,132,255,0.4); color: {pal['accent']};
                font-weight: bold; border-radius: 12px;
            """)
            self.btn_arrange_memos.setStyleSheet(f"""
                padding: 6px 14px; background: rgba(10,132,255,0.12);
                border: 1px solid rgba(10,132,255,0.4); color: {pal['accent']};
                font-weight: bold; border-radius: 12px;
            """)
            self.b_del.setStyleSheet(
                "QPushButton { padding: 8px 16px; background: rgba(255,69,58,0.12); "
                "color: #FF453A; border: 1px solid rgba(255,69,58,0.35); "
                "border-radius: 12px; font-weight: bold; } "
                "QPushButton:hover { background: rgba(255,69,58,0.25); }"
            )
            self.b_empty_trash.setStyleSheet(
                "QPushButton { padding: 8px 16px; background: rgba(255,69,58,0.12); "
                "color: #FF453A; border: 1px solid rgba(255,69,58,0.35); "
                "border-radius: 12px; font-weight: bold; } "
                "QPushButton:hover { background: rgba(255,69,58,0.25); }"
            )
            self.t_btn.setStyleSheet(f"""
                QPushButton {{ padding: 8px 16px; background-color: {pal['input']};
                border: 1px solid {pal['border']}; border-radius: 10px;
                color: {pal['text']}; font-weight: bold; }}
                QPushButton:checked {{ background-color: rgba(10,132,255,0.85);
                color: white; border-color: {pal['accent']}; }}
            """)
            self.btn_win_pin.setStyleSheet(win_btn_style_dark)
            self.btn_win_min.setStyleSheet(win_btn_style_dark)
            self.btn_win_max.setStyleSheet(win_btn_style_dark)
            self.btn_win_close.setStyleSheet(close_btn_style)
        else:
            mode = self.ui_manager.sync_manager.settings.get("light_theme_mode", "white")
            pal = LIGHT_THEMES.get(mode, LIGHT_THEMES["white"])
            self.bg.setStyleSheet(f"""
                QFrame#ExplorerBg {{
                    background-color: {pal['bg']};
                    border: 1px solid {pal['border']};
                    border-radius: 0px;
                }}
                QLabel {{
                    color: {pal['text']};
                    font-family: 'SF Pro Display', 'Pretendard', sans-serif;
                }}
                QPushButton {{
                    font-family: 'SF Pro Display', 'Pretendard', sans-serif;
                    color: {pal['text']};
                    border-radius: 0px;
                }}
                QLineEdit, QComboBox {{
                    padding: 8px 14px;
                    border: 1px solid {pal['border']};
                    border-radius: 0px;
                    color: {pal['text']};
                    background-color: {pal['input']};
                    selection-background-color: {pal['accent']};
                }}
                QLineEdit:focus, QComboBox:focus {{
                    border: 1.5px solid {pal['accent']};
                    background-color: {pal['input']};
                }}
                QComboBox QAbstractItemView {{
                    background-color: {pal['input']};
                    color: {pal['text']};
                    selection-background-color: {pal['accent']};
                    selection-color: white;
                    border: 1px solid {pal['border']};
                }}
            """)
            self.table.setStyleSheet(f"""
                QTableWidget {{
                    border: none;
                    border-radius: 0px;
                    background-color: {pal['card']};
                    color: {pal['text']};
                    outline: none;
                    gridline-color: transparent;
                    font-family: 'SF Pro Display', 'Pretendard', sans-serif;
                    font-size: 9.5pt;
                }}
                QTableWidget::item {{
                    border: none;
                    border-bottom: 1px solid {pal['border']};
                    color: {pal['text']};
                    padding: 4px 8px;
                    background-color: transparent;
                }}
                QTableWidget::item:alternate {{
                    background-color: rgba(0, 0, 0, 0.018);
                }}
                QTableWidget::item:selected {{
                    background-color: rgba(0, 122, 255, 0.14);
                    color: {pal['accent']};
                    font-weight: bold;
                    border-bottom: 1px solid rgba(0, 122, 255, 0.3);
                }}
                QHeaderView {{
                    background-color: transparent;
                    border: none;
                }}
                QHeaderView::section {{
                    background-color: {pal['bg']};
                    color: #8E8E93;
                    font-weight: 600;
                    font-size: 8.5pt;
                    font-family: 'SF Pro Display', 'Pretendard', sans-serif;
                    border: none;
                    border-bottom: 1px solid {pal['border']};
                    padding: 8px 10px;
                    letter-spacing: 0.3px;
                    text-transform: uppercase;
                }}
                QTableWidget::indicator {{
                    width: 18px;
                    height: 18px;
                    margin-left: 12px;
                    border-radius: 5px;
                }}
                QTableWidget::indicator:unchecked {{
                    border: 1.5px solid rgba(0,0,0,0.25);
                    background: transparent;
                    border-radius: 5px;
                }}
                QTableWidget::indicator:checked {{
                    background: {pal['accent']};
                    border: 1.5px solid {pal['accent']};
                    border-radius: 5px;
                }}
                QTableCornerButton::section {{
                    background-color: {pal['bg']};
                    border: none;
                }}
                QScrollBar:vertical {{
                    width: 6px;
                    background: transparent;
                    margin: 4px 2px 4px 0;
                }}
                QScrollBar::handle:vertical {{
                    background: rgba(0,0,0,0.15);
                    border-radius: 3px;
                    min-height: 24px;
                }}
                QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
            """)
            self.table.setAlternatingRowColors(True)
            self.pv.setStyleSheet(f"""
                background-color: {pal['card']};
                border: 1px solid {pal['border']};
                border-radius: 12px; padding: 12px;
                color: {pal['text']}; font-size: 10pt;
                font-family: 'SF Pro Display', 'Pretendard', sans-serif;
            """)

            btn_base = f"""
                QPushButton {{
                    padding: 8px 16px;
                    background-color: {pal['card']};
                    border: 1px solid {pal['border']};
                    border-radius: 12px;
                    color: {pal['text']};
                    font-weight: bold;
                    font-size: 9.5pt;
                }}
                QPushButton:hover {{
                    background-color: {pal['accent']};
                    color: white;
                    border-color: {pal['accent']};
                }}
            """
            self.b_new.setStyleSheet(btn_base)
            self.b_new_code.setStyleSheet(btn_base)
            self.b_ref.setStyleSheet(btn_base)
            self.b_sync.setStyleSheet(btn_base)
            self.b_res.setStyleSheet(btn_base)
            self.btn_app_theme.setStyleSheet(f"""
                padding: 0 14px; border: 1.5px solid {pal['accent']}; border-radius: 14px;
                font-weight: bold; background: rgba(0,122,255,0.08); color: {pal['accent']};
            """)
            self.btn_arrange_rolled.setStyleSheet(f"""
                padding: 6px 14px; background: rgba(0,122,255,0.08);
                border: 1px solid rgba(0,122,255,0.35); color: {pal['accent']};
                font-weight: bold; border-radius: 12px;
            """)
            self.btn_arrange_memos.setStyleSheet(f"""
                padding: 6px 14px; background: rgba(0,122,255,0.08);
                border: 1px solid rgba(0,122,255,0.35); color: {pal['accent']};
                font-weight: bold; border-radius: 12px;
            """)
            self.b_del.setStyleSheet(
                "QPushButton { padding: 8px 16px; background: rgba(255,59,48,0.07); "
                "color: #FF3B30; border: 1px solid rgba(255,59,48,0.25); "
                "border-radius: 12px; font-weight: bold; } "
                "QPushButton:hover { background: rgba(255,59,48,0.15); }"
            )
            self.b_empty_trash.setStyleSheet(
                "QPushButton { padding: 8px 16px; background: rgba(255,59,48,0.07); "
                "color: #FF3B30; border: 1px solid rgba(255,59,48,0.25); "
                "border-radius: 12px; font-weight: bold; } "
                "QPushButton:hover { background: rgba(255,59,48,0.15); }"
            )

            if hasattr(self.ui_manager, 'get_theme_icon'):
                self.b_new.setIcon(self.ui_manager.get_theme_icon("pluse.svg", is_dark))
                self.b_new_code.setIcon(self.ui_manager.get_theme_icon("codememo.svg", is_dark))
                self.b_ref.setIcon(self.ui_manager.get_theme_icon("restart-icon.svg", is_dark))
                self.b_sync.setIcon(self.ui_manager.get_theme_icon("cloude.svg", is_dark))
                self.b_del.setIcon(self.ui_manager.get_theme_icon("trashbucket.svg", is_dark, override_color="#FF3B30"))
                self.b_res.setIcon(self.ui_manager.get_theme_icon("save.svg", is_dark))
                self.b_empty_trash.setIcon(self.ui_manager.get_theme_icon("trashbucket.svg", is_dark, override_color="#FF3B30"))
            self.t_btn.setStyleSheet(f"""
                QPushButton {{ padding: 8px 16px; background-color: {pal['card']};
                border: 1px solid {pal['border']}; border-radius: 10px;
                color: {pal['text']}; font-weight: bold; }}
                QPushButton:checked {{ background-color: rgba(0,122,255,0.85);
                color: white; border-color: {pal['accent']}; }}
            """)
            self.btn_win_pin.setStyleSheet(win_btn_style_light)
            self.btn_win_min.setStyleSheet(win_btn_style_light)
            self.btn_win_max.setStyleSheet(win_btn_style_light)
            self.btn_win_close.setStyleSheet(close_btn_style)

    def sync_selection_and_checkboxes(self) -> None:
        selected_rows = set(index.row() for index in self.table.selectedIndexes())
        for r in range(self.table.rowCount()):
            item_cb = self.table.item(r, 0)
            if item_cb:
                if r in selected_rows:
                    item_cb.setCheckState(Qt.CheckState.Checked)
                else:
                    item_cb.setCheckState(Qt.CheckState.Unchecked)

    def set_filter_mode(self, mode: str) -> None:
        self.filter_mode = mode
        self.update_filter_buttons()
        self.current_page = 1
        self.refresh()

    def update_filter_buttons(self) -> None:
        theme = self.ui_manager.sync_manager.settings.get('app_theme', 'white')
        is_dark = (theme == "dark")
        
        btn_style_off = "padding: 6px 16px; background: #1C1C1E; border: 1px solid rgba(255, 255, 255, 0.2); border-radius: 12px; color: #FFFFFF; font-weight: bold;" if is_dark else "padding: 6px 16px; background: white; border: 1px solid #C7C7CC; border-radius: 12px; color: #000000; font-weight: bold;"
        btn_style_on = "padding: 6px 16px; background: #007AFF; border: 1px solid #007AFF; border-radius: 12px; color: white; font-weight: bold;"
        
        self.btn_filter_all.setStyleSheet(btn_style_on if self.filter_mode == "ALL" else btn_style_off)
        self.btn_filter_gen.setStyleSheet(btn_style_on if self.filter_mode == "GENERAL" else btn_style_off)
        self.btn_filter_code.setStyleSheet(btn_style_on if self.filter_mode == "CODE" else btn_style_off)

    def resizeEvent(self, event: Any) -> None:
        super().resizeEvent(event)
        self.grip.move(self.width() - 35, self.height() - 35)
        self.grip.resize(16, 16)

    def closeEvent(self, event: Any) -> None:
        geom = [self.x(), self.y(), self.width(), self.height()]
        self.ui_manager.sync_manager.settings['explorer_geom'] = geom
        self.ui_manager.sync_manager.save_settings(self.ui_manager.sync_manager.settings)
        super().closeEvent(event)

    def show_toast(self, m: str) -> None: 
        self.toast.setText(f"✓ {m}")
        self.toast.show()
        QTimer.singleShot(3500, self.toast.hide)

    def mousePressEvent(self, e: Any) -> None: 
        if e.button() == Qt.MouseButton.LeftButton:
            self._old_pos = e.globalPosition().toPoint()
            
    def mouseMoveEvent(self, e: Any) -> None:
        if self._old_pos and not self.isMaximized(): 
            d = e.globalPosition().toPoint() - self._old_pos
            self.move(self.x() + d.x(), self.y() + d.y())
            self._old_pos = e.globalPosition().toPoint()
            
    def mouseReleaseEvent(self, e: Any) -> None:
        self._old_pos = None
    
    def setup_btns(self) -> None:
        self.b_new        = QPushButton(" 새 메모")
        self.b_new_code   = QPushButton(" 코드 메모")
        self.b_ref        = QPushButton(" 새로고침")
        self.b_sync       = QPushButton(" 동기화")
        self.b_del        = QPushButton(" 삭제")
        self.b_res        = QPushButton(" 복구")
        self.b_empty_trash = QPushButton(" 비우기")
        
        self.b_new.clicked.connect(self.ui_manager.create_empty_memo)
        self.b_new_code.clicked.connect(self.ui_manager.create_code_memo)
        self.b_ref.clicked.connect(self.refresh)
        self.b_sync.clicked.connect(self.ui_manager.sync_manager.sync_push)
        self.b_del.clicked.connect(self.del_checked)
        self.b_res.clicked.connect(self.res_checked)
        self.b_empty_trash.clicked.connect(self.empty_trash)

    def empty_trash(self) -> None:
        if QMessageBox.question(self, "휴지통 비우기", "휴지통의 모든 메모를 영구 삭제할까요? (복구 불가)", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            cnt = self.ui_manager.sync_manager.empty_trash_locally()
            self.pv.clear()
            self.refresh()
            self.show_toast(f"🧹 휴지통의 메모 {cnt}개가 영구 삭제되었습니다.")

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
        if is_dark:
            mode = self.ui_manager.sync_manager.settings.get("dark_theme_mode", "dark")
            pal = DARK_THEMES.get(mode, DARK_THEMES["dark"])
            menu.setStyleSheet(f"QMenu {{ background: {pal['card']}; color: {pal['text']}; border: 1px solid {pal['border']}; border-radius: 8px; }} QMenu::item:selected {{ background-color: {pal['accent']}; color: white; }}")
        else:
            mode = self.ui_manager.sync_manager.settings.get("light_theme_mode", "white")
            pal = LIGHT_THEMES.get(mode, LIGHT_THEMES["white"])
            menu.setStyleSheet(f"QMenu {{ background: {pal['card']}; color: {pal['text']}; border: 1px solid {pal['border']}; border-radius: 8px; }} QMenu::item:selected {{ background-color: {pal['accent']}; color: white; }}")
        
        act_open = menu.addAction("메모 열기")
        if hasattr(self.ui_manager, 'get_theme_icon'):
            act_open.setIcon(self.ui_manager.get_theme_icon("memo.svg", is_dark))
        act_open.triggered.connect(lambda: self.ui_manager.show_specific_memo(m.get('id')))
        
        fav_text = "즐겨찾기 해제" if m.get('is_favorite') else "즐겨찾기 등록"
        act_fav = menu.addAction(fav_text)
        if hasattr(self.ui_manager, 'get_theme_icon'):
            act_fav.setIcon(self.ui_manager.get_theme_icon("favorite_true.svg" if m.get('is_favorite') else "favorite_false.svg", is_dark))
        act_fav.triggered.connect(lambda: self.toggle_fav(m))
        
        pin_text = "화면 고정 해제" if m.get('is_pinned') else "화면 고정(Pin)"
        act_pin = menu.addAction(pin_text)
        if hasattr(self.ui_manager, 'get_theme_icon'):
            act_pin.setIcon(self.ui_manager.get_theme_icon("pin_icon_True.svg" if m.get('is_pinned') else "pin_icon_False.svg", is_dark))
        act_pin.triggered.connect(lambda: self.toggle_memo_pin(m))
        
        prot_text = "삭제 방지 해제" if m.get('is_protected') else "삭제 방지 설정"
        act_prot = menu.addAction(prot_text)
        if hasattr(self.ui_manager, 'get_theme_icon'):
            act_prot.setIcon(self.ui_manager.get_theme_icon("lock_open.svg" if m.get('is_protected') else "lock_close.svg", is_dark))
        act_prot.triggered.connect(lambda: self.toggle_protect(m))

        menu.addSeparator()
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
        act_del = menu.addAction("삭제 (휴지통)")
        if hasattr(self.ui_manager, 'get_theme_icon'):
            act_del.setIcon(self.ui_manager.get_theme_icon("trashbucket.svg", is_dark, override_color="#FF453A"))
        act_del.triggered.connect(lambda: self.delete_single_memo(m))
        
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def toggle_protect(self, memo: Dict[str, Any]) -> None:
        memo['is_protected'] = not memo.get('is_protected', False)
        self.ui_manager.sync_manager.save_memo_locally(memo)
        self.show_toast(f"{'🔒 삭제 방지 설정됨' if memo['is_protected'] else '🔓 삭제 방지 해제됨'}")
        self.refresh()

    def toggle_memo_pin(self, memo: Dict[str, Any]) -> None:
        target_memos = []
        for r in range(self.table.rowCount()):
            item_cb = self.table.item(r, 0)
            if item_cb and item_cb.checkState() == Qt.CheckState.Checked:
                m = self.table.item(r, 2).data(Qt.ItemDataRole.UserRole)
                if m and m not in target_memos:
                    target_memos.append(m)
        if not target_memos:
            for r in set(index.row() for index in self.table.selectedIndexes()):
                m = self.table.item(r, 2).data(Qt.ItemDataRole.UserRole)
                if m and m not in target_memos:
                    target_memos.append(m)
        if not target_memos:
            target_memos = [memo]

        new_pinned_state = not memo.get('is_pinned', False)
        for m in target_memos:
            m['is_pinned'] = new_pinned_state
            self.ui_manager.sync_manager.save_memo_locally(m)
            memo_id = m.get('id')
            if memo_id and memo_id in self.ui_manager.memo_windows:
                self.ui_manager.memo_windows[memo_id].apply_data()

        self.show_toast(f"📌 {len(target_memos)}개 메모 {'고정 설정됨' if new_pinned_state else '고정 해제됨'}")
        self.refresh()

    def change_memo_color(self, memo: Dict[str, Any], color_hex: str) -> None:
        memo['bg_color'] = color_hex
        self.ui_manager.sync_manager.save_memo_locally(memo)
        memo_id = memo.get('id')
        if memo_id and memo_id in self.ui_manager.memo_windows:
            self.ui_manager.memo_windows[memo_id].apply_data()
        self.refresh()

    def copy_memo_text(self, memo: Dict[str, Any]) -> None:
        raw_cnt = memo.get('content', '')
        text = clean_plain_text(raw_cnt)
        QApplication.clipboard().setText(text)
        self.show_toast("본문 내용이 클립보드에 복사되었습니다.")

    def delete_single_memo(self, memo: Dict[str, Any]) -> None:
        if memo.get('is_protected'):
            self.show_toast("🔒 삭제 방지 설정된 메모입니다.")
            return
        memo_id = memo.get('id')
        if memo_id and QMessageBox.question(self, "삭제", f"'{memo.get('title','')}' 메모를 휴지통으로 이동할까요?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            self.ui_manager.close_memo_window_by_id(memo_id, is_deleting=True)
            self.ui_manager.sync_manager.delete_memo_locally(memo_id, title=memo.get('title'))
            self.ui_manager.sync_manager.delete_memos_cloud([memo_id])
            self.pv.clear()
            self.refresh()
    
    def on_cell_click(self, r: int, c: int) -> None:
        """셀 클릭 시 미리보기 업데이트 — 코드 메모는 D2Coding 폰트 적용."""
        m_item = self.table.item(r, 2)
        if m_item:
            m = m_item.data(Qt.ItemDataRole.UserRole)
            if m:
                self._is_loading_preview = True
                content = m.get('content', '')
                is_code = m.get('is_code_memo', False)
                clean_text = clean_plain_text(content)

                theme = self.ui_manager.sync_manager.settings.get('app_theme', 'white')
                is_dark = (theme == "dark")

                if is_dark:
                    bg_c = "#1A1A1C"
                    border_c = "rgba(255, 255, 255, 0.1)"
                    text_c = "#FFFFFF" if not is_code else "#E8F4FF"
                    font_part = "font-family: 'D2Coding', 'Consolas', monospace;" if is_code else "font-family: 'SF Pro Display', 'Pretendard', sans-serif;"
                else:
                    bg_c = "#F8F9FA" if not is_code else "#F0F4FF"
                    border_c = "#E5E5EA" if not is_code else "#C7D8FF"
                    text_c = "#1C1C1E" if not is_code else "#1A237E"
                    font_part = "font-family: 'D2Coding', 'Consolas', monospace;" if is_code else "font-family: 'SF Pro Display', 'Pretendard', sans-serif;"

                self.pv.setStyleSheet(
                    f"background-color: {bg_c}; "
                    f"border: 1px solid {border_c}; "
                    f"border-radius: 12px; padding: 12px; "
                    f"color: {text_c}; font-size: 10pt; {font_part}"
                )
                self.pv.setPlainText(clean_text)
                self._is_loading_preview = False
                
    def on_preview_changed(self) -> None:
        if self._is_loading_preview or self.is_trash_mode:
            return
        r = self.table.currentRow()
        if r < 0:
            return
        m_item = self.table.item(r, 2)
        if m_item:
            m = m_item.data(Qt.ItemDataRole.UserRole)
            if not m: return
            memo_id = m.get('id', '')
            new_content = self.pv.toHtml()
            m['content'] = new_content
            m['updated_at'] = datetime.datetime.now().isoformat()
            
            self.ui_manager.sync_manager.save_memo_locally(m)
            
            if memo_id in self.ui_manager.memo_windows:
                w = self.ui_manager.memo_windows[memo_id]
                w._is_updating_from_explorer = True
                w.text_edit.setHtml(new_content)
                w._is_updating_from_explorer = False
                
            if self.table.item(r, 3):
                self.table.item(r, 3).setText(datetime.datetime.now().strftime("%Y-%m-%d %H:%M"))
            
    def on_cell_double_click(self, r: int, c: int) -> None:
        if not self.is_trash_mode:
            m_item = self.table.item(r, 2)
            if m_item:
                m = m_item.data(Qt.ItemDataRole.UserRole)
                if m:
                    self.ui_manager.show_specific_memo(m.get('id') or m.get('title'))
                
    def update_btns_visibility(self) -> None:
        while self.btn_l.count():
            wi = self.btn_l.takeAt(0).widget()
            if wi:
                wi.setParent(None)
        if not self.is_trash_mode:
            self.btn_l.addWidget(self.b_new)
            self.btn_l.addWidget(self.b_new_code)
            self.btn_l.addWidget(self.b_ref)
            self.btn_l.addWidget(self.b_sync)
            self.btn_l.addStretch()
            self.btn_l.addWidget(self.b_del)
        else:
            self.btn_l.addWidget(self.b_ref)
            self.btn_l.addWidget(self.b_res)
            self.btn_l.addWidget(self.b_empty_trash)
            self.btn_l.addStretch()
            
    def toggle_trash(self) -> None: 
        self.is_trash_mode = self.t_btn.isChecked()
        self.t_btn.setText("⎌ 목록으로 돌아가기" if self.is_trash_mode else "ⓧ 휴지통 보기")
        self.pv.setReadOnly(self.is_trash_mode) 
        self.pv.clear()
        self.current_page = 1
        self.refresh()

    def on_search(self) -> None:
        self.current_page = 1
        self.refresh()

    def go_prev(self) -> None:
        if self.current_page > 1:
            self.current_page -= 1
            self.update_table()

    def go_next(self) -> None:
        total_pages = max(1, (len(self.filtered_memos) + 9) // 10)
        if self.current_page < total_pages:
            self.current_page += 1
            self.update_table()
    
    def on_header_click(self, idx: int) -> None:
        if idx == 0:
            all_c = all(self.table.item(r, 0).checkState() == Qt.CheckState.Checked for r in range(self.table.rowCount()))
            ns = Qt.CheckState.Unchecked if all_c else Qt.CheckState.Checked
            for r in range(self.table.rowCount()):
                self.table.item(r, 0).setCheckState(ns)
            
    def refresh(self) -> None:
        q = self.s_in.text().lower()
        sb = self.s_type.currentIndex() == 1
        all_m = self.ui_manager.sync_manager.load_trash_memos() if self.is_trash_mode else self.ui_manager.sync_manager.load_local_memos()
        
        hashtags = set()
        gen_cnt = 0
        code_cnt = 0
        for m in all_m:
            if m.get('is_code_memo'): code_cnt += 1
            else: gen_cnt += 1
            plain = clean_plain_text(m.get('content', ''))
            tags = re.findall(r'#([^\s#]+)', plain)
            hashtags.update(tags)
            
        self.stat_label.setText(f"📊 총 {len(all_m)}개 메모 (일반: {gen_cnt}개 | 코드: {code_cnt}개)")
            
        cur_tag = self.tag_combo.currentText()
        self.tag_combo.blockSignals(True)
        self.tag_combo.clear()
        self.tag_combo.addItem("🏷️ 모든 해시태그 (#)")
        for tag in sorted(hashtags):
            self.tag_combo.addItem(f"#{tag}")
        self.tag_combo.setCurrentText(cur_tag if cur_tag in [self.tag_combo.itemText(i) for i in range(self.tag_combo.count())] else "🏷️ 모든 해시태그 (#)")
        self.tag_combo.blockSignals(False)
        
        selected_tag = self.tag_combo.currentText()
        tag_filter = selected_tag.replace("🏷️ 모든 해시태그 (#)", "").strip()
        
        all_m.sort(key=lambda x: (x.get('is_favorite', False), x.get('updated_at', '')), reverse=True)
        
        filtered = []
        for m in all_m:
            is_code = m.get('is_code_memo', False)
            if self.filter_mode == "GENERAL" and is_code: continue
            if self.filter_mode == "CODE" and not is_code: continue
            
            plain_cnt = clean_plain_text(m.get('content',''))
            if tag_filter and tag_filter not in plain_cnt:
                continue
            if q:
                if sb and q not in plain_cnt.lower(): continue
                if not sb and q not in m.get('title','').lower(): continue
            filtered.append(m)
            
        self.filtered_memos = filtered
        self.update_table()
        self.update_btns_visibility()
        
    def update_table(self) -> None:
        self.table.setRowCount(0)
        items = self.filtered_memos[(self.current_page - 1) * 10 : self.current_page * 10]
        for m in items:
            r = self.table.rowCount()
            self.table.insertRow(r)
            self.table.setRowHeight(r, 48)
            
            c = QTableWidgetItem("")
            c.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            c.setCheckState(Qt.CheckState.Unchecked)
            self.table.setItem(r, 0, c)
            
            if not self.is_trash_mode:
                is_fav = m.get('is_favorite', False)
                fb = QPushButton()
                fb.setFixedSize(24, 24)
                fb.setCursor(Qt.CursorShape.PointingHandCursor)
                theme = self.ui_manager.sync_manager.settings.get('app_theme', 'white')
                is_dark = (theme == "dark")
                if hasattr(self.ui_manager, 'get_theme_icon'):
                    fb.setIcon(self.ui_manager.get_theme_icon("favorite_true.svg" if is_fav else "favorite_false.svg", is_dark))
                    fb.setIconSize(QSize(16, 16))
                fb.setStyleSheet("border: none; background: transparent;")
                fb.clicked.connect(lambda checked, memo=m: self.toggle_fav(memo))
                cell_w = QWidget()
                cell_l = QHBoxLayout(cell_w)
                cell_l.addWidget(fb)
                cell_l.setAlignment(Qt.AlignmentFlag.AlignCenter)
                cell_l.setContentsMargins(0, 0, 0, 0)
                self.table.setCellWidget(r, 1, cell_w)
            else: 
                self.table.setCellWidget(r, 1, QWidget())
                
            is_code = m.get('is_code_memo', False)
            title_text = m.get('title', '').strip()
            theme = self.ui_manager.sync_manager.settings.get('app_theme', 'white')
            is_dark = (theme == "dark")
            
            is_pinned = m.get('is_pinned', False)
            
            if is_code:
                lang = m.get('code_lang', 'JSON')
                badge_text = f"[{lang}] {title_text}"
            else:
                badge_text = f"{title_text}"

            t = QTableWidgetItem(badge_text)
            if hasattr(self.ui_manager, 'get_theme_icon'):
                if is_pinned:
                    t.setIcon(self.ui_manager.get_theme_icon("pin_icon_True.svg", is_dark))
                else:
                    t.setIcon(self.ui_manager.get_theme_icon("codememo.svg" if is_code else "memo.svg", is_dark))
            t.setData(Qt.ItemDataRole.UserRole, m)
            t.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
            
            if is_code:
                t.setFont(QFont("D2Coding", 10, QFont.Weight.Bold))
                
            self.table.setItem(r, 2, t)
            
            up = m.get('updated_at', '')
            ds = datetime.datetime.fromisoformat(up).strftime("%Y-%m-%d %H:%M") if up else ""
            dt = QTableWidgetItem(ds)
            dt.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
            self.table.setItem(r, 3, dt)
            
            is_prot = m.get('is_protected', False)
            prot_btn = QPushButton(" 잠김" if is_prot else " 해제")
            if hasattr(self.ui_manager, 'get_theme_icon'):
                prot_btn.setIcon(self.ui_manager.get_theme_icon("lock_close.svg" if is_prot else "lock_open.svg", is_dark))
            prot_btn.setFixedSize(76, 28)
            prot_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            
            if is_prot:
                prot_btn.setStyleSheet("QPushButton { background: rgba(255, 69, 58, 0.2); color: #FF453A; border: 1px solid rgba(255, 69, 58, 0.4); border-radius: 10px; font-weight: bold; font-size: 8.5pt; }")
            else:
                prot_btn.setStyleSheet("QPushButton { background: rgba(142, 142, 147, 0.15); color: #8E8E93; border: 1px solid rgba(142, 142, 147, 0.3); border-radius: 10px; font-weight: bold; font-size: 8.5pt; } QPushButton:hover { background: rgba(142, 142, 147, 0.3); }")
                
            prot_btn.clicked.connect(lambda checked, memo=m: self.toggle_protect(memo))
            
            cell_p_w = QWidget()
            cell_p_l = QHBoxLayout(cell_p_w)
            cell_p_l.addWidget(prot_btn)
            cell_p_l.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cell_p_l.setContentsMargins(0, 0, 0, 0)
            self.table.setCellWidget(r, 4, cell_p_w)
            
        self.p_l.setText(f"{self.current_page} / {max(1, (len(self.filtered_memos) + 9) // 10)}")
        
    def toggle_fav(self, memo: Dict[str, Any]) -> None:
        memo['is_favorite'] = not memo.get('is_favorite', False)
        self.ui_manager.sync_manager.save_memo_locally(memo)
        self.refresh()

    def del_checked(self) -> None:
        checked_memos = []
        for r in range(self.table.rowCount()):
            item_cb = self.table.item(r, 0)
            if item_cb and item_cb.checkState() == Qt.CheckState.Checked:
                m = self.table.item(r, 2).data(Qt.ItemDataRole.UserRole)
                if m and m not in checked_memos:
                    checked_memos.append(m)
                    
        if not checked_memos:
            for r in set(index.row() for index in self.table.selectedIndexes()):
                m = self.table.item(r, 2).data(Qt.ItemDataRole.UserRole)
                if m and m not in checked_memos:
                    checked_memos.append(m)

        protected_memos = [m for m in checked_memos if m.get('is_protected')]
        if protected_memos:
            self.show_toast(f"🔒 {len(protected_memos)}개 메모가 삭제 방지 상태입니다.")
            checked_memos = [m for m in checked_memos if not m.get('is_protected')]

        if checked_memos and QMessageBox.question(self, "일괄 삭제", f"선택한 {len(checked_memos)}개 메모를 휴지통으로 이동할까요?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            deleted_ids = []
            for m in checked_memos:
                memo_id = m.get('id')
                if memo_id:
                    self.ui_manager.close_memo_window_by_id(memo_id, is_deleting=True)
                    self.ui_manager.sync_manager.delete_memo_locally(memo_id, title=m.get('title'))
                    deleted_ids.append(memo_id)
            self.ui_manager.sync_manager.delete_memos_cloud(deleted_ids)
            self.pv.clear() 
            self.refresh()

    def res_checked(self) -> None:
        for r in range(self.table.rowCount()):
            if self.table.item(r, 0).checkState() == Qt.CheckState.Checked:
                m = self.table.item(r, 2).data(Qt.ItemDataRole.UserRole)
                memo_id = m.get('id')
                title = m.get('title', '')
                if memo_id:
                    ex = next((x for x in self.ui_manager.sync_manager.load_local_memos() if x.get('id') == memo_id), None)
                    if not ex or ConflictDialog(title, ex.get('content', ''), m.get('content', '')).exec() == QDialog.DialogCode.Accepted:
                        self.ui_manager.sync_manager.restore_memo_locally(memo_id)
        self.pv.clear()
        self.refresh()