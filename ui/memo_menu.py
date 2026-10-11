"""메모 창의 우클릭 메뉴와 거기서 부르는 편의 기능 (한영 변환, 전체 복사).

(MemoWindow 에 섞어 쓰는 부분)
"""
from ui import modern_style, themed_dialog
from core import reminders
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QMenu, QApplication, QLabel, QSlider, QWidgetAction
from PyQt6.QtCore import Qt, QPoint
from utils.text_utils import convert_eng_kor_smart
from utils.text_utils import clean_plain_text


class MemoMenuMixin:
    """메모 창의 우클릭 메뉴."""

    def request_delete(self) -> None:
        """메모를 휴지통으로 보냅니다. (단축키·우클릭 메뉴)

        탐색기에서 지울 때와 같게, 삭제 방지를 건 메모는 지우지 않고 내용이 있는 메모는 먼저 묻습니다.
        아무것도 적지 않은 메모는 묻지 않고 지웁니다.
        """
        if self.memo_data.get('is_protected'):
            self.show_toast("🔒 삭제 방지 설정된 메모입니다.", warn=True)
            return
        has_content = (self.is_sealed() or bool(self.memo_data.get('is_locked'))
                       or bool(clean_plain_text(self.current_content()).strip()))
        title = str(self.memo_data.get('title', '')) or "(제목 없음)"
        if has_content and not themed_dialog.confirm(self, "삭제", f"'{title}' 메모를 휴지통으로 이동할까요?",
                                                     ok_text="삭제", danger=True):
            return
        self.delete_callback(self)

    def show_menu(self, pos: QPoint) -> None:
        menu = QMenu(self)
        menu.setStyleSheet(modern_style.menu_qss(self.memo_window_get_settings()))

        s = self.memo_window_get_settings()
        sc = s.get("shortcuts", {})
        def _fmt_sc(title: str, key: str, default: str) -> str:
            val = sc.get(key, default)
            return f"{title} ({val})" if val else title

        sender_widget = self.sender()
        if hasattr(sender_widget, 'copy'):
            menu.addAction("복사 (Ctrl+C)").triggered.connect(sender_widget.copy)
            menu.addAction("잘라내기 (Ctrl+X)").triggered.connect(sender_widget.cut)
            menu.addAction("붙여넣기 (Ctrl+V)").triggered.connect(sender_widget.paste)
            menu.addAction("모두 선택 (Ctrl+A)").triggered.connect(sender_widget.selectAll)
            menu.addSeparator()

        is_code = self.memo_data.get('is_code_memo', False)
        if is_code:
            menu.addAction(_fmt_sc("코드 자동 정렬", "format_code", "Ctrl+Shift+F")).triggered.connect(self.prettify_code)
            menu.addAction("코드만 클립보드 복사").triggered.connect(self.copy_all_content)
            menu.addAction(_fmt_sc("코드 테마 전환", "toggle_code_theme", "Ctrl+Shift+L")).triggered.connect(self.toggle_code_theme)
        else:
            menu.addAction(_fmt_sc("전체 메모 내용 복사 (클립보드)", "copy_all", "Ctrl+Shift+C")).triggered.connect(self.copy_all_content)

        menu.addAction(_fmt_sc("한/영 영타 오타 변환", "eng_kor_convert", "Ctrl+Alt+E")).triggered.connect(self.convert_selected_eng_kor)

        menu.addSeparator()

        is_auto_convert = s.get("auto_eng_kor_convert", True)
        auto_convert_action = menu.addAction(f"한/영 자동 변환기 [{ 'ON' if is_auto_convert else 'OFF' }]")
        auto_convert_action.setCheckable(True)
        auto_convert_action.setChecked(is_auto_convert)
        auto_convert_action.triggered.connect(self.toggle_auto_eng_kor_setting)

        menu.addSeparator()
        menu.addAction(_fmt_sc("메모 탐색기 열기", "open_explorer", "Ctrl+E")).triggered.connect(self.ui_manager.open_memo_explorer)
        menu.addAction(_fmt_sc("저장", "save", "Ctrl+S")).triggered.connect(self.manual_save)
        menu.addAction(_fmt_sc("검색", "search", "Ctrl+F")).triggered.connect(self.show_search_only)
        menu.addAction(_fmt_sc("바꾸기", "replace", "Ctrl+H")).triggered.connect(self.show_search_and_replace)
        menu.addAction(_fmt_sc("화면 고정 토글", "toggle_pin", "Ctrl+P")).triggered.connect(self.toggle_pin)
        menu.addAction(_fmt_sc("메모 창 접기", "toggle_rollup", "Ctrl+M")).triggered.connect(self.toggle_rollup)

        ln_action = menu.addAction("행번호 표시")
        ln_action.setCheckable(True)
        ln_action.setChecked(self.memo_data.get('show_line_numbers', False))
        ln_action.triggered.connect(self.toggle_line_numbers)

        bg_action = menu.addAction("줄노트 배경")
        bg_action.setCheckable(True)
        bg_action.setChecked(self.memo_data.get('show_line_bg', False))
        bg_action.triggered.connect(self.toggle_line_bg)

        if not is_code:
            menu.addSeparator()
            cm = menu.addMenu("창 배경색 변경")
            for n, c in {"다크그레이": "#2E3440", "하늘색": "#E0F2FE", "연두색": "#DCFCE7", "노란색": "#FEF9C3", "분홍색": "#FCE7F3", "흰색": "#FFFFFF"}.items():
                cm.addAction(n).triggered.connect(lambda checked, code=c: self.change_color(code))

        menu.addSeparator()
        menu.addAction(_fmt_sc("체크리스트 켜기/끄기", "toggle_checklist", "Alt+K")).triggered.connect(self.toggle_checklist)
        has_reminder = bool(reminders.normalize(self.memo_data.get('reminder')))
        menu.addAction(_fmt_sc("⏰ 알림 바꾸기…" if has_reminder else "⏰ 알림 설정…", "set_reminder", "Ctrl+R")).triggered.connect(self.edit_reminder)
        menu.addAction(_fmt_sc("이전 내용 보기…", "show_history", "Ctrl+Shift+H")).triggered.connect(self.show_history)

        menu.addSeparator()
        if self.memo_data.get('_locked'):
            menu.addAction("🔓 잠금 해제 (암호 입력)").triggered.connect(self.prompt_unlock)
            sm_lock = self._sync_manager()
            if sm_lock and sm_lock.memo_has_master_recovery(self.memo_data.get('id', '')):
                menu.addAction("관리자 키로 복구…").triggered.connect(self.recover_with_master_key)
        elif self.memo_data.get('is_locked'):
            menu.addAction("🔒 지금 잠그기").triggered.connect(self.lock_now)
            menu.addAction("암호 변경").triggered.connect(self.set_memo_password)
            menu.addAction("암호 제거 (일반 메모로)").triggered.connect(self.remove_memo_password)
        elif not self.memo_data.get('_unreadable'):
            menu.addAction("🔒 이 메모에 암호 걸기").triggered.connect(self.set_memo_password)

        menu.addSeparator()
        # 🔆 투명도 슬라이더 서브메뉴
        opacity_menu = menu.addMenu("창 투명도 조절")
        opacity_widget = QWidget()
        opacity_layout = QHBoxLayout(opacity_widget)
        opacity_layout.setContentsMargins(12, 6, 12, 6)
        opacity_layout.setSpacing(8)
        cur_opacity_pct = int(round(float(self.memo_data.get('opacity', 1.0)) * 100))
        opa_label = QLabel(f"불투명도: {cur_opacity_pct}%")
        opa_label.setStyleSheet("color: #007AFF; font-weight: bold; font-size: 9pt; min-width: 90px;")
        opa_slider = QSlider(Qt.Orientation.Horizontal)
        opa_slider.setRange(20, 100)
        opa_slider.setValue(cur_opacity_pct)
        opa_slider.setFixedWidth(160)
        opa_slider.setStyleSheet("""
            QSlider::groove:horizontal { height: 4px; background: #C7C7CC; }
            QSlider::handle:horizontal { width: 12px; height: 18px; margin: -7px 0; background: #007AFF; }
            QSlider::sub-page:horizontal { background: #007AFF; }
        """)
        def _update_opacity(val: int) -> None:
            opa_label.setText(f"불투명도: {val}%")
            self.memo_data['opacity'] = round(val / 100.0, 2)
            self.setWindowOpacity(self.memo_data['opacity'])
            self._schedule_auto_save()
        opa_slider.valueChanged.connect(_update_opacity)
        opacity_layout.addWidget(opa_label)
        opacity_layout.addWidget(opa_slider)
        opa_action = QWidgetAction(opacity_menu)
        opa_action.setDefaultWidget(opacity_widget)
        opacity_menu.addAction(opa_action)
        opacity_menu.addSeparator()
        opacity_menu.addAction("100% (완전 불투명)").triggered.connect(lambda: opa_slider.setValue(100))
        opacity_menu.addAction("80% (약간 투명)").triggered.connect(lambda: opa_slider.setValue(80))
        opacity_menu.addAction("60% (반투명)").triggered.connect(lambda: opa_slider.setValue(60))
        opacity_menu.addAction("40% (많이 투명)").triggered.connect(lambda: opa_slider.setValue(40))

        menu.addSeparator()
        menu.addAction(_fmt_sc("메모 삭제", "delete_memo", "Alt+D")).triggered.connect(self.request_delete)
        menu.exec(self.sender().mapToGlobal(pos))

    def toggle_auto_eng_kor_setting(self) -> None:
        sm = getattr(self.close_callback, '__self__', None).sync_manager
        cur = sm.settings.get("auto_eng_kor_convert", True)
        sm.settings["auto_eng_kor_convert"] = not cur
        sm.save_settings(sm.settings)
        self.show_toast(f"🔤 한/영 자동 변환기: {'ON' if not cur else 'OFF'}")

    def convert_selected_eng_kor(self) -> None:
        cursor = self.text_edit.textCursor()
        if cursor.hasSelection():
            txt = cursor.selectedText()
            converted = convert_eng_kor_smart(txt)
            cursor.insertText(converted)
        else:
            txt = self.text_edit.toPlainText()
            converted = convert_eng_kor_smart(txt)
            self.text_edit.setPlainText(converted)
            self.text_edit.document().setModified(True)      # 본문을 바꾼 것이므로 '고침'으로 표시
        self._mark_edited()
        self.show_toast("🔤 한/영 영타 변환 완료")

    def copy_all_content(self) -> None:
        if self.memo_data.get('is_code_memo', False):
            plain_text = self.text_edit.toPlainText()
        else:
            plain_text = clean_plain_text(self.text_edit.toHtml())
        cb = QApplication.clipboard()
        cb.setText(plain_text)
        self.show_toast("📋 클립보드에 복사되었습니다.")
