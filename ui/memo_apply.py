"""메모 창에 메모의 내용과 모양 입히기: 본문·제목·색·글꼴·줄 배경·행 번호, 메모 색 바꾸기.

(MemoWindow 에 섞어 쓰는 부분)
"""
from ui.memo_editor import CodeHighlighter
from ui import modern_style
from ui import memo_geometry
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QTextCursor
from utils.text_utils import is_html_content


class MemoApplyMixin:
    """메모 창에 내용과 모양 입히기."""

    def toggle_line_numbers(self) -> None:
        self.memo_data['show_line_numbers'] = not self.memo_data.get('show_line_numbers', False)
        self.text_edit.update_line_number_area()
        self.save_callback(self.memo_data)

    def toggle_line_bg(self) -> None:
        self.memo_data['show_line_bg'] = not self.memo_data.get('show_line_bg', False)
        self.text_edit.viewport().update()
        self.save_callback(self.memo_data)

    def apply_line_bg_style(self) -> None:
        """본문 편집기의 글자색·글꼴·스크롤바."""
        is_dark_bg = self.is_dark_bg()
        text_color = "#F2F2F7" if is_dark_bg else "#1C1C1E"
        font_fam = modern_style.MONO_FONT                 # 앱 글꼴
        self.text_edit.setStyleSheet(
            f"QTextEdit {{ border:none; background: transparent; color:{text_color}; "
            f"font-family: {font_fam}; font-size: {self.memo_data.get('font_size', 11)}pt; }}"
            + modern_style.scrollbars(is_dark_bg)
        )

    def _title_color_stylesheet(self, font_size_pt: float = 12.0) -> str:
        """현재 메모 테마 팔레트 기준으로 title_edit에 적용할 stylesheet를 반환합니다.

        코드 메모는 accent 색상, 일반 메모는 text 색상을 사용합니다.
        """
        pal = self._memo_theme_palette()
        title_color = pal['accent'] if self.memo_data.get('is_code_memo', False) else pal['text']
        return (
            f"border:none; background:transparent; color:{title_color}; "
            f"font-weight:bold; font-size:{font_size_pt}pt; font-family:{modern_style.UI_FONT};"
        )

    def apply_look(self) -> None:
        """색·고정·테마·설정처럼 모양만 바뀌었을 때 부릅니다. 본문은 다시 채우지 않습니다.

        본문을 다시 채우면 커서가 맨 앞으로 가고 스크롤과 실행 취소 기록이 사라지므로,
        내용이 달라진 것이 아닐 때는 이쪽을 씁니다.
        """
        self.apply_data(refill=False)

    def apply_data(self, refill: bool = True) -> None:
        """memo_data 를 창에 반영합니다. refill 이 꺼져 있으면 본문은 그대로 두고 모양만 맞춥니다."""
        if getattr(self, '_is_applying_data', False):
            return
        self._is_applying_data = True
        try:
            # 아래에서 memo_data['content']로 편집기를 다시 채우므로, 자동 저장 대기 중인 입력을 먼저 반영해 둡니다.
            was_modified = hasattr(self, 'text_edit') and self._auto_save_timer.isActive() \
                and self.text_edit.document().isModified()
            if self._auto_save_timer.isActive() and hasattr(self, 'text_edit'):
                self.memo_data['content'] = self.current_content()
            self._apply_data_internal(refill)
            modern_style.apply_memo(self)
            # 화면을 다시 채우는 것은 수정이 아닙니다. 저장을 기다리던 입력이 있었을 때만 '고침' 표시를 유지합니다.
            if refill:
                self.text_edit.document().setModified(bool(was_modified))
        finally:
            self._is_applying_data = False

    def _apply_data_internal(self, refill: bool = True) -> None:
        is_pinned = self.memo_data.get('is_pinned', False)
        self._apply_window_flags(is_pinned)

        is_code_memo = self.memo_data.get('is_code_memo', False)
        is_dark = self.is_dark_bg()
        rolled = self._is_rolled_up
        self._apply_icons(is_pinned, is_code_memo, is_dark, rolled)

        self.btn_min.setToolTip("펼치기 (Ctrl+M)" if rolled else "접기 (Ctrl+M)")
        self.btn_max.setVisible(not rolled)
        for code_only in (self.btn_format_code, self.btn_code_theme, self.code_lang_box, self.btn_lang_icon):
            code_only.setVisible(is_code_memo and not rolled)
        self.title_edit.setStyleSheet(self._title_color_stylesheet(12.0))

        if is_code_memo:
            self._apply_code_look()
        else:
            self._recolor_default_text(is_dark)

        font_family = self.memo_data.get(
            'font_family',
            self.memo_window_get_settings().get('default_font_family', 'D2Coding')
        )
        font = QFont(font_family, self.memo_data.get('font_size', 11))
        self.text_edit.setFont(font)

        self.title_edit.setText(self.memo_data.get('title',''))
        self.title_edit.setCursorPosition(0)
        self.title_edit.deselect()
        self.refresh_reminder_badge()
        self.refresh_progress()
        self.text_edit.refresh_check_marks()

        self._is_updating_from_explorer = True
        if refill:
            cnt = str(self.memo_data.get('content',''))
            self.text_edit.setHtml(cnt) if is_html_content(cnt) else self.text_edit.setPlainText(cnt)

        # 📌 불투명도 100% 기본값 적용 (사용자가 변경한 opacity 설정 유지)
        target_opacity = float(self.memo_data.get('opacity', 1.0))
        self.setWindowOpacity(target_opacity)

        self.apply_line_bg_style()
        self.text_edit.update_line_number_area()
        self._apply_seal_state()

        self._is_updating_from_explorer = False
        self._apply_place()

    def _apply_window_flags(self, is_pinned: bool) -> None:
        """창 종류와 '항상 위' 고정. 달라졌을 때만 바꿉니다. (바꾸면 창이 숨겨지므로 보이던 창은 다시 보임)"""
        target_flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool
        if is_pinned:
            target_flags |= Qt.WindowType.WindowStaysOnTopHint

        current_flags = self.windowFlags()
        if (current_flags & (Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)) != target_flags:
            was_visible = self.isVisible()
            self.setWindowFlags(target_flags)
            if was_visible:
                self.show()

    def _apply_icons(self, is_pinned: bool, is_code_memo: bool, is_dark: bool, rolled: bool) -> None:
        """아이콘 (바탕 밝기에 맞춘 색). 버튼·바탕의 모양은 apply_data() 끝에서 디자인 스타일이 입힙니다."""
        if getattr(self, 'ui_manager', None) and hasattr(self.ui_manager, 'get_theme_icon'):
            icon = self.ui_manager.get_theme_icon
            ink = "#FFFFFF" if is_dark else "#1C1C1E"
            self.btn_pin.setIcon(icon("pin_icon_True.svg" if is_pinned else "pin_icon_False.svg", is_dark, override_color=ink))
            self.btn_min.setIcon(icon("maximize.svg" if rolled else "rollup.svg", is_dark, override_color=ink))
            self.btn_max.setIcon(icon("maximize.svg", is_dark, override_color=ink))
            self.btn_close.setIcon(icon("close.svg", is_dark, override_color="#FF453A"))
            self.s_prev_btn.setIcon(icon("arrow left.svg", is_dark, override_color=ink))
            self.s_next_btn.setIcon(icon("arrow right.svg", is_dark, override_color=ink))
            self.btn_format_code.setIcon(icon("restart-icon.svg", is_dark))
            self.btn_bullet.setIcon(icon("bullet_icon_177745.svg", is_dark))
            self.btn_num.setIcon(icon("list_numbers_icon_172368.svg", is_dark))
            self.btn_indent.setIcon(icon("들여쓰기.svg", is_dark))
            self.btn_check.setIcon(modern_style.checkbox_icon(ink))
            self.btn_outdent.setIcon(icon("내어쓰기.svg", is_dark))
            if is_code_memo:
                code_is_dark = self.memo_data.get('code_theme', 'dark') == "dark"
                self.btn_code_theme.setIcon(icon("litemode.svg" if code_is_dark else "darkmod.svg", is_dark))
                self.btn_lang_icon.setIcon(icon("language.svg", is_dark, override_color="#FFFFFF" if is_dark else "#000000"))

    def _apply_code_look(self) -> None:
        """코드 메모: 테마 버튼 글자, 고른 언어, 구문 강조."""
        code_theme = self.memo_data.get('code_theme', 'dark')
        lang = self.memo_data.get('code_lang', 'JSON')
        self.btn_code_theme.setText(" 라이트" if code_theme == "dark" else " 다크")
        self.code_lang_box.blockSignals(True)
        self.code_lang_box.setCurrentText(lang)
        self.code_lang_box.blockSignals(False)
        self.highlighter = CodeHighlighter(self.text_edit.document(), lang, code_theme)
        self.highlighter.rehighlight()

    def _recolor_default_text(self, is_dark: bool) -> None:
        """바탕 밝기가 바뀌면 기본 글자색으로 쓴 글자만 새 기본색으로 바꿉니다. (직접 고른 색은 유지)"""
        text_c = self._memo_theme_palette()['text']
        old_colors = ["#000000", "#1C1C1E", "#333333"] if is_dark else ["#FFFFFF", "#F2F2F7", "#CCCCCC"]
        doc = self.text_edit.document()
        for i in range(doc.blockCount()):
            block = doc.findBlockByNumber(i)
            it = block.begin()
            while not it.atEnd():
                frag = it.fragment()
                fmt = frag.charFormat()
                if fmt.foreground().color().name().upper() in old_colors:
                    fmt.setForeground(QColor(text_c))
                    cursor = QTextCursor(block)
                    cursor.setPosition(frag.position())
                    cursor.setPosition(frag.position() + frag.length(), QTextCursor.MoveMode.KeepAnchor)
                    cursor.mergeCharFormat(fmt)
                it += 1

    def _apply_seal_state(self) -> None:
        """잠긴(또는 읽을 수 없는) 메모는 편집을 막고 안내 문구를 보여줍니다."""
        self.text_edit.setReadOnly(self.is_sealed())
        if self.memo_data.get('_locked'):
            self.text_edit.setPlaceholderText("")          # 잠긴 메모는 가림막이 본문 자리를 덮고 안내합니다.
        elif self.memo_data.get('_unreadable'):
            self.text_edit.setPlaceholderText("⚠ 본문을 복호화할 수 없는 메모입니다. (원본은 그대로 보존됩니다)")
        else:
            self.text_edit.setPlaceholderText("")
        self.lock_overlay.refresh()
        self.refresh_lock_badge()

    def _apply_place(self) -> None:
        """창의 자리와 크기, 접힌 상태."""
        is_rolled = getattr(self, '_is_rolled_up', False) or self.memo_data.get('is_rolled_up', False)
        was_rolled = getattr(self, '_is_rolled_up', False)
        rolled_h = self._get_rolled_height()            # settings의 default_rolled_height를 우선 적용
        if is_rolled:
            self.memo_data['rolled_height'] = rolled_h
        # 이미 보이는 창은 지금 자리를 지키고, 숨어 있던 창은 고정해 둔 자리나 마지막 자리로 갑니다. (잠긴 메모는 암호 입력용 크기로)
        x, y, target_w, target_h = memo_geometry.show_target(
            self.memo_data, is_rolled, self.isVisible(), (self.x(), self.y()), rolled_h, self._pinned(is_rolled),
            getattr(self, '_normal_height', 300))
        x, y = self._clamp_to_screen(self._screen_area_for(x, y, target_w, target_h), x, y, target_w, target_h)
        self._apply_fold_state(is_rolled, x, y, target_w, target_h)

    def change_color(self, c: str) -> None:
        self.memo_data['bg_color'] = c
        self.apply_look()
        self.show()
        if hasattr(self, 'bg'):
            self.bg.style().unpolish(self.bg)
            self.bg.style().polish(self.bg)
            self.bg.update()
            self.bg.repaint()
        self.update()
        self.repaint()
        self.text_edit.viewport().update()
        self.text_edit.viewport().repaint()
        self.save_callback(self.memo_data)
        if getattr(self, 'ui_manager', None) and self.ui_manager.explorer_window and self.ui_manager.explorer_window.isVisible():
            self.ui_manager.explorer_window.update_table()
