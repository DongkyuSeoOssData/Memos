import os
import json
import winreg
import random
import shutil
import traceback
from typing import Any, List, Dict
from pathlib import Path
from PyQt6.QtCore import QTimer, QThread, pyqtSignal, QObject
from PyQt6.QtWidgets import QSystemTrayIcon

class SyncWorker(QObject):
    finished = pyqtSignal(bool, str)

    def __init__(self, sync_manager):
        super().__init__()
        self.sm = sync_manager
        self.target_method = ""
        self.titles_to_delete = []

    def execute(self):
        try:
            if self.target_method == "run_push":
                self.run_push()
            elif self.target_method == "run_pull":
                self.run_pull()
            elif self.target_method == "run_delete_batch":
                self.run_delete_batch(self.titles_to_delete)
        except Exception as e:
            error_msg = f"동기화 치명적 오류: {str(e)}"
            print(traceback.format_exc())
            self.finished.emit(False, error_msg)

    def run_push(self):
        if not self.sm.drive_api.is_available():
            self.finished.emit(False, "환경설정에서 GAS URL을 먼저 입력해주세요.")
            return
        memos = self.sm.load_local_memos()
        count = 0
        for m in memos:
            title = m.get('title')
            if title:
                if self.sm.drive_api.upload_file(f"{title}.json", m):
                    count += 1
        if count > 0:
            self.finished.emit(True, f"{count}개의 메모 업로드 완료")
        else:
            self.finished.emit(True, "업로드 완료 (변경사항 없음)")

    def run_pull(self):
        if not self.sm.drive_api.is_available():
            self.finished.emit(False, "환경설정에서 GAS URL을 먼저 입력해주세요.")
            return
        files = self.sm.drive_api.list_files()
        count = 0
        for f in files:
            name = f.get("name")
            if name and name.endswith(".json"):
                content = self.sm.drive_api.download_file(name)
                if content:
                    data = json.loads(content) if isinstance(content, str) else content
                    self.sm.save_memo_locally(data)
                    count += 1
        self.finished.emit(True, f"클라우드에서 {count}개의 메모 가져오기 완료")

    def run_delete_batch(self, titles: List[str]):
        if not self.sm.drive_api.is_available():
            self.finished.emit(False, "환경설정에서 GAS URL 설정 누락")
            return
        success_count = 0
        for title in titles:
            if self.sm.drive_api.delete_file(f"{title}.json"):
                success_count += 1
        if success_count > 0:
            self.finished.emit(True, f"{success_count}개의 메모 클라우드 휴지통 이동 완료")


