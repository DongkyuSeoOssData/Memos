from ui.memo_editor import MemoTextEdit, CodeHighlighter
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

class MemoWindow(QWidget):
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
        
        self.highlighter: Optional[CodeHighlighter] = None
        
        self.setup_ui()
        self.apply_data()
        self.bind_shortcuts()
        
        self.setMouseTracking(True)
        self.text_edit.setMouseTracking(True)
        self.text_edit.cursorPositionChanged.connect(self.update_toolbar_button_states)
        
        self.toast_label = QLabel(self)
        self.toast_label.setStyleSheet("background-color: rgba(0, 122, 255, 0.8); color: white; font-weight: bold; border-radius: 10px; padding: 6px 14px; font-size: 9.5pt;")
        self.toast_label.hide()
        self.toast_timer = QTimer(self)
        self.toast_timer.setSingleShot(True)
        self.toast_timer.timeout.connect(self.toast_label.hide)

        self._is_deleting = False
        self._title_save_timer = QTimer(self)
        self._title_save_timer.setSingleShot(True)
        self._title_save_timer.timeout.connect(self._do_title_save)

        self._wheel_save_timer = QTimer(self)
        self._wheel_save_timer.setSingleShot(True)
        self._wheel_save_timer.timeout.connect(lambda: self.save_callback(self.memo_data))

    def bind_shortcuts(self) -> None:
        s_cfg = self.memo_window_get_settings().get("shortcuts", {})
        
        QShortcut(QKeySequence(s_cfg.get("save", "Ctrl+S")), self).activated.connect(self.manual_save)
        QShortcut(QKeySequence(s_cfg.get("search", "Ctrl+F")), self).activated.connect(self.show_search_only)
        QShortcut(QKeySequence(s_cfg.get("replace", "Ctrl+H")), self).activated.connect(self.show_search_and_replace)
        QShortcut(QKeySequence(s_cfg.get("rename", "F2")), self).activated.connect(self.enable_rename)
        QShortcut(QKeySequence(s_cfg.get("eng_kor_convert", "Ctrl+Alt+E")), self).activated.connect(self.convert_selected_eng_kor)
        QShortcut(QKeySequence(s_cfg.get("toggle_fmt_bar", "Ctrl+Shift+T")), self).activated.connect(self.toggle_sub_fmt_panel)
        QShortcut(QKeySequence(s_cfg.get("copy_all", "Ctrl+Shift+C")), self).activated.connect(self.copy_all_content)
        QShortcut(QKeySequence(s_cfg.get("format_code", "Ctrl+Shift+F")), self).activated.connect(self.prettify_code)
        
        QShortcut(QKeySequence(s_cfg.get("toggle_pin", "Ctrl+P")), self).activated.connect(self.toggle_pin)
        QShortcut(QKeySequence(s_cfg.get("toggle_rollup", "Ctrl+M")), self).activated.connect(self.toggle_rollup)
        QShortcut(QKeySequence(s_cfg.get("delete_memo", "Ctrl+D")), self).activated.connect(lambda: self.delete_callback(self))
        QShortcut(QKeySequence(s_cfg.get("toggle_code_theme", "Ctrl+Shift+L")), self).activated.connect(self.toggle_code_theme)
        
        if getattr(self, 'ui_manager', None):
            QShortcut(QKeySequence(s_cfg.get("open_explorer", "Ctrl+E")), self).activated.connect(self.ui_manager.open_memo_explorer)
            QShortcut(QKeySequence(s_cfg.get("arrange_rolled_memos", "Ctrl+Alt+R")), self).activated.connect(self.ui_manager.arrange_rolled_up_memos)
            QShortcut(QKeySequence(s_cfg.get("arrange_all_memos", "Ctrl+Alt+A")), self).activated.connect(self.ui_manager.arrange_memos)
            QShortcut(QKeySequence(s_cfg.get("new_memo", "Ctrl+N")), self).activated.connect(self.ui_manager.create_empty_memo)
            QShortcut(QKeySequence(s_cfg.get("new_code_memo", "Ctrl+Shift+N")), self).activated.connect(self.ui_manager.create_code_memo)
            QShortcut(QKeySequence(s_cfg.get("open_all_memos", "Ctrl+Shift+O")), self).activated.connect(self.ui_manager.open_all_memos)
            QShortcut(QKeySequence(s_cfg.get("toggle_all_memos", "Ctrl+Shift+H")), self).activated.connect(self.ui_manager.toggle_all)

        QShortcut(QKeySequence("Esc"), self).activated.connect(self.close)

    def memo_window_get_settings(self) -> Dict[str, Any]:
        return self.ui_manager.sync_manager.settings if getattr(self, 'ui_manager', None) else {}

    def show_toast(self, text: str) -> None:
        self.toast_label.setText(text)
        self.toast_label.adjustSize()
        x = self.width() - self.toast_label.width() - 15
        y = self.height() - (self.fmt_bar.geometry().height() if hasattr(self, 'fmt_bar') else 35) - self.toast_label.height() - 20
        self.toast_label.move(max(10, x), max(10, y))
        self.toast_label.show()
        self.toast_label.raise_()
        self.toast_timer.start(1500)

    def toggle_line_numbers(self) -> None:
        self.memo_data['show_line_numbers'] = not self.memo_data.get('show_line_numbers', False)
        self.text_edit.update_line_number_area()
        self.save_callback(self.memo_data)

    def toggle_line_bg(self) -> None:
        self.memo_data['show_line_bg'] = not self.memo_data.get('show_line_bg', False)
        self.text_edit.viewport().update()
        self.save_callback(self.memo_data)

    def apply_line_bg_style(self) -> None:
        is_code_memo = self.memo_data.get('is_code_memo', False)
        if is_code_memo:
            code_theme = self.memo_data.get('code_theme', 'dark')
            is_dark_bg = (code_theme == "dark")
        else:
            bg_color = self.memo_data.get('bg_color', '#FFFFFF')
            is_dark_bg = True if bg_color in ['#2E3440', '#1C1C1E', '#000000'] else False
            if not is_dark_bg:
                c_obj = QColor(bg_color)
                if c_obj.isValid():
                    lum = (0.299 * c_obj.red() + 0.587 * c_obj.green() + 0.114 * c_obj.blue()) / 255.0
                    if lum < 0.5:
                        is_dark_bg = True

        text_color = "#F2F2F7" if is_dark_bg else "#1C1C1E"
        line_color = "rgba(255,255,255,0.15)" if is_dark_bg else "rgba(0,0,0,0.15)"
        
        font_fam = "'D2Coding'" if is_code_memo else "'D2Coding', 'Consolas', monospace"
        font_size = f"{self.memo_data.get('font_size', 11)}pt"
        style_str = f"QTextEdit {{ border:none; background: transparent; color:{text_color}; font-family: {font_fam}; font-size: {font_size}; }}"
        
        if self.memo_data.get('show_line_bg', False):
            self.text_edit.setStyleSheet(style_str)
        else:
            self.text_edit.setStyleSheet(style_str)
        
    def setup_ui(self) -> None:
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.window_layout = QVBoxLayout(self)
        self.window_layout.setContentsMargins(6, 6, 6, 6)
        
        self.bg = QWidget()
        self.bg.setObjectName("MemoBackground")
        self.bg_layout = QVBoxLayout(self.bg)
        bg_l = self.bg_layout
        self.bg_layout.setContentsMargins(14, 10, 14, 14)
        self.window_layout.addWidget(self.bg)
        apply_ios_shadow(self.bg)
        
        ctrl = QHBoxLayout()
        ctrl.setSpacing(6)
        
        # 📌 제목 레이블 (압정 영역 직전까지 확장)
        self.title_edit = QLineEdit()
        self.title_edit.setReadOnly(True)
        self.title_edit.setStyleSheet("border:none; background:transparent; font-weight:bold; font-size:11.5pt; font-family: 'D2Coding', 'Consolas', monospace;")
        self.title_edit.editingFinished.connect(self.handle_rename)
        self.title_edit.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.title_edit.customContextMenuRequested.connect(self.show_menu)
        self.title_edit.installEventFilter(self)
        ctrl.addWidget(self.title_edit, 1)
        
        self.btn_code_theme = QPushButton("")
        self.btn_code_theme.setFixedSize(90, 24)

        self.btn_code_theme.clicked.connect(self.toggle_code_theme)
        self.btn_code_theme.hide()

        self.code_lang_box = QComboBox()
        self.code_lang_box.addItems(["JSON", "C#", "VB.NET", "Power Automate", "PowerShell", "Batch (CMD)", "SQL", "Markdown", "Python", "JavaScript", "HTML", "CSS", "C++", "Java", "Plain Text"])
        self.code_lang_box.setFixedHeight(24)
        self.code_lang_box.setStyleSheet("font-size: 8.5pt; font-weight: bold; padding: 0 4px; border: 1px solid #0A84FF; border-radius: 10px; background: #1C1C1E; color: #0A84FF;")
        self.code_lang_box.currentTextChanged.connect(self.on_code_lang_changed)
        self.code_lang_box.hide()
        
        # 언어 선택 아이콘 버튼 (language.svg) - 콤보박스와 함께 표시
        self.btn_lang_icon = QPushButton("")
        self.btn_lang_icon.setFixedSize(24, 24)
        self.btn_lang_icon.setEnabled(False)  # 클릭 불가, 아이콘 표시 전용
        self.btn_lang_icon.setStyleSheet("QPushButton { background: transparent; border: none; }")
        self.btn_lang_icon.hide()

        ctrl.addWidget(self.btn_code_theme)
        ctrl.addWidget(self.btn_lang_icon)
        ctrl.addWidget(self.code_lang_box)
        ctrl.addStretch()

        # 핀 버튼
        self.btn_pin = QPushButton("")
        self.btn_pin.setFixedSize(28, 26)
        self.btn_pin.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_pin.setToolTip("화면 고정 토글 (Ctrl+P)")
        self.btn_pin.clicked.connect(self.toggle_pin)
        ctrl.addWidget(self.btn_pin)

        self.btn_min   = QPushButton("")
        self.btn_max   = QPushButton("")
        self.btn_close = QPushButton("")

        for b_item, tip in [(self.btn_min, "최소화/접기 (Ctrl+M)"), (self.btn_max, "최대화"), (self.btn_close, "닫기 (Esc)")]:
            b_item.setFixedSize(28, 26)
            b_item.setCursor(Qt.CursorShape.PointingHandCursor)
            b_item.setToolTip(tip)
            ctrl.addWidget(b_item)

        self.btn_min.clicked.connect(self.toggle_rollup)
        self.btn_max.clicked.connect(self.toggle_maximize)
        self.btn_close.clicked.connect(self.close)

        bg_l.addLayout(ctrl)
        
        self.content_container = QWidget()
        cc_layout = QVBoxLayout(self.content_container)
        cc_layout.setContentsMargins(0, 0, 0, 0)
        
        self.text_edit = MemoTextEdit(self)
        self.text_edit.setStyleSheet("border:none; background:transparent;")
        self.text_edit.textChanged.connect(self.update_content)
        self.text_edit.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.text_edit.customContextMenuRequested.connect(self.show_menu)
        self.text_edit.installEventFilter(self)
        
        self.toast = QLabel("")
        self.toast.setStyleSheet("color: #0A84FF; font-weight: bold; font-size: 10pt;")
        self.toast.hide()
        
        cc_layout.addWidget(self.toast, alignment=Qt.AlignmentFlag.AlignCenter)
        cc_layout.addWidget(self.text_edit)
        
        self.search_bar = QWidget()
        sl = QHBoxLayout(self.search_bar)
        sl.setContentsMargins(0, 4, 0, 4)
        
        self.s_in = QLineEdit()
        self.s_in.setPlaceholderText("찾을 단어")
        self.s_in.setStyleSheet("padding:6px; border:1px solid #C7C7CC; border-radius:8px; background:white; color:#000000;")
        self.s_in.returnPressed.connect(lambda: self.do_find(backward=False))
        
        self.s_count = QLabel("0/0")
        self.s_count.setStyleSheet("color: #007AFF; font-weight: bold; padding: 0 5px;")
        
        self.s_prev_btn = QPushButton("▲")
        self.s_prev_btn.setFixedSize(24, 24)
        self.s_prev_btn.setStyleSheet("background:#F2F2F7; color:#000000; border:1px solid #C7C7CC; border-radius:6px; font-weight:bold;")
        self.s_prev_btn.clicked.connect(lambda: self.do_find(backward=True))
        
        self.s_next_btn = QPushButton("▼")
        self.s_next_btn.setFixedSize(24, 24)
        self.s_next_btn.setStyleSheet("background:#F2F2F7; color:#000000; border:1px solid #C7C7CC; border-radius:6px; font-weight:bold;")
        self.s_next_btn.clicked.connect(lambda: self.do_find(backward=False))
        
        self.r_in = QLineEdit()
        self.r_in.setPlaceholderText("바꿀 단어")
        self.r_in.setStyleSheet("padding:6px; border:1px solid #C7C7CC; border-radius:8px; background:white; color:#000000;")
        self.r_in.returnPressed.connect(self.do_replace)
        
        self.r_btn = QPushButton("바꾸기")
        self.r_btn.setStyleSheet("background:#007AFF; color:white; border:none; border-radius:8px; padding:6px; font-weight:bold;")
        self.r_btn.clicked.connect(self.do_replace)
        
        self.s_close = QPushButton("")
        self.s_close.setFixedSize(24, 24)
        self.s_close.setStyleSheet("border:none; background:transparent;")
        if getattr(self, 'ui_manager', None) and hasattr(self.ui_manager, 'get_theme_icon'):
            self.s_close.setIcon(self.ui_manager.get_theme_icon("close.svg", False, override_color="#FF453A"))
        self.s_close.clicked.connect(self.search_bar.hide)
        
        for w in [self.s_in, self.s_count, self.s_prev_btn, self.s_next_btn, self.r_in, self.r_btn, self.s_close]: 
            sl.addWidget(w)
            
        self.search_bar.hide()
        cc_layout.addWidget(self.search_bar)
        
        self.fmt_bar = QHBoxLayout()
        self.fmt_bar.setContentsMargins(0, 4, 0, 0)
        self.fmt_bar.setSpacing(4)
        
        self.btn_bullet = QPushButton("")
        self.btn_num = QPushButton("")
        self.btn_indent = QPushButton("")
        self.btn_outdent = QPushButton("")
        
        self.btn_bold = QPushButton("B")
        self.btn_bold.setStyleSheet("font-weight: bold;")
        self.btn_italic = QPushButton("I")
        self.btn_italic.setStyleSheet("font-style: italic; font-family: 'Times New Roman';")
        self.btn_underline = QPushButton("U")
        self.btn_underline.setStyleSheet("text-decoration: underline;")
        
        for b in [self.btn_bullet, self.btn_num, self.btn_indent, self.btn_outdent, self.btn_bold, self.btn_italic, self.btn_underline]:
            b.setFixedSize(24, 24)
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            self.fmt_bar.addWidget(b)
            
        self.btn_bullet.clicked.connect(self.apply_bullet)
        self.btn_num.clicked.connect(self.apply_number)
        self.btn_indent.clicked.connect(self.apply_indent)
        self.btn_outdent.clicked.connect(self.apply_outdent)
        self.btn_bold.clicked.connect(self.toggle_bold)
        self.btn_italic.clicked.connect(self.toggle_italic)
        self.btn_underline.clicked.connect(self.toggle_underline)
        
        self.btn_format_code = QPushButton("{} 정렬")
        self.btn_format_code.setFixedHeight(24)
        self.btn_format_code.clicked.connect(self.prettify_code)
        self.btn_format_code.hide()
        self.fmt_bar.addWidget(self.btn_format_code)

        self.btn_toggle_sub_fmt = QPushButton("Aa ▾")
        self.btn_toggle_sub_fmt.setFixedHeight(24)
        self.btn_toggle_sub_fmt.clicked.connect(self.toggle_sub_fmt_panel)
        self.fmt_bar.addWidget(self.btn_toggle_sub_fmt)
        
        self.fmt_bar.addStretch()
        
        self.sub_fmt_widget = QWidget()
        sub_l = QHBoxLayout(self.sub_fmt_widget)
        sub_l.setContentsMargins(0, 2, 0, 0)
        sub_l.setSpacing(4)
        
        self.font_box = QFontComboBox()
        self.font_box.setMaximumWidth(120)
        self.font_box.setFixedHeight(24)
        self.font_box.setStyleSheet("font-size: 8.5pt; padding: 0px 4px; border: 1px solid #C7C7CC; border-radius: 6px; background: white; color: black;")
        self.font_box.currentFontChanged.connect(self.change_font_family)
        sub_l.addWidget(self.font_box)
        
        self.size_box = QComboBox()
        self.size_box.setFixedSize(48, 24)
        self.size_box.setStyleSheet("font-size: 8.5pt; padding: 0px 2px; border: 1px solid #C7C7CC; border-radius: 6px; background: white; color: black;")
        for sz in [8, 9, 10, 11, 12, 14, 16, 18, 20, 24, 28, 32, 36, 48, 72]:
            self.size_box.addItem(str(sz))
        self.size_box.setCurrentText(str(self.memo_data.get('font_size', 11)))
        self.size_box.currentTextChanged.connect(self.change_font_size)
        sub_l.addWidget(self.size_box)
        
        self.btn_fg_color = QPushButton("A")
        self.btn_fg_color.setFixedSize(24, 24)
        self.btn_fg_color.setToolTip("글씨색 선택 (RGB)")
        self.btn_fg_color.clicked.connect(self.choose_fg_color)
        sub_l.addWidget(self.btn_fg_color)

        self.btn_bg_color = QPushButton("▣")
        self.btn_bg_color.setFixedSize(24, 24)
        self.btn_bg_color.setToolTip("글씨 배경색 / 형광펜")
        self.btn_bg_color.clicked.connect(self.show_bg_color_menu)
        sub_l.addWidget(self.btn_bg_color)
        sub_l.addStretch()
        
        self.sub_fmt_widget.hide()
        
        cc_layout.addLayout(self.fmt_bar)
        cc_layout.addWidget(self.sub_fmt_widget)
        
        self.update_toolbar_button_states()
        bg_l.addWidget(self.content_container)
        self.grip = QSizeGrip(self)

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

    def toggle_code_theme(self) -> None:
        """코드 테마 사용자 수동 전환"""
        self.memo_data['content'] = self.text_edit.toHtml()
        cur = self.memo_data.get('code_theme',
              'dark' if self.memo_window_get_settings().get('app_theme', 'white') == 'dark' else 'light')
        new_theme = "light" if cur == "dark" else "dark"
        self.memo_data['code_theme'] = new_theme
        self.memo_data['code_theme_user_set'] = True
        self.apply_data()
        self.update()
        self.repaint()
        self.text_edit.viewport().update()
        self.manual_save()

    def update_toolbar_button_states(self) -> None:
        fmt = self.text_edit.currentCharFormat()
        is_code = self.memo_data.get('is_code_memo', False)
        if is_code:
            code_theme = self.memo_data.get('code_theme', 'dark')
            is_memo_dark_bg = (code_theme == "dark")
        else:
            bg_color = self.memo_data.get('bg_color', '#FFFFFF')
            if bg_color == "random": bg_color = "#FFFFFF"
            is_memo_dark_bg = True if bg_color in ['#2E3440', '#1C1C1E', '#000000'] else False
            if not is_memo_dark_bg:
                c_obj = QColor(bg_color)
                if c_obj.isValid():
                    lum = (0.299 * c_obj.red() + 0.587 * c_obj.green() + 0.114 * c_obj.blue()) / 255.0
                    if lum < 0.5:
                        is_memo_dark_bg = True
        
        btn_text_color = '#FFFFFF' if is_memo_dark_bg else '#000000'
        btn_style_off = f"border:none; color:{btn_text_color}; font-size:10pt; background: transparent; font-weight:bold; border-radius: 4px;"
        btn_style_on = "border:none; color:white; font-size:10pt; background: #007AFF; font-weight:bold; border-radius: 4px;"

        if getattr(self, 'ui_manager', None) and hasattr(self.ui_manager, 'get_theme_icon'):
            self.btn_bullet.setText("")
            self.btn_bullet.setIcon(self.ui_manager.get_theme_icon("bullet_icon_177745.svg", is_memo_dark_bg))
            self.btn_num.setText("")
            self.btn_num.setIcon(self.ui_manager.get_theme_icon("list_numbers_icon_172368.svg", is_memo_dark_bg))
            self.btn_indent.setText("")
            self.btn_indent.setIcon(self.ui_manager.get_theme_icon("들여쓰기.svg", is_memo_dark_bg))
            self.btn_outdent.setText("")
            self.btn_outdent.setIcon(self.ui_manager.get_theme_icon("내어쓰기.svg", is_memo_dark_bg))

        is_bold = fmt.fontWeight() == QFont.Weight.Bold
        self.btn_bold.setChecked(is_bold)
        self.btn_bold.setStyleSheet(btn_style_on if is_bold else btn_style_off)

        is_italic = fmt.fontItalic()
        self.btn_italic.setChecked(is_italic)
        self.btn_italic.setStyleSheet(btn_style_on if is_italic else btn_style_off)

        is_underline = fmt.fontUnderline()
        self.btn_underline.setChecked(is_underline)
        self.btn_underline.setStyleSheet(btn_style_on if is_underline else btn_style_off)

        cursor = self.text_edit.textCursor()
        cur_list = cursor.currentList()
        is_bullet = False
        is_num = False
        if cur_list:
            style = cur_list.format().style()
            is_bullet = (style == QTextListFormat.Style.ListDisc)
            is_num = (style == QTextListFormat.Style.ListDecimal)
            
        self.btn_bullet.setChecked(is_bullet)
        self.btn_bullet.setStyleSheet(btn_style_on if is_bullet else btn_style_off)

        self.btn_num.setChecked(is_num)
        self.btn_num.setStyleSheet(btn_style_on if is_num else btn_style_off)

    def toggle_sub_fmt_panel(self) -> None:
        is_vis = self.sub_fmt_widget.isVisible()
        self.sub_fmt_widget.setVisible(not is_vis)
        self.btn_toggle_sub_fmt.setText("Aa ▴" if not is_vis else "Aa ▾")

    def on_code_lang_changed(self, lang: str) -> None:
        self.memo_data['code_lang'] = lang
        theme = self.memo_data.get('code_theme', 'dark')
        self.highlighter = CodeHighlighter(self.text_edit.document(), lang, theme)
        self.manual_save()

    def prettify_code(self) -> None:
        """JSON / 기타 코드 자동 정렬 — 정렬 후 하이라이터 및 글씨색 강제 재적용."""
        raw_code = self.text_edit.toPlainText().strip()
        if not raw_code:
            return
        lang = self.memo_data.get('code_lang', 'JSON').upper()
        code_theme = self.memo_data.get('code_theme', 'dark')
        code_text = "#F2F2F7" if code_theme == "dark" else "#1C1C1E"

        def _apply_after_format(formatted: str) -> None:
            """setPlainText 적용 후 하이라이터 및 글씨색 복원."""
            self.text_edit.setPlainText(formatted)
            # 하이라이터 재적용
            self.highlighter = CodeHighlighter(self.text_edit.document(), lang, code_theme)
            # 전체 글씨새 재적용
            cursor = self.text_edit.textCursor()
            cursor.select(QTextCursor.SelectionType.Document)
            base_fmt = QTextCharFormat()
            base_fmt.setForeground(QColor(code_text))
            cursor.mergeCharFormat(base_fmt)
            self.manual_save()

        if "JSON" in lang:
            try:
                parsed = json.loads(raw_code)
                formatted = json.dumps(parsed, indent=2, ensure_ascii=False)
                _apply_after_format(formatted)
                self.show_toast("✨ JSON 코드 자동 정렬 완료")
                return
            except Exception:
                self.show_toast("⚠️ JSON 구문 오류 (정렬 안 됨)")
                return

        lines = raw_code.splitlines()
        formatted_lines: list = []
        indent = 0
        for line in lines:
            stripped = line.strip()
            if stripped.startswith('}') or stripped.startswith(']'):
                indent = max(0, indent - 1)
            formatted_lines.append("  " * indent + stripped)
            if stripped.endswith('{') or stripped.endswith('['):
                indent += 1

        _apply_after_format("\n".join(formatted_lines))
        self.show_toast("✨ 코드 인덴트 정렬 완료")

    def show_bg_color_menu(self) -> None:
        menu = QMenu(self)
        menu.setStyleSheet("QMenu { background: white; color: #000000; border: 1px solid #C7C7CC; border-radius: 8px; } QMenu::item:selected { background-color: #007AFF; color: white; }")
        
        menu.addAction("❌ 배경색 없음 (투명)").triggered.connect(lambda: self.set_text_bg_color(QColor(0, 0, 0, 0)))
        menu.addSeparator()
        
        highlights = {
            "🟡 노란색 형광펜": "#FEF08A",
            "🟢 연두색 형광펜": "#BBF7D0",
            "🔵 하늘색 형광펜": "#BAE6FD",
            "🩷 분홍색 형광펜": "#FBCFE8"
        }
        for name, hex_code in highlights.items():
            menu.addAction(name).triggered.connect(lambda checked, c=hex_code: self.set_text_bg_color(QColor(c)))
            
        menu.addSeparator()
        menu.addAction("사용자 지정 RGB 색상...").triggered.connect(self.choose_bg_color)
        menu.exec(self.btn_bg_color.mapToGlobal(QPoint(0, self.btn_bg_color.height())))

    def set_text_bg_color(self, color: QColor) -> None:
        fmt = self.text_edit.currentCharFormat()
        fmt.setBackground(color)
        self.text_edit.mergeCurrentCharFormat(fmt)
        bg_style = color.name() if color.alpha() > 0 else "white"
        self.btn_bg_color.setStyleSheet(f"border: 1px solid #C7C7CC; border-radius: 6px; background: {bg_style};")
        self.manual_save()

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
    
    def find_snap_target_memo(self) -> Optional['MemoWindow']:
        if not getattr(self, 'ui_manager', None):
            return None
            
        memos_below = []
        memos_above = []
        
        for other_id, other_win in self.ui_manager.memo_windows.items():
            if other_win is self or not other_win.isVisible() or not other_win._is_rolled_up:
                continue
            
            # 📌 수직 15px 이내 직접 맞닿아 있고 가로 영역이 겹칠 때만(붙어있을 때만) 탐색
            touch_below = abs(other_win.y() - (self.y() + self.height())) <= 15
            touch_above = abs((other_win.y() + other_win.height()) - self.y()) <= 15
            horiz_overlap = (self.x() < other_win.x() + other_win.width()) and (self.x() + self.width() > other_win.x())
            
            if (touch_below or touch_above) and horiz_overlap:
                dy = other_win.y() - self.y()
                if dy > 0:
                    memos_below.append((dy, other_win))
                elif dy < 0:
                    memos_above.append((abs(dy), other_win))
            
        if memos_below:
            memos_below.sort(key=lambda item: item[0])
            return memos_below[0][1]
        if memos_above:
            memos_above.sort(key=lambda item: item[0])
            return memos_above[0][1]
            
        return None

    def resizeEvent(self, event: Any) -> None:
        super().resizeEvent(event)
        if hasattr(self, 'grip'):
            # 📌 접힌 메모와 동일하게 메모 안쪽에 딱 알맞게 안착 (삐져나옴 방지)
            if self._is_rolled_up:
                self.grip.move(self.width() - 18, self.height() - 18)
            else:
                self.grip.move(self.width() - 20, self.height() - 20)
            self.grip.resize(12, 12)

        # 📌 접힌 상태에서 맞닿아 있을 때만 12px 스냅 멈춤 & 15px 이상 끌면 이탈하여 가로 자유 조절
        if self._is_rolled_up:
            self.memo_data['rolled_width'] = self.width()
            if self.height() != 53:
                self.resize(self.width(), 53)
            target_win = self.find_snap_target_memo()
            if target_win:
                target_w = target_win.width()
                mouse_x = QCursor.pos().x()
                
                if getattr(self, '_sticky_snap_origin', None):
                    start_mouse_x, snap_w = self._sticky_snap_origin
                    if abs(mouse_x - start_mouse_x) > 15:
                        self._sticky_snap_origin = None  # 15px 이상 당기면 자석 이탈!
                    else:
                        self.resize(snap_w, 53)
                        return
                
                if not getattr(self, '_sticky_snap_origin', None):
                    if abs(self.width() - target_w) <= 12:
                        self.resize(target_w, 53)
                        self._sticky_snap_origin = (mouse_x, target_w)
            else:
                self._sticky_snap_origin = None
        else:
            self.memo_data['unrolled_width'] = self.width()
            self.memo_data['unrolled_height'] = self.height()
            self.memo_data['width'] = self.width()
            self.memo_data['height'] = self.height()
        
    def show_menu(self, pos: QPoint) -> None:
        menu = QMenu(self)
        menu.setStyleSheet("QMenu { background: white; color: #000000; border: 1px solid #C7C7CC; border-radius: 8px; } QMenu::item:selected { background-color: #007AFF; color: white; }")
        
        s = self.memo_window_get_settings()
        sc = s.get("shortcuts", {})
        def _fmt_sc(title: str, key: str, default: str) -> str:
            val = sc.get(key, default)
            return f"{title} ({val})" if val else title

        sender_widget = self.sender()
        if hasattr(sender_widget, 'copy'):
            menu.addAction("복사 (Ctrl+C)").triggered.connect(sender_widget.copy)
            menu.addAction("잘라내기 (Ctrl+X)").triggered.connect(sender_widget.cut)
            menu.addAction("붙여넣기 (Ctrl+V)").triggered.connect(sender_widget.paste)
            menu.addAction("모두 선택 (Ctrl+A)").triggered.connect(sender_widget.selectAll)
            menu.addSeparator()

        is_code = self.memo_data.get('is_code_memo', False)
        if is_code:
            menu.addAction(_fmt_sc("코드 자동 정렬", "format_code", "Ctrl+Shift+F")).triggered.connect(self.prettify_code)
            menu.addAction("코드만 클립보드 복사").triggered.connect(self.copy_all_content)
            menu.addAction(_fmt_sc("코드 테마 전환", "toggle_code_theme", "Ctrl+Shift+L")).triggered.connect(self.toggle_code_theme)
        else:
            menu.addAction(_fmt_sc("전체 메모 내용 복사 (클립보드)", "copy_all", "Ctrl+Shift+C")).triggered.connect(self.copy_all_content)
            
        menu.addAction(_fmt_sc("한/영 영타 오타 변환", "eng_kor_convert", "Ctrl+Alt+E")).triggered.connect(self.convert_selected_eng_kor)
        
        menu.addSeparator()
        
        is_auto_convert = s.get("auto_eng_kor_convert", True)
        auto_convert_action = menu.addAction(f"한/영 자동 변환기 [{ 'ON' if is_auto_convert else 'OFF' }]")
        auto_convert_action.setCheckable(True)
        auto_convert_action.setChecked(is_auto_convert)
        auto_convert_action.triggered.connect(self.toggle_auto_eng_kor_setting)
        
        menu.addSeparator()
        menu.addAction(_fmt_sc("메모 탐색기 열기", "open_explorer", "Ctrl+E")).triggered.connect(self.ui_manager.open_memo_explorer)
        menu.addAction(_fmt_sc("저장", "save", "Ctrl+S")).triggered.connect(self.manual_save)
        menu.addAction(_fmt_sc("검색", "search", "Ctrl+F")).triggered.connect(self.show_search_only)
        menu.addAction(_fmt_sc("바꾸기", "replace", "Ctrl+H")).triggered.connect(self.show_search_and_replace)
        menu.addAction(_fmt_sc("화면 고정 토글", "toggle_pin", "Ctrl+P")).triggered.connect(self.toggle_pin)
        menu.addAction(_fmt_sc("메모 창 접기", "toggle_rollup", "Ctrl+M")).triggered.connect(self.toggle_rollup)
        
        ln_action = menu.addAction("행번호 표시")
        ln_action.setCheckable(True)
        ln_action.setChecked(self.memo_data.get('show_line_numbers', False))
        ln_action.triggered.connect(self.toggle_line_numbers)
        
        bg_action = menu.addAction("줄노트 배경")
        bg_action.setCheckable(True)
        bg_action.setChecked(self.memo_data.get('show_line_bg', False))
        bg_action.triggered.connect(self.toggle_line_bg)
        
        if not is_code:
            menu.addSeparator()
            cm = menu.addMenu("창 배경색 변경")
            for n, c in {"다크그레이": "#2E3440", "하늘색": "#E0F2FE", "연두색": "#DCFCE7", "노란색": "#FEF9C3", "분홍색": "#FCE7F3", "흰색": "#FFFFFF"}.items(): 
                cm.addAction(n).triggered.connect(lambda checked, code=c: self.change_color(code))

        menu.addSeparator()
        # 🔆 투명도 슬라이더 서브메뉴
        opacity_menu = menu.addMenu("창 투명도 조절")
        opacity_widget = QWidget()
        opacity_layout = QHBoxLayout(opacity_widget)
        opacity_layout.setContentsMargins(12, 6, 12, 6)
        opacity_layout.setSpacing(8)
        cur_opacity_pct = int(round(float(self.memo_data.get('opacity', 1.0)) * 100))
        opa_label = QLabel(f"불투명도: {cur_opacity_pct}%")
        opa_label.setStyleSheet("color: #007AFF; font-weight: bold; font-size: 9pt; min-width: 90px;")
        opa_slider = QSlider(Qt.Orientation.Horizontal)
        opa_slider.setRange(20, 100)
        opa_slider.setValue(cur_opacity_pct)
        opa_slider.setFixedWidth(160)
        opa_slider.setStyleSheet("""
            QSlider::groove:horizontal { height: 4px; background: #C7C7CC; border-radius: 2px; }
            QSlider::handle:horizontal { width: 18px; height: 18px; margin: -7px 0; background: #007AFF; border-radius: 9px; }
            QSlider::sub-page:horizontal { background: #007AFF; border-radius: 2px; }
        """)
        def _update_opacity(val: int) -> None:
            opa_label.setText(f"불투명도: {val}%")
            self.memo_data['opacity'] = round(val / 100.0, 2)
            self.setWindowOpacity(self.memo_data['opacity'])
            self._auto_save_timer.start(1000)
        opa_slider.valueChanged.connect(_update_opacity)
        opacity_layout.addWidget(opa_label)
        opacity_layout.addWidget(opa_slider)
        opa_action = QWidgetAction(opacity_menu)
        opa_action.setDefaultWidget(opacity_widget)
        opacity_menu.addAction(opa_action)
        opacity_menu.addSeparator()
        opacity_menu.addAction("100% (완전 불투명)").triggered.connect(lambda: opa_slider.setValue(100))
        opacity_menu.addAction("80% (약간 투명)").triggered.connect(lambda: opa_slider.setValue(80))
        opacity_menu.addAction("60% (반투명)").triggered.connect(lambda: opa_slider.setValue(60))
        opacity_menu.addAction("40% (많이 투명)").triggered.connect(lambda: opa_slider.setValue(40))

        menu.addSeparator()
        menu.addAction(_fmt_sc("메모 삭제", "delete_memo", "Ctrl+D")).triggered.connect(lambda: self.delete_callback(self))
        menu.exec(self.sender().mapToGlobal(pos))

    def toggle_auto_eng_kor_setting(self) -> None:
        sm = getattr(self.close_callback, '__self__', None).sync_manager
        cur = sm.settings.get("auto_eng_kor_convert", True)
        sm.settings["auto_eng_kor_convert"] = not cur
        sm.save_settings(sm.settings)
        self.show_toast(f"🔤 한/영 자동 변환기: {'ON' if not cur else 'OFF'}")

    def convert_selected_eng_kor(self) -> None:
        cursor = self.text_edit.textCursor()
        if cursor.hasSelection():
            txt = cursor.selectedText()
            converted = convert_eng_kor_smart(txt)
            cursor.insertText(converted)
        else:
            txt = self.text_edit.toPlainText()
            converted = convert_eng_kor_smart(txt)
            self.text_edit.setPlainText(converted)
        self.manual_save()
        self.show_toast("🔤 한/영 영타 변환 완료")

    def copy_all_content(self) -> None:
        if self.memo_data.get('is_code_memo', False):
            plain_text = self.text_edit.toPlainText()
        else:
            plain_text = clean_plain_text(self.text_edit.toHtml())
        cb = QApplication.clipboard()
        cb.setText(plain_text)
        self.show_toast("📋 클립보드에 복사되었습니다.")

    def show_search_only(self) -> None:
        self.r_in.hide()
        self.r_btn.hide()
        self.search_bar.show()
        self.s_in.setFocus()
        self.s_in.selectAll()

    def show_search_and_replace(self) -> None:
        self.r_in.show()
        self.r_btn.show()
        self.search_bar.show()
        self.s_in.setFocus()
        self.s_in.selectAll()

    def do_find(self, backward: bool = False) -> None:
        search_text = self.s_in.text()
        if not search_text:
            self.s_count.setText("0/0")
            return
            
        p = self.text_edit.palette()
        p.setColor(QPalette.ColorRole.Highlight, QColor("#007AFF"))
        p.setColor(QPalette.ColorRole.HighlightedText, QColor("#FFFFFF"))
        self.text_edit.setPalette(p)

        if backward:
            found = self.text_edit.find(search_text, QTextDocument.FindFlag.FindBackward)
        else:
            found = self.text_edit.find(search_text)

        if not found:
            c = self.text_edit.textCursor()
            c.movePosition(QTextCursor.MoveOperation.End if backward else QTextCursor.MoveOperation.Start)
            self.text_edit.setTextCursor(c)
            found = self.text_edit.find(search_text, QTextDocument.FindFlag.FindBackward if backward else QTextDocument.FindFlag(0))

        if found:
            text = self.text_edit.toPlainText().lower()
            st_low = search_text.lower()
            total = text.count(st_low)
            cursor_pos = self.text_edit.textCursor().position()
            current = text[:cursor_pos].count(st_low)
            if backward and current == 0 and total > 0: current = 1
            self.s_count.setText(f"{current}/{total}")
        else:
            self.s_count.setText("0/0")

    def do_replace(self) -> None:
        c = self.text_edit.textCursor()
        if c.hasSelection() and c.selectedText().lower() == self.s_in.text().lower(): 
            c.insertText(self.r_in.text())
            self.manual_save()
        self.do_find(backward=False)

    def toggle_bold(self) -> None:
        fmt = self.text_edit.currentCharFormat()
        is_bold = fmt.fontWeight() == QFont.Weight.Bold
        fmt.setFontWeight(QFont.Weight.Normal if is_bold else QFont.Weight.Bold)
        self.text_edit.mergeCurrentCharFormat(fmt)
        self.update_toolbar_button_states()
        self.manual_save()

    def toggle_italic(self) -> None:
        fmt = self.text_edit.currentCharFormat()
        fmt.setFontItalic(not fmt.fontItalic())
        self.text_edit.mergeCurrentCharFormat(fmt)
        self.update_toolbar_button_states()
        self.manual_save()

    def toggle_underline(self) -> None:
        fmt = self.text_edit.currentCharFormat()
        fmt.setFontUnderline(not fmt.fontUnderline())
        self.text_edit.mergeCurrentCharFormat(fmt)
        self.update_toolbar_button_states()
        self.manual_save()

    def change_font_family(self, font: QFont) -> None:
        cursor = self.text_edit.textCursor()
        if not cursor.hasSelection():
            cursor.select(QTextCursor.SelectionType.Document)
        fmt = QTextCharFormat()
        fmt.setFontFamily(font.family())
        cursor.mergeCharFormat(fmt)
        self.text_edit.mergeCurrentCharFormat(fmt)
        self.text_edit.setFont(font)
        self.memo_data['font_family'] = font.family()
        self.manual_save()

    def change_font_size(self, size_str: str) -> None:
        if not size_str.isdigit(): return
        sz = int(size_str)
        fmt = self.text_edit.currentCharFormat()
        fmt.setFontPointSize(sz)
        self.text_edit.mergeCurrentCharFormat(fmt)
        self.memo_data['font_size'] = sz
        self._auto_save_timer.start(1000)

    def choose_fg_color(self) -> None:
        color = QColorDialog.getColor(Qt.GlobalColor.black, self, "글씨색 선택")
        if color.isValid():
            cursor = self.text_edit.textCursor()
            fmt = QTextCharFormat()
            fmt.setForeground(color)
            if cursor.hasSelection():
                cursor.mergeCharFormat(fmt)
            else:
                self.text_edit.mergeCurrentCharFormat(fmt)
            
            self.btn_fg_color.setStyleSheet(
                f"font-weight: bold; color: {color.name()}; "
                f"border: 1px solid #C7C7CC; border-radius: 6px; background: white;"
            )
            self.manual_save()

    def choose_bg_color(self) -> None:
        colors = ["#FFFF00", "#00FF00", "#00FFFF", "#FF00FF", "transparent"]
        cur = getattr(self, '_current_bg_idx', -1)
        cur = (cur + 1) % len(colors)
        self._current_bg_idx = cur
        if colors[cur] == "transparent":
            color = QColor(0, 0, 0, 0)
        else:
            color = QColor(colors[cur])
        self.set_text_bg_color(color)

    def apply_bullet(self) -> None:
        cursor = self.text_edit.textCursor()
        current_list = cursor.currentList()
        if current_list:
            if current_list.format().style() == QTextListFormat.Style.ListDisc:
                block = self.text_edit.document().findBlock(cursor.selectionStart())
                end_block = self.text_edit.document().findBlock(cursor.selectionEnd())
                while True:
                    lst = block.textList()
                    if lst:
                        bf = block.blockFormat()
                        bf.setObjectIndex(-1)
                        lst.remove(block)
                        c = QTextCursor(block)
                        c.setBlockFormat(bf)
                    if block == end_block or not block.isValid(): break
                    block = block.next()
            else:
                fmt = current_list.format()
                fmt.setStyle(QTextListFormat.Style.ListDisc)
                current_list.setFormat(fmt)
        else:
            list_fmt = QTextListFormat()
            list_fmt.setStyle(QTextListFormat.Style.ListDisc)
            list_fmt.setIndent(max(1, cursor.blockFormat().indent()))
            prev_block = cursor.block().previous()
            next_block = cursor.block().next()
            target_list = None
            if prev_block.isValid() and prev_block.textList() and prev_block.textList().format().style() == QTextListFormat.Style.ListDisc:
                target_list = prev_block.textList()
            elif next_block.isValid() and next_block.textList() and next_block.textList().format().style() == QTextListFormat.Style.ListDisc:
                target_list = next_block.textList()
            
            if target_list:
                target_list.add(cursor.block())
            else:
                cursor.createList(list_fmt)
        self.update_toolbar_button_states()
        self.manual_save()

    def apply_number(self) -> None:
        cursor = self.text_edit.textCursor()
        current_list = cursor.currentList()
        if current_list:
            if current_list.format().style() == QTextListFormat.Style.ListDecimal:
                block = self.text_edit.document().findBlock(cursor.selectionStart())
                end_block = self.text_edit.document().findBlock(cursor.selectionEnd())
                while True:
                    lst = block.textList()
                    if lst:
                        bf = block.blockFormat()
                        bf.setObjectIndex(-1)
                        lst.remove(block)
                        c = QTextCursor(block)
                        c.setBlockFormat(bf)
                    if block == end_block or not block.isValid(): break
                    block = block.next()
            else:
                fmt = current_list.format()
                fmt.setStyle(QTextListFormat.Style.ListDecimal)
                current_list.setFormat(fmt)
        else:
            list_fmt = QTextListFormat()
            list_fmt.setStyle(QTextListFormat.Style.ListDecimal)
            list_fmt.setIndent(max(1, cursor.blockFormat().indent()))
            prev_block = cursor.block().previous()
            next_block = cursor.block().next()
            target_list = None
            if prev_block.isValid() and prev_block.textList() and prev_block.textList().format().style() == QTextListFormat.Style.ListDecimal:
                target_list = prev_block.textList()
            elif next_block.isValid() and next_block.textList() and next_block.textList().format().style() == QTextListFormat.Style.ListDecimal:
                target_list = next_block.textList()
            
            if target_list:
                target_list.add(cursor.block())
            else:
                cursor.createList(list_fmt)
        self.update_toolbar_button_states()
        self.manual_save()

    def apply_indent(self) -> None:
        cursor = self.text_edit.textCursor()
        fmt = cursor.blockFormat()
        if fmt.indent() < 3: 
            fmt.setIndent(fmt.indent() + 1)
            cursor.setBlockFormat(fmt)
            self.manual_save()

    def apply_outdent(self) -> None:
        cursor = self.text_edit.textCursor()
        fmt = cursor.blockFormat()
        if fmt.indent() > 0:
            fmt.setIndent(fmt.indent() - 1)
            cursor.setBlockFormat(fmt)
            self.manual_save()

    def toggle_rollup(self) -> None:
        screen = QApplication.screenAt(self.geometry().center()) or QApplication.primaryScreen()
        scr_geom = screen.availableGeometry()
        
        center_x = self.x() + self.width() / 2
        center_y = self.y() + self.height() / 2
        is_near_top = (center_y < scr_geom.top() + scr_geom.height() / 3)
        is_near_right = (center_x > scr_geom.left() + scr_geom.width() / 2)
        
        anchor_x = self.x() + self.width() if is_near_right else self.x()
        anchor_y = self.y() if is_near_top else self.y() + self.height()
        
        if not self._is_rolled_up:
            self.memo_data['unrolled_width'] = self.width()
            self.memo_data['unrolled_height'] = self.height()
            self._normal_height = self.height()
            
            rolled_h = self.memo_data.get('rolled_height', 53)
            rolled_w = self.memo_data.get('rolled_width', self.width())
            
            new_left_x = anchor_x - rolled_w if is_near_right else anchor_x
            new_top_y = anchor_y if is_near_top else anchor_y - rolled_h
            
            if new_left_x + rolled_w > scr_geom.right(): new_left_x = scr_geom.right() - rolled_w
            if new_left_x < scr_geom.left(): new_left_x = scr_geom.left()
            if new_top_y + rolled_h > scr_geom.bottom(): new_top_y = scr_geom.bottom() - rolled_h
            if new_top_y < scr_geom.top(): new_top_y = scr_geom.top()
            
            self._is_rolled_up = True
            self.memo_data['is_rolled_up'] = True
            self.memo_data['rolled_position_y'] = new_top_y
            
            self.content_container.hide()
            if hasattr(self, 'bg_layout'):
                self.bg_layout.setContentsMargins(14, 8, 14, 8)
            if hasattr(self, 'window_layout'):
                self.window_layout.setContentsMargins(0, 0, 0, 0)
            self.setMinimumSize(0, 0)
            self.setMaximumSize(16777215, 16777215)
            
            self.setGeometry(new_left_x, new_top_y, rolled_w, rolled_h)
            self.setMinimumHeight(rolled_h)
            self.setMaximumHeight(rolled_h)
            self.btn_min.setToolTip("펼치기 (Ctrl+M)")
            self.btn_max.hide()
            if hasattr(self, 'btn_code_theme'): self.btn_code_theme.hide()
            if hasattr(self, 'code_lang_box'): self.code_lang_box.hide()
            if hasattr(self, 'btn_format_code'): self.btn_format_code.hide()
            if hasattr(self, 'btn_lang_icon'): self.btn_lang_icon.hide()
            if hasattr(self, 'bg'):
                self.bg.setGraphicsEffect(None)
        else:
            target_height = self.memo_data.get('unrolled_height', self.memo_data.get('height', getattr(self, '_normal_height', 300)))
            target_width = self.memo_data.get('unrolled_width', self.memo_data.get('width', 500))
            if target_height < 150: target_height = 300
            if target_width < 200: target_width = 300

            new_left_x = anchor_x - target_width if is_near_right else anchor_x
            new_top_y = anchor_y if is_near_top else anchor_y - target_height
            
            if new_left_x + target_width > scr_geom.right(): new_left_x = scr_geom.right() - target_width
            if new_left_x < scr_geom.left(): new_left_x = scr_geom.left()
            if new_top_y + target_height > scr_geom.bottom(): new_top_y = scr_geom.bottom() - target_height
            if new_top_y < scr_geom.top(): new_top_y = scr_geom.top()

            self._is_rolled_up = False
            self.memo_data['is_rolled_up'] = False
            self.memo_data['position_y'] = new_top_y
            self.memo_data['width'] = target_width
            self.memo_data['height'] = target_height

            self.setMinimumSize(200, 150)
            self.setMaximumSize(16777215, 16777215)
            self.setGeometry(new_left_x, new_top_y, target_width, target_height)
            self.content_container.show()
            if hasattr(self, 'bg_layout'):
                self.bg_layout.setContentsMargins(14, 10, 14, 14)
            if hasattr(self, 'window_layout'):
                self.window_layout.setContentsMargins(0, 0, 0, 0)
                
            if self.memo_data.get('is_code_memo', False):
                if hasattr(self, 'btn_code_theme'): self.btn_code_theme.show()
                if hasattr(self, 'code_lang_box'): self.code_lang_box.show()
                if hasattr(self, 'btn_format_code'): self.btn_format_code.show()
                if hasattr(self, 'btn_lang_icon'): self.btn_lang_icon.show()
            self.btn_min.setToolTip("접기 (Ctrl+M)")
            self.btn_max.show()
            
        if getattr(self, 'ui_manager', None) and hasattr(self.ui_manager, 'get_theme_icon'):
            is_code = self.memo_data.get('is_code_memo', False)
            bg_c = self.memo_data.get('bg_color', '#FFFFFF')
            if bg_c == "random": bg_c = "#FFFFFF"
            
            if is_code:
                is_dark_bg = (self.memo_data.get('code_theme', 'dark') == 'dark')
            else:
                is_dark_bg = True if bg_c in ['#2E3440', '#1C1C1E', '#000000'] else False
                if not is_dark_bg:
                    c_obj = QColor(bg_c)
                    if c_obj.isValid():
                        lum = (0.299 * c_obj.red() + 0.587 * c_obj.green() + 0.114 * c_obj.blue()) / 255.0
                        if lum < 0.5: is_dark_bg = True
                        
            icon_name = "maximize.svg" if self._is_rolled_up else "rollup.svg"
            override_color = "#FFFFFF" if is_dark_bg else "#1C1C1E"
            self.btn_min.setIcon(self.ui_manager.get_theme_icon(icon_name, is_dark_bg, override_color=override_color))

        self.btn_min.style().unpolish(self.btn_min)
        self.btn_min.style().polish(self.btn_min)
        self.btn_min.update()
        self.btn_min.repaint()
        if hasattr(self, 'bg'):
            self.bg.update()
            self.bg.repaint()
        QApplication.processEvents()
            
        self.save_callback(self.memo_data)

    def update_content(self) -> None:
        if getattr(self, '_is_updating_from_explorer', False) or getattr(self, '_is_applying_data', False): return
        self._auto_save_timer.start(1000)

    def execute_auto_save(self) -> None:
        self.memo_data['content'] = self.text_edit.toHtml()
        self.memo_data['updated_at'] = datetime.datetime.now().isoformat()
        
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

    def apply_data(self) -> None:
        if getattr(self, '_is_applying_data', False):
            return
        self._is_applying_data = True
        try:
            self._apply_data_internal()
        finally:
            self._is_applying_data = False

    def _apply_data_internal(self) -> None:
        target_flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool
        is_pinned = self.memo_data.get('is_pinned', False)
        if is_pinned:
            target_flags |= Qt.WindowType.WindowStaysOnTopHint
            
        current_flags = self.windowFlags()
        if (current_flags & (Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)) != target_flags:
            was_visible = self.isVisible()
            self.setWindowFlags(target_flags)
            if was_visible:
                self.show()
        
        is_code_memo = self.memo_data.get('is_code_memo', False)

        if is_code_memo:
            code_theme = self.memo_data.get('code_theme', 'dark')
            is_memo_dark_bg = (code_theme == "dark")
        else:
            bg_color = self.memo_data.get('bg_color', '#FFFFFF')
            if bg_color == "random":
                bg_color = "#FFFFFF"
            is_memo_dark_bg = True if bg_color in ['#2E3440', '#1C1C1E', '#000000'] else False
            if not is_memo_dark_bg:
                c_obj = QColor(bg_color)
                if c_obj.isValid():
                    lum = (0.299 * c_obj.red() + 0.587 * c_obj.green() + 0.114 * c_obj.blue()) / 255.0
                    if lum < 0.5:
                        is_memo_dark_bg = True

        is_dark = is_memo_dark_bg
        override_w = "#FFFFFF" if is_dark else "#1C1C1E"

        is_pinned = self.memo_data.get('is_pinned', False)
        if getattr(self, 'ui_manager', None) and hasattr(self.ui_manager, 'get_theme_icon'):
            self.btn_pin.setIcon(self.ui_manager.get_theme_icon("pin_icon_True.svg" if is_pinned else "pin_icon_False.svg", is_dark, override_color=override_w))
            self.btn_min.setIcon(self.ui_manager.get_theme_icon("maximize.svg" if self._is_rolled_up else "rollup.svg", is_dark, override_color=override_w))
            self.btn_max.setIcon(self.ui_manager.get_theme_icon("maximize.svg", is_dark, override_color=override_w))
            self.btn_close.setIcon(self.ui_manager.get_theme_icon("close.svg", is_dark, override_color="#FF453A"))
            self.s_prev_btn.setIcon(self.ui_manager.get_theme_icon("arrow left.svg", is_dark, override_color=override_w))
            self.s_next_btn.setIcon(self.ui_manager.get_theme_icon("arrow right.svg", is_dark, override_color=override_w))
            if hasattr(self, 'btn_format_code'):
                self.btn_format_code.setIcon(self.ui_manager.get_theme_icon("restart-icon.svg", is_memo_dark_bg))

        if self._is_rolled_up:
            self.btn_min.setToolTip("펼치기 (Ctrl+M)")
            self.btn_max.hide()
        else:
            self.btn_min.setToolTip("접기 (Ctrl+M)")
            self.btn_max.show()

        if is_pinned:
            self.btn_pin.setText("")
            self.btn_pin.setStyleSheet(
                "QPushButton { background: #0A84FF; color: white; "
                "border: none; border-radius: 4px; } "
                "QPushButton:hover { background: #007AFF; }"
            )
        else:
            self.btn_pin.setText("")
            if is_memo_dark_bg:
                self.btn_pin.setStyleSheet(
                    "QPushButton { background: transparent; border: none; border-radius: 6px; } "
                    "QPushButton:hover { background: rgba(255,255,255,0.15); }"
                )
            else:
                self.btn_pin.setStyleSheet(
                    "QPushButton { background: transparent; border: none; border-radius: 6px; } "
                    "QPushButton:hover { background: rgba(0,0,0,0.08); }"
                )

        win_btn_style_dark  = ("QPushButton { background: transparent; color: #FFFFFF; font-weight: bold; "
                               "border: none; border-radius: 6px; } "
                               "QPushButton:hover { background: rgba(255,255,255,0.15); }")
        win_btn_style_light = ("QPushButton { background: transparent; color: #1C1C1E; font-weight: bold; "
                               "border: none; border-radius: 6px; } "
                               "QPushButton:hover { background: rgba(0,0,0,0.08); }")
        close_btn_style     = ("QPushButton { background: transparent; color: #FF453A; font-weight: bold; "
                               "border: none; border-radius: 6px; } "
                               "QPushButton:hover { background: #FF453A; color: white; }")

        if is_memo_dark_bg:
            self.btn_min.setStyleSheet(win_btn_style_dark)
            self.btn_max.setStyleSheet(win_btn_style_dark)
            self.btn_close.setStyleSheet(close_btn_style)
        else:
            self.btn_min.setStyleSheet(win_btn_style_light)
            self.btn_max.setStyleSheet(win_btn_style_light)
            self.btn_close.setStyleSheet(close_btn_style)

        if is_code_memo:
            if self._is_rolled_up:
                self.btn_format_code.hide()
                self.btn_code_theme.hide()
                self.code_lang_box.hide()
                if hasattr(self, 'btn_lang_icon'): self.btn_lang_icon.hide()
            else:
                self.btn_format_code.show()
                self.btn_code_theme.show()
                self.code_lang_box.show()
                if hasattr(self, 'btn_lang_icon'): self.btn_lang_icon.show()

            code_theme = self.memo_data.get('code_theme', 'dark')
            lang = self.memo_data.get('code_lang', 'JSON')

            self.btn_code_theme.setText(" 라이트" if code_theme == "dark" else " 다크")
            if getattr(self, 'ui_manager', None) and hasattr(self.ui_manager, 'get_theme_icon'):
                self.btn_code_theme.setIcon(self.ui_manager.get_theme_icon("litemode.svg" if code_theme == "dark" else "darkmod.svg", is_memo_dark_bg))
                if hasattr(self, 'btn_lang_icon'):
                    icon_color = "#FFFFFF" if is_memo_dark_bg else "#000000"
                    self.btn_lang_icon.setIcon(self.ui_manager.get_theme_icon("language.svg", is_memo_dark_bg, override_color=icon_color))
            
            self.code_lang_box.blockSignals(True)
            self.code_lang_box.setCurrentText(lang)
            self.code_lang_box.blockSignals(False)

            self.highlighter = CodeHighlighter(self.text_edit.document(), lang, code_theme)
            self.highlighter.rehighlight()

            if code_theme == "dark":
                pal = DARK_THEMES.get("dark", DARK_THEMES["dark"])
                code_bg = pal['card']
                code_text = pal['text']
            else:
                pal = LIGHT_THEMES.get("white", LIGHT_THEMES["white"])
                code_bg = pal['card']
                code_text = pal['text']

            title_c = "#007AFF"
            self.title_edit.setStyleSheet(
                f"border:none; background:transparent; color:{title_c}; "
                f"font-weight:bold; font-size:12pt; font-family: 'D2Coding';"
            )

            radius_px = "0px"
            self.bg.setStyleSheet(
                f"QWidget#MemoBackground {{ background-color: {code_bg}; "
                f"border: 1px solid {pal['border']}; "
                f"border-radius: {radius_px}; }}"
            )
            self.text_edit.setStyleSheet(
                f"QTextEdit {{ border:none; background:transparent; "
                f"color:{code_text}; font-family: 'D2Coding'; font-size:11pt; }}"
            )

            code_font_name = self.memo_data.get(
                'font_family',
                'D2Coding'
            )
            mono_font = QFont(code_font_name, self.memo_data.get('font_size', 11))
            self.text_edit.setFont(mono_font)

            btn_text_color = "#F2F2F7" if is_memo_dark_bg else "#1C1C1E"
            btn_bg_color = "rgba(255, 255, 255, 0.12)" if is_memo_dark_bg else "rgba(0, 0, 0, 0.06)"
            btn_border_color = "rgba(255, 255, 255, 0.2)" if is_memo_dark_bg else "rgba(0, 0, 0, 0.15)"

            box_style = (
                f"QPushButton, QComboBox {{ font-size: 8.5pt; font-weight: bold; padding: 2px 6px; border: 1px solid {btn_border_color}; border-radius: 0px; background: {btn_bg_color}; color: {btn_text_color}; }} "
                f"QPushButton:hover, QComboBox:hover {{ background: rgba(128, 128, 128, 0.2); }} "
                f"QPushButton:pressed, QComboBox:pressed {{ background: rgba(128, 128, 128, 0.4); }} "
                f"QComboBox::drop-down {{ border: none; }}"
            )
            self.btn_code_theme.setStyleSheet(box_style)
            self.code_lang_box.setStyleSheet(box_style)
            if hasattr(self, 'btn_format_code'):
                self.btn_format_code.setStyleSheet(box_style)
        else:
            bg_color = self.memo_data.get('bg_color', '#FFFFFF')
            if bg_color == "random":
                bg_color = "#FFFFFF"

            text_c  = "#F2F2F7" if is_memo_dark_bg else "#1C1C1E"
            title_c = "#FFFFFF" if is_memo_dark_bg else "#1C1C1E"

            self.title_edit.setStyleSheet(
                f"border:none; background:transparent; color:{title_c}; "
                f"font-weight:bold; font-size:12pt; "
                f"font-family: 'D2Coding', 'Consolas', monospace;"
            )
            self.text_edit.setStyleSheet(
                f"QTextEdit {{ border:none; background:transparent; color:{text_c}; }}"
            )
            
            # Change default text colors only, preserve custom colors
            doc = self.text_edit.document()
            target_color_name = text_c.upper()
            if is_memo_dark_bg:
                old_colors = ["#000000", "#1C1C1E", "#333333"]
            else:
                old_colors = ["#FFFFFF", "#F2F2F7", "#CCCCCC"]
                
            for i in range(doc.blockCount()):
                block = doc.findBlockByNumber(i)
                it = block.begin()
                while not it.atEnd():
                    frag = it.fragment()
                    fmt = frag.charFormat()
                    if fmt.foreground().color().name().upper() in old_colors:
                        fmt.setForeground(QColor(text_c))
                        cursor = QTextCursor(block)
                        cursor.setPosition(frag.position())
                        cursor.setPosition(frag.position() + frag.length(), QTextCursor.MoveMode.KeepAnchor)
                        cursor.mergeCharFormat(fmt)
                    it += 1

            radius_px = "0px"
            self.bg.setStyleSheet(
                f"QWidget#MemoBackground {{ background-color: {bg_color}; "
                f"border: 1px solid {'rgba(255,255,255,0.18)' if is_memo_dark_bg else '#E5E5EA'}; border-radius: {radius_px}; }}"
            )
            if hasattr(self, 'window_layout'):
                if self._is_rolled_up:
                    self.window_layout.setContentsMargins(0, 0, 0, 0)
                else:
                    self.window_layout.setContentsMargins(6, 6, 6, 6)

            if self._is_rolled_up:
                self.bg.setGraphicsEffect(None)
            else:
                apply_ios_shadow(self.bg)

            if getattr(self, 'ui_manager', None) and hasattr(self.ui_manager, 'get_theme_icon'):
                self.btn_bullet.setText("")
                self.btn_bullet.setIcon(self.ui_manager.get_theme_icon("bullet_icon_177745.svg", is_memo_dark_bg))
                self.btn_num.setText("")
                self.btn_num.setIcon(self.ui_manager.get_theme_icon("list_numbers_icon_172368.svg", is_memo_dark_bg))
                self.btn_indent.setText("")
                self.btn_indent.setIcon(self.ui_manager.get_theme_icon("들여쓰기.svg", is_memo_dark_bg))
                self.btn_outdent.setText("")
                self.btn_outdent.setIcon(self.ui_manager.get_theme_icon("내어쓰기.svg", is_memo_dark_bg))

            self.btn_format_code.hide()
            self.btn_code_theme.hide()
            self.code_lang_box.hide()

        font_family = self.memo_data.get(
            'font_family',
            self.memo_window_get_settings().get('default_font_family', 'D2Coding')
        )
        font = QFont(font_family, self.memo_data.get('font_size', 11))
        self.text_edit.setFont(font)

        # 하단 서식 툴바 컨트롤 테마 보정
        if is_memo_dark_bg:
            p_pal = DARK_THEMES["dark"]
        else:
            p_pal = LIGHT_THEMES["white"]

        tb_box_style = f"font-size: 8.5pt; font-weight: bold; padding: 0 4px; border: 1px solid {p_pal['border']}; border-radius: 6px; background: {p_pal['input']}; color: {p_pal['text']};"
        if hasattr(self, 'font_box'):
            self.font_box.setStyleSheet(tb_box_style)
        if hasattr(self, 'size_box'):
            self.size_box.setStyleSheet(tb_box_style)
        if hasattr(self, 'btn_fg_color'):
            self.btn_fg_color.setStyleSheet(f"font-weight: bold; color: {p_pal['accent']}; border: 1px solid {p_pal['border']}; border-radius: 6px; background: {p_pal['input']};")
        if hasattr(self, 'btn_bg_color'):
            self.btn_bg_color.setStyleSheet(f"font-weight: bold; color: {p_pal['accent']}; border: 1px solid {p_pal['border']}; border-radius: 6px; background: {p_pal['input']};")
        if hasattr(self, 'btn_toggle_sub_fmt'):
            self.btn_toggle_sub_fmt.setStyleSheet(f"font-size: 8pt; font-weight: bold; border: 1px solid {p_pal['border']}; border-radius: 6px; background: {p_pal['input']}; color: {p_pal['accent']}; padding: 0 4px;")
            
        self.title_edit.setText(self.memo_data.get('title',''))
        self.title_edit.setCursorPosition(0)
            
        self._is_updating_from_explorer = True
        cnt = str(self.memo_data.get('content',''))
        self.text_edit.setHtml(cnt) if "<html" in cnt else self.text_edit.setPlainText(cnt)
        
        # 📌 불투명도 100% 기본값 적용 (사용자가 변경한 opacity 설정 유지)
        target_opacity = float(self.memo_data.get('opacity', 1.0))
        self.setWindowOpacity(target_opacity)
        
        self.apply_line_bg_style()
        self.text_edit.update_line_number_area()
                
        self._is_updating_from_explorer = False
        is_rolled = getattr(self, '_is_rolled_up', False) or self.memo_data.get('is_rolled_up', False)
        screen = QApplication.screenAt(self.geometry().center()) or QApplication.primaryScreen()
        scr_geom = screen.availableGeometry()
        
        if is_rolled:
            target_w = self.memo_data.get('rolled_width', self.width())
            target_h = self.memo_data.get('rolled_height', 53)
            r_x = self.x() if self.isVisible() else self.memo_data.get('position_x', 100)
            r_y = self.y() if self.isVisible() else self.memo_data.get('rolled_position_y', 100)
            
            if r_x + target_w > scr_geom.right(): r_x = scr_geom.right() - target_w
            if r_x < scr_geom.left(): r_x = scr_geom.left()
            if r_y + target_h > scr_geom.bottom(): r_y = scr_geom.bottom() - target_h
            if r_y < scr_geom.top(): r_y = scr_geom.top()
            
            self._is_rolled_up = True
            self.memo_data['is_rolled_up'] = True
            self.memo_data['rolled_position_y'] = r_y
            self.setGeometry(r_x, r_y, target_w, target_h)
            
            self.content_container.hide()
            self.btn_min.setToolTip("펼치기 (Ctrl+M)")
            self.btn_max.hide()
            if hasattr(self, 'btn_code_theme'): self.btn_code_theme.hide()
            if hasattr(self, 'code_lang_box'): self.code_lang_box.hide()
            if hasattr(self, 'btn_format_code'): self.btn_format_code.hide()
            if hasattr(self, 'window_layout'):
                self.window_layout.setContentsMargins(0, 0, 0, 0)
        else:
            target_w = self.memo_data.get('unrolled_width', self.memo_data.get('width', 500))
            target_h = self.memo_data.get('unrolled_height', self.memo_data.get('height', 400))
            u_x = self.x() if self.isVisible() else self.memo_data.get('position_x', 100)
            u_y = self.y() if (self.isVisible() and not getattr(self, '_is_rolled_up', False)) else self.memo_data.get('position_y', 100)
            
            if u_x + target_w > scr_geom.right(): u_x = scr_geom.right() - target_w
            if u_x < scr_geom.left(): u_x = scr_geom.left()
            if u_y + target_h > scr_geom.bottom(): u_y = scr_geom.bottom() - target_h
            if u_y < scr_geom.top(): u_y = scr_geom.top()
            
            self._is_rolled_up = False
            self.memo_data['is_rolled_up'] = False
            self.memo_data['position_y'] = u_y
            self.setGeometry(u_x, u_y, target_w, target_h)
            
            self.content_container.show()
            self.btn_min.setToolTip("접기 (Ctrl+M)")
            self.btn_max.show()
            if self.memo_data.get('is_code_memo', False):
                if hasattr(self, 'btn_code_theme'): self.btn_code_theme.show()
                if hasattr(self, 'code_lang_box'): self.code_lang_box.show()
                if hasattr(self, 'btn_format_code'): self.btn_format_code.show()
            if hasattr(self, 'window_layout'):
                self.window_layout.setContentsMargins(0, 0, 0, 0)
            
    def closeEvent(self, e: Any) -> None:
        self._auto_save_timer.stop()
        if hasattr(self, '_title_save_timer'):
            self._title_save_timer.stop()

        if getattr(self, '_is_deleting', False):
            super().closeEvent(e)
            return

        if self.memo_data.get('is_code_memo', False):
            plain_text = self.text_edit.toPlainText().strip()
        else:
            plain_text = clean_plain_text(self.text_edit.toHtml()).strip()
            
        is_empty_draft = (not plain_text) and (not self.memo_data.get('is_manually_saved', False))
        
        if is_empty_draft:
            self.delete_callback(self)
        else:
            if plain_text and self.memo_data.get('is_draft'):
                self.memo_data['is_draft'] = False
                self.save_callback(self.memo_data)
                
            if self._is_rolled_up:
                old_rolled_y = self.memo_data.get('rolled_position_y', self.y())
                delta_y = self.y() - old_rolled_y
                self.memo_data['rolled_position_y'] = self.y()
                self.memo_data['position_x'] = self.x()
                if 'position_y' in self.memo_data:
                    self.memo_data['position_y'] += delta_y
            else:
                self.memo_data['position_x'], self.memo_data['position_y'] = self.x(), self.y()
                self.memo_data['width'] = self.width()
                
            self.memo_data['is_rolled_up'] = self._is_rolled_up
            if not self._is_rolled_up:
                self.memo_data['height'] = self.height()
            else:
                self.memo_data['height'] = self._normal_height
                
            self.memo_data['is_visible'] = False
            self.save_callback(self.memo_data)
            self.close_callback(self)
        super().closeEvent(e)
        
    def enable_rename(self) -> None:
        self.title_edit.setReadOnly(False)
        is_code = self.memo_data.get('is_code_memo', False)
        font_fam = "'D2Coding'" if is_code else "'D2Coding', 'Consolas', monospace"
        self.title_edit.setStyleSheet(f"border:1px solid #007AFF; background:white; color:#000000; font-weight:bold; font-size:12pt; border-radius:0px; font-family: {font_fam};")
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
                self.save_callback(self.memo_data)
            else:
                QMessageBox.warning(self, "중복", f"'{nt}' 존재.")
                self.title_edit.setText(ot)
                
        theme = self.memo_window_get_settings().get('app_theme', 'white')
        is_app_dark = (theme == "dark")
        bg_color = self.memo_data.get('bg_color', '#FFFFFF')
        is_memo_dark_bg = True if bg_color in ['#2E3440', '#1C1C1E', '#000000'] else False
        if not is_memo_dark_bg and bg_color != "random":
            c_obj = QColor(bg_color)
            if c_obj.isValid() and c_obj.lightnessF() < 0.5:
                is_memo_dark_bg = True
        is_dark = is_app_dark or is_memo_dark_bg
        is_code = self.memo_data.get('is_code_memo', False)
        
        title_color = "#007AFF" if is_code else ("#FFFFFF" if is_dark else "#1C1C1E")
        font_fam = "'D2Coding'" if is_code else "'D2Coding', 'Consolas', monospace"
        self.title_edit.setStyleSheet(f"border:none; background:transparent; color:{title_color}; font-weight:bold; font-size:12pt; font-family: {font_fam};")
        self.title_edit.setCursorPosition(0)
        if getattr(self, 'ui_manager', None) and self.ui_manager.explorer_window and self.ui_manager.explorer_window.isVisible():
            self.ui_manager.explorer_window.update_table()
        
    def toggle_pin(self) -> None:
        self.memo_data['is_pinned'] = not self.memo_data.get('is_pinned', False)
        self.apply_data()
        self.save_callback(self.memo_data)
        
    def change_color(self, c: str) -> None:
        self.memo_data['bg_color'] = c
        self.apply_data()
        self.show()
        if hasattr(self, 'bg'):
            self.bg.style().unpolish(self.bg)
            self.bg.style().polish(self.bg)
            self.bg.update()
            self.bg.repaint()
        self.update()
        self.repaint()
        self.text_edit.viewport().update()
        self.text_edit.viewport().repaint()
        self.save_callback(self.memo_data)
        if getattr(self, 'ui_manager', None) and self.ui_manager.explorer_window and self.ui_manager.explorer_window.isVisible():
            self.ui_manager.explorer_window.update_table()
    def mousePressEvent(self, e: Any) -> None: 
        if e.button() == Qt.MouseButton.LeftButton:
            if hasattr(self, 'title_edit') and not self.title_edit.isReadOnly():
                pos_in_title = self.title_edit.mapFromGlobal(e.globalPosition().toPoint())
                if not self.title_edit.rect().contains(pos_in_title):
                    self.handle_rename()

            self._old_pos = e.globalPosition().toPoint()
            self._drag_start_pos = e.globalPosition().toPoint()
            self._drag_start_win_pos = self.pos()
            self._snap_lock_origin = None
            pos_in_title = self.title_edit.mapFromGlobal(e.globalPosition().toPoint())
            self._drag_from_title = self.title_edit.rect().contains(pos_in_title)

    def mouseMoveEvent(self, e: Any) -> None: 
        if getattr(self, '_old_pos', None) and not self.isMaximized():
            curr_global = e.globalPosition().toPoint()
            
            # 📌 1) 마우스 시작점 기준 1:1 직결 절대 목표 좌표 계산 (딜레이/느림 100% 방지)
            mouse_delta = curr_global - self._drag_start_pos
            target_x = self._drag_start_win_pos.x() + mouse_delta.x()
            target_y = self._drag_start_win_pos.y() + mouse_delta.y()

            screen = QApplication.screenAt(curr_global) or QApplication.primaryScreen()
            scr_geom = screen.availableGeometry()
            
            is_title_drag = getattr(self, '_drag_from_title', False)
            ctrl_held = bool(QApplication.keyboardModifiers() & Qt.KeyboardModifier.ControlModifier)
            
            # 📌 2) 제목 드래그 시 위아래 15px 이내 Y축 고정 (좌우 슬라이딩)
            if self._is_rolled_up and is_title_drag and not ctrl_held:
                dy = abs(curr_global.y() - self._drag_start_pos.y())
                if dy <= 15:
                    target_y = self._drag_start_win_pos.y()

            new_x = target_x
            new_y = target_y

            # 📌 3) 15px 이내 실시간 부드러운 0px 레고 블록 스냅 (멈춤 현상 완전 해소)
            if self._is_rolled_up and not ctrl_held and getattr(self, 'ui_manager', None):
                snap_in = 15
                for other_id, other_win in self.ui_manager.memo_windows.items():
                    if other_win is self or not other_win.isVisible() or not other_win._is_rolled_up:
                        continue
                    
                    # 수직 스냅 (상하단 0px 및 상단 맞춤)
                    if abs(target_y - (other_win.y() + other_win.height())) < snap_in:
                        new_y = other_win.y() + other_win.height()
                    elif abs((target_y + self.height()) - other_win.y()) < snap_in:
                        new_y = other_win.y() - self.height()
                    elif abs(target_y - other_win.y()) < snap_in:
                        new_y = other_win.y()
                        
                    # 수평 스냅 (좌우 경계 0px 맞춤)
                    if abs(target_x - other_win.x()) < snap_in:
                        new_x = other_win.x()
                    elif abs((target_x + self.width()) - (other_win.x() + other_win.width())) < snap_in:
                        new_x = other_win.x() + other_win.width() - self.width()
                    elif abs(target_x - (other_win.x() + other_win.width())) < snap_in:
                        new_x = other_win.x() + other_win.width()
                    elif abs((target_x + self.width()) - other_win.x()) < snap_in:
                        new_x = other_win.x() - self.width()

                # 화면 좌측 모서리 0px 스냅
                if abs(target_x - scr_geom.left()) < snap_in:
                    new_x = scr_geom.left()

            new_x = max(scr_geom.left(), min(new_x, scr_geom.right() - self.width()))
            new_y = max(scr_geom.top(), min(new_y, scr_geom.bottom() - self.height()))

            self.move(new_x, new_y)
            self._old_pos = curr_global

    def mouseReleaseEvent(self, e: Any) -> None: 
        self._old_pos = None
        self._drag_from_title = False
        self._snap_lock_origin = None
        
        if self._is_rolled_up:
            self.memo_data['rolled_position_y'] = self.y()
            self.memo_data['position_x'] = self.x()
            self.memo_data['rolled_width'] = self.width()
            self.memo_data['rolled_height'] = self.height()
            
            unrolled_h = self.memo_data.get('unrolled_height', self.memo_data.get('height', 300))
            self.memo_data['position_y'] = (self.y() + self.height()) - unrolled_h
        else:
            self.memo_data['position_x'] = self.x()
            self.memo_data['position_y'] = self.y()
            self.memo_data['unrolled_width'] = self.width()
            self.memo_data['unrolled_height'] = self.height()
            self.memo_data['width'] = self.width()
            self.memo_data['height'] = self.height()
            
            rolled_h = self.memo_data.get('rolled_height', 53)
            self.memo_data['rolled_position_y'] = (self.y() + self.height()) - rolled_h

        self.save_callback(self.memo_data)