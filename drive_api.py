import requests
import json
from typing import Optional, Dict, Any, List

class DriveAPI:
    """
    Google Apps Script(GAS) 웹 앱을 통해 구글 드라이브와 통신하는 클래스.
    """
    def __init__(self):
        self.web_app_url: Optional[str] = None

    def set_web_app_url(self, url: str) -> None:
        self.web_app_url = url

    def is_available(self) -> bool:
        return bool(self.web_app_url and self.web_app_url.startswith("https://script.google.com"))

    def list_files(self) -> List[Dict[str, Any]]:
        """GAS를 통해 Memos 폴더 내 파일 목록 가져오기"""
        if not self.is_available(): return []
        try:
            params = {"action": "list"}
            response = requests.get(self.web_app_url, params=params, timeout=10)
            if response.status_code == 200:
                return response.json().get("files", [])
        except Exception as e:
            print(f"GAS List Error: {e}")
        return []

    def upload_file(self, filename: str, content: Dict[str, Any]) -> bool:
        """GAS를 통해 파일 업로드 (생성 또는 덮어쓰기)"""
        if not self.is_available(): return False
        try:
            data = {
                "action": "upload",
                "filename": filename,
                "content": json.dumps(content, ensure_ascii=False)
            }
            print(f"GAS Uploading: {filename} to {self.web_app_url[:40]}...")
            response = requests.post(self.web_app_url, data=json.dumps(data), timeout=10)
            print(f"GAS Upload Status: {response.status_code}, Response: {response.text}")
            return response.status_code == 200
        except Exception as e:
            print(f"GAS Upload Error: {e}")
            return False

    def download_file(self, filename: str) -> Optional[Dict[str, Any]]:
        """GAS를 통해 특정 파일 내용 다운로드"""
        if not self.is_available(): return None
        try:
            params = {"action": "download", "filename": filename}
            response = requests.get(self.web_app_url, params=params, timeout=10)
            if response.status_code == 200:
                return response.json().get("content")
        except Exception as e:
            print(f"GAS Download Error: {e}")
        return None

    def delete_file(self, filename: str) -> bool:
        """GAS를 통해 파일을 Trash_Bin 폴더로 이동 (Soft Delete)"""
        if not self.is_available(): return False
        try:
            data = {"action": "delete", "filename": filename}
            response = requests.post(self.web_app_url, data=json.dumps(data), timeout=10)
            return response.status_code == 200
        except Exception as e:
            print(f"GAS Delete Error: {e}")
            return False

    def permanent_delete_file(self, filename: str) -> bool:
        """GAS를 통해 파일을 영구 삭제 (실제 구글 드라이브 휴지통으로 이동)"""
        if not self.is_available(): return False
        try:
            data = {"action": "permanentDelete", "filename": filename}
            response = requests.post(self.web_app_url, data=json.dumps(data), timeout=10)
            return response.status_code == 200
        except Exception as e:
            print(f"GAS Permanent Delete Error: {e}")
            return False
