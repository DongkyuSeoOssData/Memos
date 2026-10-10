from typing import Dict, Iterable, List

from ui import modern_style
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QTextEdit, QVBoxLayout, QHBoxLayout, QApplication, QLabel, QDialog, QDialogButtonBox,
    QListWidget, QListWidgetItem, QPushButton, QSplitter
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


class HistoryDialog(QDialog):
    """메모의 이전 내용을 보고, 고른 내용으로 되돌리는 창."""

    def __init__(self, parent, title: str, entries: List[dict]) -> None:
        super().__init__(parent)
        self.setWindowTitle("이전 내용")
        self.resize(720, 460)
        self.chosen_index = None
        self._entries = entries
        modern_style.style_dialog(self, parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)
        hint = QLabel(f"<b>{title}</b> — 저장되기 전의 내용이 최근 것부터 보입니다. "
                      "되돌리면 지금 내용도 기록에 남으므로 다시 돌아올 수 있습니다.")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        split = QSplitter()
        self.list = QListWidget()
        for entry in entries:
            when = str(entry.get("saved_at", ""))[:16].replace("T", " ")
            label = when + ("  ·  " + entry["reason"] if entry.get("reason") else "")
            first_line = "🔒 암호 메모" if entry.get("locked") else (entry.get("text", "").strip().splitlines() or [""])[0][:40]
            item = QListWidgetItem(label + chr(10) + (first_line or "(빈 메모)"))
            item.setData(Qt.ItemDataRole.UserRole, entry.get("index"))
            self.list.addItem(item)
        self.list.currentRowChanged.connect(self._show)
        split.addWidget(self.list)
        self.preview = QTextEdit()
        self.preview.setReadOnly(True)
        split.addWidget(self.preview)
        split.setStretchFactor(0, 2)
        split.setStretchFactor(1, 3)
        layout.addWidget(split, 1)

        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Close)
        self.restore_button = self.buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.restore_button.setText("이 내용으로 되돌리기")
        self.buttons.button(QDialogButtonBox.StandardButton.Close).setText("닫기")
        self.buttons.accepted.connect(self._restore)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.restore_button.setEnabled(False)
        if entries:
            self.list.setCurrentRow(0)
        else:
            self.preview.setPlainText("아직 기록된 이전 내용이 없습니다. 메모를 고쳐서 저장하면 그 전의 내용이 여기에 쌓입니다.")

    def _show(self, row: int) -> None:
        if not (0 <= row < len(self._entries)):
            return
        entry = self._entries[row]
        if entry.get("locked"):
            self.preview.setPlainText("암호 메모의 기록입니다. 내용은 보이지 않지만 되돌릴 수 있습니다.\n"
                                      "되돌린 뒤에는 그때 쓰던 암호로 열어야 합니다.")
        else:
            self.preview.setPlainText(("제목: " + entry.get("title", "") + chr(10) + chr(10)) + entry.get("text", ""))
        self.restore_button.setEnabled(True)

    def _restore(self) -> None:
        item = self.list.currentItem()
        if item is not None:
            self.chosen_index = item.data(Qt.ItemDataRole.UserRole)
            self.accept()
