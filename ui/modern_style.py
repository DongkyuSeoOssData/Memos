"""화면 디자인 스타일.

디자인은 두 가지입니다. (settings 의 "ui_style")
- "modern": 이 파일. 면을 옅게 칠한 버튼과 카드 위주의 기본 디자인.
- "neo"   : ui/neo_style.py. 선과 여백 위주의 미니멀 디자인.

각 창은 모양을 직접 정하지 않고 여기의 apply_* 함수만 부릅니다. 디자인 스타일이 "neo"이면
같은 이름의 neo_style 함수로 넘어갑니다. 두 디자인이 함께 쓰는 도우미도 이 파일에 있습니다.
모서리는 모두 각지게(border-radius 0) 유지합니다.
"""
import functools
import tempfile
from pathlib import Path
from datetime import datetime
from typing import Any, Callable, Dict, Iterator

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QColor, QFontMetrics, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import QPushButton

from ui.themes import app_palette

UI_FONT = "'Pretendard', 'Segoe UI', 'Malgun Gothic', sans-serif"
MONO_FONT = "'D2Coding', 'Consolas', monospace"
DANGER = "#FF453A"
DEFAULT_STYLE = "modern"

# 메모 창에서 테두리 상자 모양으로 그리는 컨트롤
MEMO_BOX_CONTROLS = ("btn_code_theme", "code_lang_box", "btn_format_code", "font_box", "size_box", "btn_toggle_sub_fmt")
# 켜짐/꺼짐이 표시되는 서식 버튼과, 표시 없이 동작만 하는 버튼(목록·들여쓰기)
MEMO_TOGGLE_BUTTONS = ("btn_bold", "btn_italic", "btn_underline")
MEMO_ACTION_BUTTONS = ("btn_bullet", "btn_num", "btn_indent", "btn_outdent")


def is_neo(settings: Dict[str, Any]) -> bool:
    # "neo"가 아니면 모두 Modern 입니다. (예전 설정의 "classic" 값도 Modern 으로 취급)
    return settings.get("ui_style", DEFAULT_STYLE) == "neo"


def _settings_of(target: Any) -> Dict[str, Any]:
    """메모 창 / 환경설정 창 / 탐색기 어느 것이든 그 창이 쓰는 설정을 돌려줍니다."""
    if hasattr(target, "memo_window_get_settings"):
        return target.memo_window_get_settings()
    if hasattr(target, "sm"):
        return target.sm.settings
    return target.ui_manager.sync_manager.settings


def _styled(func: Callable[[Any], None]) -> Callable[[Any], None]:
    """디자인 스타일이 "neo"이면 neo_style 의 같은 이름 함수로 넘깁니다."""
    @functools.wraps(func)
    def wrapper(target: Any) -> None:
        if is_neo(_settings_of(target)):
            from ui import neo_style
            getattr(neo_style, func.__name__)(target)
        else:
            func(target)
    return wrapper


# ═══ 공용 도우미 ═════════════════════════════════════════════════════════════
def _rgba(color: str, alpha: float) -> str:
    c = QColor(color)
    return f"rgba({c.red()}, {c.green()}, {c.blue()}, {alpha})"


def _tint(is_dark: bool, alpha: float) -> str:
    """배경 위에 얹는 옅은 음영 (다크에서는 밝게, 라이트에서는 어둡게)."""
    return f"rgba(255, 255, 255, {alpha})" if is_dark else f"rgba(0, 0, 0, {alpha})"


def _muted(is_dark: bool) -> str:
    return "rgba(235, 235, 245, 0.55)" if is_dark else "rgba(60, 60, 67, 0.6)"


def _icon_file(name: str, size: int, draw: Callable[[QPainter], None]) -> str:
    """작은 그림을 한 번 그려 임시 폴더에 저장해 두고 그 경로를 돌려줍니다. (스타일시트의 image: url 용)"""
    path = Path(tempfile.gettempdir()) / "memoit_ui" / f"{name}.png"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        pix = QPixmap(size, size)
        pix.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        draw(painter)
        painter.end()
        pix.save(str(path))
    return path.as_posix()


