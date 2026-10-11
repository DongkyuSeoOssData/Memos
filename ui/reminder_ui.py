"""알림 설정 창과, 알림 시각이 됐을 때 뜨는 알림 팝업."""
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, Optional, Tuple

from PyQt6.QtCore import QDate, Qt, pyqtSignal
from PyQt6.QtGui import QGuiApplication, QIntValidator
from PyQt6.QtWidgets import (
    QCalendarWidget, QCheckBox, QComboBox, QDateEdit, QDialog, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QVBoxLayout, QWidget,
)

from core import reminders
from ui import modern_style, themed_dialog
from ui.themed_dialog import ThemedDialog


DEFAULT_QUICK_MINUTES = (10, 30, 60)


def quick_minutes(settings: Dict[str, Any]) -> list:
    """환경설정에서 정한 '빠른 선택' 세 개(분). 값이 이상하면 기본값을 씁니다."""
    saved = settings.get("reminder_quick_minutes")
    if isinstance(saved, (list, tuple)):
        picked = [v for v in saved if isinstance(v, int) and not isinstance(v, bool) and 1 <= v <= 10080]
        if picked:
            return picked[:3]
    return list(DEFAULT_QUICK_MINUTES)


def minutes_label(minutes: int) -> str:
    """'10분 뒤', '1시간 뒤', '1시간 30분 뒤', '1일 뒤' 같은 버튼 글자."""
    days, rest = divmod(minutes, 1440)
    hours, mins = divmod(rest, 60)
    parts = [f"{days}일" if days else "", f"{hours}시간" if hours else "", f"{mins}분" if mins else ""]
    return " ".join(p for p in parts if p) + " 뒤"


def quick_choices(now: datetime, minutes: Any = None) -> list:
    """알림 시각 빠른 선택. [(버튼 글자, 시각), …]"""
    return [(minutes_label(m), now + timedelta(minutes=m)) for m in (minutes or DEFAULT_QUICK_MINUTES)]


