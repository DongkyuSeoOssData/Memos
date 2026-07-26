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

class PasswordSetupDialog(QDialog):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("🔑 Memos 비밀번호 설정 (최초 실행)")
        self.setFixedSize(440, 320)
        self.setStyleSheet("""
            QDialog { background: #000000; font-family: 'D2Coding', 'Consolas', monospace; }
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
            QDialog {{ background-color: {pal['bg']}; font-family: 'D2Coding', 'Consolas', monospace; border: 1px solid {pal['border']}; border-radius: 16px; }}
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
            QDialog { background: #000000; font-family: 'D2Coding', 'Consolas', monospace; }
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
        self.setStyleSheet("background-color: #000000; color: #FFFFFF; font-family: 'D2Coding', 'Consolas', monospace;")
        
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