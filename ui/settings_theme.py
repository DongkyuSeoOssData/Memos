"""환경설정의 '테마 · 글꼴' 탭: 글꼴과 서식, 투명도, 메모 크기, 접은 메모 높이, 디자인 스타일, 탐색기 크기.

(SettingsWindow 에 섞어 쓰는 부분)
"""
from ui.themes import LIGHT_THEMES, DARK_THEMES
from typing import Any
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QComboBox, QCheckBox, QFrame, QFontComboBox, QGroupBox, QScrollArea, QSlider, QSpinBox
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor


class ThemeTabMixin:
    """환경설정의 테마 탭."""

    def _build_theme_tab(self) -> None:
        """'테마 & 서식' 탭: 기본 글꼴·색·코드 테마, 투명도, 메모와 탐색기의 기본 크기, 화면 스타일."""
        tab_font = QWidget()
        l_font = QVBoxLayout(tab_font)
        l_font.setContentsMargins(12, 12, 12, 12)
        l_font.setSpacing(12)

        g3 = self._build_format_group()

        # 기본 투명도 설정 그룹
        g_opacity = self._build_opacity_group()

        # 메모 기본 실행 크기 설정 그룹 — 2열 그리드
        g_size = self._build_memo_size_group()

        # 접힌 메모 크기 설정 그룹
        g_rolled = self._build_rolled_height_group()

        # 디자인 스타일 (Modern ↔ Neo 전환)
        g_style = self._build_style_group()
        l_font.addWidget(g_style)

        l_font.addWidget(g3)
        l_font.addWidget(g_opacity)
        l_font.addWidget(g_size)
        l_font.addWidget(g_rolled)

        # 메모 탐색기 크기 설정 그룹
        g_explorer = self._build_explorer_size_group()
        l_font.addWidget(g_explorer)

        l_font.addStretch()

        scroll_font = QScrollArea()
        scroll_font.setWidget(tab_font)
        scroll_font.setWidgetResizable(True)
        scroll_font.setFrameShape(QFrame.Shape.NoFrame)
        scroll_font.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_font.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.tabs.addTab(scroll_font, "테마 & 서식")

    def _build_format_group(self) -> Any:
        """기본 글꼴·색·코드 테마와 앱 색 테마."""
        g3 = QGroupBox("기본 서식 / 폰트 / 코드 테마")
        g3_l = QVBoxLayout(g3)
        g3_l.setContentsMargins(14, 22, 14, 14)
        g3_l.setSpacing(8)

        g3_l.addWidget(QLabel("기본 메모 폰트:"))
        self.default_font_box = QFontComboBox()
        self.default_font_box.setFixedHeight(36)
        g3_l.addWidget(self.default_font_box)

        g3_l.addWidget(QLabel("코드 메모 폰트:"))
        self.default_code_font_box = QFontComboBox()
        self.default_code_font_box.setFixedHeight(36)
        g3_l.addWidget(self.default_code_font_box)

        g3_l.addWidget(QLabel("기본 폰트 크기 (pt):"))
        self.default_font_size_spin = QSpinBox()
        self.default_font_size_spin.setRange(6, 72)
        self.default_font_size_spin.setValue(11)
        self.default_font_size_spin.setSuffix(" pt")
        self.default_font_size_spin.setFixedHeight(36)
        g3_l.addWidget(self.default_font_size_spin)

        g3_l.addWidget(QLabel("코드 기본 언어:"))
        self.default_code_lang_box = QComboBox()
        self.default_code_lang_box.addItems(["JSON", "C#", "VB.NET", "Power Automate", "PowerShell", "Batch (CMD)", "SQL", "Markdown", "Python", "JavaScript", "HTML", "CSS", "C++", "Java"])
        self.default_code_lang_box.setFixedHeight(36)
        g3_l.addWidget(self.default_code_lang_box)

        g3_l.addWidget(QLabel("코드 기본 테마:"))
        self.default_code_theme_box = QComboBox()
        self.default_code_theme_box.addItems(["Atom One Dark", "라이트 모드"])
        self.default_code_theme_box.setFixedHeight(36)
        g3_l.addWidget(self.default_code_theme_box)

        g3_l.addWidget(QLabel("다크 모드 스타일:"))
        self.dark_theme_box = QComboBox()
        for k, v in DARK_THEMES.items():
            self.dark_theme_box.addItem(v["name"], k)
        self.dark_theme_box.setFixedHeight(36)
        g3_l.addWidget(self.dark_theme_box)

        g3_l.addWidget(QLabel("라이트 모드 스타일:"))
        self.light_theme_box = QComboBox()
        for k, v in LIGHT_THEMES.items():
            self.light_theme_box.addItem(v["name"], k)
        self.light_theme_box.setFixedHeight(36)
        g3_l.addWidget(self.light_theme_box)

        def _on_theme_style_changed():
            self.sm.settings["dark_theme_mode"] = self.dark_theme_box.currentData()
            self.sm.settings["light_theme_mode"] = self.light_theme_box.currentData()
            self.apply_theme_style()
            if hasattr(self.sm, 'ui_manager') and self.sm.ui_manager:
                if self.sm.ui_manager.explorer_window and self.sm.ui_manager.explorer_window.isVisible():
                    self.sm.ui_manager.explorer_window.apply_theme_style()
                for w in self.sm.ui_manager.memo_windows.values():
                    if w.isVisible():
                        w.apply_look()
        self.dark_theme_box.currentIndexChanged.connect(lambda _: _on_theme_style_changed())
        self.light_theme_box.currentIndexChanged.connect(lambda _: _on_theme_style_changed())

        g3_l.addWidget(QLabel("일반 메모 기본 색상:"))
        self.default_color_combo = QComboBox()
        self.default_color_combo.setFixedHeight(36)
        for idx, (name, color_hex) in enumerate(self.colors.items()):
            self.default_color_combo.addItem(name)
            if color_hex != "random":
                self.default_color_combo.setItemData(idx, QColor(color_hex), Qt.ItemDataRole.BackgroundRole)
        g3_l.addWidget(self.default_color_combo)
        return g3

    def _build_opacity_group(self) -> Any:
        """새 메모의 기본 투명도."""
        g_opacity = QGroupBox("새 메모 기본 투명도 (불투명 100% 기본)")
        g_opacity_l = QVBoxLayout(g_opacity)
        g_opacity_l.setContentsMargins(14, 22, 14, 14)
        g_opacity_l.setSpacing(8)

        opa_row = QHBoxLayout()
        self.opacity_value_label = QLabel("100%  (완전 불투명 — 권장)")
        self.opacity_value_label.setProperty("role", "value")
        opa_row.addWidget(self.opacity_value_label)
        opa_row.addStretch()
        g_opacity_l.addLayout(opa_row)

        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(20, 100)
        self.opacity_slider.setValue(100)
        self.opacity_slider.setFixedHeight(30)
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

        opa_hint = QLabel("※ 개별 메모 우클릭 메뉴에서도 개별 조절 가능합니다.")
        opa_hint.setProperty("role", "hint")
        opa_hint.setWordWrap(True)
        g_opacity_l.addWidget(opa_hint)
        return g_opacity

    def _build_memo_size_group(self) -> Any:
        """일반 메모와 코드 메모의 기본 크기."""
        g_size = QGroupBox("메모 기본 실행 크기 (일반 & 코드)")
        g_size_l = QGridLayout(g_size)
        g_size_l.setContentsMargins(14, 22, 14, 14)
        g_size_l.setSpacing(8)

        self.spin_memo_width = QSpinBox()
        self.spin_memo_width.setRange(200, 1920)
        self.spin_memo_width.setSuffix(" px")
        self.spin_memo_width.setFixedHeight(34)

        self.spin_memo_height = QSpinBox()
        self.spin_memo_height.setRange(150, 1080)
        self.spin_memo_height.setSuffix(" px")
        self.spin_memo_height.setFixedHeight(34)

        self.spin_code_memo_width = QSpinBox()
        self.spin_code_memo_width.setRange(200, 1920)
        self.spin_code_memo_width.setSuffix(" px")
        self.spin_code_memo_width.setFixedHeight(34)

        self.spin_code_memo_height = QSpinBox()
        self.spin_code_memo_height.setRange(150, 1080)
        self.spin_code_memo_height.setSuffix(" px")
        self.spin_code_memo_height.setFixedHeight(34)

        # 일반 메모: 레이블-스핀박스 2열 배치
        g_size_l.addWidget(QLabel("일반 가로:"), 0, 0)
        g_size_l.addWidget(self.spin_memo_width, 0, 1)
        g_size_l.addWidget(QLabel("일반 세로:"), 1, 0)
        g_size_l.addWidget(self.spin_memo_height, 1, 1)
        g_size_l.addWidget(QLabel("코드 가로:"), 2, 0)
        g_size_l.addWidget(self.spin_code_memo_width, 2, 1)
        g_size_l.addWidget(QLabel("코드 세로:"), 3, 0)
        g_size_l.addWidget(self.spin_code_memo_height, 3, 1)
        g_size_l.setColumnStretch(1, 1)
        return g_size

    def _build_rolled_height_group(self) -> Any:
        """접은 메모의 높이."""
        g_rolled = QGroupBox("메모 접힌(—) 상태 높이 설정")
        g_rolled_l = QVBoxLayout(g_rolled)
        g_rolled_l.setContentsMargins(14, 22, 14, 14)
        g_rolled_l.setSpacing(8)

        rolled_row = QHBoxLayout()
        rolled_row.addWidget(QLabel("접힌 높이:"))
        self.spin_rolled_height = QSpinBox()
        self.spin_rolled_height.setRange(36, 120)   # 최소 36px(아이콘+제목 보이는 최소치), 최대 120px
        self.spin_rolled_height.setValue(53)
        self.spin_rolled_height.setSuffix(" px")
        self.spin_rolled_height.setFixedHeight(34)
        self.spin_rolled_height.setToolTip("메모를 접었을 때의 창 높이입니다. (36~120px)")
        rolled_row.addWidget(self.spin_rolled_height)
        rolled_row.addStretch()
        g_rolled_l.addLayout(rolled_row)

        rolled_hint = QLabel("✖ 제목줄·아이콘 크기가 높이에 비례하여 자동 조정됩니다. (\uc5ec백 최소: 36px 권장)")
        rolled_hint.setProperty("role", "hint")
        rolled_hint.setWordWrap(True)
        g_rolled_l.addWidget(rolled_hint)
        return g_rolled

    def _build_style_group(self) -> Any:
        """디자인 스타일 (Modern / Neo)."""
        g_style = QGroupBox("디자인 스타일")
        g_style_l = QVBoxLayout(g_style)
        g_style_l.setContentsMargins(14, 22, 14, 14)
        g_style_l.setSpacing(8)
        self.ui_style_box = QComboBox()
        self.ui_style_box.addItem("Modern (기본)", "modern")
        self.ui_style_box.addItem("Neo (미니멀 · 선 중심)", "neo")
        self.ui_style_box.setFixedHeight(36)

        def _on_ui_style_picked() -> None:
            # Neo 디자인을 고르면 어울리는 Mono 색 테마를 함께 골라 줍니다. (저장 전에 다시 바꿀 수 있음)
            if self.ui_style_box.currentData() != "neo" or getattr(self, "_loading_settings", False):
                return
            for box in (self.dark_theme_box, self.light_theme_box):
                idx = box.findData("mono")
                if idx >= 0:
                    box.setCurrentIndex(idx)
        self.ui_style_box.currentIndexChanged.connect(lambda _: _on_ui_style_picked())

        g_style_l.addWidget(self.ui_style_box)
        style_hint = QLabel("탐색기·환경설정·메모 창의 모양을 바꿉니다. 저장하면 바로 적용됩니다. "
                            "Neo는 아래 색 테마의 'Mono Paper / Mono Graphite'와 가장 잘 어울립니다.")
        style_hint.setProperty("role", "hint")
        style_hint.setWordWrap(True)
        g_style_l.addWidget(style_hint)
        return g_style

    def _build_explorer_size_group(self) -> Any:
        """메모 탐색기의 크기."""
        g_explorer = QGroupBox("메모 탐색기 크기")
        g_explorer_l = QGridLayout(g_explorer)
        g_explorer_l.setContentsMargins(14, 22, 14, 14)
        g_explorer_l.setSpacing(8)

        self.spin_explorer_width = QSpinBox()
        self.spin_explorer_width.setRange(580, 3840)
        self.spin_explorer_width.setSuffix(" px")
        self.spin_explorer_width.setFixedHeight(34)

        self.spin_explorer_height = QSpinBox()
        self.spin_explorer_height.setRange(440, 2160)
        self.spin_explorer_height.setSuffix(" px")
        self.spin_explorer_height.setFixedHeight(34)

        self.cb_explorer_fixed = QCheckBox("탐색기 크기 고정 (화면 이동·모니터 변경 시에도 크기 유지)")

        g_explorer_l.addWidget(QLabel("탐색기 가로:"), 0, 0)
        g_explorer_l.addWidget(self.spin_explorer_width, 0, 1)
        g_explorer_l.addWidget(QLabel("탐색기 세로:"), 1, 0)
        g_explorer_l.addWidget(self.spin_explorer_height, 1, 1)
        g_explorer_l.addWidget(self.cb_explorer_fixed, 2, 0, 1, 2)
        g_explorer_l.setColumnStretch(1, 1)
        return g_explorer

    def _explorer_window(self) -> Any:
        return getattr(getattr(self.sm, 'ui_manager', None), 'explorer_window', None)

    def _current_explorer_size(self) -> tuple:
        explorer = self._explorer_window()
        if explorer and not explorer.isMaximized():
            return explorer.content_width(), explorer.height()
        geom = self.sm.settings.get("explorer_geom")
        if geom and len(geom) == 4:
            return int(geom[2]), int(geom[3])
        return 620, 480

    def _explorer_geom_from_inputs(self) -> list:
        """입력한 가로·세로에 현재 탐색기 위치를 합쳐 explorer_geom 형식으로 돌려줍니다."""
        explorer = self._explorer_window()
        geom = self.sm.settings.get("explorer_geom")
        if explorer:
            x, y = explorer.content_x(), explorer.y()     # 왼쪽에 붙은 사이드바·패널은 탐색기 위치에 넣지 않음
        elif geom and len(geom) == 4:
            x, y = int(geom[0]), int(geom[1])
        else:
            x, y = 100, 100
        return [x, y, self.spin_explorer_width.value(), self.spin_explorer_height.value()]