def _check_icon(color: str = "#FFFFFF") -> str:
    """체크박스 안에 그릴 체크 표시."""
    def draw(painter: QPainter) -> None:
        pen = QPen(QColor(color))
        pen.setWidthF(4.5)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.drawPolyline(QPointF(9, 19), QPointF(15.5, 25), QPointF(27, 12))
    return _icon_file(f"check_{QColor(color).name()[1:]}", 36, draw)


def _arrow_icon(direction: str, is_dark: bool) -> str:
    """콤보박스·숫자 입력칸에 쓰는 작은 화살표."""
    def draw(painter: QPainter) -> None:
        pen = QPen(QColor(235, 235, 245, 190) if is_dark else QColor(60, 60, 67, 190))
        pen.setWidthF(2.6)
        pen.setCapStyle(Qt.PenCapStyle.SquareCap)
        pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
        painter.setPen(pen)
        tip, base = (15, 9) if direction == "down" else (9, 15)
        painter.drawPolyline(QPointF(6, base), QPointF(12, tip), QPointF(18, base))
    return _icon_file(f"arrow_{direction}_{'light' if is_dark else 'dark'}", 24, draw)


def scrollbars(is_dark: bool) -> str:
    handle = _tint(is_dark, 0.22)
    handle_hover = _tint(is_dark, 0.38)
    return f"""
        QScrollBar:vertical {{ width: 10px; background: transparent; margin: 4px 2px 4px 0; }}
        QScrollBar::handle:vertical {{ background: {handle}; border-radius: 0px; min-height: 28px; margin: 0 2px; }}
        QScrollBar::handle:vertical:hover {{ background: {handle_hover}; }}
        QScrollBar:horizontal {{ height: 10px; background: transparent; margin: 0 4px 2px 4px; }}
        QScrollBar::handle:horizontal {{ background: {handle}; border-radius: 0px; min-width: 28px; margin: 2px 0; }}
        QScrollBar::handle:horizontal:hover {{ background: {handle_hover}; }}
        QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
        QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
    """


def menu_qss(settings: Dict[str, Any]) -> str:
    """우클릭·트레이 메뉴. (앱 색 테마를 따름)"""
    pal, _ = app_palette(settings)
    on_bg, on_text = (pal['text'], pal['bg']) if is_neo(settings) else (pal['accent'], "white")
    return (f"QMenu {{ background: {pal['card']}; color: {pal['text']}; border: 1px solid {pal['border']}; "
            f"border-radius: 0px; padding: 4px; }} "
            f"QMenu::item:selected {{ background-color: {on_bg}; color: {on_text}; }}")


def _flat_button(ink: str, fill: str = "transparent") -> str:
    """제목 줄의 창 버튼처럼 테두리 없이 올렸을 때만 바탕이 드러나는 버튼."""
    return (f"QPushButton {{ background: {fill}; border: none; border-radius: 0px; }} "
            f"QPushButton:hover {{ background: {_rgba(ink, 0.12)}; }}")


def style_window_buttons(ink: str, close: Any, *others: Any) -> None:
    """최소화·최대화 등은 옅은 호버, 닫기는 빨간 호버."""
    for btn in others:
        btn.setStyleSheet(_flat_button(ink))
    close.setStyleSheet("QPushButton { background: transparent; border: none; border-radius: 0px; } "
                        f"QPushButton:hover {{ background: {DANGER}; }}")


def set_save_icon(win: Any, color: str) -> None:
    """환경설정의 저장 버튼 아이콘. (색을 채운 버튼이라 아이콘 색을 따로 지정)"""
    ui_manager = getattr(win.sm, 'ui_manager', None)
    if ui_manager is not None and hasattr(ui_manager, 'get_theme_icon'):
        win.sb.setIcon(ui_manager.get_theme_icon("save.svg", True, override_color=color))


def memo_tone(w: Any) -> tuple:
    """메모 창의 (팔레트, 다크 여부, 바탕색)."""
    pal = w._memo_theme_palette()
    bg_color = pal['card'] if w.memo_data.get('is_code_memo', False) else w.memo_bg_color()
    return pal, w.is_dark_bg(), bg_color


