from typing import Dict
from PyQt6.QtWidgets import (
    QTextEdit, QVBoxLayout, QHBoxLayout, QApplication, QLabel, QDialog, QDialogButtonBox
)
from PyQt6.QtGui import QPalette
from utils.text_utils import clean_plain_text


def _system_dialog_palette() -> Dict[str, str]:
    pal = QApplication.palette()
    return {
        'bg': pal.color(QPalette.ColorRole.Window).name(),
        'card': pal.color(QPalette.ColorRole.Base).name(),
        'input': pal.color(QPalette.ColorRole.Base).name(),
        'text': pal.color(QPalette.ColorRole.WindowText).name(),
        'border': pal.color(QPalette.ColorRole.Mid).name(),
        'accent': pal.color(QPalette.ColorRole.Highlight).name(),
        'highlight_text': pal.color(QPalette.ColorRole.HighlightedText).name(),
    }

class ConflictDialog(QDialog):
    def __init__(self, title: str, cur_c: str, trash_c: str) -> None:
        super().__init__()
        pal = _system_dialog_palette()
        self.setWindowTitle("복구 중복 확인")
        self.setFixedSize(620, 460)
        self.setStyleSheet(f"background-color: {pal['bg']}; color: {pal['text']}; font-family: 'D2Coding', 'Consolas', monospace;")
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.addWidget(QLabel(f"<b style='color:{pal['accent']}; font-size:11pt;'>'{title}'</b>이(가) 이미 존재합니다. 덮어쓰시겠습니까?"))
        
        diff = QHBoxLayout()
        for label_text, content_text in [("[현재 로컬]", clean_plain_text(cur_c)), ("[휴지통]", clean_plain_text(trash_c))]:
            box = QVBoxLayout()
            box.addWidget(QLabel(f"<b>{label_text}</b>"))
            te = QTextEdit()
            te.setPlainText(content_text)
            te.setReadOnly(True)
            te.setStyleSheet(f"border: 1px solid {pal['border']}; border-radius: 0px; padding: 10px; color: {pal['text']}; background: {pal['card']};")
            box.addWidget(te)
            diff.addLayout(box)
            
        layout.addLayout(diff)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Yes | QDialogButtonBox.StandardButton.No)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)
