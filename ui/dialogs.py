from typing import Dict, Iterable, List

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QTextEdit, QVBoxLayout, QHBoxLayout, QLabel, QDialogButtonBox,
    QLineEdit, QListWidget, QListWidgetItem, QPushButton, QWidget
)
from ui.check_marks import CheckEdit
from ui.themed_dialog import ThemedDialog
from utils.text_utils import clean_plain_text


class ConflictDialog(ThemedDialog):
    """휴지통에서 복원하려는 메모와 같은 메모가 이미 있을 때, 두 내용을 나란히 보여 주고 덮어쓸지 묻습니다."""

    def __init__(self, title: str, cur_c: str, trash_c: str, parent=None) -> None:
        super().__init__(parent, "복원 중복 확인")
        self.resize(640, 460)
        layout = self.body
        head = QLabel(f"<b>'{title}'</b> 메모가 이미 있습니다. 휴지통의 내용으로 덮어쓸까요?")
        head.setWordWrap(True)
        layout.addWidget(head)

        diff = QHBoxLayout()
        diff.setSpacing(10)
        for label_text, content_text in [("지금 있는 메모", clean_plain_text(cur_c)), ("휴지통의 메모", clean_plain_text(trash_c))]:
            box = QVBoxLayout()
            box.setSpacing(6)
            box.addWidget(QLabel(f"<b>{label_text}</b>"))
            te = QTextEdit()
            te.setPlainText(content_text)
            te.setReadOnly(True)
            box.addWidget(te)
            diff.addLayout(box)
        layout.addLayout(diff, 1)
        self.add_buttons("덮어쓰기", "취소", danger=True)


class FolderPickDialog(ThemedDialog):
    """폴더를 여러 개 골라 한 번에 삭제하기 위한 창. 폴더마다 체크 상자와 메모 개수가 보입니다."""

    def __init__(self, parent, names: List[str], counts: Dict[str, int], preselect: Iterable[str] = ()) -> None:
        super().__init__(parent, "여러 폴더 삭제")
        self.setMinimumSize(360, 420)
        self._syncing = False

        layout = self.body
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