def explorer_rows(ex: Any) -> Iterator[tuple]:
    """표가 다시 그려질 때마다: 날짜 열을 읽기 쉽게 맞추고, 행마다 (보호 버튼, 잠김 여부)를 넘겨줍니다."""
    _, is_dark = app_palette(_settings_of(ex))
    date_color = QColor(235, 235, 245, 150) if is_dark else QColor(60, 60, 67, 160)
    fm = QFontMetrics(ex.table.font())
    ex.table.setColumnWidth(3, max(120, fm.horizontalAdvance("00.00.00 00:00") + 40))
    ex.table.setColumnWidth(4, 78)
    for r in range(ex.table.rowCount()):
        date_item = ex.table.item(r, 3)
        title_item = ex.table.item(r, 2)
        if date_item:
            memo = title_item.data(Qt.ItemDataRole.UserRole) if title_item else None
            try:
                stamp = datetime.fromisoformat((memo or {}).get('updated_at', ''))
                date_item.setText(stamp.strftime("%y.%m.%d %H:%M"))    # 26.10.01 09:30
            except (TypeError, ValueError):
                pass
            date_item.setForeground(date_color)
        cell = ex.table.cellWidget(r, 4)
        btn = cell.findChild(QPushButton) if cell else None
        if btn:
            yield btn, btn.text() == "잠김"


def _explorer_pt(ex: Any) -> int:
    return max(9, round(int(getattr(ex, "ui_font_pt", 10)) * 0.88))


