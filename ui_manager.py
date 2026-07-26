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

from sync_manager import convert_eng_kor_smart, clean_plain_text


PASTEL_COLORS = ["#E0F2FE", "#DCFCE7", "#FEF9C3", "#FCE7F3", "#FFFFFF"]

DARK_THEMES = {
    "dark":    {"name": "🌙 Charcoal Gray (기본 다크)",   "bg": "#0D0D0D", "card": "#141416", "input": "#1C1C1E", "text": "#F2F2F7", "border": "rgba(255, 255, 255, 0.14)", "icon": "#FFFFFF", "accent": "#0A84FF"},
    "nord":    {"name": "❄️ Nord Dark (북유럽 쿨그레이)", "bg": "#242933", "card": "#2E3440", "input": "#3B4252", "text": "#ECEFF4", "border": "rgba(236, 239, 244, 0.16)", "icon": "#ECEFF4", "accent": "#88C0D0"},
    "tokyo":   {"name": "🌌 Tokyo Night (미드나잇 네이비)","bg": "#16161E", "card": "#1A1B26", "input": "#24283B", "text": "#C0CAF5", "border": "rgba(192, 202, 245, 0.16)", "icon": "#C0CAF5", "accent": "#7AA2F7"},
    "dracula": {"name": "🧛 Dracula Dark (다크 흑연색)",   "bg": "#21222C", "card": "#282A36", "input": "#44475A", "text": "#F8F8F2", "border": "rgba(248, 248, 242, 0.16)", "icon": "#F8F8F2", "accent": "#BD93F9"}
}

LIGHT_THEMES = {
    "white":   {"name": "☀️ Apple Pure White (클래식 화이트)", "bg": "#F2F2F7", "card": "#FFFFFF", "input": "#FFFFFF", "text": "#1C1C1E", "border": "rgba(0, 0, 0, 0.12)", "icon": "#1C1C1E", "accent": "#007AFF"},
    "ivory":   {"name": "📄 Warm Ivory (눈편한 웜 화이트)",    "bg": "#F9F8F6", "card": "#FFFFFF", "input": "#FFFFFF", "text": "#2C2A29", "border": "rgba(44, 42, 41, 0.14)", "icon": "#2C2A29", "accent": "#D97706"},
    "silver":  {"name": "❄️ Cool Silver (모던 실버 화이트)",   "bg": "#F1F5F9", "card": "#FFFFFF", "input": "#FFFFFF", "text": "#0F172A", "border": "rgba(15, 23, 42, 0.12)", "icon": "#0F172A", "accent": "#0284C7"}
}


class CodeHighlighter(QSyntaxHighlighter):
    """
    iOS 미니멀 흑백 & 모던 네온 하이라이터:
    - Light: Base Text #000000
    - Dark: Base Text #FFFFFF
    """
    def __init__(self, document: QTextDocument, lang: str = "JSON", theme: str = "dark") -> None:
        super().__init__(document)
        self.lang = lang.upper()
        self.theme = theme.lower()
        self.rules = []

        is_dark = (self.theme == "dark")
        kw_color = QColor("#FF7B72") if is_dark else QColor("#D73A49")
        str_color = QColor("#A5D6FF") if is_dark else QColor("#032F62")
        num_color = QColor("#79C0FF") if is_dark else QColor("#005CC5")
        cm_color = QColor("#8B949E") if is_dark else QColor("#6A737D")
        type_color = QColor("#D2A8FF") if is_dark else QColor("#6F42C1")

        kw_fmt = QTextCharFormat()
        kw_fmt.setForeground(kw_color)
        kw_fmt.setFontWeight(QFont.Weight.Bold)

        str_fmt = QTextCharFormat()
        str_fmt.setForeground(str_color)

        num_fmt = QTextCharFormat()
        num_fmt.setForeground(num_color)

        cm_fmt = QTextCharFormat()
        cm_fmt.setForeground(cm_color)
        cm_fmt.setFontItalic(True)

        type_fmt = QTextCharFormat()
        type_fmt.setForeground(type_color)

        if "JSON" in self.lang:
            self.rules.append((re.compile(r'"[^"\\]*(\\.[^"\\]*)*"\s*:'), type_fmt))
            self.rules.append((re.compile(r':\s*"[^"\\]*(\\.[^"\\]*)*"'), str_fmt))
            self.rules.append((re.compile(r'\b(true|false|null)\b'), kw_fmt))
            self.rules.append((re.compile(r'\b[-+]?\d*\.?\d+\b'), num_fmt))
        elif any(k in self.lang for k in ["C#", "VB.NET", "PYTHON", "JAVASCRIPT", "C++", "JAVA", "POWER"]):
            kw_pat = r'\b(public|private|protected|class|void|string|int|bool|if|else|for|foreach|while|return|using|namespace|dim|as|function|def|var|let|const|import)\b'
            self.rules.append((re.compile(kw_pat, re.IGNORECASE), kw_fmt))
            self.rules.append((re.compile(r'"[^"\\]*(\\.[^"\\]*)*"|\'[^\'\\]*(\\.[^\'\\]*)*\''), str_fmt))
            self.rules.append((re.compile(r'//.*|#.*|\'.*'), cm_fmt))
            self.rules.append((re.compile(r'\b[A-Z][a-zA-Z0-9_]*\b'), type_fmt))
            self.rules.append((re.compile(r'\b[-+]?\d+\b'), num_fmt))
        else:
            self.rules.append((re.compile(r'"[^"\\]*(\\.[^"\\]*)*"'), str_fmt))
            self.rules.append((re.compile(r'\b[-+]?\d+\b'), num_fmt))

    def highlightBlock(self, text: str) -> None:
        base_fmt = QTextCharFormat()
        base_fmt.setForeground(QColor("#FFFFFF") if self.theme == "dark" else QColor("#000000"))
        self.setFormat(0, len(text), base_fmt)

        for pattern, fmt in self.rules:
            for match in pattern.finditer(text):
                start, end = match.span()
                self.setFormat(start, end - start, fmt)


def apply_ios_shadow(widget: QWidget, blur: int = 24, offset_y: int = 4, alpha: int = 40) -> None:
    """플랫 사각형 디자인 - 그림자 효과 전면 비활성화"""
    widget.setGraphicsEffect(None)