class TimeInput(QWidget):
    """시간 입력. 시와 분을 숫자로 바로 적습니다.

    12시간제에서는 오전/오후 버튼이 보이고, 24시간제에서는 0~23시로 적습니다. 어느 쪽으로 볼지는 '24시간' 체크로 바꿉니다.
    시를 두 자리 적으면 분 칸으로 넘어가고, 12시간제에서 13~23 을 적으면 오후로 바꿔 줍니다.
    """

    changed = pyqtSignal()
    format_changed = pyqtSignal(bool)        # 24시간제로 볼지를 바꿨을 때

    def __init__(self, hour: int = 9, minute: int = 0, use_24h: bool = False) -> None:
        super().__init__()
        self._use_24h = use_24h
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        self.btn_am = QPushButton("오전")
        self.btn_pm = QPushButton("오후")
        for btn in (self.btn_am, self.btn_pm):
            btn.setCheckable(True)
            btn.setAutoDefault(False)
            btn.setProperty("role", "pick")
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedWidth(46)
            row.addWidget(btn)
        self.btn_am.clicked.connect(lambda: self._pick_half(False))
        self.btn_pm.clicked.connect(lambda: self._pick_half(True))
        self.hour = QLineEdit()
        self.minute = QLineEdit()
        for box, tip in ((self.hour, "시"), (self.minute, "분")):
            box.setValidator(QIntValidator(0, 99, box))
            box.setMaxLength(2)
            box.setAlignment(Qt.AlignmentFlag.AlignCenter)
            box.setFixedWidth(46)
            box.setPlaceholderText(tip)
            box.setProperty("role", "time")
        row.addWidget(self.hour)
        colon = QLabel(":")
        colon.setProperty("role", "title")
        row.addWidget(colon)
        row.addWidget(self.minute)
        row.addStretch(1)
        self.check_24h = QCheckBox("24시간")
        self.check_24h.setChecked(use_24h)
        self.check_24h.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.check_24h.setToolTip("켜면 0~23시로, 끄면 오전/오후로 나눠 적습니다")
        row.addWidget(self.check_24h)
        self.set_time(hour, minute)
        self.hour.textEdited.connect(self._hour_typed)
        self.minute.textEdited.connect(lambda text: self.changed.emit())
        self.check_24h.toggled.connect(self._switch_format)
        self.setFocusProxy(self.hour)

    # ── 값 ───────────────────────────────────────────────────────────────────
    def time(self) -> Optional[Tuple[int, int]]:
        """(시 0~23, 분). 칸이 비었거나 범위를 벗어나면 None."""
        if not self.hour.text() or not self.minute.text():
            return None
        hour, minute = int(self.hour.text()), int(self.minute.text())
        if minute > 59:
            return None
        if self._use_24h:
            return (hour, minute) if hour <= 23 else None
        if not 1 <= hour <= 12:
            return None
        return hour % 12 + (12 if self.btn_pm.isChecked() else 0), minute

    def set_time(self, hour: int, minute: int) -> None:
        self.btn_am.setChecked(hour < 12)
        self.btn_pm.setChecked(hour >= 12)
        self.btn_am.setVisible(not self._use_24h)
        self.btn_pm.setVisible(not self._use_24h)
        self.hour.setText(f"{hour:02d}" if self._use_24h else str(hour % 12 or 12))
        self.minute.setText(f"{minute:02d}")

    def is_24h(self) -> bool:
        return self._use_24h

    # ── 입력 ─────────────────────────────────────────────────────────────────
    def _pick_half(self, afternoon: bool) -> None:
        self.btn_am.setChecked(not afternoon)
        self.btn_pm.setChecked(afternoon)
        self.changed.emit()

    def _hour_typed(self, text: str) -> None:
        if text:
            value = int(text)
            if not self._use_24h and (13 <= value <= 23 or (value == 0 and len(text) == 2)):
                # 12시간제에서 24시간식으로 적으면 알아서 바꿔 줍니다. (15 → 오후 3, 00 → 오전 12)
                self._pick_half(value >= 12)
                self.hour.setText(str(value % 12 or 12))
                text = "00"
            # 더 적을 자릿수가 없으면 분 칸으로 넘어갑니다. (두 자리를 다 적었거나, 첫 숫자만으로 정해지는 경우)
            if len(text) == 2 or value > (2 if self._use_24h else 1):
                self.minute.setFocus()
                self.minute.selectAll()
        self.changed.emit()

    def _switch_format(self, use_24h: bool) -> None:
        current = self.time()
        self._use_24h = use_24h
        if current is not None:
            self.set_time(*current)
        else:
            self.btn_am.setVisible(not use_24h)
            self.btn_pm.setVisible(not use_24h)
        self.format_changed.emit(use_24h)
        self.changed.emit()