# ═══ 메모 탐색기 ══════════════════════════════════════════════════════════════
@_styled
def apply_explorer(ex: Any) -> None:
    pal, is_dark = app_palette(_settings_of(ex))
    pt = _explorer_pt(ex)
    small = max(8, pt - 1)
    accent, text, border = pal['accent'], pal['text'], pal['border']
    muted = _muted(is_dark)
    field_bg = pal['input'] if is_dark else pal['card']

    ex.bg.setStyleSheet(f"""
        QFrame#ExplorerBg {{ background-color: {pal['bg']}; border: 1px solid {border}; border-radius: 0px; }}
        QLabel {{ color: {text}; font-family: {UI_FONT}; font-size: {pt}pt; }}
        QPushButton {{ font-family: {UI_FONT}; color: {text}; font-size: {pt}pt; }}
        QLineEdit, QComboBox {{
            padding: 6px 12px; border: 1px solid {border}; border-radius: 0px;
            color: {text}; background-color: {field_bg};
            selection-background-color: {accent}; font-family: {UI_FONT}; font-size: {pt}pt;
        }}
        QLineEdit:hover, QComboBox:hover {{ border-color: {_tint(is_dark, 0.3)}; }}
        QLineEdit:focus, QComboBox:focus {{ border: 1.5px solid {accent}; }}
        QComboBox::drop-down {{ border: none; width: 22px; }}
        QComboBox::down-arrow {{ image: url({_arrow_icon("down", is_dark)}); width: 12px; height: 12px; }}
        QComboBox QAbstractItemView {{
            background-color: {pal['card']}; color: {text}; border: 1px solid {border};
            selection-background-color: {accent}; selection-color: white; outline: none; padding: 4px;
        }}
    """)
    ex.title_label.setStyleSheet(
        f"font-size: 14pt; border: none; font-weight: 700; letter-spacing: -0.5px; font-family: {MONO_FONT};"
    )

    ex.table.setStyleSheet(f"""
        QTableWidget {{
            border: 1px solid {border}; border-radius: 0px; background-color: {pal['card']};
            color: {text}; outline: none; gridline-color: transparent;
            font-family: {UI_FONT}; font-size: {pt}pt;
        }}
        QTableWidget::item {{
            border: none; border-bottom: 1px solid {_tint(is_dark, 0.07)};
            color: {text}; padding: 4px 8px; background-color: transparent;
        }}
        QTableWidget::item:hover {{ background-color: {_tint(is_dark, 0.04)}; }}
        QTableWidget::item:selected {{ background-color: {_rgba(accent, 0.16)}; color: {text}; }}
        QHeaderView {{ background-color: transparent; border: none; }}
        QHeaderView::section {{
            background-color: transparent; color: {muted}; font-weight: 600;
            font-size: {small}pt; font-family: {UI_FONT};
            border: none; border-bottom: 1px solid {border}; padding: 6px 8px;
        }}
        QTableWidget::indicator {{ width: 16px; height: 16px; margin-left: 12px; border-radius: 0px; }}
        QTableWidget::indicator:unchecked {{ border: 1px solid {_tint(is_dark, 0.4)}; background: transparent; }}
        QTableWidget::indicator:checked {{ background: {accent}; border: 1.5px solid {accent}; image: url({_check_icon()}); }}
        QTableCornerButton::section {{ background-color: transparent; border: none; }}
        {scrollbars(is_dark)}
    """)

    def button(fill: str, color: str, hover: str, pad: str = "6px 12px") -> str:
        return f"""
            QPushButton {{
                padding: {pad}; background-color: {fill}; border: 1px solid transparent;
                border-radius: 0px; color: {color}; font-weight: 600; font-size: {pt}pt; font-family: {UI_FONT};
            }}
            QPushButton:hover {{ background-color: {hover}; }}
        """
    ghost = button(_tint(is_dark, 0.06), text, _tint(is_dark, 0.12))
    ghost += f"QPushButton:pressed {{ background-color: {_tint(is_dark, 0.18)}; }}"
    danger = button(_rgba(DANGER, 0.10), DANGER, _rgba(DANGER, 0.20))
    accent_soft = button(_rgba(accent, 0.12), accent, _rgba(accent, 0.22))

    ex.b_new.setStyleSheet(button(accent, "white", _rgba(accent, 0.85), pad="6px 14px"))
    for btn in (ex.b_new_code, ex.b_ref, ex.b_sync, ex.b_res):
        btn.setStyleSheet(ghost)
    for btn in (ex.b_del, ex.b_empty_trash):
        btn.setStyleSheet(danger)
    for btn in (ex.btn_arrange_rolled, ex.btn_arrange_memos):
        btn.setStyleSheet(accent_soft)
    ex.btn_app_theme.setStyleSheet(f"""
        QPushButton {{
            padding: 0 12px; border: 1px solid {border}; border-radius: 0px; font-weight: 600;
            background: {_tint(is_dark, 0.05)}; color: {text}; font-size: {small}pt; font-family: {UI_FONT};
        }}
        QPushButton:hover {{ background: {_tint(is_dark, 0.12)}; }}
    """)
    ex.t_btn.setStyleSheet(
        button(_tint(is_dark, 0.06), text, _tint(is_dark, 0.12), pad="6px 14px")
        + f"QPushButton:checked {{ background-color: {accent}; color: white; }}"
    )
    pager = f"""
        QPushButton {{ background: transparent; border: none; border-radius: 0px; color: {muted}; font-weight: 700; font-size: {pt + 1}pt; }}
        QPushButton:hover {{ background: {_tint(is_dark, 0.10)}; color: {text}; }}
    """
    ex.p_b.setStyleSheet(pager)
    ex.n_b.setStyleSheet(pager)
    ex.p_l.setStyleSheet(f"font-weight: 600; margin: 0 14px; font-size: {small}pt; color: {muted}; font-family: {UI_FONT};")
    ex.stat_label.setStyleSheet(f"font-size: {small}pt; font-weight: 500; color: {muted}; font-family: {UI_FONT};")
    ex.toast.setStyleSheet(
        f"background-color: {_rgba(accent, 0.14)}; color: {accent}; font-weight: 600; font-size: {small}pt; "
        f"border-radius: 0px; padding: 2px 10px; font-family: {UI_FONT};"
    )
    apply_explorer_preview(ex)
    apply_explorer_filters(ex)
    apply_explorer_table(ex)


@_styled
def apply_explorer_chrome(ex: Any) -> None:
    """제목 줄의 창 버튼과, 색을 채운 버튼 위에 올라가는 아이콘. (아이콘이 바뀔 때마다 호출)"""
    pal, is_dark = app_palette(_settings_of(ex))
    icon = ex.ui_manager.get_theme_icon
    pinned = getattr(ex, 'is_pinned', False)
    style_window_buttons(pal['text'], ex.btn_win_close, ex.btn_win_min, ex.btn_win_max)
    ex.btn_win_pin.setStyleSheet(_flat_button(pal['text'], pal['accent'] if pinned else "transparent"))
    ex.btn_win_pin.setIcon(icon(f"pin_icon_{pinned}.svg", is_dark, override_color="#FFFFFF" if pinned else pal['icon']))
    ex.b_new.setIcon(icon("pluse.svg", is_dark, override_color="#FFFFFF"))