class PasswordSetupDialog(QDialog):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("🔑 Memos 비밀번호 설정 (최초 실행)")
        self.setFixedSize(440, 320)
        self.setStyleSheet("""
            QDialog { background: #000000; font-family: 'SF Pro Display', 'Pretendard', sans-serif; }
            QLabel { color: #FFFFFF; }
            QLineEdit { padding: 12px; border: 1px solid rgba(255, 255, 255, 0.2); border-radius: 12px; background: #1C1C1E; color: white; font-size: 10pt; }
            QLineEdit:focus { border: 1.5px solid #0A84FF; }
            QCheckBox { font-size: 9.5pt; color: #0A84FF; font-weight: bold; }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)
        
        info = QLabel("<b>보안 메모 암호화 비밀번호를 설정해주세요.</b><br/><span style='font-size:9pt; color:#8E8E93;'>다른 PC에서 구글 백업본을 열 때도 동일한 비밀번호를 입력합니다.</span>")
        info.setWordWrap(True)
        layout.addWidget(info)
        
        self.p1 = QLineEdit()
        self.p1.setEchoMode(QLineEdit.EchoMode.Password)
        self.p1.setPlaceholderText("새 비밀번호 (4자리 이상)")
        layout.addWidget(self.p1)
        
        self.p2 = QLineEdit()
        self.p2.setEchoMode(QLineEdit.EchoMode.Password)
        self.p2.setPlaceholderText("비밀번호 확인")
        layout.addWidget(self.p2)
        
        self.cb_remember = QCheckBox("☑ 이 PC에서 비밀번호 기억 (자동 로그인)")
        self.cb_remember.setChecked(True)
        layout.addWidget(self.cb_remember)
        
        self.err_lbl = QLabel("")
        self.err_lbl.setStyleSheet("color: #FF453A; font-size: 9pt; font-weight: bold;")
        layout.addWidget(self.err_lbl)
        
        btn_box = QHBoxLayout()
        ok_btn = QPushButton("설정 완료")
        ok_btn.setStyleSheet("background: #0A84FF; color: white; padding: 12px 24px; border-radius: 12px; font-weight: bold; border: none;")
        ok_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        ok_btn.clicked.connect(self.validate)
        btn_box.addStretch()
        btn_box.addWidget(ok_btn)
        layout.addLayout(btn_box)
        apply_ios_shadow(self)

    def validate(self) -> None:
        pass1 = self.p1.text().strip()
        pass2 = self.p2.text().strip()
        if len(pass1) < 4:
            self.err_lbl.setText("비밀번호는 4자리 이상 입력해야 합니다.")
            return
        if pass1 != pass2:
            self.err_lbl.setText("비밀번호 확인이 일치하지 않습니다.")
            return
        self.password = pass1
        self.remember = self.cb_remember.isChecked()
        self.accept()


class PasswordLoginDialog(QDialog):
    def __init__(self, sync_manager: Any, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.sync_manager = sync_manager
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setWindowTitle(" Memos 비밀번호 잠금 해제")
        self.setFixedSize(450, 300)
        
        theme = self.sync_manager.settings.get('app_theme', 'white')
        is_dark = (theme == "dark")
        if is_dark:
            mode = self.sync_manager.settings.get("dark_theme_mode", "dark")
            pal = DARK_THEMES.get(mode, DARK_THEMES["dark"])
        else:
            mode = self.sync_manager.settings.get("light_theme_mode", "white")
            pal = LIGHT_THEMES.get(mode, LIGHT_THEMES["white"])

        self.setStyleSheet(f"""
            QDialog {{ background-color: {pal['bg']}; font-family: 'SF Pro Display', 'Pretendard', sans-serif; border: 1px solid {pal['border']}; border-radius: 16px; }}
            QLabel {{ color: {pal['text']}; background: transparent; }}
            QLineEdit {{ padding: 12px; border: 1px solid {pal['border']}; border-radius: 12px; background: {pal['input']}; color: {pal['text']}; font-size: 10pt; }}
            QLineEdit:focus {{ border: 1.5px solid {pal['accent']}; }}
            QCheckBox {{ font-size: 9.5pt; color: {pal['accent']}; font-weight: bold; margin-top: 4px; background: transparent; }}
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)
        
        layout.addWidget(QLabel("<b>메모를 해독하려면 비밀번호를 입력해주세요.</b>"))
        
        self.p_in = QLineEdit()
        self.p_in.setEchoMode(QLineEdit.EchoMode.Password)
        self.p_in.setPlaceholderText("비밀번호 입력")
        self.p_in.returnPressed.connect(self.attempt_login)
        layout.addWidget(self.p_in)
        
        self.cb_remember = QCheckBox("이 PC에서 비밀번호 기억 (자동 로그인)")
        self.cb_remember.setChecked(self.sync_manager.settings.get("auto_login", True))
        layout.addWidget(self.cb_remember)
        
        self.err_lbl = QLabel("")
        self.err_lbl.setStyleSheet("color: #FF453A; font-size: 9pt; font-weight: bold;")
        layout.addWidget(self.err_lbl)
        
        btn_box = QHBoxLayout()
        rescue_btn = QPushButton(" 비상 복구")
        rescue_btn.setStyleSheet("background: rgba(255, 69, 58, 0.15); color: #FF453A; border: 1px solid rgba(255, 69, 58, 0.4); padding: 12px 16px; border-radius: 12px; font-weight: bold;")
        rescue_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        rescue_btn.clicked.connect(self.open_otp_rescue)
        btn_box.addWidget(rescue_btn)
        btn_box.addStretch()
        
        ok_btn = QPushButton("잠금 해제")
        ok_btn.setStyleSheet(f"background: {pal['accent']}; color: white; padding: 12px 24px; border-radius: 12px; font-weight: bold; border: none;")
        ok_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        ok_btn.clicked.connect(self.attempt_login)
        btn_box.addWidget(ok_btn)
        
        layout.addLayout(btn_box)
        apply_ios_shadow(self)

    def attempt_login(self) -> None:
        pwd = self.p_in.text().strip()
        if not pwd:
            self.err_lbl.setText("비밀번호를 입력해주세요.")
            return
        if self.sync_manager.verify_and_login(pwd):
            self.sync_manager.save_remembered_password(pwd, self.cb_remember.isChecked())
            self.accept()
        else:
            self.err_lbl.setText("비밀번호가 일치하지 않습니다.")
            self.p_in.selectAll()

    def open_otp_rescue(self) -> None:
        dlg = OTPRescueDialog(self.sync_manager, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.accept()


class OTPRescueDialog(QDialog):
    def __init__(self, sync_manager: Any, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.sync_manager = sync_manager
        self.setWindowTitle("🆘 구글 OTP 비상 복구")
        self.setFixedSize(450, 320)
        self.setStyleSheet("""
            QDialog { background: #000000; font-family: 'SF Pro Display', 'Pretendard', sans-serif; }
            QLabel { color: #FFFFFF; }
            QLineEdit { padding: 12px; border: 1px solid rgba(255, 255, 255, 0.2); border-radius: 12px; background: #1C1C1E; color: white; font-size: 10pt; }
            QLineEdit:focus { border: 1.5px solid #FF453A; }
        """)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)
        
        info = QLabel("<b>스마트폰 Google Authenticator의 6자리 OTP 번호를 입력하세요.</b><br/><span style='font-size:9pt; color:#8E8E93;'>승인 시 새로운 비밀번호로 재설정되고 모든 메모가 해독됩니다.</span>")
        info.setWordWrap(True)
        layout.addWidget(info)
        
        self.otp_in = QLineEdit()
        self.otp_in.setPlaceholderText("6자리 OTP 번호 (예: 482910)")
        self.otp_in.setStyleSheet("padding: 12px; border: 1px solid rgba(255, 255, 255, 0.2); border-radius: 12px; font-size: 12pt; font-weight: bold; letter-spacing: 2px; color: #FF453A;")
        layout.addWidget(self.otp_in)
        
        self.new_p = QLineEdit()
        self.new_p.setEchoMode(QLineEdit.EchoMode.Password)
        self.new_p.setPlaceholderText("새로운 비밀번호 (4자리 이상)")
        layout.addWidget(self.new_p)
        
        self.err_lbl = QLabel("")
        self.err_lbl.setStyleSheet("color: #FF453A; font-size: 9pt; font-weight: bold;")
        layout.addWidget(self.err_lbl)
        
        btn_box = QHBoxLayout()
        cancel_btn = QPushButton("취소")
        cancel_btn.setStyleSheet("padding: 12px 20px; background: #1C1C1E; border: 1px solid rgba(255, 255, 255, 0.2); border-radius: 12px; font-weight: bold; color: white;")
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.clicked.connect(self.reject)
        
        ok_btn = QPushButton("OTP 승인 및 비상 해제")
        ok_btn.setStyleSheet("background: #FF453A; color: white; padding: 12px 20px; border-radius: 12px; font-weight: bold; border: none;")
        ok_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        ok_btn.clicked.connect(self.attempt_rescue)
        
        btn_box.addWidget(cancel_btn)
        btn_box.addStretch()
        btn_box.addWidget(ok_btn)
        layout.addLayout(btn_box)
        apply_ios_shadow(self)

    def attempt_rescue(self) -> None:
        otp = self.otp_in.text().strip()
        new_pwd = self.new_p.text().strip()
        if len(otp) != 6 or not otp.isdigit():
            self.err_lbl.setText("6자리 숫자 OTP 번호를 입력해주세요.")
            return
        if len(new_pwd) < 4:
            self.err_lbl.setText("새 비밀번호는 4자리 이상 설정해야 합니다.")
            return
            
        if self.sync_manager.reset_password_with_otp(otp, new_pwd):
            self.sync_manager.save_remembered_password(new_pwd, True)
            QMessageBox.information(self, "비상 복구 성공", "구글 OTP 인증이 승인되었습니다.\n새로운 비밀번호로 성공적으로 해독 및 재설정되었습니다.")
            self.accept()
        else:
            self.err_lbl.setText("OTP 번호가 유효하지 않거나 만료되었습니다. (30초 확인)")
            self.otp_in.selectAll()


class ConflictDialog(QDialog):
    def __init__(self, title: str, cur_c: str, trash_c: str) -> None:
        super().__init__()
        self.setWindowTitle("복구 중복 확인")
        self.setFixedSize(620, 460)
        self.setStyleSheet("background-color: #000000; color: #FFFFFF; font-family: 'SF Pro Display', 'Pretendard', sans-serif;")
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.addWidget(QLabel(f"<b style='color:#0A84FF; font-size:11pt;'>'{title}'</b>이(가) 이미 존재합니다. 덮어쓰시겠습니까?"))
        
        diff = QHBoxLayout()
        for label_text, content_text in [("[현재 로컬]", clean_plain_text(cur_c)), ("[휴지통]", clean_plain_text(trash_c))]:
            box = QVBoxLayout()
            box.addWidget(QLabel(f"<b>{label_text}</b>"))
            te = QTextEdit()
            te.setPlainText(content_text)
            te.setReadOnly(True)
            te.setStyleSheet("border: 1px solid rgba(255, 255, 255, 0.2); border-radius: 12px; padding: 10px; color: white; background: #1C1C1E;")
            box.addWidget(te)
            diff.addLayout(box)
            
        layout.addLayout(diff)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Yes | QDialogButtonBox.StandardButton.No)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)
        apply_ios_shadow(self)


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
        self.btn_win_pin.setIcon(self.ui_manager.get_theme_icon("pin_icon_True.svg" if is_pinned else "pin_icon_False.svg", is_dark))
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
            self.ui_manager.close_memo_window_by_id(memo_id)
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
                    self.ui_manager.close_memo_window_by_id(memo_id)
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


