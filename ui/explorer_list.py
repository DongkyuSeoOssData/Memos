"""메모 탐색기의 목록: 메모를 읽어 고르고(폴더·종류·검색·태그) 정렬해 표에 채우기, 쪽 넘기기.

(MemoExplorerWindow 에 섞어 쓰는 부분)
"""
from core import reminders
from ui import checklist
from ui import modern_style
from core import folders
import datetime
from typing import Dict, Any
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QTableWidgetItem
from PyQt6.QtCore import Qt, QSize, pyqtSlot
from PyQt6.QtGui import QFont
from utils.text_utils import clean_plain_text, extract_hashtags


class ExplorerListMixin:
    """탐색기의 목록."""

    def set_filter_mode(self, mode: str) -> None:
        self.filter_mode = mode
        self.update_filter_buttons()
        self.current_page = 1
        self.refresh()

    def update_filter_buttons(self) -> None:
        modern_style.apply_explorer_filters(self)

    def on_cell_double_click(self, r: int, c: int) -> None:
        if not self.is_trash_mode:
            m_item = self.table.item(r, 2)
            if m_item:
                m = m_item.data(Qt.ItemDataRole.UserRole)
                if m:
                    memo_id = m.get('id')
                    if memo_id:
                        # id가 있으면 반드시 id로만 열기 (title 폴백 없음)
                        self.ui_manager.show_specific_memo(memo_id)
                    else:
                        self.ui_manager.show_specific_memo(m.get('title', ''))

    def update_btns_visibility(self) -> None:
        while self.btn_l.count():
            wi = self.btn_l.takeAt(0).widget()
            if wi:
                wi.setParent(None)
        if not self.is_trash_mode:
            self.btn_l.addWidget(self.b_new)
            self.btn_l.addWidget(self.b_new_code)
            self.btn_l.addWidget(self.b_ref)
            self.btn_l.addWidget(self.b_sync)
            self.btn_l.addStretch()
            self.btn_l.addWidget(self.b_del)
        else:
            self.btn_l.addWidget(self.b_ref)
            self.btn_l.addWidget(self.b_res)
            self.btn_l.addWidget(self.b_empty_trash)
            self.btn_l.addStretch()
        # 레이아웃 후 다시 텍스트/아이콘 상태 원상 복원
        self._refresh_btn_labels()

    def on_search(self) -> None:
        self.current_page = 1
        self.refresh()

    def go_prev(self) -> None:
        if self.current_page > 1:
            self.current_page -= 1
            self.update_table()

    def go_next(self) -> None:
        total_pages = max(1, (len(self.filtered_memos) + 9) // 10)
        if self.current_page < total_pages:
            self.current_page += 1
            self.update_table()

    @pyqtSlot()
    def refresh(self) -> None:
        self._flush_preview_save()
        q = self.s_in.text().lower()
        sb = self.s_type.currentIndex() == 1
        all_m = self.ui_manager.sync_manager.load_trash_memos() if self.is_trash_mode else self.ui_manager.sync_manager.load_local_memos()
        if not self.is_trash_mode:
            # 폴더를 먼저 걸러 두면 아래의 개수·해시태그·검색이 모두 그 폴더 안에서만 동작합니다.
            self._rebuild_folder_ui(all_m)
            all_m = [m for m in all_m if folders.contains(self.current_folder, folders.folder_of(m))]

        # 메모마다 본문 정리와 태그 추출은 한 번만 합니다. (아래 필터에서 다시 씀)
        # 코드 메모의 '#include', '#region' 같은 것은 태그가 아니므로 일반 메모에서만 태그를 찾습니다.
        hashtags = set()
        gen_cnt = 0
        code_cnt = 0
        digest: Dict[int, tuple] = {}
        # 본문이 그대로인 메모는 지난번에 정리해 둔 것을 씁니다. (메모가 많을 때 목록을 다시 그리는 시간을 줄임)
        # 암호 메모는 푼 내용을 여기에 남겨 두지 않도록 매번 새로 정리합니다.
        remembered = getattr(self, '_digest_cache', {})
        self._digest_cache = {}
        for m in all_m:
            content = m.get('content', '')
            is_code = bool(m.get('is_code_memo'))
            reusable = isinstance(content, str) and not m.get('is_locked')
            key = (content, is_code)
            found = remembered.get(key) if reusable else None
            if found is None:
                plain = clean_plain_text(content)
                found = (plain, [] if is_code else extract_hashtags(plain))
            if reusable:
                self._digest_cache[key] = found
            plain, tags = found
            if is_code:
                code_cnt += 1
            else:
                gen_cnt += 1
            digest[id(m)] = (plain, tags)
            hashtags.update(tags)

        self.stat_label.setText(f"총 {len(all_m)}개 메모 (일반: {gen_cnt}개 | 코드: {code_cnt}개)")
        if hasattr(self.ui_manager, 'get_theme_icon'):
            self.stat_icon.setPixmap(self.ui_manager.get_theme_icon("total.svg", False, override_color="#8E8E93").pixmap(16, 16))

        cur_tag = self.tag_combo.currentText()
        self.tag_combo.blockSignals(True)
        self.tag_combo.clear()
        self.tag_combo.addItem("#")

        max_len = 1  # 기본 '#' 기준 최소 길이
        for tag in sorted(hashtags):
            tag_str = f"#{tag}"
            self.tag_combo.addItem(tag_str)
            if len(tag_str) > max_len:
                max_len = len(tag_str)

        self.tag_combo.setCurrentText(cur_tag if cur_tag in [self.tag_combo.itemText(i) for i in range(self.tag_combo.count())] else "#")

        # 💡 동적 너비 계산 로직 추가: 폰트 사이즈(pt) 기준 대략적인 픽셀 계산 + 최소 너비 보장 (예: 기본 100px, 글자당 8px 추가)
        dynamic_width = max(100, max_len * 9 + 30)

        view = self.tag_combo.view()
        if view:
            # 드롭다운 리스트 내부는 유동적으로 너비가 넓어지게 하되, 메인 버튼은 위에서 고정함
            view.setMinimumWidth(dynamic_width)

        self.tag_combo.blockSignals(False)

        selected_tag = self.tag_combo.currentText()
        tag_filter = "" if selected_tag == "#" else selected_tag

        all_m.sort(key=lambda x: (x.get('is_favorite', False), x.get('updated_at', '')), reverse=True)

        filtered = []
        for m in all_m:
            is_code = m.get('is_code_memo', False)
            if self.filter_mode == "GENERAL" and is_code: continue
            if self.filter_mode == "CODE" and not is_code: continue

            plain_cnt, tags = digest[id(m)]
            if tag_filter and tag_filter[1:] not in tags:
                continue
            if q:
                if sb and q not in plain_cnt.lower(): continue
                if not sb and q not in m.get('title','').lower(): continue
            filtered.append(m)

        self.filtered_memos = filtered
        self.update_table()
        self.update_btns_visibility()
        # 폴더 탭 줄·글자 크기에 따라 필요한 크기가 달라지므로, 화면을 다시 채운 뒤 최소 크기를 맞춥니다.
        if not self.is_size_fixed() and not self.isMaximized():
            self._apply_minimum_size()

    def update_table(self) -> None:
        # 동기화가 끝나거나 열어 둔 메모가 저장되어 목록이 다시 그려져도, 체크해 둔 것은 그대로 둡니다.
        self._remember_checked()
        self.table.setRowCount(0)
        row_h = max(38, int(self.ui_font_pt * 3.2))
        items = self.filtered_memos[(self.current_page - 1) * 10 : self.current_page * 10]
        for m in items:
            r = self.table.rowCount()
            self.table.insertRow(r)
            self.table.setRowHeight(r, row_h)

            c = QTableWidgetItem("")
            c.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            c.setCheckState(Qt.CheckState.Checked if m.get('id') in self._checked_ids else Qt.CheckState.Unchecked)
            self.table.setItem(r, 0, c)

            if not self.is_trash_mode:
                is_fav = m.get('is_favorite', False)
                fb = QPushButton()
                fb.setFixedSize(30, 30)
                fb.setCursor(Qt.CursorShape.PointingHandCursor)
                fb.setToolTip("즐겨찾기 해제" if is_fav else "즐겨찾기 등록")
                fb.setIcon(self.favorite_icon(is_fav))
                fb.setIconSize(QSize(20, 20))
                fb.setStyleSheet("border: none; background: transparent;")
                fb.clicked.connect(lambda checked, memo=m: self.toggle_fav(memo))
                cell_w = QWidget()
                cell_l = QHBoxLayout(cell_w)
                cell_l.addWidget(fb)
                cell_l.setAlignment(Qt.AlignmentFlag.AlignCenter)
                cell_l.setContentsMargins(0, 0, 0, 0)
                self.table.setCellWidget(r, 1, cell_w)
            else:
                self.table.setCellWidget(r, 1, QWidget())

            is_code = m.get('is_code_memo', False)
            title_text = m.get('title', '').strip()
            theme = self.ui_manager.sync_manager.settings.get('app_theme', 'white')
            is_dark = (theme == "dark")

            is_pinned = m.get('is_pinned', False)

            if is_code:
                lang = m.get('code_lang', 'JSON')
                badge_text = f"[{lang}] {title_text}"
            else:
                badge_text = f"{title_text}"
            if m.get('is_locked'):
                badge_text = f"🔒 {badge_text}"
            reminder_text = reminders.describe(m.get('reminder'))
            if reminder_text:
                badge_text = f"⏰ {badge_text}"
            raw_content = m.get('content', '')
            # 암호 메모는 열려 있든 잠겨 있든 진행 표시를 내지 않습니다. (잠그고 풀 때마다 나타났다 사라지지 않게, 내용도 드러나지 않게)
            if isinstance(raw_content, str) and checklist.has_boxes(raw_content) and not (m.get('is_locked') or m.get('_locked') or m.get('_unreadable')):
                progress = checklist.progress_label(clean_plain_text(raw_content))
                if progress:
                    badge_text = f"{badge_text}  {progress}"       # 남은 일이 있으면 ☐, 다 끝냈으면 ☑

            t = QTableWidgetItem(badge_text)
            if reminder_text:
                t.setToolTip("알림: " + reminder_text)
            if hasattr(self.ui_manager, 'get_theme_icon'):
                if is_pinned:
                    t.setIcon(self.ui_manager.get_theme_icon("pin_icon_True.svg", is_dark))
                else:
                    t.setIcon(self.ui_manager.get_theme_icon("codememo.svg" if is_code else "memo.svg", is_dark))
            t.setData(Qt.ItemDataRole.UserRole, m)
            t.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)

            if is_code:
                t.setFont(QFont("D2Coding", 10, QFont.Weight.Bold))

            self.table.setItem(r, 2, t)

            up = m.get('updated_at', '')
            try:
                ds = datetime.datetime.fromisoformat(up).strftime("%y%m%d.%H%M") if up else ""
            except (TypeError, ValueError):
                # 수정시각이 깨진 메모 하나 때문에 목록 전체가 멈추지 않도록 함
                ds = ""
            dt = QTableWidgetItem(ds)
            dt.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
            self.table.setItem(r, 3, dt)

            is_prot = m.get('is_protected', False)
            prot_btn = QPushButton("잠김" if is_prot else "해제")
            if hasattr(self.ui_manager, 'get_theme_icon'):
                prot_btn.setIcon(self.ui_manager.get_theme_icon("lock_close.svg" if is_prot else "lock_open.svg", is_dark))
            prot_btn.setFixedSize(50, 28)
            prot_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            prot_btn.clicked.connect(lambda checked, memo=m: self.toggle_protect(memo))

            cell_p_w = QWidget()
            cell_p_l = QHBoxLayout(cell_p_w)
            cell_p_l.addWidget(prot_btn)
            cell_p_l.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cell_p_l.setContentsMargins(0, 0, 0, 0)
            self.table.setCellWidget(r, 4, cell_p_w)

        self.p_l.setText(f"{self.current_page} / {max(1, (len(self.filtered_memos) + 9) // 10)}")
        self.shortcut_font_refresh()
        modern_style.apply_explorer_table(self)

    def toggle_fav(self, memo: Dict[str, Any]) -> None:
        self._save_memo_meta(memo, is_favorite=not memo.get('is_favorite', False))
        self.refresh()
