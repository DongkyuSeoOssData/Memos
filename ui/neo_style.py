"""Neo 디자인: 선과 여백 위주의 미니멀 스타일.

- 면을 칠하는 대신 가는 선(hairline)으로 구획하고, 강조는 '잉크색(본문 글자색)' 한 가지로 처리합니다.
- 필터·탭은 밑줄형, 주요 버튼만 잉크색으로 채우고 나머지는 외곽선 버튼입니다.
- 모서리는 모두 각지게 유지합니다.

색은 환경설정에서 고른 색 테마를 그대로 따르며, 이 디자인에 맞춘 'Mono' 테마(라이트/다크)가 함께 제공됩니다.
진입점은 ui/modern_style.py 의 apply_* 함수들이며, 디자인 스타일이 "neo"일 때 같은 이름의 이 파일 함수로 넘어옵니다.
"""
from typing import Any

from ui.modern_style import (
    DANGER, MEMO_ACTION_BUTTONS, MEMO_BOX_CONTROLS, MEMO_TOGGLE_BUTTONS, MONO_FONT, UI_FONT,
    _arrow_icon, _check_icon, _flat_button, _muted, _rgba, _settings_of, _tint,
    explorer_rows, memo_tone, scrollbars, set_save_icon, style_window_buttons,
)
from ui.themes import app_palette


def _pt(widget: Any) -> int:
    return max(9, round(int(getattr(widget, "ui_font_pt", 10)) * 0.85))


def _outline_btn(text: str, hair: str, is_dark: bool, pt: int, pad: str = "6px 12px") -> str:
    return f"""
        QPushButton {{
            padding: {pad}; background: transparent; border: 1px solid {hair}; border-radius: 0px;
            color: {text}; font-weight: 500; font-size: {pt}pt; font-family: {UI_FONT};
        }}
        QPushButton:hover {{ border-color: {text}; }}
        QPushButton:pressed {{ background: {_tint(is_dark, 0.08)}; }}
    """


def _ink_btn(ink: str, paper: str, pt: int, pad: str = "6px 16px") -> str:
    return f"""
        QPushButton {{
            padding: {pad}; background: {ink}; border: 1px solid {ink}; border-radius: 0px;
            color: {paper}; font-weight: 600; font-size: {pt}pt; font-family: {UI_FONT};
        }}
        QPushButton:hover {{ background: {_rgba(ink, 0.82)}; border-color: {_rgba(ink, 0.82)}; }}
    """


