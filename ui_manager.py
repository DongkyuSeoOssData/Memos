from typing import List, Dict, Any, Optional
import datetime
import sys
import re
import random
from pathlib import Path

from PyQt6.QtWidgets import (QWidget, QTextEdit, QVBoxLayout, QHBoxLayout, QPushButton, 
                             QLineEdit, QMenu, QSystemTrayIcon, QApplication, QMessageBox, 
                             QLabel, QComboBox, QCheckBox, QFileDialog, QTableWidget, 
                             QTableWidgetItem, QHeaderView, QDialog, QDialogButtonBox,
                             QGraphicsDropShadowEffect, QFrame, QSizeGrip)
from PyQt6.QtCore import Qt, QPoint, QSize, QTimer, QEvent, QRect
from PyQt6.QtGui import QIcon, QAction, QColor, QShortcut, QKeySequence, QFont, QPixmap, QPainter, QTextListFormat, QTextCursor, QTextCharFormat

class ConflictDialog(QDialog):
    def __init__(self, title: str, cur_c: str, trash_c: str):
        super().__init__(); self.setWindowTitle("복구 중복 확인"); self.setFixedSize(600, 450)
        self.setStyleSheet("background-color: white; color: #000000; font-family: 'Malgun Gothic', sans-serif;")
        layout = QVBoxLayout(self); layout.addWidget(QLabel(f"<b style='color:#000000; font-size:11pt;'>'{title}'</b>이(가) 존재합니다. 덮어쓰시겠습니까?"))
        diff = QHBoxLayout()
        for l, c in [("[현재 로컬]", cur_c), ("[휴지통]", trash_c)]:
            box = QVBoxLayout(); box.addWidget(QLabel(f"<b>{l}</b>")); te = QTextEdit(); te.setPlainText(c); te.setReadOnly(True); te.setStyleSheet("border: 1px solid #E2E8F0; border-radius: 6px; padding: 5px; color: #000000;"); box.addWidget(te); diff.addLayout(box)
        layout.addLayout(diff)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Yes | QDialogButtonBox.StandardButton.No)
        btns.accepted.connect(self.accept); btns.rejected.connect(self.reject); layout.addWidget(btns)

