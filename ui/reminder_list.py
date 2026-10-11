"""예약된 알림 목록.

알림이 걸린 메모를 빨리 울리는 것부터 늘어놓고, 그 자리에서 미루기·건너뛰기·해제를 합니다.
메모 열기와 알림 바꾸기는 이 화면을 닫고 부른 쪽(탐색기)이 이어서 처리합니다. → ("open" 또는 "edit", 메모 id)
탐색기 안의 가림막에도, 대화상자에도 똑같이 들어갑니다. (input_panels 의 화면들과 같은 신호를 씀)
"""
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

from PyQt6.QtCore import QEvent, Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import QDialog, QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget

from core import reminders
from ui import live_settings, modern_style
from ui.reminder_ui import ReminderPopup, minutes_label
from ui.themed_dialog import ThemedDialog


def time_left(due: datetime, now: datetime) -> str:
    """울릴 때까지 남은 시간. 예: '25분 뒤', '3시간 10분 뒤', '2일 4시간 뒤'. 이미 지났으면 '지남'."""
    seconds = (due - now).total_seconds()
    if seconds <= 0:
        return "지남"
    minutes = int(seconds // 60)
    if minutes < 1:
        return "곧"
    if minutes >= 1440:
        minutes -= minutes % 60             # 하루가 넘으면 분은 적지 않음
    return minutes_label(minutes)


class ReminderListPanel(QWidget):
    """예약된 알림을 가까운 것부터 보여 주는 화면."""

    submitted = pyqtSignal(object)       # ("open" | "edit", 메모 id)
    cancelled = pyqtSignal()
    layout_changed = pyqtSignal()        # 줄 수가 바뀌어 화면 크기가 달라졌을 때

    WIDTH = 470                          # 가장 좁을 때의 너비. 글꼴에 따라 단추 줄이 더 넓으면 그만큼 넓어집니다.
    MAX_ROWS_HEIGHT = 360                # 줄이 이보다 많으면 줄들만 안에서 스크롤 (화면 전체가 끝없이 길어지지 않게)
    SNOOZES = ReminderPopup.SNOOZES

    def __init__(self, ui_manager: Any) -> None:
        super().__init__()
        self.ui_manager = ui_manager
        self.rows: Dict[str, QFrame] = {}                                   # 메모 id → 그 알림의 줄
        self._undo: Optional[Tuple[str, Optional[Dict[str, Any]]]] = None   # 방금 바꾼 알림의 (메모 id, 바꾸기 전 값)
        self.setMinimumWidth(self.WIDTH)
        pal, _ = modern_style.app_palette(live_settings.current())
        self.setStyleSheet(f"""
            QFrame#ReminderRow {{ border: none; border-top: 1px solid {pal['border']}; }}
            QScrollArea#ReminderRows, QWidget#ReminderRowsBody {{ background: transparent; border: none; }}
            QPushButton[role="mini"] {{ padding: 4px 8px; font-weight: 500; }}
            QLabel[role="when"] {{ font-weight: 700; }}
            QLabel[role="late"] {{ color: {modern_style.DANGER}; font-size: 9pt; font-weight: 600; }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        head = QHBoxLayout()
        title = QLabel("⏰ 예약된 알림")
        title.setProperty("role", "title")
        head.addWidget(title)
        self.count_label = QLabel("")
        self.count_label.setProperty("role", "hint")
        head.addWidget(self.count_label)
        head.addStretch(1)
        layout.addLayout(head)

        self.rows_body = QWidget()
        self.rows_body.setObjectName("ReminderRowsBody")
        self.rows_box = QVBoxLayout(self.rows_body)
        self.rows_box.setContentsMargins(0, 0, 0, 0)
        self.rows_box.setSpacing(0)
        self.rows_scroll = QScrollArea()
        self.rows_scroll.setObjectName("ReminderRows")
        self.rows_scroll.setWidgetResizable(True)
        self.rows_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.rows_scroll.setWidget(self.rows_body)
        self.rows_body.installEventFilter(self)          # 줄의 크기가 정해지면 목록 칸을 거기에 맞춤 (eventFilter)
        layout.addWidget(self.rows_scroll)
        self.empty_label = QLabel("예약된 알림이 없습니다. 메모를 우클릭해 '알림 설정'으로 걸 수 있습니다.")
        self.empty_label.setProperty("role", "hint")
        self.empty_label.setWordWrap(True)
        layout.addWidget(self.empty_label)

        foot = QHBoxLayout()
        foot.setSpacing(8)
        self.status_label = QLabel("")
        self.status_label.setProperty("role", "hint")
        foot.addWidget(self.status_label, 1)
        self.undo_button = QPushButton("되돌리기")
        self.undo_button.setProperty("role", "mini")
        self.undo_button.clicked.connect(self.undo)
        self.undo_button.hide()
        foot.addWidget(self.undo_button)
        self.close_button = QPushButton("닫기")
        self.close_button.clicked.connect(self.cancelled.emit)
        foot.addWidget(self.close_button)
        layout.addLayout(foot)

        # 열어 둔 사이에 알림이 울리거나 다른 곳에서 바뀌어도 목록이 따라갑니다.
        ui_manager.sync_manager.reminders_changed.connect(self.reload, Qt.ConnectionType.QueuedConnection)
        # 남은 시간('25분 뒤')은 열어 둔 동안에도 흘러가므로 가끔 다시 그립니다.
        self._clock = QTimer(self)
        self._clock.timeout.connect(self.reload)
        self._clock.start(30 * 1000)
        self.reload()

    # ── 목록 ─────────────────────────────────────────────────────────────────
    def reload(self) -> None:
        self._scroll_at = self.rows_scroll.verticalScrollBar().value()      # 다시 그려도 보던 자리를 지킴
        for row in self.rows.values():
            self.rows_box.removeWidget(row)
            row.hide()
            row.deleteLater()
        self.rows = {}
        now = datetime.now()
        entries = self.ui_manager.reminder_entries()
        for entry in entries:
            row = self._make_row(entry, now)
            self.rows_box.addWidget(row)
            row.show()                          # 이미 떠 있는 화면에 새로 넣은 줄은 바로 보이게
            self.rows[entry["id"]] = row
        self.count_label.setText(f"{len(entries)}개 · 빨리 울리는 순" if entries else "")
        self.empty_label.setVisible(not entries)
        self.rows_scroll.setVisible(bool(entries))
        self._fit_rows()
        QTimer.singleShot(0, self._restore_scroll)

    def _restore_scroll(self) -> None:
        self.rows_scroll.verticalScrollBar().setValue(self._scroll_at)

    def _fit_rows(self) -> None:
        """목록 칸을 줄들의 크기에 맞춥니다. 줄이 많으면 MAX_ROWS_HEIGHT 까지만 키우고 그 안에서 스크롤합니다."""
        hint = self.rows_body.sizeHint()
        tall = hint.height() > self.MAX_ROWS_HEIGHT
        size = (hint.width() + (self.rows_scroll.verticalScrollBar().sizeHint().width() if tall else 0),
                min(hint.height(), self.MAX_ROWS_HEIGHT))
        if size != (self.rows_scroll.minimumWidth(), self.rows_scroll.height()):
            self.rows_scroll.setVerticalScrollBarPolicy(
                Qt.ScrollBarPolicy.ScrollBarAsNeeded if tall else Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self.rows_scroll.setMinimumWidth(size[0])
            self.rows_scroll.setFixedHeight(size[1])
            self.layout_changed.emit()

    def eventFilter(self, obj: Any, event: Any) -> bool:
        if obj is self.rows_body and event.type() == QEvent.Type.LayoutRequest:
            self._fit_rows()
        return False

    def _make_row(self, entry: Dict[str, Any], now: datetime) -> QFrame:
        memo_id, reminder = entry["id"], entry["reminder"]
        row = QFrame()
        row.setObjectName("ReminderRow")
        box = QVBoxLayout(row)
        box.setContentsMargins(0, 8, 0, 8)
        box.setSpacing(3)

        top = QHBoxLayout()
        top.setSpacing(8)
        when = QLabel(reminders.describe(reminder))
        when.setProperty("role", "when")
        top.addWidget(when)
        left = time_left(entry["due"], now)
        left_label = QLabel(left)
        left_label.setProperty("role", "late" if left == "지남" else "hint")
        top.addWidget(left_label)
        top.addStretch(1)
        box.addLayout(top)

        text = ("🔒 " if entry["locked"] else "") + " ".join(entry["title"].split())
        title = QLabel(text)
        title.setText(title.fontMetrics().elidedText(text, Qt.TextElideMode.ElideRight, self.WIDTH - 12))
        title.setToolTip(text)
        box.addWidget(title)

        buttons = QHBoxLayout()
        buttons.setSpacing(4)
        row.buttons = {}

        def add(key: Any, label: str, action: Any, tip: str = "") -> None:
            btn = QPushButton(label)
            btn.setProperty("role", "mini")
            btn.setAutoDefault(False)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip(tip)
            btn.clicked.connect(lambda checked=False: action())
            buttons.addWidget(btn)
            row.buttons[key] = btn

        add("open", "열기", lambda: self.submitted.emit(("open", memo_id)), "이 메모 열기")
        hint = QLabel("미루기")
        hint.setProperty("role", "hint")
        buttons.addSpacing(6)
        buttons.addWidget(hint)
        for label, minutes in self.SNOOZES:
            add(minutes, "+" + ("1일" if minutes == 1440 else label), lambda m=minutes: self.postpone(memo_id, m),
                "예약된 시각에서 그만큼 늦춥니다")
        if reminder.get("repeat") != "none":
            add("skip", "건너뛰기", lambda: self.skip(memo_id), "이번 차례만 건너뛰고 다음 차례로 넘깁니다")
        buttons.addStretch(1)
        add("edit", "바꾸기", lambda: self.submitted.emit(("edit", memo_id)), "알림 시각·반복 바꾸기")
        add("clear", "해제", lambda: self.clear(memo_id), "이 메모의 알림을 없앱니다")
        box.addLayout(buttons)
        return row

    # ── 그 자리에서 하는 일 ──────────────────────────────────────────────────
    def postpone(self, memo_id: str, minutes: int) -> None:
        self._apply(memo_id, lambda: self.ui_manager.postpone_reminder(memo_id, minutes), "미뤘습니다")

    def skip(self, memo_id: str) -> None:
        self._apply(memo_id, lambda: self.ui_manager.skip_reminder(memo_id), "이번 차례를 건너뛰었습니다")

    def clear(self, memo_id: str) -> None:
        self._apply(memo_id, lambda: self.ui_manager.change_reminder(memo_id, None), "알림을 해제했습니다")

    def undo(self) -> None:
        if self._undo is not None:
            memo_id, before = self._undo
            self._apply(memo_id, lambda: self.ui_manager.change_reminder(memo_id, before), "되돌렸습니다", can_undo=False)

    def _apply(self, memo_id: str, action: Any, done_text: str, can_undo: bool = True) -> None:
        before = self.ui_manager.sync_manager.reminders.get(memo_id)
        title = next((e["title"] for e in self.ui_manager.reminder_entries() if e["id"] == memo_id), "")
        saved = action()
        after = self.ui_manager.sync_manager.reminders.get(memo_id)
        self._undo = (memo_id, dict(before) if before else None) if can_undo and after != before else None
        self.undo_button.setVisible(self._undo is not None)
        if saved:
            detail = f" → {reminders.describe(after)}" if after else ""
            self.status_label.setText(f"✓ {done_text}{detail}" + (f" · {title}" if title and not after else ""))
        else:
            self.status_label.setText("⚠ 저장하지 못했습니다 · 메모 폴더를 확인하세요")
        self.reload()

    def focus_first(self) -> None:
        self.close_button.setFocus()

    def keyPressEvent(self, event: Any) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.cancelled.emit()
            return
        super().keyPressEvent(event)


def ask_reminder_list(parent: Any, ui_manager: Any) -> Optional[Tuple[str, str]]:
    """예약된 알림 목록을 띄웁니다. 메모 열기·알림 바꾸기를 골랐으면 ("open" | "edit", 메모 id), 그냥 닫았으면 None.

    탐색기에서 부르면 탐색기 안의 카드로, 그럴 자리가 없으면 대화상자로 띄웁니다.
    """
    panel = ReminderListPanel(ui_manager)
    window = parent.window() if parent is not None else None
    overlay = getattr(window, "inline_overlay", None)
    if overlay is not None and overlay.can_host(panel.sizeHint().width() + 80, 320):
        return overlay.run(panel, card=True)
    dialog = ThemedDialog(parent, "예약된 알림", fit_content=True)
    dialog.body.addWidget(panel)
    picked: Dict[str, Any] = {}
    panel.submitted.connect(lambda action: (picked.update(action=action), dialog.accept()))
    panel.cancelled.connect(dialog.reject)
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return None
    return picked.get("action")
