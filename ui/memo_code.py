"""코드 메모: 코드 테마 전환, 언어 고르기, 코드 자동 정렬.

(MemoWindow 에 섞어 쓰는 부분)
"""
from ui.memo_editor import CodeHighlighter
import json
from PyQt6.QtGui import QColor, QTextCursor, QTextCharFormat


class MemoCodeMixin:
    """코드 메모의 기능."""

    def toggle_code_theme(self) -> None:
        """코드 테마 사용자 수동 전환"""
        self.memo_data['content'] = self.current_content()
        cur = self.memo_data.get('code_theme',
              'dark' if self.memo_window_get_settings().get('app_theme', 'white') == 'dark' else 'light')
        new_theme = "light" if cur == "dark" else "dark"
        self.memo_data['code_theme'] = new_theme
        self.memo_data['code_theme_user_set'] = True
        self.apply_look()
        self.update()
        self.repaint()
        self.text_edit.viewport().update()
        self._mark_edited()

    def on_code_lang_changed(self, lang: str) -> None:
        self.memo_data['code_lang'] = lang
        theme = self.memo_data.get('code_theme', 'dark')
        self.highlighter = CodeHighlighter(self.text_edit.document(), lang, theme)
        self._mark_edited()

    def prettify_code(self) -> None:
        """JSON / 기타 코드 자동 정렬 — 정렬 후 하이라이터 및 글씨색 강제 재적용."""
        raw_code = self.text_edit.toPlainText().strip()
        if not raw_code:
            return
        lang = self.memo_data.get('code_lang', 'JSON').upper()
        code_theme = self.memo_data.get('code_theme', 'dark')
        code_text = "#F2F2F7" if code_theme == "dark" else "#1C1C1E"

        def _apply_after_format(formatted: str) -> None:
            """setPlainText 적용 후 하이라이터 및 글씨색 복원."""
            self.text_edit.setPlainText(formatted)
            self.text_edit.document().setModified(True)      # 본문을 바꾼 것이므로 '고침'으로 표시
            # 하이라이터 재적용
            self.highlighter = CodeHighlighter(self.text_edit.document(), lang, code_theme)
            # 전체 글씨새 재적용
            cursor = self.text_edit.textCursor()
            cursor.select(QTextCursor.SelectionType.Document)
            base_fmt = QTextCharFormat()
            base_fmt.setForeground(QColor(code_text))
            cursor.mergeCharFormat(base_fmt)
            self._mark_edited()

        if "JSON" in lang:
            try:
                parsed = json.loads(raw_code)
                formatted = json.dumps(parsed, indent=2, ensure_ascii=False)
                _apply_after_format(formatted)
                self.show_toast("✨ JSON 코드 자동 정렬 완료")
                return
            except Exception:
                self.show_toast("⚠️ JSON 구문 오류 (정렬 안 됨)")
                return

        lines = raw_code.splitlines()
        formatted_lines: list = []
        indent = 0
        for line in lines:
            stripped = line.strip()
            if stripped.startswith('}') or stripped.startswith(']'):
                indent = max(0, indent - 1)
            formatted_lines.append("  " * indent + stripped)
            if stripped.endswith('{') or stripped.endswith('['):
                indent += 1

        _apply_after_format("\n".join(formatted_lines))
        self.show_toast("✨ 코드 인덴트 정렬 완료")