class SyncManager(QObject):
    def __init__(self, drive_api: Any):
        super().__init__()
        self.drive_api = drive_api
        self.base_path = Path.home() / ".memoit_custom"
        self.settings_path = self.base_path / "settings.json"
        self.ui_manager = None
        self.active_threads = [] 

        self.settings = self.load_settings()
        cp = self.settings.get("local_memo_path")
        self.local_path = Path(cp) if cp else self.base_path / "memos"
        self.local_path.mkdir(parents=True, exist_ok=True)
        self.trash_path = self.local_path / "trash_bin"
        self.trash_path.mkdir(parents=True, exist_ok=True)
        
        self.drive_api.set_web_app_url(self.settings.get("drive_folder_id", ""))
        self.sync_timer = QTimer()
        self.setup_timer()
        
        QTimer.singleShot(3000, self.sync_pull)
        QTimer.singleShot(8000, self.sync_push)

    def set_ui_manager(self, ui_manager):
        self.ui_manager = ui_manager

    def load_settings(self) -> Dict[str, Any]:
        defaults = {"drive_folder_id": "", "local_memo_path": str(Path.home() / ".memoit_custom" / "memos"), "sync_interval_index": 0, "auto_start": False, "default_memo_color": "#E0F2FE"}
        self.base_path.mkdir(parents=True, exist_ok=True)
        if self.settings_path.exists():
            try:
                with open(self.settings_path, "r", encoding="utf-8") as f:
                    return {**defaults, **json.load(f)}
            except: pass
        return defaults

    def save_settings(self, new_s: Dict[str, Any]) -> None:
        self.settings = new_s
        try:
            with open(self.settings_path, "w", encoding="utf-8") as f:
                json.dump(self.settings, f, ensure_ascii=False, indent=2)
            self.local_path = Path(self.settings.get("local_memo_path"))
            self.local_path.mkdir(parents=True, exist_ok=True)
            self.trash_path = self.local_path / "trash_bin"
            self.trash_path.mkdir(parents=True, exist_ok=True)
            self.drive_api.set_web_app_url(self.settings.get("drive_folder_id", ""))
            self.setup_timer()
        except: pass

    def setup_timer(self) -> None:
        intervals = [60, 600, 1800, 3600]
        idx = self.settings.get("sync_interval_index", 0)
        self.sync_timer.stop()
        try: self.sync_timer.timeout.disconnect()
        except: pass
        self.sync_timer.timeout.connect(self.sync_push)
        self.sync_timer.start(intervals[idx] * 1000)

    def load_local_memos(self) -> List[Dict[str, Any]]:
        memos = []
        if not self.local_path.exists(): return memos
        for f in self.local_path.glob("*.json"):
            if "trash_bin" in str(f): continue
            try:
                with open(f, "r", encoding="utf-8") as file:
                    m = json.load(file); m['title'] = f.stem; memos.append(m)
            except: pass
        return memos

    def load_trash_memos(self) -> List[Dict[str, Any]]:
        memos = []
        if not self.trash_path.exists(): return memos
        for f in self.trash_path.glob("*.json"):
            try:
                with open(f, "r", encoding="utf-8") as file:
                    m = json.load(file); m['title'] = f.stem; memos.append(m)
            except: pass
        return memos

    def restore_memo_locally(self, title: str) -> bool:
        src, dst = self.trash_path / f"{title}.json", self.local_path / f"{title}.json"
        try:
            if src.exists():
                if dst.exists(): dst.unlink()
                shutil.move(str(src), str(dst)); return True
        except: pass
        return False

    def save_memo_locally(self, data: Dict[str, Any]) -> None:
        f = self.local_path / f"{data.get('title', 'Untitled')}.json"
        try:
            with open(f, "w", encoding="utf-8") as file:
                json.dump(data, file, ensure_ascii=False, indent=2)
        except: pass

    def rename_memo_locally(self, ot: str, nt: str, data: Dict[str, Any]) -> bool:
        op, np = self.local_path / f"{ot}.json", self.local_path / f"{nt}.json"
        if np.exists() and ot != nt: return False
        try:
            if op.exists(): op.rename(np)
            data['title'] = nt; self.save_memo_locally(data); return True
        except: return False

    def delete_memo_locally(self, title: str) -> None:
        src, dst = self.local_path / f"{title}.json", self.trash_path / f"{title}.json"
        if src.exists():
            try:
                if dst.exists(): dst.unlink()
                shutil.move(str(src), str(dst))
            except: pass

    def delete_memos_cloud(self, titles: List[str]):
        worker = SyncWorker(self)
        worker.target_method = "run_delete_batch"
        worker.titles_to_delete = titles
        self._start_worker(worker)

    def sync_push(self) -> None:
        worker = SyncWorker(self)
        worker.target_method = "run_push"
        self._start_worker(worker)

    def sync_pull(self) -> None:
        worker = SyncWorker(self)
        worker.target_method = "run_pull"
        self._start_worker(worker)

    def _start_worker(self, worker):
        """파이썬 가비지 컬렉터(GC)에 의한 스레드 멈춤/증발을 막는 핵심 방어막"""
        thread = QThread()
        
        # [가장 중요한 픽스] 일꾼(worker) 객체가 메모리에서 증발하지 않도록 스레드에 강제 결속
        thread.worker = worker 
        
        worker.moveToThread(thread)
        thread.started.connect(worker.execute)
        
        worker.finished.connect(self.on_sync_finished)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        
        def cleanup():
            if thread in self.active_threads:
                self.active_threads.remove(thread)
                
        thread.finished.connect(cleanup)
        self.active_threads.append(thread)
        thread.start()

    def on_sync_finished(self, success, message):
        print(f"[동기화 로그] 성공: {success}, 내용: {message}")
        if self.ui_manager:
            # 1. 탐색기 창이 열려있으면 무조건 예쁜 커스텀 토스트 메시지로 띄움
            if self.ui_manager.explorer_window and self.ui_manager.explorer_window.isVisible():
                self.ui_manager.explorer_window.show_toast(message)
            
            # 2. 탐색기가 닫혀있는 백그라운드 상태일 때
            else:
                # 성공(True)했을 때는 윈도우 알림을 띄우지 않고 완전히 침묵함 (사용자 방해 금지)
                if not success:
                    # 실패/에러 시에만 어쩔 수 없이 윈도우 트레이 알림으로 알려줌
                    self.ui_manager.tray_icon.showMessage(
                        "Memos 동기화 오류", 
                        message, 
                        QSystemTrayIcon.MessageIcon.Warning, 
                        3000
                    )
                
            if success and "가져오기 완료" in message and self.ui_manager.explorer_window:
                self.ui_manager.explorer_window.refresh()