# ═══ 메모 탐색기 ══════════════════════════════════════════════════════════════
def apply_explorer(ex: Any) -> None:
    pal, is_dark = app_palette(_settings_of(ex))
    pt = _pt(ex)
    small = max(8, pt - 1)
    ink, paper, surface, hair, accent = pal['text'], pal['bg'], pal['card'], pal['border'], pal['accent']
    muted = _muted(is_dark)

    ex.bg.setStyleSheet(f"""
        QFrame#ExplorerBg {{ background-color: {paper}; border: 1px solid {hair}; border-radius: 0px; }}
        QLabel {{ color: {ink}; font-family: {UI_FONT}; font-size: {pt}pt; }}
        QPushButton {{ font-family: {UI_FONT}; color: {ink}; font-size: {pt}pt; }}
        QLineEdit, QComboBox {{
            padding: 6px 10px; border: none; border-bottom: 1px solid {hair}; border-radius: 0px;
            color: {ink}; background-color: transparent;
            selection-background-color: {accent}; font-family: {UI_FONT}; font-size: {pt}pt;
        }}
        QLineEdit:hover, QComboBox:hover {{ border-bottom-color: {muted}; }}
        QLineEdit:focus, QComboBox:focus {{ border-bottom: 1px solid {ink}; }}
        QComboBox::drop-down {{ border: none; width: 20px; }}
        QComboBox::down-arrow {{ image: url({_arrow_icon("down", is_dark)}); width: 11px; height: 11px; }}
        QComboBox QAbstractItemView {{
            background-color: {surface}; color: {ink}; border: 1px solid {hair};
            selection-background-color: {ink}; selection-color: {paper}; outline: none; padding: 2px;
        }}
    """)

    ex.title_label.setStyleSheet(
        f"font-size: {pt + 5}pt; border: none; font-weight: 700; letter-spacing: -0.5px; "
        f"color: {ink}; font-family: {UI_FONT};"
    )

    ex.table.setStyleSheet(f"""
        QTableWidget {{
            border: none; border-top: 1px solid {ink}; border-bottom: 1px solid {hair}; border-radius: 0px;
            background-color: transparent; color: {ink}; outline: none; gridline-color: transparent;
            font-family: {UI_FONT}; font-size: {pt}pt;
        }}
        QTableWidget::item {{
            border: none; border-bottom: 1px solid {_tint(is_dark, 0.07)};
            color: {ink}; padding: 4px 8px; background-color: transparent;
        }}
        QTableWidget::item:hover {{ background-color: {_tint(is_dark, 0.035)}; }}
        QTableWidget::item:selected {{ background-color: {_tint(is_dark, 0.08)}; color: {ink}; }}
        QHeaderView {{ background-color: transparent; border: none; }}
        QHeaderView::section {{
            background-color: transparent; color: {muted}; font-weight: 500;
            font-size: {small}pt; font-family: {UI_FONT};
            border: none; border-bottom: 1px solid {hair}; padding: 7px 8px;
        }}
        QTableWidget::indicator {{ width: 14px; height: 14px; margin-left: 13px; border-radius: 0px; }}
        QTableWidget::indicator:unchecked {{ border: 1px solid {muted}; background: transparent; }}
        QTableWidget::indicator:checked {{ background: {ink}; border: 1px solid {ink}; image: url({_check_icon(paper)}); }}
        QTableCornerButton::section {{ background-color: transparent; border: none; }}
        {scrollbars(is_dark)}
    """)

    outline = _outline_btn(ink, hair, is_dark, pt)
    ex.b_new.setStyleSheet(_ink_btn(ink, paper, pt))
    for btn in (ex.b_new_code, ex.b_ref, ex.b_sync, ex.b_res, ex.btn_arrange_rolled, ex.btn_arrange_memos):
        btn.setStyleSheet(outline)
    danger = f"""
        QPushButton {{
            padding: 6px 12px; background: transparent; border: 1px solid {_rgba(DANGER, 0.45)}; border-radius: 0px;
            color: {DANGER}; font-weight: 500; font-size: {pt}pt; font-family: {UI_FONT};
        }}
        QPushButton:hover {{ background: {DANGER}; color: white; border-color: {DANGER}; }}
    """
    for btn in (ex.b_del, ex.b_empty_trash):
        btn.setStyleSheet(danger)
    ex.btn_app_theme.setStyleSheet(_outline_btn(ink, hair, is_dark, small, pad="0 10px"))
    ex.t_btn.setStyleSheet(outline + f"""
        QPushButton:checked {{ background: {ink}; color: {paper}; border-color: {ink}; }}
    """)
    pager = f"""
        QPushButton {{ background: transparent; border: none; border-radius: 0px; color: {muted}; font-weight: 600; font-size: {pt + 1}pt; }}
        QPushButton:hover {{ color: {ink}; }}
    """
    ex.p_b.setStyleSheet(pager)
    ex.n_b.setStyleSheet(pager)
    ex.p_l.setStyleSheet(f"font-weight: 500; margin: 0 14px; font-size: {small}pt; color: {muted}; font-family: {UI_FONT};")
    ex.stat_label.setStyleSheet(f"font-size: {small}pt; font-weight: 400; color: {muted}; font-family: {UI_FONT};")
    ex.toast.setStyleSheet(
        f"background-color: {ink}; color: {paper}; font-weight: 500; font-size: {small}pt; "
        f"border-radius: 0px; padding: 2px 10px; font-family: {UI_FONT};"
    )
    apply_explorer_preview(ex)
    apply_explorer_filters(ex)
    apply_explorer_table(ex)