class LineNumberArea(QWidget):
    def __init__(self, editor: 'MemoTextEdit') -> None:
        super().__init__(editor)
        self.editor = editor

    def sizeHint(self) -> QSize:
        return QSize(self.editor.line_number_area_width(), 0)

    def paintEvent(self, event: Any) -> None:
        self.editor.line_number_area_paint_event(event)


class MemoTextEdit(QTextEdit):
    def __init__(self, memo_window: 'MemoWindow') -> None:
        super().__init__()
        self.memo_window = memo_window
        self.extra_cursors: List[QTextCursor] = []
        self.line_number_area = LineNumberArea(self)
        self.document().documentLayout().update.connect(self.update_line_number_area)
        self.verticalScrollBar().valueChanged.connect(self.line_number_area.update)
        self.textChanged.connect(self.update_line_number_area)

    def mousePressEvent(self, e: Any) -> None:
        if e.button() == Qt.MouseButton.LeftButton and (e.modifiers() & Qt.KeyboardModifier.AltModifier):
            click_cursor = self.cursorForPosition(e.pos())
            all_positions = [c.position() for c in ([self.textCursor()] + self.extra_cursors)]
            if click_cursor.position() not in all_positions:
                self.extra_cursors.append(click_cursor)
            self.viewport().update()
            e.accept()
            return
        elif e.button() == Qt.MouseButton.LeftButton and not (e.modifiers() & Qt.KeyboardModifier.AltModifier):
            if self.extra_cursors:
                self.extra_cursors.clear()
                self.viewport().update()
        super().mousePressEvent(e)

    def line_number_area_width(self) -> int:
        if not self.memo_window.memo_data.get('show_line_numbers', False):
            return 0
        digits = len(str(max(1, self.document().blockCount())))
        return 15 + self.fontMetrics().horizontalAdvance('9') * digits

    def update_line_number_area(self) -> None:
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)
        self.line_number_area.setVisible(self.memo_window.memo_data.get('show_line_numbers', False))
        cr = self.contentsRect()
        self.line_number_area.setGeometry(QRect(cr.left(), cr.top(), self.line_number_area_width(), cr.height()))
        self.line_number_area.update()

    def resizeEvent(self, e: Any) -> None:
        super().resizeEvent(e)
        cr = self.contentsRect()
        self.line_number_area.setGeometry(QRect(cr.left(), cr.top(), self.line_number_area_width(), cr.height()))

    def line_number_area_paint_event(self, event: Any) -> None:
        painter = QPainter(self.line_number_area)
        theme = self.memo_window.memo_window_get_settings().get('app_theme', 'white')
        is_dark = (theme == "dark")
        
        bg_color = QColor(0, 0, 0, 40) if is_dark else QColor(0, 0, 0, 15)
        text_color = QColor("#8E8E93")
            
        painter.fillRect(event.rect(), bg_color) 
        painter.setPen(text_color) 
        painter.setFont(self.font())
        
        block = self.document().begin()
        scroll_y = self.verticalScrollBar().value()
        block_number = 0
        
        while block.isValid():
            block_bb = self.document().documentLayout().blockBoundingRect(block)
            pos_y = block_bb.top() - scroll_y
            
            if pos_y <= event.rect().bottom() and pos_y + block_bb.height() >= event.rect().top():
                painter.drawText(
                    0, int(pos_y), self.line_number_area.width() - 5, self.fontMetrics().height(),
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, str(block_number + 1)
                )
                                 
            block = block.next()
            block_number += 1

    def keyPressEvent(self, e: Any) -> None:
        if e.key() == Qt.Key.Key_Escape:
            self.memo_window.close()
            e.accept()
            return

        is_code = self.memo_window.memo_data.get('is_code_memo', False)

        # VS Code 스타일 멀티 커서 복제 (Ctrl+Alt+Up/Down, Alt+Shift+Up/Down, Ctrl+Shift+Up/Down)
        has_ctrl = bool(e.modifiers() & Qt.KeyboardModifier.ControlModifier)
        has_alt = bool(e.modifiers() & Qt.KeyboardModifier.AltModifier)
        has_shift = bool(e.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        is_multi_shortcut = (has_ctrl and has_alt) or (has_alt and has_shift) or (has_ctrl and has_shift)

        if is_multi_shortcut and e.key() in (Qt.Key.Key_Up, Qt.Key.Key_Down):
            base_cursor = self.extra_cursors[-1] if self.extra_cursors else self.textCursor()
            new_cursor = QTextCursor(base_cursor)
            if e.key() == Qt.Key.Key_Down:
                moved = new_cursor.movePosition(QTextCursor.MoveOperation.Down)
            else:
                moved = new_cursor.movePosition(QTextCursor.MoveOperation.Up)
            
            if moved:
                self.extra_cursors.append(new_cursor)
                self.viewport().update()
            e.accept()
            return

        # 멀티 커서 활성화 시 타이핑 / 백스페이스 / Delete 동기화 처리
        if self.extra_cursors:
            if e.key() == Qt.Key.Key_Escape:
                self.extra_cursors.clear()
                self.viewport().update()
                e.accept()
                return

            all_cursors = [self.textCursor()] + self.extra_cursors
            pos_dict = {}
            for c in all_cursors:
                pos_dict[c.position()] = c
            all_cursors = list(pos_dict.values())
            all_cursors.sort(key=lambda c: c.position(), reverse=True)
            key_text = e.text()

            if e.key() == Qt.Key.Key_Backspace:
                self.textCursor().beginEditBlock()
                for c in all_cursors:
                    if c.hasSelection():
                        c.removeSelectedText()
                    else:
                        c.deletePreviousChar()
                self.textCursor().endEditBlock()
                self.setTextCursor(all_cursors[0])
                self.extra_cursors = all_cursors[1:]
                self.viewport().update()
                e.accept()
                return
            elif e.key() == Qt.Key.Key_Delete:
                self.textCursor().beginEditBlock()
                for c in all_cursors:
                    if c.hasSelection():
                        c.removeSelectedText()
                    else:
                        c.deleteChar()
                self.textCursor().endEditBlock()
                self.setTextCursor(all_cursors[0])
                self.extra_cursors = all_cursors[1:]
                self.viewport().update()
                e.accept()
                return
            elif key_text and (key_text.isprintable() or key_text in ('\r', '\n', '\t')):
                if not (has_ctrl and not (has_alt or has_shift)):
                    self.textCursor().beginEditBlock()
                    for c in all_cursors:
                        if c.hasSelection():
                            c.removeSelectedText()
                        c.insertText(key_text)
                    self.textCursor().endEditBlock()
                    self.setTextCursor(all_cursors[0])
                    self.extra_cursors = all_cursors[1:]
                    self.viewport().update()
                    e.accept()
                    return

        # VS Code 스타일 줄 상하 이동 (Alt+Up / Alt+Down)
        if (e.modifiers() == Qt.KeyboardModifier.AltModifier) and e.key() in (Qt.Key.Key_Up, Qt.Key.Key_Down):
            cursor = self.textCursor()
            block = cursor.block()
            if e.key() == Qt.Key.Key_Up and block.previous().isValid():
                cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
                cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
                line_text = cursor.selectedText()
                cursor.removeSelectedText()
                cursor.deletePreviousChar()
                cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
                cursor.insertText(line_text + "\n")
                cursor.movePosition(QTextCursor.MoveOperation.Up)
                self.setTextCursor(cursor)
            elif e.key() == Qt.Key.Key_Down and block.next().isValid():
                cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
                cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
                line_text = cursor.selectedText()
                cursor.removeSelectedText()
                cursor.deleteChar()
                cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock)
                cursor.insertText("\n" + line_text)
                self.setTextCursor(cursor)
            e.accept()
            return

        # 코드 메모 전용 IDE 고급 기능: 자동 괄호/따옴표/스마트 딜리트/지속적 스마트 들여쓰기
        if is_code:
            cursor = self.textCursor()
            key_text = e.text()

            # 1. 백스페이스(Backspace) 연결 괄호 쌍 동시 삭제
            if e.key() == Qt.Key.Key_Backspace and not cursor.hasSelection():
                pos = cursor.position()
                doc_text = self.toPlainText()
                if 0 < pos < len(doc_text):
                    prev_char = doc_text[pos - 1]
                    next_char = doc_text[pos]
                    pair_map = {'{': '}', '(': ')', '[': ']', '"': '"', "'": "'"}
                    if prev_char in pair_map and pair_map[prev_char] == next_char:
                        cursor.deletePreviousChar()
                        cursor.deleteChar()
                        self.setTextCursor(cursor)
                        e.accept()
                        return

            # 2. 닫는 괄호/따옴표 덮어쓰기 (Overtyping)
            if key_text in ('}', ')', ']', '"', "'") and not cursor.hasSelection():
                pos = cursor.position()
                doc_text = self.toPlainText()
                if pos < len(doc_text) and doc_text[pos] == key_text:
                    cursor.movePosition(QTextCursor.MoveOperation.Right)
                    self.setTextCursor(cursor)
                    e.accept()
                    return

            # 3. 여는 괄호/따옴표 자동 완성
            pair_map = {'{': '}', '(': ')', '[': ']', '"': '"', "'": "'"}
            if key_text in pair_map:
                closing = pair_map[key_text]
                if cursor.hasSelection():
                    sel = cursor.selectedText()
                    cursor.insertText(f"{key_text}{sel}{closing}")
                else:
                    cursor.insertText(f"{key_text}{closing}")
                    cursor.movePosition(QTextCursor.MoveOperation.Left)
                self.setTextCursor(cursor)
                e.accept()
                return

            # 4. 지속적인 스마트 엔터 들여쓰기 유지 (Auto-Indentation Level Maintenance)
            if e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                pos = cursor.position()
                doc_text = self.toPlainText()

                # (1) { | } 사이에서 Enter 누를 시 3줄 자동 형성 및 정밀 들여쓰기
                if 0 < pos < len(doc_text) and doc_text[pos - 1] in ('{', '[', '(') and doc_text[pos] in ('}', ']', ')'):
                    line_text = cursor.block().text()
                    indent_str = line_text[:len(line_text) - len(line_text.lstrip())]
                    cursor.insertText(f"\n{indent_str}    \n{indent_str}")
                    cursor.movePosition(QTextCursor.MoveOperation.Up)
                    cursor.movePosition(QTextCursor.MoveOperation.EndOfLine)
                    self.setTextCursor(cursor)
                    e.accept()
                    return

                # (2) 일반 엔터 누를 시 이전 줄의 들여쓰기(공백)를 지속 유지 + 여는 기호 수용
                line_text = cursor.block().text()
                indent_str = line_text[:len(line_text) - len(line_text.lstrip())]
                
                stripped_line = line_text[:cursor.positionInBlock()].rstrip()
                if stripped_line and stripped_line[-1] in ('{', '[', '(', ':'):
                    indent_str += "    "

                cursor.insertText(f"\n{indent_str}")
                self.setTextCursor(cursor)
                e.accept()
                return

        if e.key() == Qt.Key.Key_Backtab or (e.key() == Qt.Key.Key_Tab and e.modifiers() & Qt.KeyboardModifier.ShiftModifier):
            self.memo_window.apply_outdent()
            e.accept()
            return
        elif e.key() == Qt.Key.Key_Tab:
            self.memo_window.apply_indent()
            e.accept()
            return
        elif e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            cursor = self.textCursor()
            current_indent = cursor.blockFormat().indent()
            super().keyPressEvent(e)
            if current_indent > 0:
                new_cursor = self.textCursor()
                bf = new_cursor.blockFormat()
                bf.setIndent(current_indent)
                new_cursor.setBlockFormat(bf)
            return
            
        super().keyPressEvent(e)

    def paintEvent(self, event: Any) -> None:
        painter = QPainter(self.viewport())
        show_bg = self.memo_window.memo_data.get('show_line_bg', False)
        is_code = self.memo_window.memo_data.get('is_code_memo', False)
        
        if is_code:
            code_theme = self.memo_window.memo_data.get('code_theme', 'dark')
            is_dark_bg = (code_theme == "dark")
        else:
            bg_color = self.memo_window.memo_data.get('bg_color', '#FFFFFF')
            if bg_color == "random": bg_color = "#FFFFFF"
            is_dark_bg = True if bg_color in ['#2E3440', '#1C1C1E', '#000000'] else False
            if not is_dark_bg:
                c_obj = QColor(bg_color)
                if c_obj.isValid():
                    lum = (0.299 * c_obj.red() + 0.587 * c_obj.green() + 0.114 * c_obj.blue()) / 255.0
                    if lum < 0.5:
                        is_dark_bg = True

        grid_color = QColor(255, 255, 255, 45) if is_dark_bg else QColor(0, 0, 0, 45)
        indent_color = QColor(142, 142, 147, 100) 
        scroll_y = self.verticalScrollBar().value()
        fm = self.fontMetrics()
        line_height = fm.lineSpacing()
        
        if show_bg:
            painter.setPen(grid_color)
            block = self.document().begin()
            last_bottom = 0
            while block.isValid():
                block_bb = self.document().documentLayout().blockBoundingRect(block)
                pos_y = block_bb.top() - scroll_y
                line_bottom = int(pos_y + block_bb.height())
                if line_bottom > 0 and pos_y <= self.viewport().height():
                    painter.drawLine(0, line_bottom, self.viewport().width(), line_bottom)
                last_bottom = line_bottom
                block = block.next()
            
            y = last_bottom + line_height if last_bottom > 0 else int(line_height - (scroll_y % line_height))
            while y < self.viewport().height():
                painter.drawLine(0, y, self.viewport().width(), y)
                y += line_height

        if not is_code:
            painter.setPen(indent_color)
            space_width = fm.horizontalAdvance(' ')
            tab_width = space_width * 4 
            indent_width_block = int(self.document().indentWidth())
            block = self.document().begin()
            
            while block.isValid():
                block_bb = self.document().documentLayout().blockBoundingRect(block)
                pos_y = block_bb.top() - scroll_y
                if pos_y <= event.rect().bottom() and pos_y + block_bb.height() >= event.rect().top():
                    base_x = block_bb.left()
                    block_indent = block.blockFormat().indent()
                    if block_indent > 0:
                        for i in range(1, block_indent + 1):
                            x = int(base_x - (block_indent - i) * indent_width_block - indent_width_block + (space_width * 2))
                            if x > 0: painter.drawLine(x, int(pos_y), x, int(pos_y + block_bb.height()))

                    text = block.text()
                    space_count = sum(4 if ch == '\t' else 1 for ch in text if ch in [' ', '\t'])
                    space_indent = space_count // 4
                    for i in range(1, space_indent + 1):
                        x = int(base_x + (i * tab_width) - space_width)
                        if x > 0: painter.drawLine(x, int(pos_y), x, int(pos_y + block_bb.height()))
                block = block.next()
                
        painter.end()
        super().paintEvent(event)

    def wheelEvent(self, event: Any) -> None:
        modifiers = QApplication.keyboardModifiers()
        delta = event.angleDelta().y()
        if modifiers == Qt.KeyboardModifier.ControlModifier:
            f = self.font()
            s = max(8, min(40, f.pointSize() + (1 if delta > 0 else -1)))
            f.setPointSize(s)
            self.setFont(f)
            cursor = self.textCursor()
            cursor.select(QTextCursor.SelectionType.Document)
            fmt = QTextCharFormat()
            fmt.setFont(f)
            cursor.mergeCharFormat(fmt)
            self.memo_window.memo_data['font_size'] = s
            self.update_line_number_area()
            if hasattr(self.memo_window, '_wheel_save_timer'):
                self.memo_window._wheel_save_timer.start(1000)
            self.memo_window.show_toast(f"폰트 크기: {s}pt")
            event.accept() 
            return
        elif modifiers == Qt.KeyboardModifier.ShiftModifier:
            op = max(0.3, min(1.0, self.memo_window.windowOpacity() + (0.05 if delta > 0 else -0.05)))
            self.memo_window.setWindowOpacity(op)
            self.memo_window.memo_data['opacity'] = op
            if hasattr(self.memo_window, '_wheel_save_timer'):
                self.memo_window._wheel_save_timer.start(1000)
            self.memo_window.show_toast(f"투명도: {int(op * 100)}%")
            event.accept() 
            return
        super().wheelEvent(event)


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
        self.toast_label.setStyleSheet("background-color: #007AFF; color: white; font-weight: bold; border-radius: 10px; padding: 6px 14px; font-size: 9.5pt;")
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
        
        if self.memo_data.get('show_line_bg', False):
            self.text_edit.setStyleSheet(f"QTextEdit {{ border:none; background: transparent; color:{text_color}; background-image: repeating-linear-gradient(transparent, transparent 27px, {line_color} 28px); background-attachment: local; }}")
        else:
            self.text_edit.setStyleSheet(f"QTextEdit {{ border:none; background: transparent; color:{text_color}; }}")
        
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
        self.title_edit.setStyleSheet("border:none; background:transparent; font-weight:bold; font-size:11.5pt; font-family: 'SF Pro Display', 'Pretendard', sans-serif;")
        self.title_edit.editingFinished.connect(self.handle_rename)
        self.title_edit.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.title_edit.customContextMenuRequested.connect(self.show_menu)
        self.title_edit.installEventFilter(self)
        ctrl.addWidget(self.title_edit, 1)
        
        self.btn_code_theme = QPushButton("")
        self.btn_code_theme.setFixedSize(90, 24)
        self.btn_code_theme.setStyleSheet("font-size: 8pt; font-weight: bold; border: 1px solid #0A84FF; border-radius: 10px; background: #1C1C1E; color: #0A84FF; padding: 0 6px;")
        self.btn_code_theme.clicked.connect(self.toggle_code_theme)
        self.btn_code_theme.hide()

        self.code_lang_box = QComboBox()
        self.code_lang_box.addItems(["JSON", "C#", "VB.NET", "Power Automate", "PowerShell", "Batch (CMD)", "SQL", "Markdown", "Python", "JavaScript", "HTML", "CSS", "C++", "Java", "Plain Text"])
        self.code_lang_box.setFixedHeight(24)
        self.code_lang_box.setStyleSheet("font-size: 8.5pt; font-weight: bold; padding: 0 4px; border: 1px solid #0A84FF; border-radius: 10px; background: #1C1C1E; color: #0A84FF;")
        self.code_lang_box.currentTextChanged.connect(self.on_code_lang_changed)
        self.code_lang_box.hide()
        
        ctrl.addWidget(self.btn_code_theme)
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
        self.memo_data['content'] = self.text_edit.toPlainText()
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
        btn_style_off = f"border:none; color:{btn_text_color}; font-size:10pt; background: transparent; font-weight:bold;"
        btn_style_on = "border:none; color:white; font-size:10pt; background: #007AFF; font-weight:bold; border-radius: 6px;"

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
        self.btn_toggle_sub_fmt.setText("A🎨 ▴" if not is_vis else "A🎨 ▾")

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
        menu.addAction("🎨 사용자 지정 RGB 색상...").triggered.connect(self.choose_bg_color)
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
        
        is_code = self.memo_data.get('is_code_memo', False)
        if is_code:
            menu.addAction("✨ 코드 자동 정렬 (Ctrl+Shift+F)").triggered.connect(self.prettify_code)
            menu.addAction("📋 코드만 클립보드 복사").triggered.connect(self.copy_all_content)
            menu.addAction("🌙 / ☀️ 코드 테마 전환 (Ctrl+Shift+L)").triggered.connect(self.toggle_code_theme)
        else:
            menu.addAction("📋 전체 메모 내용 복사 (클립보드)").triggered.connect(self.copy_all_content)
            
        menu.addAction("🔤 한/영 영타 오타 변환 (Ctrl+Alt+E)").triggered.connect(self.convert_selected_eng_kor)
        
        menu.addSeparator()
        s = self.memo_window_get_settings()
        is_auto_convert = s.get("auto_eng_kor_convert", True)
        auto_convert_action = menu.addAction(f"🔤 한/영 자동 변환기 [{ 'ON' if is_auto_convert else 'OFF' }]")
        auto_convert_action.setCheckable(True)
        auto_convert_action.setChecked(is_auto_convert)
        auto_convert_action.triggered.connect(self.toggle_auto_eng_kor_setting)
        
        menu.addSeparator()
        menu.addAction("저장 (Ctrl+S)").triggered.connect(self.manual_save)
        menu.addAction("검색 (Ctrl+F)").triggered.connect(self.show_search_only)
        menu.addAction("바꾸기 (Ctrl+H)").triggered.connect(self.show_search_and_replace)
        menu.addAction("📌 화면 고정 토글 (Ctrl+P)").triggered.connect(self.toggle_pin)
        menu.addAction("📐 메모 창 접기 (Ctrl+M)").triggered.connect(self.toggle_rollup)
        
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
        opacity_menu = menu.addMenu("🔆 창 투명도 조절")
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
        menu.addAction("ⓧ 메모 삭제 (Ctrl+D)").triggered.connect(lambda: self.delete_callback(self))
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
        """글씨색 선택 (순차 변경)"""
        colors = ["#000000", "#FF3B30", "#007AFF", "#34C759", "#FF9500", "#FFFFFF"]
        cur = getattr(self, '_current_fg_idx', -1)
        cur = (cur + 1) % len(colors)
        self._current_fg_idx = cur
        color = QColor(colors[cur])
        
        cursor = self.text_edit.textCursor()
        if not cursor.hasSelection():
            cursor.select(QTextCursor.SelectionType.Document)
        fmt = QTextCharFormat()
        fmt.setForeground(color)
        cursor.mergeCharFormat(fmt)
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
        list_fmt = QTextListFormat()
        list_fmt.setStyle(QTextListFormat.Style.ListDisc)
        list_fmt.setIndent(1)
        cursor.createList(list_fmt)
        self.update_toolbar_button_states()
        self.manual_save()

    def apply_number(self) -> None:
        cursor = self.text_edit.textCursor()
        list_fmt = QTextListFormat()
        list_fmt.setStyle(QTextListFormat.Style.ListDecimal)
        list_fmt.setIndent(1)
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
        if self.memo_data.get('is_code_memo', False):
            self.memo_data['content'] = self.text_edit.toPlainText()
        else:
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
        self.memo_data['is_manually_saved'] = True
        self.memo_data['is_draft'] = False
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
        f = Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool
        f = f | Qt.WindowType.WindowStaysOnTopHint if self.memo_data.get('is_pinned') else f
        self.setWindowFlags(f)
        
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
                "border: none; border-radius: 12px; font-weight: bold; font-size: 9pt; } "
                "QPushButton:hover { background: #007AFF; }"
            )
        else:
            self.btn_pin.setText("")
            pin_btn_bg     = "rgba(255,255,255,0.12)" if is_memo_dark_bg else "rgba(0,0,0,0.06)"
            pin_btn_border = "rgba(255,255,255,0.18)" if is_memo_dark_bg else "rgba(0,0,0,0.15)"
            pin_btn_color  = "#AEAEB2" if is_memo_dark_bg else "#636366"
            self.btn_pin.setStyleSheet(
                f"QPushButton {{ background: {pin_btn_bg}; color: {pin_btn_color}; "
                f"border: 1px solid {pin_btn_border}; border-radius: 12px; font-size: 9pt; }} "
                f"QPushButton:hover {{ background: #0A84FF; color: white; border-color: #0A84FF; }}"
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
            else:
                self.btn_format_code.show()
                self.btn_code_theme.show()
                self.code_lang_box.show()

            code_theme = self.memo_data.get('code_theme', 'dark')
            lang = self.memo_data.get('code_lang', 'JSON')

            self.btn_code_theme.setText(" 라이트" if code_theme == "dark" else " 다크")
            if getattr(self, 'ui_manager', None) and hasattr(self.ui_manager, 'get_theme_icon'):
                self.btn_code_theme.setIcon(self.ui_manager.get_theme_icon("litemode.svg" if code_theme == "dark" else "darkmod.svg", is_memo_dark_bg))
            
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

            title_c = pal['accent']
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

            box_style = f"font-size: 8.5pt; font-weight: bold; padding: 2px 6px; border: 1px solid {btn_border_color}; border-radius: 0px; background: {btn_bg_color}; color: {btn_text_color};"
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
                f"font-family: 'SF Pro Display', 'Pretendard', sans-serif;"
            )
            self.text_edit.setStyleSheet(
                f"QTextEdit {{ border:none; background:transparent; color:{text_c}; }}"
            )

            self.text_edit.setTextColor(QColor(text_c))
            cursor = self.text_edit.textCursor()
            cursor.select(QTextCursor.SelectionType.Document)
            base_fmt = QTextCharFormat()
            base_fmt.setForeground(QColor(text_c))
            cursor.mergeCharFormat(base_fmt)

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
        if self.memo_data.get('is_code_memo', False):
            if "<html" in cnt:
                cnt = clean_plain_text(cnt)
            self.text_edit.setPlainText(cnt)
        else:
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
        self.title_edit.setStyleSheet("border:1px solid #007AFF; background:white; color:#000000; font-weight:bold; font-size:12pt; border-radius:0px;")
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
        
        title_color = "#64D2FF" if is_code else ("#FFFFFF" if is_dark else "#1C1C1E")
        self.title_edit.setStyleSheet(f"border:none; background:transparent; color:{title_color}; font-weight:bold; font-size:12pt;")
        self.title_edit.setCursorPosition(0)
        if getattr(self, 'ui_manager', None) and self.ui_manager.explorer_window and self.ui_manager.explorer_window.isVisible():
            self.ui_manager.explorer_window.update_table()
        
    def toggle_pin(self) -> None:
        self.memo_data['is_pinned'] = not self.memo_data.get('is_pinned', False)
        self.apply_data()
        self.show()
        self.save_callback(self.memo_data)
        self.show_toast("📌 화면 고정 켜짐" if self.memo_data['is_pinned'] else "📍 화면 고정 해제됨")
        
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
        self.sync_manager.set_ui_manager(self)
        self.setup_tray()
    
    def get_theme_icon(self, svg_name: str, is_dark: Optional[bool] = None, override_color: Optional[str] = None) -> QIcon:
        if getattr(sys, 'frozen', False):
            base_dir = Path(getattr(sys, '_MEIPASS', Path(__file__).parent))
        else:
            base_dir = Path(__file__).parent
            
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
        icon = self.get_theme_icon("memo.svg", is_dark=False, override_color="#000000")
        self.tray_icon = QSystemTrayIcon(icon)
        self.tray_icon.activated.connect(self.on_tray_activated)
        
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
        
        act_new = menu.addAction(f"새 메모 ({s.get('new_memo', 'Ctrl+N')})")
        act_new.setIcon(self.get_theme_icon("memo.svg", is_dark))
        act_new.triggered.connect(self.create_empty_memo)

        act_code = menu.addAction(f"새 코드 메모 ({s.get('new_code_memo', 'Ctrl+Shift+N')})")
        act_code.setIcon(self.get_theme_icon("codememo.svg", is_dark))
        act_code.triggered.connect(self.create_code_memo)

        act_arr_r = menu.addAction(f"접은 메모 정렬 ({s.get('arrange_rolled_memos', 'Ctrl+Alt+R')})")
        act_arr_r.setIcon(self.get_theme_icon("정렬1.svg", is_dark))
        act_arr_r.triggered.connect(self.arrange_rolled_up_memos)

        act_exp = menu.addAction(f"메모 탐색기 ({s.get('open_explorer', 'Ctrl+E')})")
        act_exp.setIcon(self.get_theme_icon("memo.svg", is_dark))
        act_exp.triggered.connect(self.open_memo_explorer)

        act_arr_a = menu.addAction(f"펼친 메모 정렬 ({s.get('arrange_all_memos', 'Ctrl+Alt+A')})")
        act_arr_a.setIcon(self.get_theme_icon("정렬2.svg", is_dark))
        act_arr_a.triggered.connect(self.arrange_memos)

        act_sync = menu.addAction("지금 동기화")
        act_sync.setIcon(self.get_theme_icon("cloude.svg", is_dark))
        act_sync.triggered.connect(self.sync_manager.sync_push)
        
        self.toggle_action = menu.addAction("모두 숨기기")
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
        
        self.tray_icon.setContextMenu(menu)
        self.tray_icon.show()

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
            
    def close_memo_window_by_id(self, memo_id: str) -> None:
        if memo_id in self.memo_windows:
            self.memo_windows[memo_id].close()

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
        self.a = QCheckBox("윈도우 시작 시 자동 실행")
        
        self.cb_gen_line_num = QCheckBox("일반 메모: 최초 실행 시 행번호 표시")
        self.cb_gen_line_bg = QCheckBox("일반 메모: 최초 실행 시 줄노트 배경 표시")
        self.cb_code_line_num = QCheckBox("코드 메모: 최초 실행 시 행번호 표시")
        self.cb_code_line_bg = QCheckBox("코드 메모: 최초 실행 시 줄노트 배경 표시")
        
        for cb_item in [
            self.cb_default_pin, self.cb_auto_eng_kor, self.a,
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
        self.u = QLineEdit()
        self.u.setPlaceholderText("https://script.google.com/macros/s/.../exec")
        self.u.setFixedHeight(40)
        
        self.btn_test_url = QPushButton(" 연결 테스트")
        self.btn_test_url.setFixedHeight(40)
        self.btn_test_url.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_test_url.clicked.connect(self.test_gas_url)
        
        url_box.addWidget(self.u)
        url_box.addWidget(self.btn_test_url)
        g1_l.addLayout(url_box)
        
        g1_l.addWidget(QLabel("로컬 메모 저장 위치:"))
        ph = QHBoxLayout()
        self.p = QLineEdit()
        self.p.setReadOnly(True)
        self.p.setFixedHeight(40)
        self.btn_change_path = QPushButton(" 경로 변경")
        self.btn_change_path.setFixedHeight(40)
        self.btn_change_path.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_change_path.clicked.connect(self.sel)
        ph.addWidget(self.p)
        ph.addWidget(self.btn_change_path)
        g1_l.addLayout(ph)
        
        g1_l.addWidget(QLabel("자동 동기화 주기:"))
        self.s = QComboBox()
        self.s.addItems(["1분마다", "10분마다", "30분마다", "1시간마다"])
        self.s.setFixedHeight(40)
        g1_l.addWidget(self.s)
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
        self.c = QComboBox()
        self.c.setFixedHeight(40)
        for idx, (name, color_hex) in enumerate(self.colors.items()):
            self.c.addItem(name)
            if color_hex != "random":
                self.c.setItemData(idx, QColor(color_hex), Qt.ItemDataRole.BackgroundRole)
        g3_l.addWidget(self.c)
        
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
        url = self.u.text().strip()
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

    def _on_ping_success(self) -> None:
        self.sync_cb.setChecked(True)
        if hasattr(self.sm, 'ui_manager') and self.sm.ui_manager and self.sm.ui_manager.explorer_window:
            self.sm.ui_manager.explorer_window.show_toast("✓ 구글 드라이브 연결 성공! (자동 동기화 활성화)")
        else:
            QMessageBox.information(self, "연결 테스트 성공", "구글 드라이브 연결 성공!")

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
            QWidget {{ font-family: 'SF Pro Display', 'Pretendard', sans-serif; font-size: 9.5pt; color: {pal['text']}; background-color: {pal['bg']}; }}
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
            "메모 전체 정렬": "arrange_all_memos"
        }
        for r in range(self.shortcut_table.rowCount()):
            name = self.shortcut_table.item(r, 0).text()
            key_seq = self.shortcut_table.cellWidget(r, 1).keySequence().toString()
            if name in shortcut_keys_map:
                shortcuts_dict[shortcut_keys_map[name]] = key_seq
                
        trash_days_map = {0: 0, 1: 0, 2: 15, 3: 30}
        
        ns = {
            "use_sync": self.sync_cb.isChecked(),
            "drive_folder_id": self.u.text().strip(), 
            "local_memo_path": self.p.text().strip(), 
            "sync_interval_index": self.s.currentIndex(), 
            "auto_start": self.a.isChecked(), 
            "auto_login": is_auto_login,
            "default_memo_color": list(self.colors.values())[self.c.currentIndex()],
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
        QMessageBox.information(self, "알림", "설정이 성공적으로 저장되었습니다.")

    def sel(self) -> None:
        p = QFileDialog.getExistingDirectory(self, "선택", self.p.text())
        if p:
            self.p.setText(p)

    def load(self) -> None:
        s = self.sm.settings
        self.sync_cb.setChecked(s.get("use_sync", False))
        self.u.setText(s.get("drive_folder_id",""))
        self.p.setText(str(self.sm.local_path))
        self.s.setCurrentIndex(s.get("sync_interval_index", 0))
        self.a.setChecked(s.get("auto_start", False))
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
                self.c.setCurrentIndex(i)
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
            ("메모 전체 정렬", sc_map.get("arrange_all_memos", "Ctrl+Alt+A"))
        ]
        
        self.shortcut_table.setRowCount(0)
        for label_text, seq_text in shortcut_items:
            r = self.shortcut_table.rowCount()
            self.shortcut_table.insertRow(r)
            self.shortcut_table.setItem(r, 0, QTableWidgetItem(label_text))
            
            k_edit = QKeySequenceEdit(QKeySequence(seq_text))
            k_edit.setStyleSheet("border: 1px solid #C7C7CC; border-radius: 6px; padding: 2px;")
            self.shortcut_table.setCellWidget(r, 1, k_edit)