@_styled
def apply_explorer_preview(ex: Any) -> None:
    pal, is_dark = app_palette(_settings_of(ex))
    ex.pv.setStyleSheet(f"""
        QTextEdit {{
            background-color: {pal['card']}; border: 1px solid {pal['border']}; border-radius: 0px;
            padding: 10px 12px; color: {pal['text']}; font-size: {_explorer_pt(ex)}pt;
            font-family: {MONO_FONT};
        }}
        QTextEdit:focus {{ border: 1.5px solid {pal['accent']}; }}
        {scrollbars(is_dark)}
    """)


@_styled
def apply_explorer_filters(ex: Any) -> None:
    """전체/일반/코드 필터: 선택된 항목만 강조색으로 채웁니다."""
    pal, is_dark = app_palette(_settings_of(ex))
    pt = _explorer_pt(ex)
    on = (f"QPushButton {{ padding: 6px 14px; background: {pal['accent']}; border: 1px solid {pal['accent']}; "
          f"border-radius: 0px; color: white; font-weight: 600; font-size: {pt}pt; font-family: {UI_FONT}; }}")
    off = (f"QPushButton {{ padding: 6px 14px; background: {_tint(is_dark, 0.06)}; border: 1px solid transparent; "
           f"border-radius: 0px; color: {pal['text']}; font-weight: 600; font-size: {pt}pt; font-family: {UI_FONT}; }} "
           f"QPushButton:hover {{ background: {_tint(is_dark, 0.12)}; }}")
    for btn, mode in ((ex.btn_filter_all, "ALL"), (ex.btn_filter_gen, "GENERAL"), (ex.btn_filter_code, "CODE")):
        btn.setStyleSheet(on if ex.filter_mode == mode else off)


@_styled
def apply_explorer_table(ex: Any) -> None:
    """표가 다시 그려질 때마다 행 안의 보호 버튼을 다듬습니다."""
    _, is_dark = app_palette(_settings_of(ex))
    for btn, locked in explorer_rows(ex):
        color = DANGER if locked else _muted(is_dark)
        bg = _rgba(DANGER, 0.12) if locked else _tint(is_dark, 0.06)
        btn.setStyleSheet(
            f"QPushButton {{ background: {bg}; color: {color}; border: none; border-radius: 0px; "
            f"font-weight: 600; font-size: 8.5pt; font-family: {UI_FONT}; }} "
            f"QPushButton:hover {{ background: {_tint(is_dark, 0.14)}; }}"
        )