def apply_explorer_chrome(ex: Any) -> None:
    pal, is_dark = app_palette(_settings_of(ex))
    ink = pal['text']
    icon = ex.ui_manager.get_theme_icon
    pinned = getattr(ex, 'is_pinned', False)
    style_window_buttons(ink, ex.btn_win_close, ex.btn_win_min, ex.btn_win_max)
    ex.btn_win_pin.setStyleSheet(_flat_button(ink, _rgba(ink, 0.16) if pinned else "transparent"))
    ex.btn_win_pin.setIcon(icon(f"pin_icon_{pinned}.svg", is_dark, override_color=pal['icon']))
    # 잉크색으로 채운 버튼 위에서는 아이콘을 바탕색으로 그려야 보입니다.
    ex.b_new.setIcon(icon("pluse.svg", is_dark, override_color=pal['bg']))


def apply_explorer_preview(ex: Any) -> None:
    pal, is_dark = app_palette(_settings_of(ex))
    ex.pv.setStyleSheet(f"""
        QTextEdit {{
            background-color: {pal['card']}; border: 1px solid {pal['border']}; border-radius: 0px;
            padding: 10px 12px; color: {pal['text']}; font-size: {_pt(ex)}pt;
            font-family: {MONO_FONT};
        }}
        QTextEdit:focus {{ border: 1px solid {pal['text']}; }}
        {scrollbars(is_dark)}
    """)


def apply_explorer_filters(ex: Any) -> None:
    """전체/일반/코드: 선택된 항목에만 잉크색 밑줄이 그어지는 탭."""
    pal, is_dark = app_palette(_settings_of(ex))
    pt = _pt(ex)
    base = f"padding: 6px 12px; background: transparent; border: none; border-radius: 0px; font-size: {pt}pt; font-family: {UI_FONT};"
    on = f"QPushButton {{ {base} border-bottom: 2px solid {pal['text']}; color: {pal['text']}; font-weight: 700; }}"
    off = (f"QPushButton {{ {base} border-bottom: 2px solid transparent; color: {_muted(is_dark)}; font-weight: 500; }} "
           f"QPushButton:hover {{ color: {pal['text']}; }}")
    for btn, mode in ((ex.btn_filter_all, "ALL"), (ex.btn_filter_gen, "GENERAL"), (ex.btn_filter_code, "CODE")):
        btn.setStyleSheet(on if ex.filter_mode == mode else off)


def apply_explorer_table(ex: Any) -> None:
    pal, is_dark = app_palette(_settings_of(ex))
    for btn, locked in explorer_rows(ex):
        color = DANGER if locked else _muted(is_dark)
        edge = _rgba(DANGER, 0.5) if locked else pal['border']
        btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {color}; border: 1px solid {edge}; border-radius: 0px; "
            f"font-weight: 500; font-size: 8.5pt; font-family: {UI_FONT}; }} "
            f"QPushButton:hover {{ border-color: {pal['text']}; color: {pal['text']}; }}"
        )


