from utils.crypto_utils import dpapi_encrypt, dpapi_decrypt
from utils.text_utils import clean_plain_text
from core.sync_worker import SyncWorker
import traceback
import sys
import json
import shutil
import uuid
import winreg
from datetime import datetime
from typing import Any, List, Dict, Optional
from pathlib import Path
from PyQt6.QtCore import QTimer, QThread, pyqtSignal, QObject
from PyQt6.QtWidgets import QSystemTrayIcon
from crypto_manager import CryptoManager



def set_auto_start(enable: bool) -> None:
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    app_name = "MemoitApp"
    executable = sys.executable if getattr(sys, 'frozen', False) else f'"{sys.executable}" "{sys.argv[0]}"'
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_ALL_ACCESS)
        if enable:
            winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, executable)
        else:
            try:
                winreg.DeleteValue(key, app_name)
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
    except Exception as e:
        print(f"Auto start registry error: {e}")

class SyncManager(QObject):
    DEFAULT_SETTINGS: Dict[str, Any] = {
        "use_sync": False,
        "drive_folder_id": "",
        "local_memo_path": str(Path.home() / ".memoit_custom" / "memos"),
        "sync_interval_index": 0,
        "auto_start": False,
        "auto_login": False,
        "default_memo_color": "#E0F2FE",
        "default_font_family": "D2Coding",
        "default_code_font_family": "D2Coding",
        "default_code_lang": "JSON",
        "default_code_theme": "dark",
        "auto_eng_kor_convert": True,
        "default_gen_line_numbers": False,
        "default_gen_line_bg": False,
        "default_code_line_numbers": True,
        "default_code_line_bg": False,
        "default_show_line_numbers": False,
        "default_show_line_bg": False,
        "default_is_pinned": False,
        "trash_auto_delete_days": 0,
        "app_theme": "white",
        "default_memo_opacity": 1.0,
        "default_memo_width": 350,
        "default_memo_height": 380,
        "default_code_memo_width": 700,
        "default_code_memo_height": 380,
        "explorer_is_pinned": True,
        "shortcuts": {
            "eng_kor_convert": "Ctrl+Alt+E",
            "toggle_fmt_bar": "Ctrl+Shift+T",
            "copy_all": "Ctrl+Shift+C",
            "format_code": "Ctrl+Shift+F",
            "new_memo": "Ctrl+N",
            "new_code_memo": "Ctrl+Shift+N",
            "save": "Ctrl+S",
            "search": "Ctrl+F",
            "rename": "F2",
            "open_explorer": "Ctrl+E",
            "replace": "Ctrl+H",
            "toggle_pin": "Ctrl+P",
            "toggle_rollup": "Ctrl+M",
            "delete_memo": "Ctrl+D",
            "toggle_code_theme": "Ctrl+Shift+L",
            "arrange_rolled_memos": "Ctrl+Alt+R",
            "arrange_all_memos": "Ctrl+Alt+A"
        }
    }

    def __init__(self, drive_api: Any) -> None:
        super().__init__()
        self.drive_api = drive_api
        self.crypto = CryptoManager()
        self.session_password: Optional[str] = None
        
        self.base_path = Path.home() / ".memoit_custom"
        self.settings_path = self.base_path / "settings.json"
        self.vault_path = self.base_path / "user_vault.json"
        self.error_log_path = self.base_path / "error.log"
        
        self.settings = self.load_settings()

        self.ui_manager: Any = None
        self.active_threads: List[QThread] = [] 

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

    def has_vault(self) -> bool:
        return self.vault_path.exists()

    def create_vault(self, password: str) -> bool:
        try:
            self.base_path.mkdir(parents=True, exist_ok=True)
            verification_payload = self.crypto.encrypt_text("MEMOIT_VAULT_TEST_VERIFICATION", password)
            with open(self.vault_path, "w", encoding="utf-8") as f:
                json.dump(verification_payload, f, ensure_ascii=False, indent=2)
            self.session_password = password
            return True
        except Exception as e:
            self.log_error(f"암호 보관함 생성 실패: {e}", e)
            return False

    def verify_and_login(self, password: str) -> bool:
        if not self.has_vault():
            return False
        try:
            with open(self.vault_path, "r", encoding="utf-8") as f:
                vault_data = json.load(f)
            decrypted = self.crypto.decrypt_text(vault_data, password)
            if decrypted == "MEMOIT_VAULT_TEST_VERIFICATION":
                self.session_password = password
                return True
        except Exception as e:
            self.log_error(f"비밀번호 검증 오류: {e}", e)
        return False

    def try_auto_login(self) -> bool:
        if not self.settings.get("auto_login", False):
            return False
        token = self.settings.get("saved_pwd_token", "")
        if not token:
            return False
        saved_pwd = dpapi_decrypt(token)
        if saved_pwd and self.verify_and_login(saved_pwd):
            return True
        return False

    def save_remembered_password(self, password: str, auto_login: bool) -> None:
        self.settings["auto_login"] = auto_login
        if auto_login and password:
            self.settings["saved_pwd_token"] = dpapi_encrypt(password)
        else:
            self.settings["saved_pwd_token"] = ""
        self.save_settings(self.settings)

    def verify_otp_unlock(self, otp_code: str) -> bool:
        if self.crypto.verify_otp(otp_code):
            self.session_password = "__MASTER_OTP_UNLOCKED__"
            return True
        return False

    def reset_password_with_otp(self, otp_code: str, new_password: str) -> bool:
        if not self.crypto.verify_otp(otp_code):
            return False
        
        memos = self.load_local_memos()
        if self.create_vault(new_password):
            for m in memos:
                self.save_memo_locally(m)
            return True
        return False

    def is_unlocked(self) -> bool:
        return (self.session_password is not None) or (not self.has_vault())

    def log_error(self, message: str, exc: Optional[Exception] = None) -> None:
        try:
            self.base_path.mkdir(parents=True, exist_ok=True)
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            log_entry = f"[{now_str}] {message}\n"
            if exc:
                log_entry += f"{traceback.format_exc()}\n"
            with open(self.error_log_path, "a", encoding="utf-8") as f:
                f.write(log_entry)
        except Exception:
            pass

    def set_ui_manager(self, ui_manager: Any) -> None:
        self.ui_manager = ui_manager

    def load_settings(self) -> Dict[str, Any]:
        defaults = dict(self.DEFAULT_SETTINGS)
        self.base_path.mkdir(parents=True, exist_ok=True)
        if self.settings_path.exists():
            try:
                with open(self.settings_path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    loaded_shortcuts = loaded.get("shortcuts", {})
                    merged_shortcuts = {**defaults.get("shortcuts", {}), **loaded_shortcuts}
                    return {**defaults, **loaded, "shortcuts": merged_shortcuts}
            except Exception as e:
                self.log_error("설정 파일 로드 실패", e)
        return defaults

    def save_settings(self, new_s: Dict[str, Any]) -> None:
        self.settings = new_s
        try:
            with open(self.settings_path, "w", encoding="utf-8") as f:
                json.dump(self.settings, f, ensure_ascii=False, indent=2)
            self.local_path = Path(self.settings.get("local_memo_path", str(self.base_path / "memos")))
            self.local_path.mkdir(parents=True, exist_ok=True)
            self.trash_path = self.local_path / "trash_bin"
            self.trash_path.mkdir(parents=True, exist_ok=True)
            self.drive_api.set_web_app_url(self.settings.get("drive_folder_id", ""))
            
            set_auto_start(self.settings.get("auto_start", False))
            self.setup_timer()
        except Exception as e:
            self.log_error("설정 파일 저장 실패", e)

    def setup_timer(self) -> None:
        intervals = [60, 600, 1800, 3600]
        idx = self.settings.get("sync_interval_index", 0)
        idx = max(0, min(idx, len(intervals) - 1))
        self.sync_timer.stop()
        try:
            self.sync_timer.timeout.disconnect()
        except Exception:
            pass
        
        if self.settings.get("use_sync", True):
            self.sync_timer.timeout.connect(self.sync_push)
            self.sync_timer.start(intervals[idx] * 1000)

    def load_local_memos(self) -> List[Dict[str, Any]]:
        memos: List[Dict[str, Any]] = []
        seen_ids = set()
        
        if not self.local_path.exists(): 
            return memos
            
        for f in list(self.local_path.glob("*.json")):
            if "trash_bin" in str(f): 
                continue
            try:
                with open(f, "r", encoding="utf-8") as file:
                    m = json.load(file)
                
                if isinstance(m, dict):
                    memo_id = m.get('id')
                    if not memo_id or len(memo_id) < 8:
                        memo_id = str(uuid.uuid4())
                        m['id'] = memo_id

                    if memo_id in seen_ids:
                        continue

                    # 휴지통에 동일 ID나 파일명이 이미 존재하는 경우 (삭제 후 잔존한 껍데기 파일 자동 삭제)
                    if (self.trash_path / f.name).exists() or (self.trash_path / f"{memo_id}.json").exists():
                        try:
                            f.unlink()
                        except Exception:
                            pass
                        continue

                    seen_ids.add(memo_id)
                    
                    raw_content = m.get('content')
                    needs_re_encryption = False

                    if isinstance(raw_content, dict):
                        if raw_content.get("is_encrypted"):
                            try:
                                decrypted_content = self.crypto.decrypt_text(raw_content, self.session_password)
                            except Exception:
                                decrypted_content = "[복호화 실패 메모]"
                        else:
                            decrypted_content = str(raw_content.get("content", ""))
                    else:
                        decrypted_content = str(raw_content) if raw_content is not None else ""
                        needs_re_encryption = True

                    m['content'] = decrypted_content
                    
                    # 0자 내용인 빈 초안 메모는 디스크에서 자동으로 깔끔히 청소 및 제외
                    if m.get('is_draft') and not m.get('is_manually_saved') and not clean_plain_text(decrypted_content):
                        try:
                            f.unlink()
                        except Exception:
                            pass
                        continue

                    memos.append(m)

                    expected_file = self.local_path / f"{memo_id}.json"
                    if (needs_re_encryption or f.name != expected_file.name) and self.is_unlocked():
                        self.save_memo_locally(m)
                        if f.name != expected_file.name:
                            try:
                                f.unlink()
                            except Exception as e:
                                self.log_error(f"구버전 레거시 메모 파일 정리 실패 ({f.name}): {e}", e)
            except Exception as e:
                self.log_error(f"로컬 메모 파일 읽기 에러 ({f.name}): {e}", e)
                
        return memos

    def load_trash_memos(self) -> List[Dict[str, Any]]:
        memos: List[Dict[str, Any]] = []
        if not self.trash_path.exists(): return memos
        for f in list(self.trash_path.glob("*.json")):
            try:
                with open(f, "r", encoding="utf-8") as file:
                    m = json.load(file)
                
                if isinstance(m, dict):
                    if 'id' not in m:
                        m['id'] = f.stem
                        
                    raw_content = m.get('content')
                    if isinstance(raw_content, dict):
                        if raw_content.get("is_encrypted"):
                            try:
                                m['content'] = self.crypto.decrypt_text(raw_content, self.session_password)
                            except Exception:
                                m['content'] = "[암호화된 복호화 실패 메모]"
                        else:
                            m['content'] = str(raw_content.get("content", ""))
                    else:
                        m['content'] = str(raw_content) if raw_content is not None else ""
                    memos.append(m)
            except Exception as e:
                self.log_error(f"휴지통 메모 읽기 에러 ({f.name}): {e}", e)
        return memos

    def restore_memo_locally(self, memo_id: str) -> bool:
        src = self.trash_path / f"{memo_id}.json"
        dst = self.local_path / f"{memo_id}.json"
        try:
            if src.exists():
                if dst.exists(): dst.unlink()
                shutil.move(str(src), str(dst))
                return True
        except Exception as e:
            self.log_error(f"로컬 메모 복구 실패 ({memo_id}): {e}", e)
        return False

    def save_memo_locally(self, data: Dict[str, Any]) -> bool:
        memo_id = data.get('id')
        if not memo_id:
            memo_id = str(uuid.uuid4())
            data['id'] = memo_id

        plain_content = str(data.get('content', ''))
        plain_text = clean_plain_text(plain_content)

        # 미작성 빈 초안 메모(is_draft == True, 내용 없음, 수동저장 안함)는 디스크 저장을 차단하며 기존 파일이 있으면 파기
        if data.get('is_draft') and not data.get('is_manually_saved') and not plain_text:
            f = self.local_path / f"{memo_id}.json"
            if f.exists():
                try:
                    f.unlink()
                except Exception:
                    pass
            return False

        memo_to_save = dict(data)
        encrypted_payload = self.crypto.encrypt_text(plain_content, self.session_password)
        memo_to_save['content'] = encrypted_payload

        f = self.local_path / f"{memo_id}.json"
        try:
            with open(f, "w", encoding="utf-8") as file:
                json.dump(memo_to_save, file, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            self.log_error(f"로컬 메모 저장 실패 ({memo_id}): {e}", e)
            return False

    def rename_memo_locally(self, ot: str, nt: str, data: Dict[str, Any]) -> bool:
        try:
            data['title'] = nt
            self.save_memo_locally(data)
            return True
        except Exception as e:
            self.log_error(f"메모 제목 변경 실패 ({ot} -> {nt}): {e}", e)
            return False

    def delete_memo_locally(self, memo_id: str, title: Optional[str] = None) -> None:
        if not memo_id: return
        self.trash_path.mkdir(parents=True, exist_ok=True)
        
        # 1. ID 기반 파일 연동 이동
        src = self.local_path / f"{memo_id}.json"
        dst = self.trash_path / f"{memo_id}.json"
        
        if src.exists():
            try:
                if dst.exists(): dst.unlink()
                shutil.move(str(src), str(dst))
            except Exception as e:
                self.log_error(f"로컬 메모 휴지통 이동 실패 ({memo_id}): {e}", e)

        # 2. 제목, ID 및 파일명 기반 레거시/중복 파생 파일 전수 수거 및 휴지통 이동
        if self.local_path.exists():
            for f in list(self.local_path.glob("*.json")):
                if "trash_bin" in str(f) or f.is_dir(): continue
                try:
                    with open(f, "r", encoding="utf-8") as file:
                        m_data = json.load(file)
                    if isinstance(m_data, dict):
                        file_id = m_data.get('id')
                        file_title = m_data.get('title')
                        if file_id == memo_id or (title and file_title == title) or (f.stem == memo_id) or (title and f.stem == title):
                            target_dst = self.trash_path / f.name
                            if target_dst.exists(): target_dst.unlink()
                            shutil.move(str(f), str(target_dst))
                except Exception:
                    pass

    def empty_trash_locally(self) -> int:
        count = 0
        if self.trash_path.exists():
            for f in list(self.trash_path.glob("*.json")):
                try:
                    f.unlink()
                    count += 1
                except Exception:
                    pass
        return count

    def delete_memos_cloud(self, ids: List[str]) -> None:
        if not self.settings.get("use_sync", True): return 
        worker = SyncWorker(self)
        worker.target_method = "run_delete_batch"
        worker.titles_to_delete = ids
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

    def _start_worker(self, worker: SyncWorker) -> None:
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

    def on_sync_finished(self, success: bool, message: str) -> None:
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
            if success and ("가져오기 완료" in message or "업로드 완료" in message) and self.ui_manager.explorer_window:
                self.ui_manager.explorer_window.refresh()