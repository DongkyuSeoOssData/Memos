import os
import json
import winreg
import random
import shutil
import traceback
import base64
import hashlib
from typing import Any, List, Dict
from pathlib import Path
from PyQt6.QtCore import QTimer, QThread, pyqtSignal, QObject
from PyQt6.QtWidgets import QSystemTrayIcon
from cryptography.fernet import Fernet

# [보안] 로컬에만 존재하고 깃에는 올라가지 않는 비상용 마스터 키 볼트 연동 (선택적)
try:
    from secure_vault import EmergencyVault
except ImportError:
    class EmergencyVault:
        def __init__(self): pass
        def decrypt(self, encrypted_bytes: bytes) -> dict: return {}


class UserKeyManager:
    """사용자 지정 키 기반 암/복호화 핸들러"""
    def __init__(self, raw_user_pass: str = "DefaultUserKey"):
        self.cipher = self._create_cipher(raw_user_pass)

    def _create_cipher(self, secret: str) -> Fernet:
        kdf = hashlib.pbkdf2_hmac(
            'sha256',
            secret.encode('utf-8'),
            b'user_dynamic_salt_v1',
            100_000
        )
        key = base64.urlsafe_b64encode(kdf)
        return Fernet(key)

    def encrypt(self, data_dict: dict) -> bytes:
        json_str = json.dumps(data_dict, ensure_ascii=False)
        return self.cipher.encrypt(json_str.encode('utf-8'))

    def decrypt(self, encrypted_bytes: bytes) -> dict:
        try:
            decrypted_bytes = self.cipher.decrypt(encrypted_bytes)
            return json.loads(decrypted_bytes.decode('utf-8'))
        except Exception:
            return {}


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
        
        # 설정 먼저 로드
        self.settings = self.load_settings()
        
        # [핵심] 최초 실행이거나 사용자 키가 기본값인 경우 입력 팝업 띄우기
        user_pass = self.settings.get("user_secret_key", "DefaultUserKey")
        if user_pass == "DefaultUserKey":
            user_pass = self._prompt_for_user_key()
            self.settings["user_secret_key"] = user_pass
            self.save_settings(self.settings)

        # 사용자 지정 키 핸들러 초기화
        self.encryptor = UserKeyManager(user_pass)
        self.emergency_vault = EmergencyVault()

        self.ui_manager = None
        self.active_threads = [] 

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

    def _prompt_for_user_key(self) -> str:
        """최초 실행 시 사용자로부터 암호화 키를 입력받는 다이얼로그"""
        from PyQt6.QtWidgets import QInputDialog, QLineEdit
        
        # 다이얼로그가 안정적으로 뜨도록 반복 혹은 기본값 처리
        while True:
            text, ok = QInputDialog.getText(
                None, 
                "메모 보안 설정", 
                "메모를 암호화할 비밀번호(개인 키)를 입력하세요:", 
                QLineEdit.EchoMode.Password, 
                ""
            )
            if ok and text.strip():
                return text.strip()
            # 강제로 닫거나 입력을 안 한 경우 기본값으로 방어
            if not ok:
                return "DefaultUserKey"

    def set_ui_manager(self, ui_manager):
        self.ui_manager = ui_manager

    def load_settings(self) -> Dict[str, Any]:
        defaults = {
            "use_sync": True, 
            "drive_folder_id": "", 
            "local_memo_path": str(Path.home() / ".memoit_custom" / "memos"), 
            "sync_interval_index": 0, 
            "auto_start": False, 
            "default_memo_color": "#E0F2FE",
            "user_secret_key": "DefaultUserKey"
        }
        self.base_path.mkdir(parents=True, exist_ok=True)
        if self.settings_path.exists():
            try:
                with open(self.settings_path, "r", encoding="utf-8") as f:
                    return {**defaults, **json.load(f)}
            except: pass
        return defaults

    def save_settings(self, new_s: Dict[str, Any]) -> None:
        self.settings = new_s
        # 사용자 키가 변경되었을 경우 암호화 핸들러 동적 갱신
        new_pass = self.settings.get("user_secret_key", "DefaultUserKey")
        self.encryptor = UserKeyManager(new_pass)

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
        
        if self.settings.get("use_sync", True):
            self.sync_timer.timeout.connect(self.sync_push)
            self.sync_timer.start(intervals[idx] * 1000)

    def load_local_memos(self) -> List[Dict[str, Any]]:
        memos = []
        if not self.local_path.exists(): return memos
        for f in self.local_path.glob("*.json"):
            if "trash_bin" in str(f): continue
            try:
                with open(f, "rb") as file:
                    file_bytes = file.read()
                
                # 1순위: 사용자 지정 키로 복호화 시도
                m = self.encryptor.decrypt(file_bytes)
                # 2순위 (실패 시): 비상용 마스터 키 볼트로 복호화 시도
                if not m:
                    m = self.emergency_vault.decrypt(file_bytes)
                # 3순위 (구버전 평문 호환): 일반 JSON 파싱 시도
                if not m:
                    try:
                        m = json.loads(file_bytes.decode('utf-8'))
                    except:
                        pass
                
                if m:
                    m['title'] = f.stem
                    memos.append(m)
            except: pass
        return memos

    def load_trash_memos(self) -> List[Dict[str, Any]]:
        memos = []
        if not self.trash_path.exists(): return memos
        for f in self.trash_path.glob("*.json"):
            try:
                with open(f, "rb") as file:
                    file_bytes = file.read()
                
                m = self.encryptor.decrypt(file_bytes)
                if not m:
                    m = self.emergency_vault.decrypt(file_bytes)
                if not m:
                    try:
                        m = json.loads(file_bytes.decode('utf-8'))
                    except:
                        pass
                
                if m:
                    m['title'] = f.stem
                    memos.append(m)
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
            encrypted_bytes = self.encryptor.encrypt(data)
            with open(f, "wb") as file:
                file.write(encrypted_bytes)
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
        if not self.settings.get("use_sync", True): return 
        worker = SyncWorker(self)
        worker.target_method = "run_delete_batch"
        worker.titles_to_delete = titles
        self._start_worker(worker)

    def sync_push(self) -> None:
        if not self.settings.get("use_sync", True):
            self.on_sync_finished(True, "로컬 모드로 작동 중입니다. (동기화 OFF)")
            return
        worker = SyncWorker(self)
        worker.target_method = "run_push"
        self._start_worker(worker)

    def sync_pull(self) -> None:
        if not self.settings.get("use_sync", True):
            self.on_sync_finished(True, "로컬 모드로 작동 중입니다. (동기화 OFF)")
            return
        worker = SyncWorker(self)
        worker.target_method = "run_pull"
        self._start_worker(worker)

    def _start_worker(self, worker):
        thread = QThread()
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
            if self.ui_manager.explorer_window and self.ui_manager.explorer_window.isVisible():
                self.ui_manager.explorer_window.show_toast(message)
            else:
                if not success:
                    self.ui_manager.tray_icon.showMessage(
                        "Memos 동기화 오류", 
                        message, 
                        QSystemTrayIcon.MessageIcon.Warning, 
                        3000
                    )
            if success and "가져오기 완료" in message and self.ui_manager.explorer_window:
                self.ui_manager.explorer_window.refresh()