# ═══ 환경설정 ════════════════════════════════════════════════════════════════
def apply_settings(win: Any) -> None:
    pal, is_dark = app_palette(_settings_of(win))
    pt = max(9, int(getattr(win, "ui_font_pt", 10)) - 1)
    small = max(8, pt - 1)
    ink, paper, surface, hair = pal['text'], pal['bg'], pal['card'], pal['border']
    muted = _muted(is_dark)

    win.setStyleSheet(f"""
        SettingsWindow#SettingsWindow, QWidget#SettingsWindow {{ background-color: {paper}; }}
        QWidget {{ font-family: {UI_FONT}; font-size: {pt}pt; color: {ink}; background-color: {paper}; }}
        QTabWidget::pane {{ border: none; border-top: 1px solid {hair}; background: {paper}; top: -1px; }}
        QTabBar {{ background: transparent; }}
        QTabBar::tab {{
            padding: 9px 4px; margin-right: 22px; font-weight: 500; font-size: {pt}pt;
            background: transparent; color: {muted}; border: none; border-bottom: 2px solid transparent; border-radius: 0px;
        }}
        QTabBar::tab:hover {{ color: {ink}; }}
        QTabBar::tab:selected {{ color: {ink}; font-weight: 700; border-bottom: 2px solid {ink}; }}
        QGroupBox {{
            font-weight: 600; border: none; border-top: 1px solid {hair}; border-radius: 0px;
            margin-top: 22px; padding-top: 10px; background: transparent; color: {ink};
        }}
        QGroupBox::title {{
            subcontrol-origin: margin; left: 0px; padding: 0 8px 0 0; color: {muted};
            font-size: {small}pt; font-weight: 600;
        }}
        QGroupBox QWidget {{ background-color: transparent; }}
        QLineEdit, QComboBox, QFontComboBox, QSpinBox, QKeySequenceEdit {{
            padding: 6px 10px; border: 1px solid {hair}; border-radius: 0px;
            color: {ink}; background-color: {surface}; font-size: {pt}pt;
        }}
        QLineEdit:hover, QComboBox:hover, QSpinBox:hover {{ border-color: {muted}; }}
        QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{ border: 1px solid {ink}; }}
        QKeySequenceEdit {{ padding: 0; border: none; background: transparent; }}
        QKeySequenceEdit QLineEdit {{ padding: 2px 8px; }}
        QComboBox::drop-down {{ border: none; width: 24px; }}
        QComboBox::down-arrow {{ image: url({_arrow_icon("down", is_dark)}); width: 11px; height: 11px; }}
        QComboBox QAbstractItemView {{
            background-color: {surface}; color: {ink}; border: 1px solid {hair};
            selection-background-color: {ink}; selection-color: {paper}; outline: none;
        }}
        QSpinBox::up-button, QSpinBox::down-button {{ width: 20px; border: none; background: transparent; }}
        QSpinBox::up-button:hover, QSpinBox::down-button:hover {{ background: {_tint(is_dark, 0.08)}; }}
        QSpinBox::up-arrow {{ image: url({_arrow_icon("up", is_dark)}); width: 10px; height: 10px; }}
        QSpinBox::down-arrow {{ image: url({_arrow_icon("down", is_dark)}); width: 10px; height: 10px; }}
        QPushButton {{
            padding: 7px 14px; background: transparent; border: 1px solid {hair};
            border-radius: 0px; color: {ink}; font-weight: 500; font-size: {pt}pt;
        }}
        QPushButton:hover {{ border-color: {ink}; }}
        QPushButton:pressed {{ background: {_tint(is_dark, 0.08)}; }}
        QTableWidget {{
            border: none; border-top: 1px solid {ink}; border-bottom: 1px solid {hair}; border-radius: 0px;
            background: transparent; color: {ink}; font-size: {pt}pt; gridline-color: transparent; outline: none;
        }}
        QTableWidget::item {{ padding: 4px 8px; border: none; border-bottom: 1px solid {_tint(is_dark, 0.07)}; }}
        QTableWidget::item:selected {{ background: {_tint(is_dark, 0.08)}; color: {ink}; }}
        QHeaderView {{ background: transparent; }}
        QHeaderView::section {{
            background: transparent; color: {muted}; font-weight: 500; border: none;
            border-bottom: 1px solid {hair}; padding: 7px 8px; font-size: {small}pt;
        }}
        QCheckBox {{ color: {ink}; background: transparent; spacing: 10px; padding: 2px 0; }}
        QCheckBox::indicator {{ width: 14px; height: 14px; border-radius: 0px; border: 1px solid {muted}; background: transparent; }}
        QCheckBox::indicator:hover {{ border-color: {ink}; }}
        QCheckBox::indicator:checked {{ background: {ink}; border-color: {ink}; image: url({_check_icon(paper)}); }}
        QLabel {{ color: {ink}; background: transparent; }}
        QLabel[role="hint"] {{ color: {muted}; font-size: {small}pt; }}
        QLabel[role="value"], QCheckBox[role="value"] {{ color: {ink}; font-weight: 700; }}
        QSlider::groove:horizontal {{ height: 2px; background: {hair}; border-radius: 0px; }}
        QSlider::sub-page:horizontal {{ background: {ink}; border-radius: 0px; }}
        QSlider::handle:horizontal {{ width: 10px; height: 16px; margin: -7px 0; background: {ink}; border-radius: 0px; }}
        QScrollArea {{ background: {paper}; border: none; }}
        QScrollArea > QWidget > QWidget {{ background: {paper}; }}
        {scrollbars(is_dark)}
    """)
    win.sb.setStyleSheet(_ink_btn(ink, paper, pt + 1, pad="10px"))
    # 잉크색으로 채운 버튼 위에서는 아이콘을 바탕색으로 그려야 보입니다.
    set_save_icon(win, paper)