class MemoExplorerWindow(QWidget):
    def __init__(self, ui_manager: Any):
        super().__init__(); self.ui_manager = ui_manager; self.current_page = 1; self.items_per_page = 10; self.filtered_memos = []; self.is_trash_mode = False; self._old_pos = None
        self._is_loading_preview = False
        self.init_ui()
    
    def apply_text_stroke(self, widget):
        eff = QGraphicsDropShadowEffect()
        eff.setBlurRadius(3)
        eff.setColor(QColor(255, 255, 255, 255))
        eff.setOffset(0, 0)
        widget.setGraphicsEffect(eff)
    
    def init_ui(self) -> None:
        self.setWindowTitle("메모 탐색기")
        geom = self.ui_manager.sync_manager.settings.get('explorer_geom')
        if geom and len(geom) == 4:
            self.setGeometry(geom[0], geom[1], geom[2], geom[3])
        else:
            self.resize(900, 750)
            
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | 
            Qt.WindowType.WindowStaysOnTopHint | 
            Qt.WindowType.WindowSystemMenuHint | 
            Qt.WindowType.WindowMinimizeButtonHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        main_l = QVBoxLayout(self); main_l.setContentsMargins(15, 15, 15, 15)
        
        self.bg = QFrame(); self.bg.setObjectName("ExplorerBg")
        self.bg.setStyleSheet("""
            QFrame#ExplorerBg { background-color: #F8FAFC; border: 1px solid #CBD5E1; border-radius: 16px; } 
            QLabel { color: #000000; font-family: 'Pretendard', 'Malgun Gothic', sans-serif; } 
            QPushButton { font-family: 'Pretendard', 'Malgun Gothic', sans-serif; color: #000000; } 
            QLineEdit, QComboBox { padding: 8px 12px; border: 1px solid #CBD5E1; border-radius: 6px; color: #000000; background-color: white; }
            QLineEdit:focus, QComboBox:focus { border: 1px solid #38BDF8; }
        """)
        bg_l = QVBoxLayout(self.bg); bg_l.setContentsMargins(20, 20, 20, 20); main_l.addWidget(self.bg)
        
        ctrl = QHBoxLayout(); title_l = QLabel("📄 <b>Memos Explorer</b>"); title_l.setStyleSheet("font-size: 13pt; border: none; color: #000000;")
        
        self.toast = QLabel("")
        self.toast.setStyleSheet("color: #2563EB; font-weight: bold; font-size: 11pt; margin-left: 15px;")
        self.toast.hide()

        self.btn_pin = QPushButton("⚲"); self.btn_min = QPushButton("_"); self.btn_max = QPushButton("□"); self.btn_close = QPushButton("✕")
        for b in [self.btn_pin, self.btn_min, self.btn_max, self.btn_close]:
            b.setFixedSize(32, 32)
            b.setStyleSheet("QPushButton { border: none; color: #000000; background: transparent; font-weight: bold; font-size: 14pt; } QPushButton:hover { background-color: #E2E8F0; border-radius: 6px; }")
            self.apply_text_stroke(b)
        
        self.btn_pin.setCheckable(True)
        self.btn_pin.setChecked(True)
        self.btn_pin.setStyleSheet("QPushButton { border: none; color: #2563EB; background: transparent; font-weight: bold; font-size: 14pt; }")
        
        self.btn_pin.clicked.connect(self.toggle_pin); self.btn_min.clicked.connect(self.showMinimized); self.btn_max.clicked.connect(self.toggle_max); self.btn_close.clicked.connect(self.close)
        
        ctrl.addWidget(title_l)
        ctrl.addWidget(self.toast)
        ctrl.addStretch()
        ctrl.addWidget(self.btn_pin); ctrl.addWidget(self.btn_min); ctrl.addWidget(self.btn_max); ctrl.addWidget(self.btn_close)
        bg_l.addLayout(ctrl)

        sh_l = QHBoxLayout(); self.s_type = QComboBox(); self.s_type.addItems(["제목 검색", "본문 검색"]); self.s_in = QLineEdit(); self.s_in.setPlaceholderText("검색어를 입력해 주세요...")
        self.s_in.textChanged.connect(self.on_search); self.t_btn = QPushButton("ⓧ 휴지통 보기"); self.t_btn.setCheckable(True); self.t_btn.clicked.connect(self.toggle_trash)
        self.t_btn.setStyleSheet("QPushButton { padding: 8px 16px; background-color: white; border: 1px solid #CBD5E1; border-radius: 6px; color: #000000; font-weight: bold; } QPushButton:checked { background-color: #F1F5F9; color: #000000; }")
        sh_l.addWidget(self.s_type); sh_l.addWidget(self.s_in); sh_l.addWidget(self.t_btn); bg_l.addLayout(sh_l)
        
        self.table = QTableWidget(0, 4); self.table.setHorizontalHeaderLabels(["선택", "★", "제 목", "수정일시"])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows); self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setShowGrid(False); self.table.cellClicked.connect(self.on_cell_click); self.table.cellDoubleClicked.connect(self.on_cell_double_click)
        self.table.setTextElideMode(Qt.TextElideMode.ElideRight)
        
        self.table.setStyleSheet("""
            QTableWidget { border: 1px solid #E2E8F0; border-radius: 8px; background-color: white; color: #000000; outline: none; } 
            QTableWidget::item { border-bottom: 1px solid #F1F5F9; color: #000000; } 
            QTableWidget::item:selected { background-color: #AED6F1; color: #000000; } 
            QHeaderView::section { background-color: white; color: #000000; font-weight: bold; border: none; border-bottom: 2px solid #AED6F1; padding: 10px; }
            QTableWidget::indicator { width: 16px; height: 16px; margin-left: 17px; }
            QTableCornerButton::section { background-color: white; border: none; }
        """)
        self.table.setFocusPolicy(Qt.FocusPolicy.NoFocus) 
        
        self.table.verticalHeader().setStyleSheet("""
            QHeaderView { background-color: white; border: none; }
            QHeaderView::section { background-color: white; border: none; color: #000000; font-weight: bold; padding-left: 10px; border-bottom: 1px solid #F1F5F9; }
        """)
        
        h = self.table.horizontalHeader(); h.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed); self.table.setColumnWidth(0, 50)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed); self.table.setColumnWidth(1, 50)
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch); h.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents); h.sectionClicked.connect(self.on_header_click); bg_l.addWidget(self.table)
        
        pg_l = QHBoxLayout(); self.p_b = QPushButton("❮"); self.p_b.setFixedSize(30, 30); self.p_b.clicked.connect(self.go_prev)
        self.p_l = QLabel("1 / 1"); self.p_l.setStyleSheet("font-weight: bold; color: #000000; margin: 0 15px;")
        self.n_b = QPushButton("❯"); self.n_b.setFixedSize(30, 30); self.n_b.clicked.connect(self.go_next)
        for b in [self.p_b, self.n_b]: b.setStyleSheet("QPushButton { border: none; color: #000000; font-weight: bold; } QPushButton:hover { background-color: #E2E8F0; border-radius: 15px; }")
        pg_l.addStretch(); pg_l.addWidget(self.p_b); pg_l.addWidget(self.p_l); pg_l.addWidget(self.n_b); pg_l.addStretch(); bg_l.addLayout(pg_l)
        
        bg_l.addWidget(QLabel("<b>📄 본문 미리보기 및 빠른 수정</b>")); self.pv = QTextEdit(); self.pv.setFixedHeight(110)
        self.pv.setReadOnly(False) 
        self.pv.setStyleSheet("background-color: white; border: 1px solid #E2E8F0; border-radius: 8px; padding: 12px; color: #000000; font-size: 10pt;"); bg_l.addWidget(self.pv)
        self.pv.textChanged.connect(self.on_preview_changed)
        
        self.btn_box = QWidget(); self.btn_l = QHBoxLayout(self.btn_box); self.btn_l.setContentsMargins(0, 15, 0, 0); bg_l.addWidget(self.btn_box); self.setup_btns(); self.refresh()
        
        self.grip = QSizeGrip(self)
        
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.grip.move(self.width() - 35, self.height() - 35)
        self.grip.resize(16, 16)

    def closeEvent(self, event):
        geom = [self.x(), self.y(), self.width(), self.height()]
        self.ui_manager.sync_manager.settings['explorer_geom'] = geom
        self.ui_manager.sync_manager.save_settings(self.ui_manager.sync_manager.settings)
        super().closeEvent(event)

    def show_toast(self, m: str): 
        self.toast.setText(f"✓ {m}")
        self.toast.show()
        QTimer.singleShot(3500, self.toast.hide)

    def mousePressEvent(self, e): 
        if e.button() == Qt.MouseButton.LeftButton: self._old_pos = e.globalPosition().toPoint()
            
    def mouseMoveEvent(self, e):
        if self._old_pos: 
            d = e.globalPosition().toPoint() - self._old_pos; self.move(self.x() + d.x(), self.y() + d.y()); self._old_pos = e.globalPosition().toPoint()
            
    def mouseReleaseEvent(self, e): self._old_pos = None
    
    def setup_btns(self):
        self.b_new = QPushButton("➕ 새 메모"); self.b_ref = QPushButton("↻ 새로고침"); self.b_sync = QPushButton("⇄ 지금 동기화"); self.b_del = QPushButton("ⓧ 삭제 (휴지통)"); self.b_res = QPushButton("⎌ 복구하기")
        for b in [self.b_new, self.b_ref, self.b_sync, self.b_res]: b.setStyleSheet("QPushButton { padding: 12px 20px; background: white; border: 1px solid #CBD5E1; border-radius: 8px; color: #1E293B; font-weight: bold; } QPushButton:hover { background: #F1F5F9; }")
        self.b_del.setStyleSheet("QPushButton { padding: 12px 20px; background: #FEF2F2; color: #EF4444; border: 1px solid #FECACA; border-radius: 8px; font-weight: bold; } QPushButton:hover { background: #FEE2E2; }")
        self.b_new.clicked.connect(self.ui_manager.create_empty_memo); self.b_ref.clicked.connect(self.refresh); self.b_sync.clicked.connect(self.ui_manager.sync_manager.sync_push); self.b_del.clicked.connect(self.del_checked); self.b_res.clicked.connect(self.res_checked)
    
    def on_cell_click(self, r, c):
        self.table.selectRow(r)
        if c != 0:
            it = self.table.item(r, 0)
            if it: it.setCheckState(Qt.CheckState.Unchecked if it.checkState() == Qt.CheckState.Checked else Qt.CheckState.Checked)
        m_item = self.table.item(r, 2)
        if m_item:
            m = m_item.data(Qt.ItemDataRole.UserRole)
            if m: 
                self._is_loading_preview = True 
                content = m.get('content', '')
                if "<html" in content or "<body" in content: self.pv.setHtml(content)
                else: self.pv.setPlainText(content)
                self._is_loading_preview = False
                
    def on_preview_changed(self):
        if self._is_loading_preview or self.is_trash_mode: return
        r = self.table.currentRow()
        if r < 0: return
        m_item = self.table.item(r, 2)
        if m_item:
            m = m_item.data(Qt.ItemDataRole.UserRole)
            m['content'] = self.pv.toHtml()
            m['updated_at'] = datetime.datetime.now().isoformat()
            self.ui_manager.sync_manager.save_memo_locally(m)
            title = m.get('title')
            if title in self.ui_manager.memo_windows:
                w = self.ui_manager.memo_windows[title]
                w._is_updating_from_explorer = True
                w.text_edit.setHtml(m['content'])
                w._is_updating_from_explorer = False
            self.table.item(r, 3).setText(datetime.datetime.now().strftime("%Y-%m-%d %H:%M"))
            
    def on_cell_double_click(self, r, c):
        if not self.is_trash_mode:
            m_item = self.table.item(r, 2)
            if m_item:
                m = m_item.data(Qt.ItemDataRole.UserRole)
                if m: self.ui_manager.show_specific_memo(m.get('title'))
                
    def update_btns_visibility(self):
        while self.btn_l.count():
            wi = self.btn_l.takeAt(0).widget()
            if wi: wi.setParent(None)
        if not self.is_trash_mode:
            self.btn_l.addWidget(self.b_new); self.btn_l.addWidget(self.b_ref); self.btn_l.addWidget(self.b_sync); self.btn_l.addStretch(); self.btn_l.addWidget(self.b_del)
        else:
            self.btn_l.addWidget(self.b_ref); self.btn_l.addWidget(self.b_res); self.btn_l.addStretch()
            
    def toggle_trash(self): 
        self.is_trash_mode = self.t_btn.isChecked()
        self.t_btn.setText("⎌ 목록으로 돌아가기" if self.is_trash_mode else "ⓧ 휴지통 보기")
        self.pv.setReadOnly(self.is_trash_mode) 
        self.current_page = 1; self.refresh()
        
    def toggle_max(self): [self.showNormal() or self.btn_max.setText("□") if self.isMaximized() else self.showMaximized() or self.btn_max.setText("❐")]
    def toggle_pin(self):
        f = self.windowFlags()
        if self.btn_pin.isChecked(): f |= Qt.WindowType.WindowStaysOnTopHint; self.btn_pin.setStyleSheet("border: none; color: #2563EB; background: transparent; font-weight: bold; font-size: 14pt;")
        else: f &= ~Qt.WindowType.WindowStaysOnTopHint; self.btn_pin.setStyleSheet("border: none; color: #000000; background: transparent; font-weight: bold; font-size: 14pt;")
        self.setWindowFlags(f); self.show()
    def on_search(self): self.current_page = 1; self.refresh()
    def go_prev(self): [setattr(self, 'current_page', self.current_page-1) or self.update_table() if self.current_page > 1 else None]
    def go_next(self): [setattr(self, 'current_page', self.current_page+1) or self.update_table() if self.current_page < (len(self.filtered_memos)+9)//10 else None]
    
    def on_header_click(self, idx):
        if idx == 0:
            all_c = all(self.table.item(r, 0).checkState() == Qt.CheckState.Checked for r in range(self.table.rowCount()))
            ns = Qt.CheckState.Unchecked if all_c else Qt.CheckState.Checked
            for r in range(self.table.rowCount()): self.table.item(r, 0).setCheckState(ns)
            
    def refresh(self):
        q = self.s_in.text().lower(); sb = self.s_type.currentIndex() == 1; all_m = self.ui_manager.sync_manager.load_trash_memos() if self.is_trash_mode else self.ui_manager.sync_manager.load_local_memos()
        all_m.sort(key=lambda x: (x.get('is_favorite', False), x.get('updated_at', '')), reverse=True)
        self.filtered_memos = [m for m in all_m if (not q) or (sb and q in re.sub(r'<[^>]+>', '', m.get('content','')).lower()) or (not sb and q in m.get('title','').lower())]
        self.update_table(); self.update_btns_visibility()
        
    def update_table(self):
        self.table.setRowCount(0); items = self.filtered_memos[(self.current_page-1)*10 : self.current_page*10]
        for m in items:
            r = self.table.rowCount(); self.table.insertRow(r); self.table.setRowHeight(r, 48)
            c = QTableWidgetItem(""); c.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled); c.setCheckState(Qt.CheckState.Unchecked); self.table.setItem(r, 0, c)
            
            if not self.is_trash_mode:
                is_fav = m.get('is_favorite')
                fb = QPushButton("★" if is_fav else "☆")
                fb.setFixedSize(30, 30)
                btn_color = "#D97706" if is_fav else "#94A3B8" 
                fb.setStyleSheet(f"border: none; background: transparent; font-size: 16pt; color: {btn_color}; padding-bottom: 3px;")
                fb.clicked.connect(lambda checked, memo=m: self.toggle_fav(memo))
                cell_w = QWidget(); cell_l = QHBoxLayout(cell_w); cell_l.addWidget(fb)
                cell_l.setAlignment(Qt.AlignmentFlag.AlignCenter); cell_l.setContentsMargins(0, 0, 0, 0); self.table.setCellWidget(r, 1, cell_w)
            else: 
                self.table.setCellWidget(r, 1, QWidget())
                
            t_text = m.get('title', '').strip()
            t = QTableWidgetItem(t_text); t.setData(Qt.ItemDataRole.UserRole, m)
            t.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
            self.table.setItem(r, 2, t)
            
            up = m.get('updated_at', ''); ds = datetime.datetime.fromisoformat(up).strftime("%Y-%m-%d %H:%M") if up else ""
            dt = QTableWidgetItem(ds); dt.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
            self.table.setItem(r, 3, dt)
            
        self.p_l.setText(f"{self.current_page} / {max(1, (len(self.filtered_memos)+9)//10)}")
        
    def toggle_fav(self, memo): memo['is_favorite'] = not memo.get('is_favorite', False); self.ui_manager.sync_manager.save_memo_locally(memo); self.refresh()
    def del_checked(self):
        ck = [self.table.item(r, 2).data(Qt.ItemDataRole.UserRole).get('title') for r in range(self.table.rowCount()) if self.table.item(r, 0).checkState() == Qt.CheckState.Checked]
        if ck and QMessageBox.question(self, "삭제", f"{len(ck)}개 삭제?", QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            for title in ck: self.ui_manager.close_memo_window(title); self.ui_manager.sync_manager.delete_memo_locally(title)
            self.ui_manager.sync_manager.delete_memos_cloud(ck); self.refresh()
    def res_checked(self):
        for r in range(self.table.rowCount()):
            if self.table.item(r, 0).checkState() == Qt.CheckState.Checked:
                m = self.table.item(r, 2).data(Qt.ItemDataRole.UserRole); title = m.get('title'); ex = next((x for x in self.ui_manager.sync_manager.load_local_memos() if x.get('title') == title), None)
                if not ex or ConflictDialog(title, ex.get('content', ''), m.get('content', '')).exec() == QDialog.DialogCode.Accepted: self.ui_manager.sync_manager.restore_memo_locally(title)
        self.refresh()

class LineNumberArea(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor
    def sizeHint(self):
        return QSize(self.editor.line_number_area_width(), 0)
    def paintEvent(self, event):
        self.editor.line_number_area_paint_event(event)

class MemoTextEdit(QTextEdit):
    def __init__(self, memo_window):
        super().__init__()
        self.memo_window = memo_window
        self.line_number_area = LineNumberArea(self)
        self.document().documentLayout().update.connect(self.update_line_number_area)
        self.verticalScrollBar().valueChanged.connect(self.line_number_area.update)
        self.textChanged.connect(self.update_line_number_area)

    def line_number_area_width(self):
        if not self.memo_window.memo_data.get('show_line_numbers', False): return 0
        digits = len(str(max(1, self.document().blockCount())))
        return 15 + self.fontMetrics().horizontalAdvance('9') * digits

    def update_line_number_area(self):
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)
        self.line_number_area.setVisible(self.memo_window.memo_data.get('show_line_numbers', False))
        cr = self.contentsRect()
        self.line_number_area.setGeometry(QRect(cr.left(), cr.top(), self.line_number_area_width(), cr.height()))
        self.line_number_area.update()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        cr = self.contentsRect()
        self.line_number_area.setGeometry(QRect(cr.left(), cr.top(), self.line_number_area_width(), cr.height()))

    def line_number_area_paint_event(self, event):
        painter = QPainter(self.line_number_area)
        painter.fillRect(event.rect(), QColor(0, 0, 0, 15)) 
        painter.setPen(QColor("#64748B")) 
        painter.setFont(self.font())
        
        block = self.document().begin()
        scroll_y = self.verticalScrollBar().value()
        level_counts = {}
        last_level = 0
        
        while block.isValid():
            text = block.text()
            if text.strip() == "":
                block_num_str = ""
            else:
                b_indent = block.blockFormat().indent()
                space_count = sum(4 if ch == '\t' else 1 for ch in text if ch in [' ', '\t'])
                current_level = (b_indent * 4 + space_count) // 4
                
                if current_level > last_level:
                    level_counts[current_level] = 1
                elif current_level < last_level:
                    for lvl in list(level_counts.keys()):
                        if lvl > current_level: del level_counts[lvl]
                    level_counts[current_level] = level_counts.get(current_level, 0) + 1
                else:
                    level_counts[current_level] = level_counts.get(current_level, 0) + 1
                    
                block_num_str = str(level_counts[current_level])
                last_level = current_level
            
            block_bb = self.document().documentLayout().blockBoundingRect(block)
            pos_y = block_bb.top() - scroll_y
            
            if block_num_str and pos_y <= event.rect().bottom() and pos_y + block_bb.height() >= event.rect().top():
                painter.drawText(0, int(pos_y), self.line_number_area.width() - 5, self.fontMetrics().height(),
                                 Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, block_num_str)
            block = block.next()

    def keyPressEvent(self, e):
        # Tab 키를 누를 때 툴바의 들여쓰기 기능(apply_indent) 실행
        if e.key() == Qt.Key.Key_Tab:
            if e.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                # Shift + Tab -> 내어쓰기 (아래 포맷바 '⇤' 버튼 기능)
                self.memo_window.apply_outdent()
            else:
                # Tab -> 들여쓰기 (아래 포맷바 '⇥' 버튼 기능)
                self.memo_window.apply_indent()
            return

        # 엔터(Enter)를 칠 때 윗줄의 들여쓰기 단계를 그대로 유지
        elif e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            cursor = self.textCursor()
            current_indent = cursor.blockFormat().indent()
            super().keyPressEvent(e)
            if current_indent > 0:
                new_cursor = self.textCursor()
                bf = new_cursor.blockFormat()
                bf.setIndent(current_indent)
                new_cursor.setBlockFormat(bf)
            return
            
        super().keyPressEvent(e)

    def paintEvent(self, event):
        painter = QPainter(self.viewport())
        show_bg = self.memo_window.memo_data.get('show_line_bg', False)
        
        # [세로선 완벽 제거] 가로 줄노트 배경만 렌더링
        if show_bg:
            grid_color = QColor(71, 85, 105, 60)
            scroll_y = self.verticalScrollBar().value()
            fm = self.fontMetrics()
            line_height = fm.lineSpacing()
            
            painter.setPen(grid_color)
            block = self.document().begin()
            last_bottom = 0
            
            while block.isValid():
                block_bb = self.document().documentLayout().blockBoundingRect(block)
                pos_y = block_bb.top() - scroll_y
                line_bottom = int(pos_y + block_bb.height())
                
                if line_bottom > 0 and pos_y <= self.viewport().height():
                    painter.drawLine(0, line_bottom, self.viewport().width(), line_bottom)
                last_bottom = line_bottom
                block = block.next()
            
            y = last_bottom + line_height if last_bottom > 0 else int(line_height - (scroll_y % line_height))
            while y < self.viewport().height():
                painter.drawLine(0, y, self.viewport().width(), y)
                y += line_height

        painter.end()
        super().paintEvent(event)

    def wheelEvent(self, event):
        modifiers = QApplication.keyboardModifiers()
        delta = event.angleDelta().y()
        if modifiers == Qt.KeyboardModifier.ControlModifier:
            f = self.font()
            s = max(8, min(40, f.pointSize() + (1 if delta > 0 else -1)))
            f.setPointSize(s)
            self.setFont(f)
            cursor = self.textCursor()
            cursor.select(QTextCursor.SelectionType.Document)
            fmt = QTextCharFormat()
            fmt.setFont(f)
            cursor.mergeCharFormat(fmt)
            self.memo_window.memo_data['font_size'] = s
            self.update_line_number_area()
            self.memo_window.save_callback(self.memo_window.memo_data)
            self.memo_window.show_toast(f"폰트 크기: {s}pt")
            event.accept() 
            return
        elif modifiers == Qt.KeyboardModifier.ShiftModifier:
            op = max(0.25, min(1.0, self.memo_window.windowOpacity() + (0.05 if delta > 0 else -0.05)))
            self.memo_window.setWindowOpacity(op)
            self.memo_window.memo_data['opacity'] = op
            self.memo_window.save_callback(self.memo_window.memo_data)
            self.memo_window.show_toast(f"투명도: {int(op * 100)}%")
            event.accept() 
            return
        super().wheelEvent(event)

class LineNumberArea(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor
    def sizeHint(self):
        return QSize(self.editor.line_number_area_width(), 0)
    def paintEvent(self, event):
        self.editor.line_number_area_paint_event(event)

class MemoTextEdit(QTextEdit):
    def __init__(self, memo_window):
        super().__init__()
        self.memo_window = memo_window
        self.line_number_area = LineNumberArea(self)
        self.document().documentLayout().update.connect(self.update_line_number_area)
        self.verticalScrollBar().valueChanged.connect(self.line_number_area.update)
        self.textChanged.connect(self.update_line_number_area)

    def line_number_area_width(self):
        if not self.memo_window.memo_data.get('show_line_numbers', False): return 0
        digits = len(str(max(1, self.document().blockCount())))
        return 15 + self.fontMetrics().horizontalAdvance('9') * digits

    def update_line_number_area(self):
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)
        self.line_number_area.setVisible(self.memo_window.memo_data.get('show_line_numbers', False))
        cr = self.contentsRect()
        self.line_number_area.setGeometry(QRect(cr.left(), cr.top(), self.line_number_area_width(), cr.height()))
        self.line_number_area.update()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        cr = self.contentsRect()
        self.line_number_area.setGeometry(QRect(cr.left(), cr.top(), self.line_number_area_width(), cr.height()))

    def line_number_area_paint_event(self, event):
        painter = QPainter(self.line_number_area)
        painter.fillRect(event.rect(), QColor(0, 0, 0, 15)) 
        painter.setPen(QColor("#64748B")) 
        painter.setFont(self.font())
        
        block = self.document().begin()
        scroll_y = self.verticalScrollBar().value()
        block_number = 0
        
        while block.isValid():
            block_bb = self.document().documentLayout().blockBoundingRect(block)
            pos_y = block_bb.top() - scroll_y
            
            if pos_y <= event.rect().bottom() and pos_y + block_bb.height() >= event.rect().top():
                painter.drawText(0, int(pos_y), self.line_number_area.width() - 5, self.fontMetrics().height(),
                                 Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, str(block_number + 1))
                                 
            block = block.next()
            block_number += 1

    def keyPressEvent(self, e):
        # 1. Shift + Tab (내어쓰기) -> 공백 입력 원천 차단 및 내어쓰기 실행
        if e.key() == Qt.Key.Key_Backtab or (e.key() == Qt.Key.Key_Tab and e.modifiers() & Qt.KeyboardModifier.ShiftModifier):
            self.memo_window.apply_outdent()
            e.accept()
            return

        # 2. Tab (들여쓰기) -> 공백 입력 원천 차단 및 들여쓰기 실행
        elif e.key() == Qt.Key.Key_Tab:
            self.memo_window.apply_indent()
            e.accept()
            return
            
        # 3. Enter (자동 들여쓰기 유지)
        elif e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            cursor = self.textCursor()
            current_indent = cursor.blockFormat().indent()
            super().keyPressEvent(e)
            if current_indent > 0:
                new_cursor = self.textCursor()
                bf = new_cursor.blockFormat()
                bf.setIndent(current_indent)
                new_cursor.setBlockFormat(bf)
            return
            
        super().keyPressEvent(e)

    def paintEvent(self, event):
        painter = QPainter(self.viewport())
        show_bg = self.memo_window.memo_data.get('show_line_bg', False)
        grid_color = QColor(71, 85, 105, 60)
        indent_color = QColor(148, 163, 184, 150) 
        scroll_y = self.verticalScrollBar().value()
        fm = self.fontMetrics()
        line_height = fm.lineSpacing()
        
        if show_bg:
            painter.setPen(grid_color)
            block = self.document().begin()
            last_bottom = 0
            while block.isValid():
                block_bb = self.document().documentLayout().blockBoundingRect(block)
                pos_y = block_bb.top() - scroll_y
                line_bottom = int(pos_y + block_bb.height())
                if line_bottom > 0 and pos_y <= self.viewport().height():
                    painter.drawLine(0, line_bottom, self.viewport().width(), line_bottom)
                last_bottom = line_bottom
                block = block.next()
            
            y = last_bottom + line_height if last_bottom > 0 else int(line_height - (scroll_y % line_height))
            while y < self.viewport().height():
                painter.drawLine(0, y, self.viewport().width(), y)
                y += line_height

        painter.setPen(indent_color)
        space_width = fm.horizontalAdvance(' ')
        tab_width = space_width * 4 
        indent_width_block = int(self.document().indentWidth())
        block = self.document().begin()
        
        while block.isValid():
            block_bb = self.document().documentLayout().blockBoundingRect(block)
            pos_y = block_bb.top() - scroll_y
            if pos_y <= event.rect().bottom() and pos_y + block_bb.height() >= event.rect().top():
                base_x = block_bb.left()
                block_indent = block.blockFormat().indent()
                if block_indent > 0:
                    for i in range(1, block_indent + 1):
                        x = int(base_x - (block_indent - i) * indent_width_block - indent_width_block + (space_width * 2))
                        if x > 0: painter.drawLine(x, int(pos_y), x, int(pos_y + block_bb.height()))

                text = block.text()
                space_count = sum(4 if ch == '\t' else 1 for ch in text if ch in [' ', '\t'])
                space_indent = space_count // 4
                for i in range(1, space_indent + 1):
                    x = int(base_x + (i * tab_width) - space_width)
                    if x > 0: painter.drawLine(x, int(pos_y), x, int(pos_y + block_bb.height()))
            block = block.next()
            
        painter.end()
        super().paintEvent(event)

    def wheelEvent(self, event):
        modifiers = QApplication.keyboardModifiers()
        delta = event.angleDelta().y()
        if modifiers == Qt.KeyboardModifier.ControlModifier:
            f = self.font()
            s = max(8, min(40, f.pointSize() + (1 if delta > 0 else -1)))
            f.setPointSize(s)
            self.setFont(f)
            cursor = self.textCursor()
            cursor.select(QTextCursor.SelectionType.Document)
            fmt = QTextCharFormat()
            fmt.setFont(f)
            cursor.mergeCharFormat(fmt)
            self.memo_window.memo_data['font_size'] = s
            self.update_line_number_area()
            self.memo_window.save_callback(self.memo_window.memo_data)
            self.memo_window.show_toast(f"폰트 크기: {s}pt")
            event.accept() 
            return
        elif modifiers == Qt.KeyboardModifier.ShiftModifier:
            op = max(0.25, min(1.0, self.memo_window.windowOpacity() + (0.05 if delta > 0 else -0.05)))
            self.memo_window.setWindowOpacity(op)
            self.memo_window.memo_data['opacity'] = op
            self.memo_window.save_callback(self.memo_window.memo_data)
            self.memo_window.show_toast(f"투명도: {int(op * 100)}%")
            event.accept() 
            return
        super().wheelEvent(event)
        
class MemoWindow(QWidget):
    def __init__(self, m: Dict[str, Any], sc: Any, dc: Any, rc: Any, cc: Any):
        super().__init__()
        self.memo_data = m; self.save_callback = sc; self.delete_callback = dc; self.rename_callback = rc; self.close_callback = cc; self._old_pos = None
        self._is_updating_from_explorer = False
        self._is_rolled_up = False 
        self._normal_height = 400
        self.setup_ui(); self.apply_data(); self.setMouseTracking(True); self.text_edit.setMouseTracking(True); QShortcut(QKeySequence("Ctrl+S"), self).activated.connect(self.manual_save)
        self.toast_label = QLabel(self)
        self.toast_label.setStyleSheet("background-color: rgba(30, 41, 59, 0.85); color: white; font-weight: bold; border-radius: 6px; padding: 6px 12px; font-size: 10pt;")
        self.toast_label.hide()
        self.toast_timer = QTimer(self)
        self.toast_timer.setSingleShot(True)
        self.toast_timer.timeout.connect(self.toast_label.hide)

    # --- 신규 추가: 토스트 알림 출력 함수 ---
    def show_toast(self, text: str):
        self.toast_label.setText(text)
        self.toast_label.adjustSize()
        # 메모장 중앙 상단 위치 계산
        x = (self.width() - self.toast_label.width()) // 2
        y = 50
        self.toast_label.move(x, y)
        self.toast_label.show()
        self.toast_label.raise_()
        self.toast_timer.start(1000) # 1초 후 자동으로 숨김
    
    def update_line_numbers(self):
        if hasattr(self, 'line_num_bar') and self.line_num_bar.isVisible():
            doc = self.text_edit.document()
            block_count = doc.blockCount()
            
            # VS Code 스타일: 자릿수에 맞춰 좌측 사이드바 너비 자동 확장 (예: 100줄 이상이면 자동 넓어짐)
            digits = len(str(block_count))
            self.line_num_bar.setFixedWidth(max(32, 12 * digits + 10))
            
            nums = "\n".join(str(i) for i in range(1, block_count + 1))
            self.line_num_bar.setPlainText(nums)
            self.line_num_bar.setFont(self.text_edit.font())
            self.line_num_bar.verticalScrollBar().setValue(self.text_edit.verticalScrollBar().value())

    def toggle_line_numbers(self):
        self.memo_data['show_line_numbers'] = not self.memo_data.get('show_line_numbers', False)
        self.text_edit.update_line_number_area()
        self.save_callback(self.memo_data)

    def toggle_line_bg(self):
        self.memo_data['show_line_bg'] = not self.memo_data.get('show_line_bg', False)
        self.text_edit.viewport().update() # 화면 즉시 다시 그리기
        self.save_callback(self.memo_data)

    def apply_line_bg_style(self):
        # 줄노트 배경 CSS 스타일 적용
        if self.memo_data.get('show_line_bg', False):
            self.text_edit.setStyleSheet("QTextEdit { border:none; background: transparent; color:#000000; font-family: 'Malgun Gothic'; background-image: repeating-linear-gradient(transparent, transparent 27px, #CBD5E1 28px); background-attachment: local; }")
        else:
            self.text_edit.setStyleSheet("QTextEdit { border:none; background: transparent; color:#000000; font-family: 'Malgun Gothic'; }")

    def apply_text_stroke(self, widget):
        eff = QGraphicsDropShadowEffect(self)
        eff.setBlurRadius(3)
        eff.setColor(QColor(255, 255, 255, 255))
        eff.setOffset(0, 0)
        widget.setGraphicsEffect(eff)
        
    def setup_ui(self) -> None:
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        self.bg = QWidget()
        self.bg.setObjectName("MemoBackground")
        bg_l = QVBoxLayout(self.bg)
        layout.addWidget(self.bg)
        
        ctrl = QHBoxLayout()
        self.title_edit = QLineEdit()
        self.title_edit.setReadOnly(True)
        
        QShortcut(QKeySequence("F2"), self).activated.connect(self.enable_rename)
        QShortcut(QKeySequence("Ctrl+F"), self).activated.connect(self.show_search)
        QShortcut(QKeySequence("Ctrl+H"), self).activated.connect(self.show_search)
        
        self.title_edit.setStyleSheet("border:none; background:transparent; color:#000000; font-weight:bold; font-size:12pt; font-family: 'Malgun Gothic';")
        self.title_edit.editingFinished.connect(self.handle_rename)
        self.title_edit.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.title_edit.customContextMenuRequested.connect(self.show_menu)
        self.title_edit.installEventFilter(self)
        
        self.btn_pin = QPushButton("⚲")
        self.btn_min = QPushButton("_")
        self.btn_close = QPushButton("✕")
        for b in [self.btn_pin, self.btn_min, self.btn_close]:
            b.setFixedSize(26, 26)
            b.setStyleSheet("border:none; color:#000000; background:transparent; font-weight:bold; font-size:14pt;")
            self.apply_text_stroke(b)
            
        self.btn_pin.clicked.connect(self.toggle_pin)
        self.btn_min.clicked.connect(self.toggle_rollup)
        self.btn_close.clicked.connect(self.close)
        
        ctrl.addWidget(self.title_edit)
        ctrl.addWidget(self.btn_pin)
        ctrl.addWidget(self.btn_min)
        ctrl.addWidget(self.btn_close)
        bg_l.addLayout(ctrl)
        
        self.content_container = QWidget()
        cc_layout = QVBoxLayout(self.content_container)
        cc_layout.setContentsMargins(0,0,0,0)
        
        # ▼▼ 신형 커스텀 엔진(MemoTextEdit) 탑재 (행번호 자동 포함) ▼▼
        self.text_edit = MemoTextEdit(self)
        self.text_edit.setStyleSheet("border:none; background:transparent; color:#000000; font-family: 'Malgun Gothic';")
        self.text_edit.textChanged.connect(self.update_content)
        self.text_edit.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.text_edit.customContextMenuRequested.connect(self.show_menu)
        self.text_edit.installEventFilter(self)
        
        cc_layout.addWidget(self.text_edit)
        
        # 찾기/바꾸기 바
        self.search_bar = QWidget()
        sl = QHBoxLayout(self.search_bar)
        sl.setContentsMargins(0, 0, 0, 0)
        
        self.s_in = QLineEdit()
        self.s_in.setPlaceholderText("찾을 단어")
        self.s_in.setStyleSheet("padding:4px; border:1px solid #CBD5E1; border-radius:4px; background:white; color:#000000;")
        self.s_in.returnPressed.connect(lambda: self.do_find(backward=False))
        
        self.s_count = QLabel("0/0")
        self.s_count.setStyleSheet("color: #3B82F6; font-weight: bold; padding: 0 5px;")
        
        self.s_prev_btn = QPushButton("▲")
        self.s_prev_btn.setFixedSize(24, 24)
        self.s_prev_btn.setStyleSheet("background:#F1F5F9; color:#000000; border:1px solid #CBD5E1; border-radius:4px; font-weight:bold;")
        self.s_prev_btn.clicked.connect(lambda: self.do_find(backward=True))
        
        self.s_next_btn = QPushButton("▼")
        self.s_next_btn.setFixedSize(24, 24)
        self.s_next_btn.setStyleSheet("background:#F1F5F9; color:#000000; border:1px solid #CBD5E1; border-radius:4px; font-weight:bold;")
        self.s_next_btn.clicked.connect(lambda: self.do_find(backward=False))
        
        self.r_in = QLineEdit()
        self.r_in.setPlaceholderText("바꿀 단어")
        self.r_in.setStyleSheet("padding:4px; border:1px solid #CBD5E1; border-radius:4px; background:white; color:#000000;")
        self.r_in.returnPressed.connect(self.do_replace)
        
        self.r_btn = QPushButton("바꾸기")
        self.r_btn.setStyleSheet("background:#3B82F6; color:white; border:none; border-radius:4px; padding:4px; font-weight:bold;")
        self.r_btn.clicked.connect(self.do_replace)
        
        self.s_close = QPushButton("✕")
        self.s_close.setFixedSize(24, 24)
        self.s_close.setStyleSheet("border:none; color:#EF4444; font-weight:bold;")
        self.s_close.clicked.connect(self.search_bar.hide)
        
        for w in [self.s_in, self.s_count, self.s_prev_btn, self.s_next_btn, self.r_in, self.r_btn, self.s_close]: 
            sl.addWidget(w)
            
        self.search_bar.hide()
        cc_layout.addWidget(self.search_bar)
        
        self.fmt_bar = QHBoxLayout()
        self.btn_bullet = QPushButton("•")
        self.btn_num = QPushButton("1.")
        self.btn_indent = QPushButton("⇥")
        self.btn_outdent = QPushButton("⇤")
        for b in [self.btn_bullet, self.btn_num, self.btn_indent, self.btn_outdent]:
            b.setFixedSize(26, 26)
            b.setStyleSheet("border:none; color:#475569; font-weight:bold; font-size:12pt; background: transparent;")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            self.fmt_bar.addWidget(b)
            
        self.btn_bullet.clicked.connect(self.apply_bullet)
        self.btn_num.clicked.connect(self.apply_number)
        self.btn_indent.clicked.connect(self.apply_indent)
        self.btn_outdent.clicked.connect(self.apply_outdent)
        self.fmt_bar.addStretch()
        cc_layout.addLayout(self.fmt_bar)
        
        bg_l.addWidget(self.content_container)
        self.grip = QSizeGrip(self)

    def eventFilter(self, obj, event):
        if hasattr(self, 'title_edit') and obj == self.title_edit:
            # 제목창 더블클릭 시 롤업 토글
            if event.type() == QEvent.Type.MouseButtonDblClick and event.button() == Qt.MouseButton.LeftButton:
                self.toggle_rollup()
                return True 
                
            # 평상시 마우스로 잡고 창 이동하기
            if self.title_edit.isReadOnly():
                if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                    self.mousePressEvent(event)
                    return True
                elif event.type() == QEvent.Type.MouseMove:
                    self.mouseMoveEvent(event)
                    return True
                elif event.type() == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
                    self.mouseReleaseEvent(event)
                    return True
                    
        return super().eventFilter(obj, event)
    
    def resizeEvent(self, event):
        super().resizeEvent(event)
        # 언제나 창 우측 하단 끄트머리에 핸들이 오도록 위치 보정
        if hasattr(self, 'grip'):
            self.grip.move(self.width() - 20, self.height() - 20)
            self.grip.resize(12, 12)
        
    def show_menu(self, pos):
        menu = QMenu(self)
        menu.setStyleSheet("QMenu { background: white; color: #000000; border: 1px solid #CBD5E1; border-radius: 4px; } QMenu::item:selected { background-color: #F1F5F9; }")
        menu.addAction("저장 (Ctrl+S)").triggered.connect(self.manual_save)
        menu.addAction("검색/바꾸기 (Ctrl+F)").triggered.connect(self.show_search)
        
        # 우클릭 행번호 표시 옵션
        ln_action = menu.addAction("행번호 표시 (VS Code 스타일)")
        ln_action.setCheckable(True)
        ln_action.setChecked(self.memo_data.get('show_line_numbers', False))
        ln_action.triggered.connect(self.toggle_line_numbers)
        
        # [신규] 우클릭 줄노트 배경 옵션
        bg_action = menu.addAction("줄노트 배경")
        bg_action.setCheckable(True)
        bg_action.setChecked(self.memo_data.get('show_line_bg', False))
        bg_action.triggered.connect(self.toggle_line_bg)
        
        menu.addSeparator()
        cm = menu.addMenu("색상 변경")
        for n, c in {"하늘색": "#E0F2FE", "연두색": "#DCFCE7", "노란색": "#FEF9C3", "분홍색": "#FCE7F3", "흰색": "#FFFFFF"}.items(): 
            cm.addAction(n).triggered.connect(lambda checked, code=c: self.change_color(code))
        menu.addSeparator()
        menu.addAction("고정 토글").triggered.connect(self.toggle_pin)
        menu.addAction("삭제 (휴지통)").triggered.connect(lambda: self.delete_callback(self))
        menu.exec(self.sender().mapToGlobal(pos))

    def toggle_rollup(self):
        # 현재 창이 위치한 모니터 화면 정보 가동
        screen = QApplication.screenAt(self.geometry().center()) or QApplication.primaryScreen()
        scr_geom = screen.availableGeometry()
        
        if not self._is_rolled_up:
            self._normal_height = self.height()
            self.content_container.hide()
            self.setMinimumHeight(0)
            self.setMaximumHeight(16777215)
            
            y_shift = self._normal_height - 50
            new_y = self.y() + y_shift
            
            if new_y + 50 > scr_geom.bottom():
                new_y = scr_geom.bottom() - 50
                
            self._actual_y_shift = new_y - self.y()
            self.move(self.x(), new_y)
            
            self.resize(self.width(), 50)
            self.setMinimumHeight(50)
            self.setMaximumHeight(50)
            self._is_rolled_up = True
            self.btn_min.setText("□") 
        else:
            self.setMinimumHeight(0)
            self.setMaximumHeight(16777215)
            self.content_container.show()
            
            y_shift = getattr(self, '_actual_y_shift', self._normal_height - 50)
            new_y = self.y() - y_shift
            
            if new_y < scr_geom.top():
                new_y = scr_geom.top()
                
            self.move(self.x(), new_y)
            self.resize(self.width(), self._normal_height)
            self.setMinimumSize(200, 150)
            self._is_rolled_up = False
            self.btn_min.setText("_")
            
    def manual_save(self): self.update_content(); self.save_callback(self.memo_data)

    def show_search(self):
        self.search_bar.setVisible(not self.search_bar.isVisible())
        if self.search_bar.isVisible():
            self.s_in.setFocus()
            self.s_in.selectAll()

    def do_find(self, backward=False):
        search_text = self.s_in.text()
        if not search_text:
            self.s_count.setText("0/0")
            return
            
        from PyQt6.QtGui import QPalette, QColor, QTextCursor, QTextDocument
        bg = self.memo_data.get('bg_color', '#FFFFFF')
        
        if bg == "#E0F2FE": h_bg = "#EA580C" 
        elif bg == "#DCFCE7": h_bg = "#9333EA" 
        elif bg == "#FEF9C3": h_bg = "#2563EB" 
        elif bg == "#FCE7F3": h_bg = "#059669" 
        else: h_bg = "#E11D48" 
        
        p = self.text_edit.palette()
        p.setColor(QPalette.ColorRole.Highlight, QColor(h_bg))
        p.setColor(QPalette.ColorRole.HighlightedText, QColor("#FFFFFF"))
        self.text_edit.setPalette(p)

        # 방향(위/아래)에 따른 검색 옵션 적용
        if backward:
            found = self.text_edit.find(search_text, QTextDocument.FindFlag.FindBackward)
        else:
            found = self.text_edit.find(search_text)

        if not found:
            # 문서 끝(또는 처음)에 도달하면 반대편으로 넘어가서 다시 찾음
            c = self.text_edit.textCursor()
            c.movePosition(QTextCursor.MoveOperation.End if backward else QTextCursor.MoveOperation.Start)
            self.text_edit.setTextCursor(c)
            found = self.text_edit.find(search_text, QTextDocument.FindFlag.FindBackward if backward else QTextDocument.FindFlag(0))

        if found:
            text = self.text_edit.toPlainText().lower()
            st_low = search_text.lower()
            total = text.count(st_low)
            cursor_pos = self.text_edit.textCursor().position()
            current = text[:cursor_pos].count(st_low)
            # 만약 위로 찾기 중이라서 순서가 밀리면 보정
            if backward and current == 0 and total > 0: current = 1
            self.s_count.setText(f"{current}/{total}")
        else:
            self.s_count.setText("0/0")

    def do_replace(self):
        c = self.text_edit.textCursor()
        if c.hasSelection() and c.selectedText().lower() == self.s_in.text().lower(): 
            c.insertText(self.r_in.text())
            self.manual_save()
        self.do_find(backward=False) # 바꾸고 나서는 무조건 아래로(다음) 찾기
    
    def apply_bullet(self): self.text_edit.textCursor().createList(QTextListFormat.Style.ListDisc); self.manual_save()
    def apply_number(self): self.text_edit.textCursor().createList(QTextListFormat.Style.ListDecimal); self.manual_save()
    def apply_indent(self):
        cursor = self.text_edit.textCursor(); fmt = cursor.blockFormat()
        if fmt.indent() < 2: 
            fmt.setIndent(fmt.indent() + 1); cursor.setBlockFormat(fmt); self.manual_save()
    def apply_outdent(self):
        cursor = self.text_edit.textCursor(); fmt = cursor.blockFormat()
        if fmt.indent() > 0:
            fmt.setIndent(fmt.indent() - 1); cursor.setBlockFormat(fmt); self.manual_save()
    
    def apply_data(self):
        f = Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool
        f = f | Qt.WindowType.WindowStaysOnTopHint if self.memo_data.get('is_pinned') else f
        self.setWindowFlags(f)
        self.bg.setStyleSheet(f"QWidget#MemoBackground {{ background-color: {self.memo_data.get('bg_color', '#E0F2FE')}; border: 1px solid rgba(0,0,0,0.1); border-radius: 12px; }}")
        self.title_edit.setText(self.memo_data.get('title',''))
        self.title_edit.setCursorPosition(0)
        
        self._is_updating_from_explorer = True
        cnt = self.memo_data.get('content','')
        self.text_edit.setHtml(cnt) if "<html" in cnt else self.text_edit.setPlainText(cnt)
        
        f_size = self.memo_data.get('font_size', 11)
        font = self.text_edit.font()
        font.setPointSize(f_size)
        self.text_edit.setFont(font)
        if hasattr(self, 'line_num_bar'):
            self.line_num_bar.setFont(font)
            
        self.setWindowOpacity(self.memo_data.get('opacity', 1.0))
        
        # 줄노트 배경 복원
        self.apply_line_bg_style()
        
        # 행번호 복원
        show_ln = self.memo_data.get('show_line_numbers', False)
        if hasattr(self, 'line_num_bar'):
            self.line_num_bar.setVisible(show_ln)
            if show_ln:
                self.update_line_numbers()
                
        self._is_updating_from_explorer = False
        self.setGeometry(self.memo_data.get('position_x',100), self.memo_data.get('position_y',100), self.memo_data.get('width',500), self.memo_data.get('height',400))
        self.btn_pin.setStyleSheet(f"border:none; color:{'#2563EB' if self.memo_data.get('is_pinned') else '#000000'}; background:transparent; font-weight:bold; font-size:14pt;")
        self.apply_text_stroke(self.btn_pin)
        
    def closeEvent(self, e):
        self.memo_data['position_x'], self.memo_data['position_y'] = self.x(), self.y()
        self.memo_data['width'] = self.width()
        # 접힌 상태로 끄더라도 펼쳐졌을 때의 정상 높이를 기억하게 처리
        if not self._is_rolled_up:
            self.memo_data['height'] = self.height()
        else:
            self.memo_data['height'] = self._normal_height
            
        self.memo_data['is_visible'] = False
        self.save_callback(self.memo_data)
        self.close_callback(self)
        super().closeEvent(e)
        
    def enable_rename(self):
        # F2를 누르면 수정 가능 모드로 변신
        self.title_edit.setReadOnly(False)
        self.title_edit.setStyleSheet("border:1px solid #3B82F6; background:white; color:#000000; font-weight:bold; font-size:12pt; font-family: 'Malgun Gothic'; border-radius:4px;")
        self.title_edit.setFocus()
        self.title_edit.selectAll()

    def handle_rename(self):
        nt = re.sub(r'[\\/*?:"<>|]', "", self.title_edit.text().strip())
        ot = self.memo_data.get('title','')
        if not nt or nt == ot:
            self.title_edit.setText(ot)
        else:
            if self.rename_callback(ot, nt, self.memo_data):
                self.memo_data['title'] = nt
                self.save_callback(self.memo_data)
            else:
                QMessageBox.warning(self, "중복", f"'{nt}' 존재.")
                self.title_edit.setText(ot)
                
        # 이름 수정이 끝나면 다시 드래그 가능한 읽기 전용 상태로 복구
        self.title_edit.setReadOnly(True)
        self.title_edit.setStyleSheet("border:none; background:transparent; color:#000000; font-weight:bold; font-size:12pt; font-family: 'Malgun Gothic';")
        self.title_edit.setCursorPosition(0)
        
    def toggle_pin(self): self.memo_data['is_pinned'] = not self.memo_data.get('is_pinned', False); self.apply_data(); self.show(); self.save_callback(self.memo_data)
    
    def update_content(self):
        if self._is_updating_from_explorer: return
        self.memo_data['content'] = self.text_edit.toHtml()
        self.memo_data['updated_at'] = datetime.datetime.now().isoformat(); self.save_callback(self.memo_data)
        
    def change_color(self, c): self.memo_data['bg_color'] = c; self.apply_data(); self.save_callback(self.memo_data)
    
    def mousePressEvent(self, e): 
        if e.button() == Qt.MouseButton.LeftButton:
            self._old_pos = e.globalPosition().toPoint()

    def mouseMoveEvent(self, e): 
        if getattr(self, '_old_pos', None):
            delta = e.globalPosition().toPoint() - self._old_pos
            new_x = self.x() + delta.x()
            new_y = self.y() + delta.y()

            # [핵심] 마우스 커서/메모 창이 위치한 현재 모니터를 동적으로 찾기 (듀얼/다중 모니터 대응)
            screen = QApplication.screenAt(e.globalPosition().toPoint()) or QApplication.primaryScreen()
            scr_geom = screen.availableGeometry()
            
            # 해당 모니터의 작업표시줄 및 모니터 경계를 벗어나지 않도록 통제
            new_x = max(scr_geom.left(), min(new_x, scr_geom.right() - self.width()))
            new_y = max(scr_geom.top(), min(new_y, scr_geom.bottom() - self.height()))

            self.move(new_x, new_y)
            self._old_pos = e.globalPosition().toPoint()

    def mouseReleaseEvent(self, e): 
        self._old_pos = None
        self.memo_data.update({'position_x': self.x(), 'position_y': self.y(), 'width': self.width()})
        if not self._is_rolled_up: 
            self.memo_data['height'] = self.height()
        self.save_callback(self.memo_data)

class UIManager:
    def __init__(self, sm: Any):
        self.sync_manager = sm; self.memo_windows: Dict[str, MemoWindow] = {}; self._all_visible = True; self.explorer_window = None; self._last_pos = QPoint(100, 100); self.sync_manager.set_ui_manager(self); self.setup_tray()
    
    def setup_tray(self) -> None:
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor("#AED6F1"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(0, 0, 64, 64, 16, 16)
        painter.setPen(QColor("#000000"))
        font = QFont("Arial", 13, QFont.Weight.Bold)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "Memos")
        painter.end()
        
        self.tray_icon = QSystemTrayIcon(QIcon(pixmap))
        self.tray_icon.activated.connect(self.on_tray_activated)
        
        menu = QMenu()
        menu.setStyleSheet("background: white; color: #000000; border: 1px solid #CBD5E1;")
        
        # 메뉴 항목들 추가
        menu.addAction("➕ 새 메모").triggered.connect(self.create_empty_memo)
        menu.addAction("📄 메모 탐색기").triggered.connect(self.open_memo_explorer)
        menu.addAction("▤ 메모 바둑판 정렬").triggered.connect(self.arrange_memos) # 👈 정렬 기능 추가됨
        menu.addAction("⇄ 지금 동기화").triggered.connect(self.sync_manager.sync_push)
        
        self.toggle_action = menu.addAction("모두 숨기기")
        self.toggle_action.triggered.connect(self.toggle_all)
        
        menu.addSeparator()
        menu.addAction("⚙ 환경설정").triggered.connect(self.open_settings)
        menu.addSeparator()
        menu.addAction("✕ 종료").triggered.connect(QApplication.quit)
        
        self.tray_icon.setContextMenu(menu)
        self.tray_icon.show()

    def arrange_memos(self):
        screen = QApplication.primaryScreen().availableGeometry()
        x, y = screen.x() + 20, screen.y() + 20
        max_row_height = 0
        
        # 현재 화면에 켜져 있는 메모들만 모아서 정렬
        visible_memos = [w for w in self.memo_windows.values() if w.isVisible()]
        
        for w in visible_memos:
            w_width = w.width()
            # 접혀있는 상태라면 원래 높이를 기준으로 줄바꿈 계산
            w_height = w.height() if not w._is_rolled_up else getattr(w, '_normal_height', 400)
            
            # 메모가 우측 화면 경계를 넘어가면 다음 줄로 이동
            if x + w_width > screen.right():
                x = screen.x() + 20
                y += max_row_height + 20
                max_row_height = 0
                
            w.move(x, y)
            w.memo_data.update({'position_x': x, 'position_y': y})
            w.save_callback(w.memo_data)
            
            x += w_width + 20
            max_row_height = max(max_row_height, w_height)

    def on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            if self.explorer_window and self.explorer_window.isVisible():
                self.explorer_window.hide()
            else:
                self.open_memo_explorer()

    def toggle_all(self):
        for w in self.memo_windows.values(): [w.hide() if self._all_visible else (w.show() or w.raise_())]
        self.toggle_action.setText("모두 보이기" if self._all_visible else "모두 숨기기"); self._all_visible = not self._all_visible
        
    def open_memo_explorer(self):
        if not self.explorer_window: 
            self.explorer_window = MemoExplorerWindow(self)
        self.explorer_window.setWindowState(self.explorer_window.windowState() & ~Qt.WindowState.WindowMinimized | Qt.WindowState.WindowActive)
        self.explorer_window.show()
        self.explorer_window.raise_()
        self.explorer_window.activateWindow()

    def open_settings(self):
        self.settings_window = SettingsWindow(self.sync_manager); self.settings_window.show()
        
    def show_all_memos(self):
        ms = self.sync_manager.load_local_memos()
        if not ms:
            self.create_empty_memo()
        else:
            for m in ms:
                self.create_new_memo(m, show_on_create=m.get('is_visible', True))
                
    def show_specific_memo(self, title: str):
        if title in self.memo_windows: 
            w = self.memo_windows[title]
            w.memo_data['is_visible'] = True
            self.notify_save(w.memo_data)
            w.show(); w.raise_(); w.activateWindow()
        else:
            for m in self.sync_manager.load_local_memos():
                if m.get('title') == title: 
                    m['is_visible'] = True
                    self.sync_manager.save_memo_locally(m)
                    self.create_new_memo(m, show_on_create=True)
                    break
                    
    def create_empty_memo(self):
        import uuid
        memo_id = str(uuid.uuid4())
        
        # 환경설정 기본값 가져오기
        cfg = getattr(self.sync_manager, 'settings', {})
        default_ln = cfg.get('default_show_line_numbers', False)
        default_bg = cfg.get('default_show_line_bg', False)
        default_color = cfg.get('default_memo_color', '#E0F2FE')
        
        # 중복되지 않는 고유한 새 메모 제목 생성
        existing_titles = [m.get('title') for m in self.sync_manager.load_local_memos()]
        base_title = "새 메모"
        title = base_title
        idx = 1
        while title in existing_titles:
            idx += 1
            title = f"{base_title} {idx}"
            
        memo_data = {
            'id': memo_id,
            'title': title,
            'content': '',
            'bg_color': default_color,
            'font_size': 11,
            'opacity': 1.0,
            'is_pinned': False,
            'is_visible': True,
            'position_x': 120 + (random.randint(0, 5) * 20),
            'position_y': 120 + (random.randint(0, 5) * 20),
            'width': 300,
            'height': 350,
            'show_line_numbers': default_ln,
            'show_line_bg': default_bg,
            'updated_at': datetime.datetime.now().isoformat()
        }
        
        # 로컬 저장소에 저장 및 화면에 생성
        self.sync_manager.save_memo_locally(memo_data)
        self.create_new_memo(memo_data, show_on_create=True)
        
        # 탐색기가 열려있다면 목록 새로고침
        if self.explorer_window and self.explorer_window.isVisible():
            self.explorer_window.refresh()
        
    def create_new_memo(self, m, show_on_create=False):
        t = m.get('title','Unknown')
        if t in self.memo_windows: 
            if show_on_create: self.memo_windows[t].show(); self.memo_windows[t].raise_()
        else: 
            w = MemoWindow(m, self.notify_save, self.delete_memo, self.sync_manager.rename_memo_locally, self.on_close)
            self.memo_windows[t] = w
            if show_on_create: w.show()
            
    def close_memo_window(self, t): [self.memo_windows[t].close() if t in self.memo_windows else None]
    
    def notify_save(self, m): 
        self.sync_manager.save_memo_locally(m)
        if self.explorer_window and self.explorer_window.isVisible():
            self.explorer_window.refresh()
            
    def on_close(self, w): t = w.memo_data.get('title'); [self.memo_windows.pop(t) if t in self.memo_windows else None]
    def delete_memo(self, w): t = w.memo_data.get('title','Unknown'); w.close(); self.sync_manager.delete_memo_locally(t); [self.explorer_window.refresh() if self.explorer_window else None]

class SettingsWindow(QWidget):
    def __init__(self, sm: Any):
        super().__init__(); self.sm = sm; self.colors = {"하늘색": "#E0F2FE", "연두색": "#DCFCE7", "노란색": "#FEF9C3", "분홍색": "#FCE7F3", "흰색": "#FFFFFF", "랜덤": "random"}; self.init_ui(); self.load()
    def init_ui(self):
        self.setWindowTitle("환경설정"); self.setFixedSize(450, 600); self.setStyleSheet("background: white; color: #000000; font-family: 'Malgun Gothic';")
        l = QVBoxLayout(self); l.setContentsMargins(20, 20, 20, 20)
        
        # --- [추가] 동기화 ON/OFF 옵션 ---
        self.sync_cb = QCheckBox("☁️ 구글 드라이브 동기화 사용 (해제 시 완벽한 로컬 모드)")
        self.sync_cb.setStyleSheet("font-weight: bold; color: #2563EB; margin-bottom: 10px;")
        l.addWidget(self.sync_cb)
        
        l.addWidget(QLabel("<b>GAS URL:</b>")); self.u = QLineEdit(); self.u.setStyleSheet("padding: 8px; border: 1px solid #CBD5E1; border-radius: 4px; color: #000000;"); l.addWidget(self.u)
        l.addWidget(QLabel("<b>저장 경로:</b>")); ph = QHBoxLayout(); self.p = QLineEdit(); self.p.setReadOnly(True); self.p.setStyleSheet("padding: 8px; border: 1px solid #CBD5E1; border-radius: 4px; background: #F8FAFC; color: #000000;")
        b = QPushButton("선택"); b.setStyleSheet("padding: 8px; background: #F1F5F9; border: 1px solid #CBD5E1; border-radius: 4px; color: #000000;"); b.clicked.connect(self.sel)
        ph.addWidget(self.p); ph.addWidget(b); l.addLayout(ph); l.addWidget(QLabel("<b>기본 색상:</b>"))
        
        self.c = QComboBox()
        for idx, (name, color_hex) in enumerate(self.colors.items()):
            self.c.addItem(name)
            if color_hex != "random":
                self.c.setItemData(idx, QColor(color_hex), Qt.ItemDataRole.BackgroundRole)
        self.c.setStyleSheet("padding: 8px; border: 1px solid #CBD5E1; border-radius: 4px; color: #000000;")
        l.addWidget(self.c)

        l.addWidget(QLabel("<b>동기화 주기:</b>")); self.s = QComboBox(); self.s.addItems(["1분","10분","30분","1시간"]); self.s.setStyleSheet("padding: 8px; border: 1px solid #CBD5E1; border-radius: 4px; color: #000000;")
        l.addWidget(self.s); self.a = QCheckBox("자동 시작"); l.addWidget(self.a)
        
        # [추가] 새 메모 기본 옵션
        self.cb_default_line_num = QCheckBox("최초 메모 실행 시 행번호 표시")
        l.addWidget(self.cb_default_line_num)
        self.cb_default_line_bg = QCheckBox("최초 메모 실행 시 줄노트 배경 표시")
        l.addWidget(self.cb_default_line_bg)
        
        l.addStretch()
        sb = QPushButton("설정 저장"); sb.setStyleSheet("background:#F0F9FF; color:#0369A1; padding:12px; font-weight:bold; border-radius:8px; border:1px solid #BAE6FD;"); sb.clicked.connect(self.save); l.addWidget(sb)

    def save(self):
        ns = {
            "use_sync": self.sync_cb.isChecked(),
            "drive_folder_id": self.u.text().strip(), 
            "local_memo_path": self.p.text().strip(), 
            "sync_interval_index": self.s.currentIndex(), 
            "auto_start": self.a.isChecked(), 
            "default_memo_color": list(self.colors.values())[self.c.currentIndex()],
            "default_show_line_numbers": self.cb_default_line_num.isChecked(), # 신규 추가 저장 항목
            "default_show_line_bg": self.cb_default_line_bg.isChecked()       # 신규 추가 저장 항목
        }
        self.sm.save_settings(ns); QMessageBox.information(self, "알림", "저장되었습니다.")

    def sel(self): p = QFileDialog.getExistingDirectory(self, "선택", self.p.text()); [self.p.setText(p) if p else None]
    def load(self):
        s = self.sm.settings
        self.sync_cb.setChecked(s.get("use_sync", True))
        self.u.setText(s.get("drive_folder_id",""))
        self.p.setText(str(self.sm.local_path))
        self.s.setCurrentIndex(s.get("sync_interval_index", 0))
        self.a.setChecked(s.get("auto_start", False))
        
        # [핵심 수정] 저장되어 있던 최초 메모 실행 시 행번호/줄노트 배경 옵션 값을 체크박스에 반영
        self.cb_default_line_num.setChecked(s.get("default_show_line_numbers", False))
        self.cb_default_line_bg.setChecked(s.get("default_show_line_bg", False))
        
        curr = s.get("default_memo_color", "#E0F2FE")
        [self.c.setCurrentIndex(i) for i, (n, c) in enumerate(self.colors.items()) if c == curr]