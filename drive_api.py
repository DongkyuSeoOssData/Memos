import requests
import json
from typing import Optional, Dict, Any, List

class DriveAPI:
    """
    Google Apps Script(GAS) 웹 앱을 통해 구글 드라이브와 통신하여
    파일 목록 조회, 업로드, 다운로드 및 소프트/영구 삭제를 수행하는 통합 API 래퍼 클래스.
    """
    def __init__(self) -> None:
        """DriveAPI 클래스 초기화"""
        self.web_app_url: Optional[str] = None
        # 요청마다 새로 연결하지 않도록 세션 하나를 재사용합니다. (메모가 많을 때 동기화 시간 단축)
        self._session = requests.Session()
        # 스크립트에 ACCESS_TOKEN 을 설정해 두었을 때 함께 보내는 접근 암호. (비어 있으면 보내지 않음)
        self.access_token: str = ""

    def set_web_app_url(self, url: str) -> None:
        """
        동기화에 사용할 GAS 웹 앱 엔드포인트 URL을 설정합니다.

        Args:
            url (str): 환경설정에 저장된 구글 앱스 스크립트 웹 앱 URL.
        """
        self.web_app_url = url.strip() if url else None

    def set_access_token(self, token: str) -> None:
        """스크립트 속성 ACCESS_TOKEN 과 같은 값을 설정합니다. 모든 요청에 함께 보냅니다."""
        self.access_token = (token or "").strip()

    def _with_token(self, fields: Dict[str, Any]) -> Dict[str, Any]:
        if self.access_token:
            fields["token"] = self.access_token
        return fields

    def is_available(self) -> bool:
        """
        클라우드 동기화 API가 유효하게 설정되어 있는지 검증합니다.

        Returns:
            bool: 유효한 GAS URL이 존재하는 경우 True, 그렇지 않으면 False.
        """
        return bool(self.web_app_url and self.web_app_url.startswith("http"))

    def ping_web_app(self) -> bool:
        """
        GAS 웹 앱 엔드포인트가 정상적으로 통신되는지 5초 타임아웃으로 안전하게 핑 검증을 수행합니다.

        Returns:
            bool: 200 OK 응답 수신 시 True, 통신 실패 시 False.
        """
        # 응답 코드만으로는 접근 암호가 틀린 경우를 가려낼 수 없으므로, 파일 목록을 실제로 받아 봅니다.
        return self.list_files(timeout=5) is not None

    def list_files(self, timeout: int = 10) -> Optional[List[Dict[str, Any]]]:
        """
        GAS를 통해 구글 드라이브의 Memos 폴더 내 파일 목록을 가져옵니다.

        Returns:
            Optional[List[Dict[str, Any]]]: 파일 객체 목록 (파일명, 수정시각 등 포함).
            목록을 받아오지 못했으면 None. ("파일이 하나도 없음"과 "조회 실패"를 구분하기 위함)
        """
        if not self.is_available() or not self.web_app_url:
            return None
        try:
            params = self._with_token({"action": "list"})
            response = self._session.get(self.web_app_url, params=params, timeout=timeout)
            if response.status_code == 200:
                files = response.json().get("files")
                if isinstance(files, list):
                    return files
        except Exception as e:
            print(f"GAS List Error: {e}")
        return None

    def upload_file(self, filename: str, content: Dict[str, Any]) -> bool:
        """
        GAS를 통해 단일 메모 파일(JSON)을 구글 드라이브로 업로드(생성/덮어쓰기)합니다.

        Args:
            filename (str): 업로드 대상 파일명 (예: {memo_id}.json)
            content (Dict[str, Any]): 업로드할 메모 데이터 딕셔너리

        Returns:
            bool: 업로드 성공 여부.
        """
        if not self.is_available() or not self.web_app_url:
            return False
        try:
            data = self._with_token({
                "action": "upload",
                "filename": filename,
                "content": json.dumps(content, ensure_ascii=False)
            })
            response = self._session.post(self.web_app_url, data=json.dumps(data), timeout=10)
            # GAS는 스크립트 오류·권한 문제도 200 + HTML로 돌려주므로, 스크립트가 보낸 "Success" 본문까지 확인합니다.
            return response.status_code == 200 and response.text.strip().startswith("Success")
        except Exception as e:
            print(f"GAS Upload Error: {e}")
            return False

    def download_file(self, filename: str) -> Optional[Dict[str, Any]]:
        """
        GAS를 통해 특정 파일의 내용(JSON)을 다운로드합니다.

        Args:
            filename (str): 다운로드 대상 파일명

        Returns:
            Optional[Dict[str, Any]]: 파싱된 메모 데이터 딕셔너리, 실패 시 None.
        """
        if not self.is_available() or not self.web_app_url:
            return None
        try:
            params = self._with_token({"action": "download", "filename": filename})
            response = self._session.get(self.web_app_url, params=params, timeout=10)
            if response.status_code == 200:
                res_data = response.json()
                content = res_data.get("content")
                if isinstance(content, str):
                    return json.loads(content)
                elif isinstance(content, dict):
                    return content
        except Exception as e:
            print(f"GAS Download Error: {e}")
        return None

    def delete_file(self, filename: str) -> bool:
        """
        GAS를 통해 파일 이동 (Memos -> Trash_Bin 폴더로 소프트 삭제 처리)을 수행합니다.

        Args:
            filename (str): 삭제할 메모 파일명 (예: {memo_id}.json)

        Returns:
            bool: 이동 성공 여부.
        """
        if not self.is_available() or not self.web_app_url:
            return False
        try:
            data = self._with_token({"action": "delete", "filename": filename})
            response = self._session.post(self.web_app_url, data=json.dumps(data), timeout=10)
            return response.status_code == 200 and response.text.strip().startswith("Moved to Trash")
        except Exception as e:
            print(f"GAS Delete Error: {e}")
            return False