# ═══ 환경설정 ════════════════════════════════════════════════════════════════
@_styled
def apply_settings(win: Any) -> None:
    pal, is_dark = app_palette(_settings_of(win))
    pt = max(9, int(getattr(win, "ui_font_pt", 10)) - 1)
    small = max(8, pt - 1)
    accent, text, border = pal['accent'], pal['text'], pal['border']
    muted = _muted(is_dark)
    field_bg = pal['input'] if is_dark else pal['card']

    win.setStyleSheet(f"""
        SettingsWindow#SettingsWindow, QWidget#SettingsWindow {{ background-color: {pal['bg']}; }}
        QWidget {{ font-family: {UI_FONT}; font-size: {pt}pt; color: {text}; background-color: {pal['bg']}; }}
        QTabWidget::pane {{ border: none; background: {pal['bg']}; top: 6px; }}
        QTabBar {{ background: transparent; }}
        QTabBar::tab {{
            padding: 8px 16px; margin-right: 6px; font-weight: 600; font-size: {pt}pt;
            background: {_tint(is_dark, 0.05)}; color: {muted}; border: none; border-radius: 0px;
        }}
        QTabBar::tab:hover {{ background: {_tint(is_dark, 0.10)}; color: {text}; }}
        QTabBar::tab:selected {{ background: {_rgba(accent, 0.14)}; color: {accent}; }}
        QGroupBox {{
            font-weight: 600; border: 1px solid {border}; border-radius: 0px;
            margin-top: 14px; padding-top: 14px; background: {pal['card']}; color: {text};
        }}
        QGroupBox::title {{ subcontrol-origin: margin; left: 14px; padding: 0 6px; color: {accent}; font-size: {small}pt; }}
        QGroupBox QWidget {{ background-color: transparent; }}
        QLineEdit, QComboBox, QFontComboBox, QSpinBox, QKeySequenceEdit {{
            padding: 6px 10px; border: 1px solid {border}; border-radius: 0px;
            color: {text}; background-color: {field_bg}; font-size: {pt}pt;
        }}
        QLineEdit:hover, QComboBox:hover, QSpinBox:hover {{ border-color: {_tint(is_dark, 0.3)}; }}
        QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{ border: 1.5px solid {accent}; }}
        QKeySequenceEdit {{ padding: 0; border: none; background: transparent; }}
        QKeySequenceEdit QLineEdit {{ padding: 2px 8px; }}
        QComboBox::drop-down {{ border: none; width: 24px; }}
        QComboBox::down-arrow {{ image: url({_arrow_icon("down", is_dark)}); width: 12px; height: 12px; }}
        QComboBox QAbstractItemView {{
            background-color: {pal['card']}; color: {text}; border: 1px solid {border};
            selection-background-color: {accent}; selection-color: white; outline: none;
        }}
        QSpinBox::up-button, QSpinBox::down-button {{ width: 20px; border: none; background: transparent; }}
        QSpinBox::up-button:hover, QSpinBox::down-button:hover {{ background: {_tint(is_dark, 0.10)}; }}
        QSpinBox::up-arrow {{ image: url({_arrow_icon("up", is_dark)}); width: 10px; height: 10px; }}
        QSpinBox::down-arrow {{ image: url({_arrow_icon("down", is_dark)}); width: 10px; height: 10px; }}
        QPushButton {{
            padding: 7px 14px; background: {_tint(is_dark, 0.06)}; border: 1px solid transparent;
            border-radius: 0px; color: {text}; font-weight: 600; font-size: {pt}pt;
        }}
        QPushButton:hover {{ background: {_tint(is_dark, 0.12)}; }}
        QPushButton:pressed {{ background: {_tint(is_dark, 0.18)}; }}
        QTableWidget {{
            border: 1px solid {border}; border-radius: 0px; background: {pal['card']}; color: {text};
            font-size: {pt}pt; gridline-color: {_tint(is_dark, 0.06)}; outline: none;
        }}
        QTableWidget::item {{ padding: 4px 8px; border: none; }}
        QTableWidget::item:selected {{ background: {_rgba(accent, 0.14)}; color: {text}; }}
        QHeaderView {{ background: transparent; }}
        QHeaderView::section {{
            background: transparent; color: {muted}; font-weight: 600; border: none;
            border-bottom: 1px solid {border}; padding: 6px 8px; font-size: {small}pt;
        }}
        QCheckBox {{ color: {text}; background: transparent; spacing: 10px; padding: 2px 0; }}
        QCheckBox::indicator {{ width: 16px; height: 16px; border-radius: 0px; border: 1px solid {_tint(is_dark, 0.4)}; background: {field_bg}; }}
        QCheckBox::indicator:hover {{ border-color: {accent}; }}
        QCheckBox::indicator:checked {{ background: {accent}; border-color: {accent}; image: url({_check_icon()}); }}
        QLabel {{ color: {text}; background: transparent; }}
        QLabel[role="hint"] {{ color: {muted}; font-size: {small}pt; }}
        QLabel[role="value"], QCheckBox[role="value"] {{ color: {accent}; font-weight: 700; }}
        QSlider::groove:horizontal {{ height: 4px; background: {_tint(is_dark, 0.15)}; border-radius: 0px; }}
        QSlider::sub-page:horizontal {{ background: {accent}; border-radius: 0px; }}
        QSlider::handle:horizontal {{ width: 16px; height: 16px; margin: -7px 0; background: {accent}; border-radius: 0px; border: 2px solid {pal['card']}; }}
        QScrollArea {{ background: {pal['bg']}; border: none; }}
        QScrollArea > QWidget > QWidget {{ background: {pal['bg']}; }}
        {scrollbars(is_dark)}
    """)
    win.sb.setStyleSheet(f"""
        QPushButton {{
            background: {accent}; color: white; padding: 10px; font-weight: 700;
            font-size: {pt + 1}pt; border-radius: 0px; border: none; font-family: {UI_FONT};
        }}
        QPushButton:hover {{ background: {_rgba(accent, 0.85)}; }}
    """)
    set_save_icon(win, "#FFFFFF")


