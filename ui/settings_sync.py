"""환경설정의 '동기화' 탭: 동기화 주소·접근 암호·주기, 연결 확인.

(SettingsWindow 에 섞어 쓰는 부분)
"""
from PyQt6.QtCore import QMetaObject, pyqtSlot
from typing import Any
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLineEdit, QLabel, QComboBox, QCheckBox, QFrame, QGroupBox, QScrollArea
from PyQt6.QtCore import Qt
import threading


class SyncTabMixin:
    """환경설정의 동기화 탭."""

    def _build_sync_tab(self) -> None:
        """'구글 동기화' 탭: 메모 폴더, 동기화 주소와 토큰, 동기화 주기, 준비 방법 안내."""
        tab_sync = QWidget()
        l_sync = QVBoxLayout(tab_sync)
        l_sync.setContentsMargins(15, 15, 15, 15)
        l_sync.setSpacing(15)

        g1 = self._build_sync_group()
        l_sync.addWidget(g1)
        g_help = self._build_sync_help_group()
        l_sync.addWidget(g_help)

        l_sync.addStretch()

        scroll_sync = QScrollArea()
        scroll_sync.setWidget(tab_sync)
        scroll_sync.setWidgetResizable(True)
        scroll_sync.setFrameShape(QFrame.Shape.NoFrame)
        scroll_sync.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_sync.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.tabs.addTab(scroll_sync, "구글 동기화")

    def _build_sync_group(self) -> Any:
        """메모 폴더, 동기화 주소와 토큰, 동기화 주기."""
        g1 = QGroupBox("구글 드라이브 백업 및 동기화 설정")
        g1_l = QVBoxLayout(g1)
        g1_l.setContentsMargins(18, 24, 18, 18)
        g1_l.setSpacing(12)

        self.sync_cb = QCheckBox("구글 드라이브 동기화 활성화")
        self.sync_cb.setProperty("role", "value")
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

        g1_l.addWidget(QLabel("동기화 접근 암호 (선택):"))
        self.token_input = QLineEdit()
        self.token_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.token_input.setPlaceholderText("스크립트 속성 ACCESS_TOKEN 에 넣은 값")
        self.token_input.setFixedHeight(40)
        g1_l.addWidget(self.token_input)
        token_hint = QLabel("스크립트에 ACCESS_TOKEN 을 설정하면 이 값을 아는 기기만 메모를 읽고 쓸 수 있습니다. "
                            "모바일 화면에서도 같은 값을 입력합니다.")
        token_hint.setProperty("role", "hint")
        token_hint.setWordWrap(True)
        g1_l.addWidget(token_hint)

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

        g1_l.addWidget(QLabel("변경 후 동기화까지 기다리는 시간:"))
        self.sync_interval_combo = QComboBox()
        self.sync_interval_combo.addItems(["1분 뒤", "10분 뒤", "30분 뒤", "1시간 뒤"])
        self.sync_interval_combo.setFixedHeight(40)
        g1_l.addWidget(self.sync_interval_combo)
        sync_hint = QLabel("정해진 간격마다 무조건 동기화하지 않습니다. 메모를 고치면 이 시간만큼 기다렸다가 바뀐 메모만 올립니다. "
                           "고친 것이 없을 때는 다른 기기의 변경이 있는지 15분마다 파일 목록만 확인합니다. "
                           "탐색기의 동기화 버튼을 누르면 바로 동기화합니다.")
        sync_hint.setProperty("role", "hint")
        sync_hint.setWordWrap(True)
        g1_l.addWidget(sync_hint)
        return g1

    def test_gas_url(self) -> None:
        url = self.url_input.text().strip()
        if not url or not url.startswith("http"):
            self.show_toast("http(s):// 로 시작하는 주소를 입력하세요", warn=True)
            return

        self.sm.drive_api.set_web_app_url(url)
        self.sm.drive_api.set_access_token(self.token_input.text())
        self.show_toast("연결 테스트 중…")

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
        self.show_toast("연결 성공 (동기화 켬)")

    @pyqtSlot()
    def _on_ping_failed(self) -> None:
        self.show_toast("연결 실패 (주소·접근 암호 확인)", warn=True)
