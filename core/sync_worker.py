import os
import sys
import json
import shutil
import uuid
import winreg
import ctypes
import ctypes.wintypes
import base64
import re
import traceback
import html
from datetime import datetime
from typing import Any, List, Dict, Optional, Tuple
from pathlib import Path
from PyQt6.QtCore import QTimer, QThread, pyqtSignal, QObject
from PyQt6.QtWidgets import QSystemTrayIcon
from crypto_manager import CryptoManager

class SyncWorker(QObject):
    finished = pyqtSignal(bool, str)

    def __init__(self, sync_manager: Any) -> None:
        super().__init__()
        self.sm = sync_manager
        self.target_method: str = ""
        self.titles_to_delete: List[str] = []

    def execute(self) -> None:
        try:
            if self.target_method == "run_push":
                self.run_push()
            elif self.target_method == "run_pull":
                self.run_pull()
            elif self.target_method == "run_delete_batch":
                self.run_delete_batch(self.titles_to_delete)
        except Exception as e:
            error_msg = f"동기화 치명적 오류: {str(e)}"
            self.sm.log_error(error_msg, e)
            self.finished.emit(False, error_msg)

    def run_push(self) -> None:
        if not self.sm.drive_api.is_available():
            self.finished.emit(False, "환경설정에서 GAS URL을 먼저 입력해주세요.")
            return
        
        count = 0
        for f in self.sm.local_path.glob("*.json"):
            if "trash_bin" in str(f):
                continue
            try:
                with open(f, "r", encoding="utf-8") as file:
                    memo_data = json.load(file)
                memo_id = memo_data.get('id')
                if memo_id:
                    filename = f"{memo_id}.json"
                    if self.sm.drive_api.upload_file(filename, memo_data):
                        count += 1
            except Exception as e:
                self.sm.log_error(f"Push 파일 읽기 실패 ({f.name}): {e}", e)
                    
        if count > 0:
            self.finished.emit(True, f"{count}개의 암호화된 메모 업로드 완료")
        else:
            self.finished.emit(True, "업로드 완료 (변경사항 없음)")

    def run_pull(self) -> None:
        if not self.sm.drive_api.is_available():
            self.finished.emit(False, "환경설정에서 GAS URL을 먼저 입력해주세요.")
            return
        
        files = self.sm.drive_api.list_files()
        
        local_timestamps: Dict[str, str] = {}
        for f in self.sm.local_path.glob("*.json"):
            if "trash_bin" in str(f): continue
            try:
                with open(f, "r", encoding="utf-8") as file:
                    m = json.load(file)
                    if isinstance(m, dict) and 'id' in m:
                        local_timestamps[m['id']] = m.get('updated_at', '')
            except Exception:
                pass

        count = 0
        for f in files:
            name = f.get("name")
            if name and name.endswith(".json"):
                content = self.sm.drive_api.download_file(name)
                if content:
                    try:
                        if isinstance(content, str):
                            data_json = json.loads(content)
                        else:
                            data_json = content
                            
                        if isinstance(data_json, dict) and 'id' in data_json:
                            memo_id = data_json['id']
                            if memo_id in local_timestamps:
                                local_time_str = local_timestamps[memo_id]
                                remote_time_str = data_json.get('updated_at', '')

                                try:
                                    local_dt = datetime.fromisoformat(local_time_str) if local_time_str else datetime.min
                                    remote_dt = datetime.fromisoformat(remote_time_str) if remote_time_str else datetime.min
                                    if remote_dt <= local_dt:
                                        continue
                                except Exception:
                                    pass

                            raw_file = self.sm.local_path / f"{memo_id}.json"
                            with open(raw_file, "w", encoding="utf-8") as out_f:
                                json.dump(data_json, out_f, ensure_ascii=False, indent=2)
                            count += 1
                    except Exception as e:
                        self.sm.log_error(f"Pull 처리 중 에러 ({name}): {e}", e)
                        
        self.finished.emit(True, f"클라우드에서 {count}개의 메모 가져오기 완료")

    def run_delete_batch(self, ids: List[str]) -> None:
        if not self.sm.drive_api.is_available():
            self.finished.emit(False, "환경설정에서 GAS URL 설정 누락")
            return
        success_count = 0
        for memo_id in ids:
            if self.sm.drive_api.delete_file(f"{memo_id}.json"):
                success_count += 1
        if success_count > 0:
            self.finished.emit(True, f"{success_count}개의 메모 클라우드 휴지통 이동 완료")