# ═══ 메모 창 ═════════════════════════════════════════════════════════════════
@_styled
def apply_memo(w: Any) -> None:
    pal, is_dark, bg_color = memo_tone(w)
    ink = pal['text']
    w.bg.setStyleSheet(
        f"QWidget#MemoBackground {{ background-color: {bg_color}; "
        f"border: 1px solid {_tint(is_dark, 0.16 if is_dark else 0.10)}; border-radius: 0px; }}"
    )
    w.toast_label.setStyleSheet(
        f"background-color: {_tint(is_dark, 0.78 if not is_dark else 0.22)}; color: white; font-weight: 600; "
        f"border-radius: 0px; padding: 5px 12px; font-size: 9pt; font-family: {UI_FONT};"
    )
    style_window_buttons(ink, w.btn_close, w.btn_min, w.btn_max)
    pinned = w.memo_data.get('is_pinned', False)
    w.btn_pin.setStyleSheet(_flat_button(ink, pal['accent'] if pinned else "transparent"))
    box = (f"QPushButton, QComboBox {{ font-size: 8.5pt; font-weight: 600; padding: 2px 6px; border: 1px solid {_rgba(ink, 0.2)}; "
           f"border-radius: 0px; background: {_rgba(ink, 0.06)}; color: {ink}; font-family: {UI_FONT}; }} "
           f"QPushButton:hover, QComboBox:hover {{ background: {_rgba(ink, 0.14)}; }} QComboBox::drop-down {{ border: none; }}")
    for name in MEMO_BOX_CONTROLS:
        getattr(w, name).setStyleSheet(box)
    swatch = (f"QPushButton {{ font-size: 9pt; font-weight: 700; padding: 0; border: 1px solid {_rgba(ink, 0.2)}; "
              f"border-radius: 0px; background: {_rgba(ink, 0.06)}; color: {ink}; }} "
              f"QPushButton:hover {{ background: {_rgba(ink, 0.14)}; }}")
    w.btn_fg_color.setStyleSheet(swatch)
    w.btn_bg_color.setStyleSheet(swatch)
    w.search_bar.setStyleSheet(
        box + f"QLineEdit {{ padding: 4px 8px; border: 1px solid {_rgba(ink, 0.25)}; border-radius: 0px; "
        f"background: transparent; color: {ink}; font-family: {UI_FONT}; }} "
        f"QLineEdit:focus {{ border-color: {pal['accent']}; }} "
        f"QLabel {{ color: {ink}; font-weight: 600; padding: 0 5px; }}"
    )
    apply_memo_toolbar(w)


@_styled
def apply_memo_toolbar(w: Any) -> None:
    """서식 버튼. 굵게·기울임·밑줄만 켜진 상태를 강조색으로 표시하고, 목록·들여쓰기 버튼은 칠하지 않습니다."""
    pal = w._memo_theme_palette()
    ink = pal['text']
    off = (f"QPushButton {{ border: none; color: {ink}; font-size: 10pt; background: transparent; font-weight: bold; border-radius: 0px; }} "
           f"QPushButton:hover {{ background: {_rgba(ink, 0.12)}; }}")
    on = f"QPushButton {{ border: none; color: white; font-size: 10pt; background: {pal['accent']}; font-weight: bold; border-radius: 0px; }}"
    for name in MEMO_TOGGLE_BUTTONS:
        btn = getattr(w, name)
        btn.setStyleSheet(on if btn.isChecked() else off)
    for name in MEMO_ACTION_BUTTONS:
        getattr(w, name).setStyleSheet(off)