class HistoryView(QWidget):
    """메모의 이전 내용을 보고, 고른 내용으로 되돌리는 화면.

    왼쪽에는 기록 목록(저장 시각과 제목)만 보이고, 하나를 누르면 오른쪽에 그 본문과 '되돌리기' 버튼이 펼쳐집니다.
    되돌리기를 누르면 submitted(기록 번호) 를, 닫으면 cancelled 를 보냅니다.
    """

    submitted = pyqtSignal(object)
    cancelled = pyqtSignal()
    layout_changed = pyqtSignal()        # 본문 쪽이 펼쳐져 화면 크기가 달라졌을 때

    LIST_WIDTH = 230
    DETAIL_WIDTH = 340

    def __init__(self, title: str, entries: List[dict], wide: bool = False, reveal=None, check=None) -> None:
        super().__init__()
        self.chosen_index = None
        self.chosen_password = ""           # 되돌릴 기록을 푸는 데 쓴 암호 (메모가 열려 있어 그 키로 풀리면 빈 글자)
        self._entries = entries
        self._reveal = reveal               # (기록 번호, 암호) → 본문 글자 또는 None. 암호 메모의 기록을 열어 볼 때 씁니다.
        self._check = check                 # (기록 번호, 암호) → 되돌릴 수 없는 이유 (되돌릴 수 있으면 빈 글자)
        self._password = ""                 # 한 번 맞은 암호는 이 화면이 떠 있는 동안 다른 기록에도 써 봅니다.

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(12)

        # 왼쪽: 기록 목록
        left = QVBoxLayout()
        left.setSpacing(8)
        hint = QLabel(f"<b>{title}</b><br>저장되기 전의 내용입니다. 최근 것부터 보이며, 누르면 본문이 옆에 펼쳐집니다.")
        hint.setWordWrap(True)
        hint.setProperty("role", "hint")
        hint.setFixedWidth(self.LIST_WIDTH)
        left.addWidget(hint)
        self.list = QListWidget()
        self.list.setFixedWidth(self.LIST_WIDTH)
        for entry in entries:
            when = str(entry.get("saved_at", ""))[5:16].replace("T", " ").replace("-", ".")
            name = "🔒 암호 메모" if entry.get("locked") else (str(entry.get("title", "")) or "(제목 없음)")
            item = QListWidgetItem(when + chr(10) + name)
            item.setToolTip(entry.get("reason", "") or name)
            item.setData(Qt.ItemDataRole.UserRole, entry.get("index"))
            self.list.addItem(item)
        if not entries:
            empty = QListWidgetItem("아직 기록이 없습니다." + chr(10) + "메모를 고쳐 저장하면 쌓입니다.")
            empty.setFlags(Qt.ItemFlag.NoItemFlags)
            self.list.addItem(empty)
        left.addWidget(self.list, 1)
        self.close_button = QPushButton("닫기")
        self.close_button.clicked.connect(self.cancelled.emit)
        left.addWidget(self.close_button)
        row.addLayout(left)

        # 오른쪽: 고른 기록의 본문 (기록을 고르기 전에는 숨김)
        self.detail = QWidget()
        self.detail.setFixedWidth(self.DETAIL_WIDTH)
        right = QVBoxLayout(self.detail)
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(8)
        self.detail_title = QLabel("")
        self.detail_title.setProperty("role", "title")
        self.detail_title.setWordWrap(True)
        right.addWidget(self.detail_title)
        # 암호 메모의 기록: 암호를 넣어야 내용이 보입니다. (되돌리기 전에 확인할 수 있도록)
        self.unlock_row = QWidget()
        unlock = QHBoxLayout(self.unlock_row)
        unlock.setContentsMargins(0, 0, 0, 0)
        unlock.setSpacing(6)
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_edit.setPlaceholderText("그때 쓰던 암호를 넣으면 내용이 보입니다")
        self.password_edit.returnPressed.connect(self._unlock_current)
        unlock.addWidget(self.password_edit, 1)
        self.unlock_button = QPushButton("내용 보기")
        self.unlock_button.clicked.connect(self._unlock_current)
        unlock.addWidget(self.unlock_button)
        self.unlock_row.hide()
        right.addWidget(self.unlock_row)
        self.unlock_error = QLabel("")
        self.unlock_error.setProperty("role", "error")
        self.unlock_error.hide()
        right.addWidget(self.unlock_error)

        self.preview = CheckEdit()                      # 체크 상자를 본문과 같은 네모로 보여 줌 (읽기 전용이라 눌러도 바뀌지 않음)
        self.preview.setReadOnly(True)
        right.addWidget(self.preview, 1)
        self.restore_button = QPushButton("이 내용으로 되돌리기")
        self.restore_button.setProperty("role", "primary")
        self.restore_button.clicked.connect(self._restore)
        self.restore_button.setEnabled(False)
        right.addWidget(self.restore_button)
        self.detail.hide()
        row.addWidget(self.detail)

        self.list.currentRowChanged.connect(self._show)
        self.list.itemClicked.connect(lambda item: self._show(self.list.row(item)))

    def focus_first(self) -> None:
        self.list.setFocus()

    def _show(self, row: int) -> None:
        if not (0 <= row < len(self._entries)):
            return
        entry = self._entries[row]
        when = str(entry.get("saved_at", ""))[:16].replace("T", " ")
        reason = "  ·  " + entry["reason"] if entry.get("reason") else ""
        self.detail_title.setText((str(entry.get("title", "")) or "(제목 없음)") + chr(10) + when + reason)
        self.unlock_error.hide()
        opened = None
        if entry.get("locked") and self._reveal:
            # 메모가 열려 있으면 그 키로, 아니면 앞서 맞은 암호로 먼저 열어 봅니다.
            opened = self._reveal(entry.get("index"), self._password)
        self.unlock_row.setVisible(bool(entry.get("locked")) and opened is None and self._reveal is not None)
        if not entry.get("locked"):
            self.preview.setPlainText(entry.get("text", ""))
        elif opened is not None:
            self.preview.setPlainText(opened)
        else:
            self.preview.setPlainText("암호 메모의 기록입니다. 위에 그때 쓰던 암호를 넣으면 내용을 볼 수 있습니다.\n"
                                      "되돌릴 때도 그 암호가 필요합니다. 되돌린 뒤에도 메모의 암호는 지금 그대로입니다.")
        self.restore_button.setEnabled(True)
        if self.detail.isHidden():
            self.detail.show()
            self.layout_changed.emit()

    def _unlock_current(self) -> None:
        """암호 칸의 암호로 지금 고른 기록을 열어 봅니다."""
        row = self.list.currentRow()
        if self._reveal is None or not (0 <= row < len(self._entries)):
            return
        password = self.password_edit.text()
        opened = self._reveal(self._entries[row].get("index"), password) if password else None
        if opened is None:
            self.unlock_error.setText("⚠ 암호가 일치하지 않습니다." if password else "⚠ 암호를 입력하세요.")
            self.unlock_error.show()
            self.password_edit.selectAll()
            self.password_edit.setFocus()
            return
        self._password = password
        self.password_edit.clear()
        self.unlock_error.hide()
        self.unlock_row.hide()
        self.preview.setPlainText(opened)

    def _restore(self) -> None:
        item = self.list.currentItem()
        if item is None or item.data(Qt.ItemDataRole.UserRole) is None:
            return
        index = item.data(Qt.ItemDataRole.UserRole)
        password = self._password or self.password_edit.text()
        problem = self._check(index, password) if self._check else ""
        if problem:
            # 잠긴 메모이거나 다른 암호로 잠긴 기록: 닫지 않고 이유를 알려 줍니다.
            self.unlock_error.setText("⚠ " + problem)
            self.unlock_error.show()
            if self.unlock_row.isVisible():
                self.password_edit.setFocus()
            return
        self.chosen_index, self.chosen_password = index, password
        self.submitted.emit(index)


