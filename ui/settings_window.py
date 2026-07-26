from PyQt6.QtCore import QMetaObject, pyqtSlot
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

class SettingsWindow(QWidget):
    def __init__(self, sm: Any) -> None:
        super().__init__()
        self.sm = sm
        self.colors = {
            "랜덤": "random",
            "다크그레이": "#2E3440",
            "하늘색": "#E0F2FE", 
            "연두색": "#DCFCE7", 
            "노란색": "#FEF9C3", 
            "분홍색": "#FCE7F3", 
            "흰색": "#FFFFFF"
        }
        self.init_ui()
        self.apply_theme_style()
        self.load()

    def init_ui(self) -> None:
        self.setObjectName("SettingsWindow")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setWindowTitle("Memos Settings")
        self.setFixedSize(740, 960)
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(18, 18, 18, 18)
        
        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)
        
        # --- TAB 1: 일반 설정 ---
        tab_general = QWidget()
        l_gen = QVBoxLayout(tab_general)
        l_gen.setContentsMargins(15, 15, 15, 15)
        l_gen.setSpacing(15)
        
        g2 = QGroupBox("자동 로그인 및 보안 계정")
        g2_l = QVBoxLayout(g2)
        g2_l.setContentsMargins(18, 24, 18, 18)
        self.cb_auto_login = QCheckBox("이 PC에서 비밀번호 기억 (자동 로그인)")
        self.cb_auto_login.setStyleSheet("font-weight: bold; color: #007AFF; font-size: 10pt;")
        g2_l.addWidget(self.cb_auto_login)
        l_gen.addWidget(g2)

        g4 = QGroupBox("시스템 편의 및 실행 옵션")
        g4_l = QVBoxLayout(g4)
        g4_l.setContentsMargins(18, 24, 18, 18)
        g4_l.setSpacing(12)
        
        self.cb_default_pin = QCheckBox("새 메모 실행 시 화면 고정 기본 적용")
        self.cb_auto_eng_kor = QCheckBox("한/영 영타 오타 자동 변환기 사용")
        self.auto_start_cb = QCheckBox("윈도우 시작 시 자동 실행")
        
        self.cb_gen_line_num = QCheckBox("일반 메모: 최초 실행 시 행번호 표시")
        self.cb_gen_line_bg = QCheckBox("일반 메모: 최초 실행 시 줄노트 배경 표시")
        self.cb_code_line_num = QCheckBox("코드 메모: 최초 실행 시 행번호 표시")
        self.cb_code_line_bg = QCheckBox("코드 메모: 최초 실행 시 줄노트 배경 표시")
        
        for cb_item in [
            self.cb_default_pin, self.cb_auto_eng_kor, self.auto_start_cb,
            self.cb_gen_line_num, self.cb_gen_line_bg,
            self.cb_code_line_num, self.cb_code_line_bg
        ]:
            g4_l.addWidget(cb_item)
            
        g4_l.addWidget(QLabel("휴지통 보관 기간:"))
        self.trash_auto_delete_box = QComboBox()
        self.trash_auto_delete_box.addItems(["없음 (수동 비우기)", "즉시 삭제 (0일)", "15일 경과 시 자동 삭제", "30일 경과 시 자동 삭제"])
        self.trash_auto_delete_box.setFixedHeight(40)
        g4_l.addWidget(self.trash_auto_delete_box)
        l_gen.addWidget(g4)

        l_gen.addStretch()
        
        self.tabs.addTab(tab_general, "일반 설정")

        # --- TAB 2: 구글 동기화 ---
        tab_sync = QWidget()
        l_sync = QVBoxLayout(tab_sync)
        l_sync.setContentsMargins(15, 15, 15, 15)
        l_sync.setSpacing(15)
        
        g1 = QGroupBox("구글 드라이브 백업 및 동기화 설정")
        g1_l = QVBoxLayout(g1)
        g1_l.setContentsMargins(18, 24, 18, 18)
        g1_l.setSpacing(12)
        
        self.sync_cb = QCheckBox("구글 드라이브 동기화 활성화")
        self.sync_cb.setStyleSheet("font-weight: bold; color: #007AFF; font-size: 10pt;")
        g1_l.addWidget(self.sync_cb)
        
        g1_l.addWidget(QLabel("GAS Web App URL:"))
        url_box = QHBoxLayout()
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://script.google.com/macros/s/.../exec")
        self.url_input.setFixedHeight(40)
        
        self.btn_test_url = QPushButton(" 연결 테스트")
        self.btn_test_url.setFixedHeight(40)
        self.btn_test_url.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_test_url.clicked.connect(self.test_gas_url)
        
        url_box.addWidget(self.url_input)
        url_box.addWidget(self.btn_test_url)
        g1_l.addLayout(url_box)
        
        g1_l.addWidget(QLabel("로컬 메모 저장 위치:"))
        ph = QHBoxLayout()
        self.path_input = QLineEdit()
        self.path_input.setReadOnly(True)
        self.path_input.setFixedHeight(40)
        self.btn_change_path = QPushButton(" 경로 변경")
        self.btn_change_path.setFixedHeight(40)
        self.btn_change_path.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_change_path.clicked.connect(self.sel)
        ph.addWidget(self.path_input)
        ph.addWidget(self.btn_change_path)
        g1_l.addLayout(ph)
        
        g1_l.addWidget(QLabel("자동 동기화 주기:"))
        self.sync_interval_combo = QComboBox()
        self.sync_interval_combo.addItems(["1분마다", "10분마다", "30분마다", "1시간마다"])
        self.sync_interval_combo.setFixedHeight(40)
        g1_l.addWidget(self.sync_interval_combo)
        l_sync.addWidget(g1)
        l_sync.addStretch()
        
        self.tabs.addTab(tab_sync, "구글 동기화")

        # --- TAB 3: 테마 & 서식 ---
        tab_font = QWidget()
        l_font = QVBoxLayout(tab_font)
        l_font.setContentsMargins(15, 15, 15, 15)
        l_font.setSpacing(15)
        
        g3 = QGroupBox("기본 서식 / 폰트 / 코드 테마 설정")
        g3_l = QVBoxLayout(g3)
        g3_l.setContentsMargins(18, 24, 18, 18)
        g3_l.setSpacing(12)
        
        g3_l.addWidget(QLabel("기본 메모 폰트:"))
        self.default_font_box = QFontComboBox()
        self.default_font_box.setFixedHeight(40)
        g3_l.addWidget(self.default_font_box)
        
        g3_l.addWidget(QLabel("코드 메모 폰트:"))
        self.default_code_font_box = QFontComboBox()
        self.default_code_font_box.setFixedHeight(40)
        g3_l.addWidget(self.default_code_font_box)
        
        f_row3 = QHBoxLayout()
        f_row3.setSpacing(15)
        
        box_lang_l = QVBoxLayout()
        box_lang_l.addWidget(QLabel("코드 기본 언어:"))
        self.default_code_lang_box = QComboBox()
        self.default_code_lang_box.addItems(["JSON", "C#", "VB.NET", "Power Automate", "PowerShell", "Batch (CMD)", "SQL", "Markdown", "Python", "JavaScript", "HTML", "CSS", "C++", "Java"])
        self.default_code_lang_box.setFixedHeight(40)
        box_lang_l.addWidget(self.default_code_lang_box)
        f_row3.addLayout(box_lang_l)
        
        box_theme_l = QVBoxLayout()
        box_theme_l.addWidget(QLabel("코드 기본 테마:"))
        self.default_code_theme_box = QComboBox()
        self.default_code_theme_box.addItems(["Atom One Dark", "라이트 모드"])
        self.default_code_theme_box.setFixedHeight(40)
        box_theme_l.addWidget(self.default_code_theme_box)
        f_row3.addLayout(box_theme_l)
        
        g3_l.addLayout(f_row3)

        f_row4 = QHBoxLayout()
        f_row4.setSpacing(15)

        box_dark_theme_l = QVBoxLayout()
        box_dark_theme_l.addWidget(QLabel("다크 모드 스타일:"))
        self.dark_theme_box = QComboBox()
        for k, v in DARK_THEMES.items():
            self.dark_theme_box.addItem(v["name"], k)
        self.dark_theme_box.setFixedHeight(40)
        box_dark_theme_l.addWidget(self.dark_theme_box)
        f_row4.addLayout(box_dark_theme_l)

        box_light_theme_l = QVBoxLayout()
        box_light_theme_l.addWidget(QLabel("라이트 모드 스타일:"))
        self.light_theme_box = QComboBox()
        for k, v in LIGHT_THEMES.items():
            self.light_theme_box.addItem(v["name"], k)
        self.light_theme_box.setFixedHeight(40)
        box_light_theme_l.addWidget(self.light_theme_box)
        f_row4.addLayout(box_light_theme_l)

        def _on_theme_style_changed():
            self.sm.settings["dark_theme_mode"] = self.dark_theme_box.currentData()
            self.sm.settings["light_theme_mode"] = self.light_theme_box.currentData()
            self.apply_theme_style()
            if hasattr(self.sm, 'ui_manager') and self.sm.ui_manager:
                if self.sm.ui_manager.explorer_window and self.sm.ui_manager.explorer_window.isVisible():
                    self.sm.ui_manager.explorer_window.apply_theme_style()
                for w in self.sm.ui_manager.memo_windows.values():
                    if w.isVisible():
                        w.apply_data()
        self.dark_theme_box.currentIndexChanged.connect(lambda _: _on_theme_style_changed())
        self.light_theme_box.currentIndexChanged.connect(lambda _: _on_theme_style_changed())

        g3_l.addLayout(f_row4)
        
        g3_l.addWidget(QLabel("일반 메모 기본 색상:"))
        self.default_color_combo = QComboBox()
        self.default_color_combo.setFixedHeight(40)
        for idx, (name, color_hex) in enumerate(self.colors.items()):
            self.default_color_combo.addItem(name)
            if color_hex != "random":
                self.default_color_combo.setItemData(idx, QColor(color_hex), Qt.ItemDataRole.BackgroundRole)
        g3_l.addWidget(self.default_color_combo)
        
        # 기본 투명도 설정 그룹
        g_opacity = QGroupBox("새 메모 기본 투명도 (불투명 100% 기본)")
        g_opacity_l = QVBoxLayout(g_opacity)
        g_opacity_l.setContentsMargins(18, 24, 18, 18)
        g_opacity_l.setSpacing(8)
        
        opa_row = QHBoxLayout()
        self.opacity_value_label = QLabel("100%  (완전 불투명 — 권장)")
        self.opacity_value_label.setStyleSheet("font-weight: bold; color: #007AFF; font-size: 10pt;")
        opa_row.addWidget(self.opacity_value_label)
        opa_row.addStretch()
        g_opacity_l.addLayout(opa_row)
        
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(20, 100)
        self.opacity_slider.setValue(100)
        self.opacity_slider.setFixedHeight(32)
        self.opacity_slider.setStyleSheet("""
            QSlider::groove:horizontal { height: 6px; background: #C7C7CC; border-radius: 3px; }
            QSlider::handle:horizontal { width: 22px; height: 22px; margin: -8px 0; background: #007AFF; border-radius: 11px; }
            QSlider::sub-page:horizontal { background: #007AFF; border-radius: 3px; }
        """)
        def _settings_opacity_changed(val: int) -> None:
            if val == 100:
                self.opacity_value_label.setText(f"{val}%  (완전 불투명 — 권장)")
            elif val >= 80:
                self.opacity_value_label.setText(f"{val}%  (약간 투명)")
            elif val >= 60:
                self.opacity_value_label.setText(f"{val}%  (반투명)")
            else:
                self.opacity_value_label.setText(f"{val}%  (많이 투명)")
        self.opacity_slider.valueChanged.connect(_settings_opacity_changed)
        g_opacity_l.addWidget(self.opacity_slider)
        
        opa_hint = QLabel("※ 개별 메모 창 우클릭 메뉴 → 창 투명도 조절 에서도 개별 조절 가능합니다.")
        opa_hint.setStyleSheet("font-size: 8.5pt; color: #8E8E93;")
        opa_hint.setWordWrap(True)
        g_opacity_l.addWidget(opa_hint)

        # --- 메모 기본 실행 크기 설정 그룹 (일반 & 코드 독립 설정) ---
        g_size = QGroupBox("메모 기본 실행 크기 설정 (일반 메모 & 코드 메모)")
        g_size_l = QGridLayout(g_size)
        g_size_l.setContentsMargins(18, 24, 18, 18)
        g_size_l.setSpacing(12)
        
        self.spin_memo_width = QSpinBox()
        self.spin_memo_width.setRange(200, 1920)
        self.spin_memo_width.setSuffix(" px")
        self.spin_memo_width.setFixedHeight(36)
        
        self.spin_memo_height = QSpinBox()
        self.spin_memo_height.setRange(150, 1080)
        self.spin_memo_height.setSuffix(" px")
        self.spin_memo_height.setFixedHeight(36)

        self.spin_code_memo_width = QSpinBox()
        self.spin_code_memo_width.setRange(200, 1920)
        self.spin_code_memo_width.setSuffix(" px")
        self.spin_code_memo_width.setFixedHeight(36)
        
        self.spin_code_memo_height = QSpinBox()
        self.spin_code_memo_height.setRange(150, 1080)
        self.spin_code_memo_height.setSuffix(" px")
        self.spin_code_memo_height.setFixedHeight(36)

        g_size_l.addWidget(QLabel("일반 메모 가로:"), 0, 0)
        g_size_l.addWidget(self.spin_memo_width, 0, 1)
        g_size_l.addWidget(QLabel("일반 메모 세로:"), 0, 2)
        g_size_l.addWidget(self.spin_memo_height, 0, 3)

        g_size_l.addWidget(QLabel("코드 메모 가로:"), 1, 0)
        g_size_l.addWidget(self.spin_code_memo_width, 1, 1)
        g_size_l.addWidget(QLabel("코드 메모 세로:"), 1, 2)
        g_size_l.addWidget(self.spin_code_memo_height, 1, 3)

        l_font.addWidget(g3)
        l_font.addWidget(g_opacity)
        l_font.addWidget(g_size)
        l_font.addStretch()
        
        self.tabs.addTab(tab_font, "테마 & 서식")

        # --- TAB 4:  단축키 설정 (17종 전체 커스텀) ---
        tab_shortcuts = QWidget()
        l_sc = QVBoxLayout(tab_shortcuts)
        l_sc.setContentsMargins(15, 15, 15, 15)
        l_sc.addWidget(QLabel("<b>[전역 단축키 설정 - 17종]</b><br/><span style='font-size:8.5pt; color:#8E8E93;'>원하는 기능을 선택 후 클릭하여 단축키를 즉시 조합 변경하세요.</span>"))
        
        self.shortcut_table = QTableWidget(0, 2)
        self.shortcut_table.setHorizontalHeaderLabels(["기능", "단축키"])
        self.shortcut_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        l_sc.addWidget(self.shortcut_table)
        
        self.tabs.addTab(tab_shortcuts, "단축키 설정")
        
        self.sb = QPushButton("설정 저장")
        self.sb.setCursor(Qt.CursorShape.PointingHandCursor)
        self.sb.setStyleSheet("background: #007AFF; color: white; padding: 12px; font-weight: bold; font-size: 11pt; border-radius: 12px; border: none;")
        self.sb.clicked.connect(self.save)
        main_layout.addWidget(self.sb)
        apply_ios_shadow(self)

    def test_gas_url(self) -> None:
        url = self.url_input.text().strip()
        if not url or not url.startswith("http"):
            QMessageBox.warning(self, "연결 테스트 실패", "유효한 HTTP/HTTPS URL을 입력해주세요.")
            return

        self.sm.drive_api.set_web_app_url(url)
        if hasattr(self.sm, 'ui_manager') and self.sm.ui_manager and self.sm.ui_manager.explorer_window:
            self.sm.ui_manager.explorer_window.show_toast("🔄 구글 드라이브 연결 테스트 중...")
            
        def _async_ping():
            try:
                res = self.sm.drive_api.ping_web_app()
                if res:
                    QMetaObject.invokeMethod(self, "_on_ping_success", Qt.ConnectionType.QueuedConnection)
                else:
                    QMetaObject.invokeMethod(self, "_on_ping_failed", Qt.ConnectionType.QueuedConnection)
            except Exception:
                QMetaObject.invokeMethod(self, "_on_ping_failed", Qt.ConnectionType.QueuedConnection)

        threading.Thread(target=_async_ping, daemon=True).start()

    @pyqtSlot()
    def _on_ping_success(self) -> None:
        self.sync_cb.setChecked(True)
        if hasattr(self.sm, 'ui_manager') and self.sm.ui_manager and self.sm.ui_manager.explorer_window:
            self.sm.ui_manager.explorer_window.show_toast("✓ 구글 드라이브 연결 성공! (자동 동기화 활성화)")
        else:
            QMessageBox.information(self, "연결 테스트 성공", "구글 드라이브 연결 성공!")

    @pyqtSlot()
    def _on_ping_failed(self) -> None:
        if hasattr(self.sm, 'ui_manager') and self.sm.ui_manager and self.sm.ui_manager.explorer_window:
            self.sm.ui_manager.explorer_window.show_toast("❌ 구글 드라이브 연결 실패 (URL 및 권한 확인)")
        else:
            QMessageBox.warning(self, "연결 테스트 실패", "구글 서버 응답이 없거나 URL이 올바르지 않습니다.")

    def apply_theme_style(self) -> None:
        theme = self.sm.settings.get('app_theme', 'white')
        is_dark = (theme == "dark")
        
        if is_dark:
            mode = self.sm.settings.get("dark_theme_mode", "dark")
            pal = DARK_THEMES.get(mode, DARK_THEMES["dark"])
        else:
            mode = self.sm.settings.get("light_theme_mode", "white")
            pal = LIGHT_THEMES.get(mode, LIGHT_THEMES["white"])

        self.setStyleSheet(f"""
            SettingsWindow#SettingsWindow, QWidget#SettingsWindow {{
                background-color: {pal['bg']};
            }}
            QWidget {{ font-family: 'D2Coding', 'Consolas', monospace; font-size: 9.5pt; color: {pal['text']}; background-color: {pal['bg']}; }}
            QTabWidget::pane {{ border: 1px solid {pal['border']}; border-radius: 0px; background: {pal['card']}; }}
            QTabBar::tab {{ padding: 10px 20px; font-weight: bold; background: {pal['bg']}; color: {pal['text']}; border-top-left-radius: 0px; border-top-right-radius: 0px; margin-right: 4px; }}
            QTabBar::tab:selected {{ background: {pal['accent']}; color: white; }}
            QGroupBox {{ font-weight: bold; border: 1px solid {pal['border']}; border-radius: 0px; margin-top: 12px; padding-top: 15px; background: {pal['card']}; color: {pal['text']}; }}
            QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 4px; color: {pal['accent']}; }}
            QLineEdit, QComboBox, QFontComboBox {{ padding: 8px 12px; border: 1px solid {pal['border']}; border-radius: 0px; color: {pal['text']}; background-color: {pal['input']}; }}
            QLineEdit:focus, QComboBox:focus {{ border: 1.5px solid {pal['accent']}; }}
            QComboBox QAbstractItemView {{ background-color: {pal['card']}; color: {pal['text']}; selection-background-color: {pal['accent']}; selection-color: white; }}
            QPushButton {{ padding: 8px 16px; background: {pal['card']}; border: 1px solid {pal['border']}; border-radius: 0px; color: {pal['text']}; font-weight: bold; }}
            QPushButton:hover {{ background: {pal['accent']}; color: white; }}
            QTableWidget {{ border: 1px solid {pal['border']}; border-radius: 0px; background: {pal['card']}; color: {pal['text']}; }}
            QHeaderView::section {{ background: {pal['bg']}; color: {pal['accent']}; font-weight: bold; border: none; }}
            QCheckBox {{ color: {pal['text']}; background: transparent; }}
            QLabel {{ color: {pal['text']}; background: transparent; }}
        """)

        if hasattr(self.sm, 'ui_manager') and hasattr(self.sm.ui_manager, 'get_theme_icon'):
            self.tabs.setTabIcon(0, self.sm.ui_manager.get_theme_icon("setting.svg", is_dark))
            self.tabs.setTabIcon(1, self.sm.ui_manager.get_theme_icon("cloude.svg", is_dark))
            self.tabs.setTabIcon(2, self.sm.ui_manager.get_theme_icon("colorpalette_89189.svg", is_dark))
            self.tabs.setTabIcon(3, self.sm.ui_manager.get_theme_icon("keyboard_119981.svg", is_dark))
            self.btn_test_url.setIcon(self.sm.ui_manager.get_theme_icon("search.svg", is_dark))
            self.btn_change_path.setIcon(self.sm.ui_manager.get_theme_icon("memo.svg", is_dark))
            self.sb.setIcon(self.sm.ui_manager.get_theme_icon("save.svg", True))
            
        self.sb.setStyleSheet(f"background: {pal['accent']}; color: white; padding: 12px; font-weight: bold; font-size: 11pt; border-radius: 0px; border: none;")

    def save(self) -> None:
        is_auto_login = self.cb_auto_login.isChecked()
        
        shortcuts_dict = {}
        shortcut_keys_map = {
            "한/영 영타 오타 변환": "eng_kor_convert",
            "서식 툴바 접기/열기": "toggle_fmt_bar",
            "전체 메모 내용 복사": "copy_all",
            "코드 자동 정렬 (Prettify)": "format_code",
            "새 메모 생성": "new_memo",
            "새 코드 메모 생성": "new_code_memo",
            "메모 저장": "save",
            "검색": "search",
            "제목 수정": "rename",
            "메모 탐색기 열기": "open_explorer",
            "찾아 바꾸기 창 열기": "replace",
            "화면 항상 고정(Pin) 토글": "toggle_pin",
            "메모 창 접기/펼치기 토글": "toggle_rollup",
            "현재 메모 삭제": "delete_memo",
            "코드 테마 전환 (다크/라이트)": "toggle_code_theme",
            "접은 메모 정렬": "arrange_rolled_memos",
            "메모 전체 정렬": "arrange_all_memos",
            "모든 메모 켜기": "open_all_memos",
            "모든 메모 숨기기/보이기 토글": "toggle_all_memos"
        }
        for r in range(self.shortcut_table.rowCount()):
            name = self.shortcut_table.item(r, 0).text()
            key_seq = self.shortcut_table.cellWidget(r, 1).keySequence().toString()
            if name in shortcut_keys_map:
                shortcuts_dict[shortcut_keys_map[name]] = key_seq
                
        trash_days_map = {0: 0, 1: 0, 2: 15, 3: 30}
        
        ns = {
            "use_sync": self.sync_cb.isChecked(),
            "drive_folder_id": self.url_input.text().strip(),
            "local_memo_path": self.path_input.text().strip(),
            "sync_interval_index": self.sync_interval_combo.currentIndex(),
            "auto_start": self.auto_start_cb.isChecked(),
            "auto_login": is_auto_login,
            "default_memo_color": list(self.colors.values())[self.default_color_combo.currentIndex()],
            "default_font_family": self.default_font_box.currentFont().family(),
            "default_code_font_family": self.default_code_font_box.currentFont().family(),
            "default_code_lang": self.default_code_lang_box.currentText(),
            "default_code_theme": "dark" if self.default_code_theme_box.currentIndex() == 0 else "light",
            "auto_eng_kor_convert": self.cb_auto_eng_kor.isChecked(),
            "default_gen_line_numbers": self.cb_gen_line_num.isChecked(),
            "default_gen_line_bg": self.cb_gen_line_bg.isChecked(),
            "default_code_line_numbers": self.cb_code_line_num.isChecked(),
            "default_code_line_bg": self.cb_code_line_bg.isChecked(),
            "default_show_line_numbers": self.cb_gen_line_num.isChecked(),
            "default_show_line_bg": self.cb_gen_line_bg.isChecked(),
            "default_is_pinned": self.cb_default_pin.isChecked(),
            "trash_auto_delete_days": trash_days_map.get(self.trash_auto_delete_box.currentIndex(), 0),
            "app_theme": self.sm.settings.get("app_theme", "white"),
            "dark_theme_mode": self.dark_theme_box.currentData(),
            "light_theme_mode": self.light_theme_box.currentData(),
            "default_memo_opacity": round(self.opacity_slider.value() / 100.0, 2),
            "default_memo_width": self.spin_memo_width.value(),
            "default_memo_height": self.spin_memo_height.value(),
            "default_code_memo_width": self.spin_code_memo_width.value(),
            "default_code_memo_height": self.spin_code_memo_height.value(),
            "shortcuts": shortcuts_dict
        }
        self.sm.save_settings(ns)
        if not is_auto_login:
            self.sm.save_remembered_password("", False)
            
        if hasattr(self.sm, 'ui_manager') and hasattr(self.sm.ui_manager, 'update_tray_menu'):
            self.sm.ui_manager.update_tray_menu()
            
        QMessageBox.information(self, "알림", "설정이 성공적으로 저장되었습니다.")

    def sel(self) -> None:
        p = QFileDialog.getExistingDirectory(self, "선택", self.path_input.text())
        if p:
            self.path_input.setText(p)

    def load(self) -> None:
        s = self.sm.settings
        self.sync_cb.setChecked(s.get("use_sync", False))
        self.url_input.setText(s.get("drive_folder_id",""))
        self.path_input.setText(str(self.sm.local_path))
        self.sync_interval_combo.setCurrentIndex(s.get("sync_interval_index", 0))
        self.auto_start_cb.setChecked(s.get("auto_start", False))
        self.cb_auto_login.setChecked(s.get("auto_login", False))
        self.cb_default_pin.setChecked(s.get("default_is_pinned", False))
        self.cb_auto_eng_kor.setChecked(s.get("auto_eng_kor_convert", True))
        # 투명도 슬라이더 로드
        saved_opacity = s.get("default_memo_opacity", 1.0)
        self.opacity_slider.setValue(int(round(saved_opacity * 100)))
        
        self.spin_memo_width.setValue(s.get("default_memo_width", 350))
        self.spin_memo_height.setValue(s.get("default_memo_height", 380))
        self.spin_code_memo_width.setValue(s.get("default_code_memo_width", 500))
        self.spin_code_memo_height.setValue(s.get("default_code_memo_height", 380))
        
        self.cb_gen_line_num.setChecked(s.get("default_gen_line_numbers", s.get("default_show_line_numbers", False)))
        self.cb_gen_line_bg.setChecked(s.get("default_gen_line_bg", s.get("default_show_line_bg", False)))
        self.cb_code_line_num.setChecked(s.get("default_code_line_numbers", True))
        self.cb_code_line_bg.setChecked(s.get("default_code_line_bg", False))
        
        def_font = s.get("default_font_family", "D2Coding")
        def_code_font = s.get("default_code_font_family", "D2Coding")
        
        self.default_font_box.setCurrentFont(QFont(def_font))
        self.default_code_font_box.setCurrentFont(QFont(def_code_font))
        
        self.default_code_lang_box.setCurrentText(s.get("default_code_lang", "JSON"))
        self.default_code_theme_box.setCurrentIndex(0 if s.get("default_code_theme", "dark") == "dark" else 1)
        
        dark_mode_val = s.get("dark_theme_mode", "dark")
        self.dark_theme_box.blockSignals(True)
        for i in range(self.dark_theme_box.count()):
            if self.dark_theme_box.itemData(i) == dark_mode_val:
                self.dark_theme_box.setCurrentIndex(i)
                break
        self.dark_theme_box.blockSignals(False)

        light_mode_val = s.get("light_theme_mode", "white")
        self.light_theme_box.blockSignals(True)
        for i in range(self.light_theme_box.count()):
            if self.light_theme_box.itemData(i) == light_mode_val:
                self.light_theme_box.setCurrentIndex(i)
                break
        self.light_theme_box.blockSignals(False)

        curr = s.get("default_memo_color", "#FFFFFF")
        for i, (n, c) in enumerate(self.colors.items()):
            if c == curr:
                self.default_color_combo.setCurrentIndex(i)
                break
                
        trash_days = s.get("trash_auto_delete_days", 0)
        if trash_days == 15: self.trash_auto_delete_box.setCurrentIndex(2)
        elif trash_days == 30: self.trash_auto_delete_box.setCurrentIndex(3)
        else: self.trash_auto_delete_box.setCurrentIndex(0)
                
        sc_map = s.get("shortcuts", {})
        shortcut_items = [
            ("한/영 영타 오타 변환", sc_map.get("eng_kor_convert", "Ctrl+Alt+E")),
            ("서식 툴바 접기/열기", sc_map.get("toggle_fmt_bar", "Ctrl+Shift+T")),
            ("전체 메모 내용 복사", sc_map.get("copy_all", "Ctrl+Shift+C")),
            ("코드 자동 정렬 (Prettify)", sc_map.get("format_code", "Ctrl+Shift+F")),
            ("새 메모 생성", sc_map.get("new_memo", "Ctrl+N")),
            ("새 코드 메모 생성", sc_map.get("new_code_memo", "Ctrl+Shift+N")),
            ("메모 저장", sc_map.get("save", "Ctrl+S")),
            ("검색", sc_map.get("search", "Ctrl+F")),
            ("제목 수정", sc_map.get("rename", "F2")),
            ("메모 탐색기 열기", sc_map.get("open_explorer", "Ctrl+E")),
            ("찾아 바꾸기 창 열기", sc_map.get("replace", "Ctrl+H")),
            ("화면 항상 고정(Pin) 토글", sc_map.get("toggle_pin", "Ctrl+P")),
            ("메모 창 접기/펼치기 토글", sc_map.get("toggle_rollup", "Ctrl+M")),
            ("현재 메모 삭제", sc_map.get("delete_memo", "Ctrl+D")),
            ("코드 테마 전환 (다크/라이트)", sc_map.get("toggle_code_theme", "Ctrl+Shift+L")),
            ("접은 메모 정렬", sc_map.get("arrange_rolled_memos", "Ctrl+Alt+R")),
            ("메모 전체 정렬", sc_map.get("arrange_all_memos", "Ctrl+Alt+A")),
            ("모든 메모 켜기", sc_map.get("open_all_memos", "Ctrl+Shift+O")),
            ("모든 메모 숨기기/보이기 토글", sc_map.get("toggle_all_memos", "Ctrl+Shift+H"))
        ]
        
        self.shortcut_table.setRowCount(0)
        for label_text, seq_text in shortcut_items:
            r = self.shortcut_table.rowCount()
            self.shortcut_table.insertRow(r)
            self.shortcut_table.setItem(r, 0, QTableWidgetItem(label_text))
            
            k_edit = QKeySequenceEdit(QKeySequence(seq_text))
            k_edit.setStyleSheet("border: 1px solid #C7C7CC; border-radius: 6px; padding: 2px;")
            self.shortcut_table.setCellWidget(r, 1, k_edit)