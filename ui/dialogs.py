from typing import Dict, Iterable, List
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QTextEdit, QVBoxLayout, QHBoxLayout, QApplication, QLabel, QDialog, QDialogButtonBox,
    QListWidget, QListWidgetItem, QPushButton
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


class FolderPickDialog(QDialog):
    """폴더를 여러 개 골라 한 번에 삭제하기 위한 창. 폴더마다 체크 상자와 메모 개수가 보입니다."""

    def __init__(self, parent, names: List[str], counts: Dict[str, int], preselect: Iterable[str] = ()) -> None:
        super().__init__(parent)
        self.setWindowTitle("여러 폴더 삭제")
        self.setMinimumSize(360, 420)
        self._syncing = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)
        hint = QLabel("삭제할 폴더를 고르세요. 상위 폴더를 고르면 하위 폴더도 함께 삭제됩니다.\n"
                      "메모는 지워지지 않고 미분류로 옮겨집니다.")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.list = QListWidget()
        chosen = set(preselect)
        for path in names:
            depth = path.count("/")
            item = QListWidgetItem("　" * depth + path.rsplit("/", 1)[-1] + f"  ({counts.get(path, 0)})")
            item.setData(Qt.ItemDataRole.UserRole, path)
            item.setFlags((item.flags() | Qt.ItemFlag.ItemIsUserCheckable) & ~Qt.ItemFlag.ItemIsSelectable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.list.addItem(item)
        self.list.itemChanged.connect(self._on_item_changed)
        for i in range(self.list.count()):
            if self.list.item(i).data(Qt.ItemDataRole.UserRole) in chosen:
                self.list.item(i).setCheckState(Qt.CheckState.Checked)
        layout.addWidget(self.list, 1)

        pick_row = QHBoxLayout()
        for label, state in (("모두 선택", Qt.CheckState.Checked), ("모두 해제", Qt.CheckState.Unchecked)):
            btn = QPushButton(label)
            btn.clicked.connect(lambda checked, st=state: self._set_all(st))
            pick_row.addWidget(btn)
        pick_row.addStretch()
        layout.addLayout(pick_row)

        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText("삭제")
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("취소")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self._refresh_ok()

    def _set_all(self, state: Qt.CheckState) -> None:
        for i in range(self.list.count()):
            self.list.item(i).setCheckState(state)

    def _on_item_changed(self, item: QListWidgetItem) -> None:
        """상위 폴더를 고르거나 풀면 그 아래 폴더도 같이 바꿉니다. (상위를 지우면 하위도 지워지므로)"""
        if self._syncing:
            return
        self._syncing = True
        path = item.data(Qt.ItemDataRole.UserRole)
        for i in range(self.list.count()):
            other = self.list.item(i)
            if other.data(Qt.ItemDataRole.UserRole).startswith(path + "/"):
                other.setCheckState(item.checkState())
        self._syncing = False
        self._refresh_ok()

    def _refresh_ok(self) -> None:
        if hasattr(self, "buttons"):
            self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(bool(self.selected()))

    def selected(self) -> List[str]:
        return [self.list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.list.count())
                if self.list.item(i).checkState() == Qt.CheckState.Checked]
