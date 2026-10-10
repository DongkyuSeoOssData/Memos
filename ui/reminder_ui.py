"""알림 설정 창과, 알림 시각이 됐을 때 뜨는 알림 팝업."""
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, Optional

from PyQt6.QtCore import QDateTime, Qt
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import (
    QComboBox, QDateTimeEdit, QDialog, QDialogButtonBox, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QVBoxLayout, QWidget,
)

from core import reminders
from ui import modern_style


def _next_weekday(now: datetime, weekday: int, hour: int) -> datetime:
    days = (weekday - now.weekday()) % 7 or 7
    return (now + timedelta(days=days)).replace(hour=hour, minute=0, second=0, microsecond=0)


def quick_choices(now: datetime) -> list:
    """자주 쓰는 알림 시각. [(버튼 글자, 시각), …]"""
    evening = now.replace(hour=18, minute=0, second=0, microsecond=0)
    out = [("10분 뒤", now + timedelta(minutes=10)), ("1시간 뒤", now + timedelta(hours=1))]
    if evening > now:
        out.append(("오늘 저녁 6시", evening))
    out.append(("내일 아침 9시", (now + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)))
    out.append(("다음 주 월요일 9시", _next_weekday(now, 0, 9)))
    return out


class ReminderDialog(QDialog):
    """날짜·시간과 반복(크론식 포함)을 정합니다. 확인하면 result_reminder 에 알림이, 해제하면 None 이 담깁니다."""

    def __init__(self, parent: Any, current: Optional[Dict[str, Any]] = None, title: str = "") -> None:
        super().__init__(parent)
        self.setWindowTitle("알림 설정")
        self.setMinimumWidth(420)
        self.result_reminder: Optional[Dict[str, Any]] = None
        self.cleared = False
        modern_style.style_dialog(self, parent)
        current = reminders.normalize(current)
        now = datetime.now()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)
        if title:
            layout.addWidget(QLabel(f"<b>{title}</b>"))

        self.when = QDateTimeEdit()
        self.when.setCalendarPopup(True)
        self.when.setDisplayFormat("yyyy-MM-dd (ddd) HH:mm")
        start = reminders.due_at(current) if current else (now + timedelta(hours=1)).replace(second=0, microsecond=0)
        self.when.setDateTime(QDateTime(start))
        layout.addWidget(QLabel("알릴 날짜와 시간"))
        layout.addWidget(self.when)

        quick = QGridLayout()
        quick.setSpacing(6)
        for i, (label, moment) in enumerate(quick_choices(now)):
            btn = QPushButton(label)
            btn.setAutoDefault(False)
            btn.clicked.connect(lambda checked, m=moment: self.when.setDateTime(QDateTime(m.replace(microsecond=0))))
            quick.addWidget(btn, i // 3, i % 3)
        layout.addLayout(quick)

        layout.addWidget(QLabel("반복"))
        self.repeat = QComboBox()
        for key in reminders.REPEATS:
            self.repeat.addItem(reminders.REPEAT_LABELS[key], key)
        self.repeat.setCurrentIndex(max(0, self.repeat.findData(current["repeat"] if current else "none")))
        self.repeat.currentIndexChanged.connect(self._refresh)
        layout.addWidget(self.repeat)

        self.cron = QLineEdit(current["cron"] if current else "")
        self.cron.setPlaceholderText("분 시 일 월 요일   예: 0 9 * * 1-5  (평일 오전 9시)")
        self.cron.textChanged.connect(self._refresh)
        layout.addWidget(self.cron)
        self.preview = QLabel("")
        self.preview.setWordWrap(True)
        layout.addWidget(self.preview)
        self.when.dateTimeChanged.connect(self._refresh)

        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText("알림 걸기")
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("취소")
        if current:
            clear = self.buttons.addButton("알림 해제", QDialogButtonBox.ButtonRole.DestructiveRole)
            clear.clicked.connect(self._clear)
        self.buttons.accepted.connect(self._accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self._refresh()

    def chosen(self) -> Dict[str, Any]:
        """지금 화면의 값으로 만든 알림. 크론식이 틀리면 ValueError."""
        return reminders.make(self.when.dateTime().toPyDateTime(), self.repeat.currentData(), self.cron.text())

    def _refresh(self) -> None:
        is_cron = self.repeat.currentData() == "cron"
        self.cron.setVisible(is_cron)
        self.when.setEnabled(not is_cron)          # 크론식은 식이 시각을 정합니다.
        ok = self.buttons.button(QDialogButtonBox.StandardButton.Ok)
        try:
            reminder = self.chosen()
        except ValueError as e:
            self.preview.setText(f"⚠ {e}")
            ok.setEnabled(False)
            return
        ok.setEnabled(True)
        if is_cron:
            upcoming, moment = [], datetime.now()
            for _ in range(3):
                moment = reminders.next_cron(self.cron.text(), moment)
                upcoming.append(reminders.describe({"at": moment.isoformat(), "repeat": "none"}))
            self.preview.setText("다음 알림: " + "  →  ".join(upcoming))
        elif reminders.due_at(reminder) <= datetime.now():
            self.preview.setText("⚠ 이미 지난 시각입니다. 저장하면 바로 울립니다.")
        else:
            self.preview.setText("다음 알림: " + reminders.describe(reminder))

    def _accept(self) -> None:
        try:
            self.result_reminder = self.chosen()
        except ValueError:
            return
        self.accept()

    def _clear(self) -> None:
        self.cleared = True
        self.result_reminder = None
        self.accept()


def ask_reminder(parent: Any, current: Optional[Dict[str, Any]], title: str = "") -> tuple:
    """알림 설정 창을 띄웁니다. → (바꿨는지, 새 알림 또는 None)"""
    dialog = ReminderDialog(parent, current, title)
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return False, None
    return True, dialog.result_reminder


class ReminderPopup(QWidget):
    """알림 시각이 됐을 때 화면 오른쪽 아래에 뜨는 창. 메모 열기 / 미루기 / 완료를 고릅니다."""

    SNOOZES = (("10분", 10), ("1시간", 60), ("내일", 24 * 60))

    def __init__(self, settings: Dict[str, Any], memo_id: str, title: str, detail: str,
                 on_open: Callable[[str], None], on_snooze: Callable[[str, int], None], slot: int = 0) -> None:
        super().__init__()
        self.memo_id = memo_id
        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)   # 하던 일의 입력을 빼앗지 않음
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setObjectName("ReminderPopup")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(modern_style.popup_qss(settings))
        self.setFixedWidth(340)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)
        head = QLabel("⏰ 알림")
        head.setProperty("role", "hint")
        layout.addWidget(head)
        self.title_label = QLabel(title or "(제목 없음)")
        self.title_label.setProperty("role", "title")
        self.title_label.setWordWrap(True)
        layout.addWidget(self.title_label)
        if detail:
            body = QLabel(detail)
            body.setWordWrap(True)
            layout.addWidget(body)

        row = QHBoxLayout()
        row.setSpacing(6)
        open_btn = QPushButton("메모 열기")
        open_btn.setProperty("role", "primary")
        open_btn.clicked.connect(lambda: (on_open(memo_id), self.close()))
        row.addWidget(open_btn, 1)
        done = QPushButton("완료")
        done.clicked.connect(self.close)
        row.addWidget(done, 1)
        layout.addLayout(row)

        later = QHBoxLayout()
        later.setSpacing(6)
        later_label = QLabel("미루기")
        later_label.setProperty("role", "hint")
        later.addWidget(later_label)
        later.addStretch()
        self.snooze_buttons = {}
        for label, minutes in self.SNOOZES:
            btn = QPushButton(label)
            btn.clicked.connect(lambda checked, m=minutes: (on_snooze(memo_id, m), self.close()))
            later.addWidget(btn)
            self.snooze_buttons[minutes] = btn
        layout.addLayout(later)

        self.adjustSize()
        screen = QGuiApplication.primaryScreen()
        if screen:
            area = screen.availableGeometry()
            self.move(area.left() + area.width() - self.width() - 16,
                      area.top() + area.height() - (self.height() + 12) * (slot + 1) - 4)