class ReminderForm(QWidget):
    """알림을 정하는 화면. 메모 창 안의 가림막에도, 대화상자에도 똑같이 들어갑니다.

    '반복'을 끄면 날짜(달력)와 시간을 한 번 고르고, 켜면 반복 방식에 맞는 입력만 보입니다.
      매일·평일마다 → 시간 / 매주 → 요일(여러 개) + 시간 / 매월 → 날짜(여러 개) + 시간 / 크론식 → 식
    확인하면 submitted((True, 알림 또는 None)) 을, 취소하면 cancelled 를 보냅니다. (알림 해제는 None)
    """

    submitted = pyqtSignal(object)
    cancelled = pyqtSignal()
    layout_changed = pyqtSignal()        # 보이는 입력이 바뀌어 화면 크기가 달라졌을 때

    REPEAT_CHOICES = (("daily", "매일"), ("weekdays", "평일마다 (월~금)"), ("weekly", "매주"), ("monthly", "매월"), ("cron", "크론식으로 지정"))
    CRON_EXAMPLES = (
        ("0 9 * * *", "매일 오전 9시"),
        ("0 9 * * 1-5", "평일(월~금) 오전 9시"),
        ("30 18 * * 5", "매주 금요일 오후 6시 30분"),
        ("0 10 1,15 * *", "매월 1일과 15일 오전 10시"),
        ("0 9,14 * * *", "매일 오전 9시와 오후 2시"),
        ("*/30 9-18 * * 1-5", "평일 9시~18시대에 30분마다"),
        ("0 9 1 1,7 *", "1월 1일과 7월 1일 오전 9시"),
    )
    CRON_HELP = (
        "띄어쓰기로 나눈 다섯 칸을 순서대로 적습니다.<br>"
        "<b>분</b>(0-59) &nbsp; <b>시</b>(0-23) &nbsp; <b>일</b>(1-31) &nbsp; <b>월</b>(1-12) &nbsp; <b>요일</b>(0-6)<br>"
        "요일: 0 일 · 1 월 · 2 화 · 3 수 · 4 목 · 5 금 · 6 토<br>"
        "<b>*</b> 모든 값 &nbsp;·&nbsp; <b>1,15</b> 1과 15 &nbsp;·&nbsp; <b>1-5</b> 1부터 5까지 &nbsp;·&nbsp; <b>*/10</b> 10마다"
    )

    def __init__(self, current: Optional[Dict[str, Any]] = None, title: str = "", heading: str = "") -> None:
        super().__init__()
        self.result_reminder: Optional[Dict[str, Any]] = None
        self.cleared = False
        current = reminders.normalize(current)
        repeating = bool(current) and current["repeat"] != "none"
        now = datetime.now()
        use_24h = bool(themed_dialog.current_settings().get("time_24h", False))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        if heading:
            head = QLabel(heading)
            head.setProperty("role", "title")
            layout.addWidget(head)
        if title:
            layout.addWidget(QLabel(f"<b>{title}</b>"))

        # ── 한 번만 울리는 알림: 날짜(달력) + 빠른 선택 ──
        self.once_box = QWidget()
        once = QVBoxLayout(self.once_box)
        once.setContentsMargins(0, 0, 0, 0)
        once.setSpacing(8)
        date_row = QHBoxLayout()
        date_row.setSpacing(10)
        date_row.addWidget(QLabel("날짜"))
        self.date = QDateEdit()
        self.date.setCalendarPopup(True)
        self.date.setDisplayFormat("yyyy-MM-dd (ddd)")
        self.date.calendarWidget().setGridVisible(False)
        self.date.calendarWidget().setVerticalHeaderFormat(QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader)
        date_row.addWidget(self.date, 1)
        once.addLayout(date_row)
        quick = QGridLayout()
        quick.setSpacing(6)
        for n, (label, moment) in enumerate(quick_choices(now, quick_minutes(themed_dialog.current_settings()))):
            btn = QPushButton(label)
            btn.setAutoDefault(False)
            btn.setProperty("role", "quick")
            btn.clicked.connect(lambda checked, m=moment: self._set_moment(m))
            quick.addWidget(btn, n // 3, n % 3)
        once.addLayout(quick)
        layout.addWidget(self.once_box)

        # ── 반복 ──
        repeat_row = QHBoxLayout()
        repeat_row.setSpacing(10)
        self.repeat_check = QCheckBox("반복")
        self.repeat_check.setChecked(repeating)
        repeat_row.addWidget(self.repeat_check)
        self.repeat = QComboBox()
        for key, label in self.REPEAT_CHOICES:
            self.repeat.addItem(label, key)
        self.repeat.setCurrentIndex(max(0, self.repeat.findData(current["repeat"])) if repeating else 0)
        repeat_row.addWidget(self.repeat, 1)
        layout.addLayout(repeat_row)

        # 요일 (매주)
        self.weekday_box = QWidget()
        week = QHBoxLayout(self.weekday_box)
        week.setContentsMargins(0, 0, 0, 0)
        week.setSpacing(4)
        chosen_weekdays = current.get("weekdays") if repeating and current.get("weekdays") else [now.weekday()]
        self.weekday_buttons = []
        for n, name in enumerate("월화수목금토일"):
            btn = self._toggle(name, n in chosen_weekdays)
            week.addWidget(btn, 1)
            self.weekday_buttons.append(btn)
        layout.addWidget(self.weekday_box)

        # 날짜 (매월)
        self.day_box = QWidget()
        month = QVBoxLayout(self.day_box)
        month.setContentsMargins(0, 0, 0, 0)
        month.setSpacing(6)
        grid = QGridLayout()
        grid.setSpacing(4)
        chosen_days = current.get("days") if repeating and current.get("days") else [now.day]
        self.day_buttons = {}
        for day in range(1, 32):
            btn = self._toggle(str(day), day in chosen_days)
            grid.addWidget(btn, (day - 1) // 7, (day - 1) % 7)
            self.day_buttons[day] = btn
        month.addLayout(grid)
        month.addWidget(self._hint("날짜를 여러 개 고를 수 있습니다. 29~31일처럼 그 달에 없는 날짜는 그 달의 마지막 날에 울립니다."))
        layout.addWidget(self.day_box)

        # 시간 (크론식이 아닌 모든 경우)
        self.time_box = QWidget()
        time_row = QHBoxLayout(self.time_box)
        time_row.setContentsMargins(0, 0, 0, 0)
        time_row.setSpacing(10)
        if repeating:
            base = reminders._parse_at(current.get("resume") or current["at"])
        elif current:
            base = reminders.due_at(current)
        else:
            base = (now + timedelta(hours=1)).replace(second=0, microsecond=0)
        self.time = TimeInput(base.hour, base.minute, use_24h)
        self.time.format_changed.connect(self._save_time_format)
        time_row.addWidget(self.time, 1)
        layout.addWidget(self.time_box)
        self.date.setDate(QDate(base.year, base.month, base.day) if not repeating else QDate(now.year, now.month, now.day))

        # 크론식
        self.cron_box = QWidget()
        cron = QVBoxLayout(self.cron_box)
        cron.setContentsMargins(0, 0, 0, 0)
        cron.setSpacing(6)
        self.cron = QLineEdit(current["cron"] if repeating else "")
        self.cron.setPlaceholderText("분 시 일 월 요일     예: 0 9 * * 1-5")
        cron.addWidget(self.cron)
        cron.addWidget(self._hint(self.CRON_HELP))
        cron.addWidget(self._hint("예시 (누르면 입력됩니다)"))
        self.example_buttons = []
        for expr, meaning in self.CRON_EXAMPLES:
            btn = QPushButton(f"{expr:<20}{meaning}")
            btn.setProperty("role", "example")
            btn.setAutoDefault(False)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda checked, e=expr: self.cron.setText(e))
            cron.addWidget(btn)
            self.example_buttons.append(btn)
        layout.addWidget(self.cron_box)

        self.preview = QLabel("")
        self.preview.setWordWrap(True)
        layout.addWidget(self.preview)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        self.clear_button = None
        if current:
            self.clear_button = QPushButton("알림 해제")
            self.clear_button.setAutoDefault(False)
            self.clear_button.clicked.connect(self._clear)
            buttons.addWidget(self.clear_button)
        buttons.addStretch(1)
        self.ok_button = QPushButton("알림 걸기")
        self.ok_button.setProperty("role", "primary")
        self.ok_button.clicked.connect(self._accept)
        buttons.addWidget(self.ok_button)
        self.cancel_button = QPushButton("취소")
        self.cancel_button.setAutoDefault(False)
        self.cancel_button.clicked.connect(self.cancelled.emit)
        buttons.addWidget(self.cancel_button)
        layout.addLayout(buttons)

        for signal in (self.repeat_check.toggled, self.repeat.currentIndexChanged, self.cron.textChanged,
                       self.date.dateChanged, self.time.changed):
            signal.connect(self._refresh)
        self._refresh()

    def _toggle(self, text: str, on: bool) -> QPushButton:
        """요일·날짜를 고르는 누름 단추. (여러 개를 켤 수 있음)"""
        btn = QPushButton(text)
        btn.setCheckable(True)
        btn.setChecked(on)
        btn.setAutoDefault(False)
        btn.setProperty("role", "pick")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.toggled.connect(self._refresh)
        return btn

    @staticmethod
    def _hint(text: str) -> QLabel:
        label = QLabel(text)
        label.setProperty("role", "hint")
        label.setWordWrap(True)
        return label

    def focus_first(self) -> None:
        self.time.hour.setFocus()
        self.time.hour.selectAll()

    def _set_moment(self, moment: datetime) -> None:
        self.date.setDate(QDate(moment.year, moment.month, moment.day))
        self.time.set_time(moment.hour, moment.minute)
        self._refresh()

    @staticmethod
    def _save_time_format(use_24h: bool) -> None:
        """12시간제/24시간제 선택을 기억하고, 알림 시각을 보여 주는 곳들도 같은 방식으로 맞춥니다."""
        themed_dialog.save_settings({"time_24h": use_24h})

    def repeat_key(self) -> str:
        """지금 고른 반복 방식. 반복을 껐으면 'none'."""
        return self.repeat.currentData() if self.repeat_check.isChecked() else "none"

    def chosen(self) -> Dict[str, Any]:
        """지금 화면의 값으로 만든 알림. 값이 모자라거나 틀리면 ValueError."""
        key = self.repeat_key()
        if key == "cron":
            return reminders.make(datetime.now(), "cron", self.cron.text())
        moment = self.time.time()
        if moment is None:
            raise ValueError("시간을 바르게 적어 주세요. (예: 오후 3:30 또는 15:30)")
        if key == "none":
            day = self.date.date()
            return reminders.make(datetime(day.year(), day.month(), day.day(), moment[0], moment[1]), "none")
        return reminders.make_repeating(
            key, moment[0], moment[1], datetime.now(),
            weekdays=[n for n, btn in enumerate(self.weekday_buttons) if btn.isChecked()],
            days=[day for day, btn in self.day_buttons.items() if btn.isChecked()])

    def _refresh(self, *args: Any) -> None:
        key = self.repeat_key()
        self.repeat.setEnabled(self.repeat_check.isChecked())
        self.once_box.setVisible(key == "none")
        self.weekday_box.setVisible(key == "weekly")
        self.day_box.setVisible(key == "monthly")
        self.time_box.setVisible(key != "cron")
        self.cron_box.setVisible(key == "cron")
        self.layout_changed.emit()

        try:
            reminder = self.chosen()
        except ValueError as e:
            self.preview.setText(f"⚠ {e}")
            self.ok_button.setEnabled(False)
            return
        self.ok_button.setEnabled(True)
        if key == "none":
            late = reminders.due_at(reminder) <= datetime.now()
            self.preview.setText("⚠ 이미 지난 시각입니다. 저장하면 바로 울립니다." if late else "알림: " + reminders.describe(reminder))
            return
        times = [reminders.describe({"at": moment.isoformat(), "repeat": "none"}) for moment in reminders.upcoming(reminder, 3)]
        self.preview.setText(f"<b>{reminders.repeat_text(reminder)}</b><br>다음 알림: " + "<br>→ ".join(times))

    def _accept(self) -> None:
        try:
            self.result_reminder = self.chosen()
        except ValueError:
            return
        self.submitted.emit((True, self.result_reminder))

    def _clear(self) -> None:
        self.cleared = True
        self.result_reminder = None
        self.submitted.emit((True, None))

    def keyPressEvent(self, event: Any) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.cancelled.emit()
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._accept()
        else:
            super().keyPressEvent(event)


class ReminderDialog(ThemedDialog):
    """알림 설정 화면을 담은 대화상자. (탐색기에서 부르거나, 메모가 접혀 있거나 작아서 메모 안에 띄울 수 없을 때)

    form 의 입력 칸들은 이 대화상자에서도 같은 이름으로 쓸 수 있습니다. (dialog.repeat_check 등)
    """

    def __init__(self, parent: Any, current: Optional[Dict[str, Any]] = None, title: str = "") -> None:
        super().__init__(parent, "알림 설정", fit_content=True)       # 보이는 입력에 맞춰 창 높이가 따라감
        self.form = ReminderForm(current, title)
        self.form.setMinimumWidth(390)
        self.body.addWidget(self.form)
        self.form.submitted.connect(lambda result: self.accept())
        self.form.cancelled.connect(self.reject)

    def __getattr__(self, name: str) -> Any:
        if name == "form":
            raise AttributeError(name)
        return getattr(self.form, name)


def ask_reminder(parent: Any, current: Optional[Dict[str, Any]], title: str = "") -> tuple:
    """알림을 정합니다. → (바꿨는지, 새 알림 또는 None)

    메모 창에서 부르면 그 메모의 오른쪽에 붙는 패널로(메모가 작거나 접혀 있어도 전체가 보임),
    탐색기에서 부르면 탐색기 안의 카드로 묻습니다. 그럴 수 없을 때만 대화상자를 띄웁니다.
    """
    window = parent.window() if parent is not None else None
    if hasattr(window, "side_panel") and window.isVisible() and not window.side_panel().is_busy():
        result = window.side_panel().run(ReminderForm(current), "⏰ 알림 설정", min_width=350)
        return result if result else (False, None)
    overlay = getattr(window, "inline_overlay", None)
    if overlay is not None and overlay.can_host(460, 420):
        form = ReminderForm(current, title, heading="⏰ 알림 설정")
        form.setMinimumWidth(380)
        result = overlay.run(form, card=True)
        return result if result else (False, None)
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