# ═══ 메모 창 ═════════════════════════════════════════════════════════════════
def apply_memo(w: Any) -> None:
    pal, is_dark, bg_color = memo_tone(w)
    ink = pal['text']
    # 밝은 메모는 위쪽에만 굵은 잉크색 선을 둔 '카드' 형태.
    # 어두운 메모에서는 잉크색이 흰색에 가까워 흰 줄처럼 튀므로(특히 접었을 때) 네 변 모두 옅은 선으로 둡니다.
    top_line = "" if is_dark else f" border-top: 2px solid {ink};"
    w.bg.setStyleSheet(
        f"QWidget#MemoBackground {{ background-color: {bg_color}; "
        f"border: 1px solid {_rgba(ink, 0.22)};{top_line} border-radius: 0px; }}"
    )
    w.toast_label.setStyleSheet(
        f"background-color: {ink}; color: {bg_color}; font-weight: 500; "
        f"border-radius: 0px; padding: 4px 12px; font-size: 9pt; font-family: {UI_FONT};"
    )
    style_window_buttons(ink, w.btn_close, w.btn_min, w.btn_max)
    pinned = w.memo_data.get('is_pinned', False)
    w.btn_pin.setStyleSheet(_flat_button(ink, _rgba(ink, 0.16) if pinned else "transparent"))
    box = (f"QPushButton, QComboBox {{ font-size: 8.5pt; font-weight: 500; padding: 2px 6px; border: 1px solid {_rgba(ink, 0.25)}; "
           f"border-radius: 0px; background: transparent; color: {ink}; font-family: {UI_FONT}; }} "
           f"QPushButton:hover, QComboBox:hover {{ border-color: {ink}; }} QComboBox::drop-down {{ border: none; }}")
    for name in MEMO_BOX_CONTROLS:
        getattr(w, name).setStyleSheet(box)
    swatch = (f"QPushButton {{ font-size: 9pt; font-weight: 600; padding: 0; border: 1px solid {_rgba(ink, 0.25)}; "
              f"border-radius: 0px; background: transparent; color: {ink}; }} "
              f"QPushButton:hover {{ border-color: {ink}; }}")
    w.btn_fg_color.setStyleSheet(swatch)
    w.btn_bg_color.setStyleSheet(swatch)
    w.search_bar.setStyleSheet(
        box + f"QLineEdit {{ padding: 4px 8px; border: 1px solid {_rgba(ink, 0.25)}; border-radius: 0px; "
        f"background: transparent; color: {ink}; font-family: {UI_FONT}; }} "
        f"QLineEdit:focus {{ border-color: {ink}; }} "
        f"QLabel {{ color: {ink}; font-weight: 600; padding: 0 5px; }}"
    )
    apply_memo_toolbar(w)


def apply_memo_toolbar(w: Any) -> None:
    """서식 버튼. 굵게·기울임·밑줄만 켜진 상태를 잉크색으로 채우고, 목록·들여쓰기 버튼은 칠하지 않습니다."""
    pal, _, bg_color = memo_tone(w)
    ink = pal['text']
    off = (f"QPushButton {{ border: none; color: {ink}; font-size: 10pt; background: transparent; font-weight: 600; border-radius: 0px; }} "
           f"QPushButton:hover {{ background: {_rgba(ink, 0.12)}; }}")
    on = f"QPushButton {{ border: none; color: {bg_color}; font-size: 10pt; background: {ink}; font-weight: 700; border-radius: 0px; }}"
    for name in MEMO_TOGGLE_BUTTONS:
        btn = getattr(w, name)
        btn.setStyleSheet(on if btn.isChecked() else off)
    for name in MEMO_ACTION_BUTTONS:
        getattr(w, name).setStyleSheet(off)