class HistoryDialog(ThemedDialog):
    """이전 내용 화면을 담은 대화상자. (탐색기에서 부를 때)"""

    def __init__(self, parent, title: str, entries: List[dict], reveal=None, check=None) -> None:
        super().__init__(parent, "이전 내용", fit_content=True)       # 본문이 펼쳐지면 창도 따라 넓어짐
        self.view = HistoryView(title, entries, wide=True, reveal=reveal, check=check)
        self.view.setMinimumHeight(400)
        self.body.addWidget(self.view)
        self.view.submitted.connect(lambda index: self.accept())
        self.view.cancelled.connect(self.reject)

    def __getattr__(self, name: str):
        if name == "view":
            raise AttributeError(name)
        return getattr(self.view, name)


def pick_history(parent, title: str, entries: List[dict], reveal=None, check=None):
    """되돌릴 기록을 고릅니다. → (기록 번호, 그 기록을 푸는 데 쓴 암호) (닫으면 None)

    메모 창에서 부르면 그 메모의 오른쪽에 붙는 패널로, 그 밖에는 대화상자로 보여 줍니다.
    reveal(기록 번호, 암호) 은 암호 메모의 기록을 열어 볼 때, check(기록 번호, 암호) 는 되돌릴 수 있는지 확인할 때 씁니다.
    """
    window = parent.window() if parent is not None else None
    if hasattr(window, "side_panel") and window.isVisible() and not window.side_panel().is_busy():
        view = HistoryView(title, entries, reveal=reveal, check=check)
        chosen = window.side_panel().run(view, "이전 내용", min_height=460)
        return None if chosen is None else (chosen, view.chosen_password)
    dialog = HistoryDialog(parent, title, entries, reveal, check)
    if dialog.exec() and dialog.chosen_index is not None:
        return dialog.chosen_index, dialog.chosen_password
    return None


class FolderOpenDialog(ThemedDialog):
    """'메모 열기' 단축키: 열 폴더를 고르는 창. 전체·미분류·폴더마다 메모 개수가 보입니다. 더블클릭이나 '열기'로 고릅니다."""

    def __init__(self, parent, entries: List[tuple]) -> None:
        super().__init__(parent, "메모 열기")
        self.chosen = None
        self.body.addWidget(QLabel("어느 폴더의 메모를 열까요? (하위 폴더 포함)"))
        self.list = QListWidget()
        self.list.setMinimumSize(320, 300)
        for path, label, count in entries:              # (폴더 경로, 보여 줄 이름, 메모 수)
            item = QListWidgetItem(f"{label}  ({count}개)")
            item.setData(Qt.ItemDataRole.UserRole, path)
            self.list.addItem(item)
        if self.list.count():
            self.list.setCurrentRow(0)
        self.list.itemDoubleClicked.connect(lambda item: self.accept())
        self.body.addWidget(self.list, 1)
        self.add_buttons("열기", "취소")

    def accept(self) -> None:
        item = self.list.currentItem()
        self.chosen = item.data(Qt.ItemDataRole.UserRole) if item else None
        super().accept()


def ask_folder_to_open(parent, entries: List[tuple]):
    """열 폴더를 고릅니다. 폴더 경로(전체는 folders.ALL), 취소면 None."""
    dialog = FolderOpenDialog(parent, entries)
    return dialog.chosen if dialog.exec() else None
