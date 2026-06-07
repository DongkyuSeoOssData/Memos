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
from PyQt6.QtCore import Qt, QPoint, QSize, QTimer
from PyQt6.QtGui import QIcon, QAction, QColor, QShortcut, QKeySequence, QFont, QPixmap, QPainter, QPainterPath, QTextListFormat

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
            
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint) 
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


class MemoWindow(QWidget):
    def __init__(self, m: Dict[str, Any], sc: Any, dc: Any, rc: Any, cc: Any):
        super().__init__()
        self.memo_data = m; self.save_callback = sc; self.delete_callback = dc; self.rename_callback = rc; self.close_callback = cc; self._old_pos = None
        self._is_updating_from_explorer = False
        self._is_rolled_up = False 
        self._normal_height = 400
        self.setup_ui(); self.apply_data(); self.setMouseTracking(True); self.text_edit.setMouseTracking(True); QShortcut(QKeySequence("Ctrl+S"), self).activated.connect(self.manual_save)
    
    def apply_text_stroke(self, widget):
        eff = QGraphicsDropShadowEffect(self)
        eff.setBlurRadius(3)
        eff.setColor(QColor(255, 255, 255, 255))
        eff.setOffset(0, 0)
        widget.setGraphicsEffect(eff)
        
    def setup_ui(self) -> None:
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground); layout = QVBoxLayout(self); layout.setContentsMargins(5, 5, 5, 5)
        self.bg = QWidget(); self.bg.setObjectName("MemoBackground"); bg_l = QVBoxLayout(self.bg); layout.addWidget(self.bg)
        
        ctrl = QHBoxLayout(); self.title_edit = QLineEdit(); self.title_edit.setStyleSheet("border:none; background:transparent; color:#000000; font-weight:bold; font-size:12pt; font-family: 'Malgun Gothic';")
        self.title_edit.editingFinished.connect(self.handle_rename); self.title_edit.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu); self.title_edit.customContextMenuRequested.connect(self.show_menu)
        
        self.btn_pin = QPushButton("⚲"); self.btn_min = QPushButton("_"); self.btn_close = QPushButton("✕")
        for b in [self.btn_pin, self.btn_min, self.btn_close]:
            b.setFixedSize(26, 26)
            b.setStyleSheet("border:none; color:#000000; background:transparent; font-weight:bold; font-size:14pt;")
            self.apply_text_stroke(b)
            
        self.btn_pin.clicked.connect(self.toggle_pin); self.btn_min.clicked.connect(self.toggle_rollup); self.btn_close.clicked.connect(self.close)
        ctrl.addWidget(self.title_edit); ctrl.addStretch(); ctrl.addWidget(self.btn_pin); ctrl.addWidget(self.btn_min); ctrl.addWidget(self.btn_close); bg_l.addLayout(ctrl)
        
        self.content_container = QWidget()
        cc_layout = QVBoxLayout(self.content_container); cc_layout.setContentsMargins(0,0,0,0)
        
        self.text_edit = QTextEdit(); self.text_edit.setStyleSheet("border:none; background:transparent; color:#000000; font-size:11pt; font-family: 'Malgun Gothic';")
        self.text_edit.textChanged.connect(self.update_content); self.text_edit.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu); self.text_edit.customContextMenuRequested.connect(self.show_menu)
        cc_layout.addWidget(self.text_edit)
        
        self.fmt_bar = QHBoxLayout()
        self.btn_bullet = QPushButton("•"); self.btn_num = QPushButton("1."); self.btn_indent = QPushButton("⇥"); self.btn_outdent = QPushButton("⇤")
        for b in [self.btn_bullet, self.btn_num, self.btn_indent, self.btn_outdent]:
            b.setFixedSize(26, 26); b.setStyleSheet("border:none; color:#475569; font-weight:bold; font-size:12pt; background: transparent;"); b.setCursor(Qt.CursorShape.PointingHandCursor); self.fmt_bar.addWidget(b)
        self.fmt_bar.addStretch()
        
        self.btn_bullet.clicked.connect(self.apply_bullet); self.btn_num.clicked.connect(self.apply_number); self.btn_indent.clicked.connect(self.apply_indent); self.btn_outdent.clicked.connect(self.apply_outdent)
        cc_layout.addLayout(self.fmt_bar)
        bg_l.addWidget(self.content_container)
        
        # --- [중요 픽스] 창 조절 핸들을 레이아웃 밖, 창 전체의 우측 하단에 고정 배치 ---
        self.grip = QSizeGrip(self)
        
    def resizeEvent(self, event):
        super().resizeEvent(event)
        # 언제나 창 우측 하단 끄트머리에 핸들이 오도록 위치 보정
        if hasattr(self, 'grip'):
            self.grip.move(self.width() - 20, self.height() - 20)
            self.grip.resize(12, 12)
        
    def show_menu(self, pos):
        menu = QMenu(self); menu.setStyleSheet("QMenu { background: white; color: #000000; border: 1px solid #CBD5E1; border-radius: 4px; } QMenu::item:selected { background-color: #F1F5F9; }")
        menu.addAction("저장 (Ctrl+S)").triggered.connect(self.manual_save); menu.addSeparator(); cm = menu.addMenu("색상 변경")
        for n, c in {"하늘색": "#E0F2FE", "연두색": "#DCFCE7", "노란색": "#FEF9C3", "분홍색": "#FCE7F3", "흰색": "#FFFFFF"}.items(): cm.addAction(n).triggered.connect(lambda checked, code=c: self.change_color(code))
        menu.addSeparator(); menu.addAction("고정 토글").triggered.connect(self.toggle_pin); menu.addAction("삭제 (휴지통)").triggered.connect(lambda: self.delete_callback(self)); menu.exec(self.sender().mapToGlobal(pos))
        
    def toggle_rollup(self):
        # --- [중요 픽스] 접었을 때 딱 글씨 크기(40px)로만 세로 높이 고정 및 가로 조절 개방 ---
        if not self._is_rolled_up:
            self._normal_height = self.height()
            self.content_container.hide()
            
            # 높이 제한을 풀고 40px로 축소
            self.setMinimumHeight(0)
            self.setMaximumHeight(16777215)
            self.resize(self.width(), 50)
            
            # 접힌 상태에서는 세로 고정, 가로만 조절되도록 제약 조건 부여
            self.setMinimumHeight(50)
            self.setMaximumHeight(50)
            
            self._is_rolled_up = True
            self.btn_min.setText("□") 
        else:
            # 펼칠 때 가로/세로 모두 조절되도록 제약 해제
            self.setMinimumHeight(0)
            self.setMaximumHeight(16777215)
            self.content_container.show()
            self.resize(self.width(), self._normal_height)
            self.setMinimumSize(200, 150)
            
            self._is_rolled_up = False
            self.btn_min.setText("_")
            
    def manual_save(self): self.update_content(); self.save_callback(self.memo_data)
    
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
        f = Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool; [f := f | Qt.WindowType.WindowStaysOnTopHint if self.memo_data.get('is_pinned') else f]
        self.setWindowFlags(f); bg = self.memo_data.get('bg_color', '#E0F2FE')
        self.bg.setStyleSheet(f"QWidget#MemoBackground {{ background-color: {bg}; border: 1px solid rgba(0,0,0,0.1); border-radius: 12px; }}")
        
        self.title_edit.setText(self.memo_data.get('title',''))
        self.title_edit.setCursorPosition(0)
        
        self._is_updating_from_explorer = True
        content = self.memo_data.get('content','')
        if "<html" in content or "<body" in content: self.text_edit.setHtml(content)
        else: self.text_edit.setPlainText(content)
        self._is_updating_from_explorer = False
            
        self.setGeometry(self.memo_data.get('position_x',100), self.memo_data.get('position_y',100), self.memo_data.get('width',500), self.memo_data.get('height',400))
        
        is_pinned = self.memo_data.get('is_pinned', False)
        if is_pinned:
            self.btn_pin.setStyleSheet("border:none; color:#2563EB; background:transparent; font-weight:bold; font-size:14pt;")
        else:
            self.btn_pin.setStyleSheet("border:none; color:#000000; background:transparent; font-weight:bold; font-size:14pt;")
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
        
    def handle_rename(self):
        nt = self.title_edit.text().strip(); ot = self.memo_data.get('title','')
        if not nt or nt == ot: return
        nt = re.sub(r'[\\/*?:"<>|]', "", nt)
        if self.rename_callback(ot, nt, self.memo_data): 
            self.memo_data['title'] = nt
            self.title_edit.setCursorPosition(0) 
            self.save_callback(self.memo_data)
        else: QMessageBox.warning(self, "중복", f"'{nt}' 존재."); self.title_edit.setText(ot); self.title_edit.setCursorPosition(0)
        
    def toggle_pin(self): self.memo_data['is_pinned'] = not self.memo_data.get('is_pinned', False); self.apply_data(); self.show(); self.save_callback(self.memo_data)
    
    def update_content(self):
        if self._is_updating_from_explorer: return
        self.memo_data['content'] = self.text_edit.toHtml()
        self.memo_data['updated_at'] = datetime.datetime.now().isoformat(); self.save_callback(self.memo_data)
        
    def change_color(self, c): self.memo_data['bg_color'] = c; self.apply_data(); self.save_callback(self.memo_data)
    
    def mousePressEvent(self, e): 
        if e.button() == Qt.MouseButton.LeftButton: self._old_pos = e.globalPosition().toPoint()
            
    def mouseMoveEvent(self, e):
        if self._old_pos: 
            d = e.globalPosition().toPoint() - self._old_pos
            self.move(self.x() + d.x(), self.y() + d.y())
            self._old_pos = e.globalPosition().toPoint()
            
    def mouseReleaseEvent(self, e): 
        self._old_pos = None
        self.memo_data['position_x'], self.memo_data['position_y'] = self.x(), self.y()
        self.memo_data['width'] = self.width()
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
        
        menu = QMenu(); menu.setStyleSheet("background: white; color: #000000; border: 1px solid #CBD5E1;"); menu.addAction("➕ 새 메모").triggered.connect(self.create_empty_memo); menu.addAction("📄 메모 탐색기").triggered.connect(self.open_memo_explorer); menu.addAction("⇄ 지금 동기화").triggered.connect(self.sync_manager.sync_push); self.toggle_action = menu.addAction("모두 숨기기"); self.toggle_action.triggered.connect(self.toggle_all); menu.addSeparator(); menu.addAction("⚙ 환경설정").triggered.connect(self.open_settings); menu.addSeparator(); menu.addAction("✕ 종료").triggered.connect(QApplication.quit); self.tray_icon.setContextMenu(menu); self.tray_icon.show()
        
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
        t = f"Memo_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}"; c = self.sync_manager.settings.get("default_memo_color","#E0F2FE"); c = random.choice(["#E0F2FE","#DCFCE7","#FEF9C3","#FCE7F3","#FFFFFF"]) if c=="random" else c
        self._last_pos += QPoint(30, 30); [setattr(self, '_last_pos', QPoint(100, 100)) if self._last_pos.x() > 500 else None]
        m = {"title": t, "content": "", "position_x": self._last_pos.x(), "position_y": self._last_pos.y(), "width": 500, "height": 400, "bg_color": c, "is_pinned": True, "is_visible": True, "updated_at": datetime.datetime.now().isoformat()}
        self.sync_manager.save_memo_locally(m)
        self.create_new_memo(m, show_on_create=True)
        if self.explorer_window: self.explorer_window.refresh()
        
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
        self.setWindowTitle("환경설정"); self.setFixedSize(450, 520); self.setStyleSheet("background: white; color: #000000; font-family: 'Malgun Gothic';")
        l = QVBoxLayout(self); l.setContentsMargins(20, 20, 20, 20)
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
        l.addWidget(self.s); self.a = QCheckBox("자동 시작"); l.addWidget(self.a); l.addStretch()
        sb = QPushButton("설정 저장"); sb.setStyleSheet("background:#F0F9FF; color:#0369A1; padding:12px; font-weight:bold; border-radius:8px; border:1px solid #BAE6FD;"); sb.clicked.connect(self.save); l.addWidget(sb)
    def sel(self): p = QFileDialog.getExistingDirectory(self, "선택", self.p.text()); [self.p.setText(p) if p else None]
    def load(self):
        s = self.sm.settings; self.u.setText(s.get("drive_folder_id","")); self.p.setText(str(self.sm.local_path)); self.s.setCurrentIndex(s.get("sync_interval_index",0)); self.a.setChecked(s.get("auto_start",False))
        curr = s.get("default_memo_color","#E0F2FE"); [self.c.setCurrentIndex(i) for i, (n, c) in enumerate(self.colors.items()) if c == curr]
    def save(self):
        ns = {"drive_folder_id": self.u.text().strip(), "local_memo_path": self.p.text().strip(), "sync_interval_index": self.s.currentIndex(), "auto_start": self.a.isChecked(), "default_memo_color": list(self.colors.values())[self.c.currentIndex()]}
        self.sm.save_settings(ns); QMessageBox.information(self, "알림", "저장되었습니다.")