"""처리하지 못한 오류를 기록하고 메일로 알립니다.

버튼·타이머 같은 Qt 슬롯 안에서 잡히지 않은 오류가 나면 PyQt 는 프로그램을 끝내 버립니다.
여기서 그 오류를 받아 error.log 에 남기고, 프로그램은 계속 돌게 합니다.

오류 보고 메일
 - 환경설정의 '오류가 나면 보고 메일 보내기'가 켜져 있고 동기화 주소가 설정돼 있을 때만 보냅니다.
 - 메일은 사용자의 구글 앱스 스크립트가 보냅니다. 받는 주소는 스크립트 속성 ERROR_MAIL_TO 이고,
   없으면 스크립트 주인의 구글 계정 주소입니다. (받는 주소를 앱이 정하지 않으므로 앱에는 주소가 들어 있지 않음)
 - 보내는 내용은 앱 버전, 시각, Windows·Python 버전, 오류의 종류와 호출 경로(traceback)입니다. 메모의 제목·본문은 넣지 않습니다.
 - 같은 오류는 한 번만, 한 번 실행하는 동안 MAX_PER_RUN 통까지만, MIN_GAP_SEC 초에 한 통씩만 보냅니다.
 - 스크립트는 접근 암호(ACCESS_TOKEN)를 설정해 둔 경우에만 보고 메일을 받습니다.
"""
import hashlib
import platform
import sys
import threading
import time
import traceback
from datetime import datetime
from typing import Any, Callable, Optional

from core.defaults import APP_VERSION

MAX_PER_RUN = 5
MIN_GAP_SEC = 60


class ErrorReporter:
    def __init__(self, sync_manager: Any, clock: Callable[[], float] = time.monotonic) -> None:
        self.sm = sync_manager
        self._clock = clock
        self._seen: set = set()
        self._sent = 0
        self._last_sent_at: Optional[float] = None
        self._lock = threading.Lock()
        # 오류가 났음을 화면에 알리는 함수. (앱이 화면을 만든 뒤 넣어 줍니다. 주 스레드에서만 부릅니다)
        self.notify: Optional[Callable[[], None]] = None
        self._last_notice_at: Optional[float] = None

    def enabled(self) -> bool:
        api = self.sm.drive_api
        return (bool(self.sm.settings.get("error_report", True)) and hasattr(api, "send_error_report")
                and bool(api.is_available()))

    def handle(self, exc_type: Any, exc: Any, tb: Any) -> None:
        """처리하지 못한 오류 하나를 기록하고, 조건이 맞으면 메일로 알립니다. 여기서는 어떤 오류도 밖으로 내보내지 않습니다."""
        try:
            trace = "".join(traceback.format_exception(exc_type, exc, tb))
            self.sm.log_error("처리하지 못한 오류" + chr(10) + trace)
            self._tell_user()
            self.submit(f"{getattr(exc_type, '__name__', exc_type)}: {exc}", trace)
        except Exception:
            pass

    def _tell_user(self) -> None:
        """화면에도 한마디 알립니다. 같은 오류가 되풀이돼도 MIN_GAP_SEC 에 한 번만."""
        if self.notify is None or threading.current_thread() is not threading.main_thread():
            return
        now = self._clock()
        if self._last_notice_at is not None and now - self._last_notice_at < MIN_GAP_SEC:
            return
        self._last_notice_at = now
        try:
            self.notify()
        except Exception:
            pass

    def submit(self, summary: str, trace: str) -> bool:
        """오류 보고 메일을 보냅니다. (뒤에서) 보내기로 했으면 True, 조건에 걸려 보내지 않았으면 False."""
        if not self.enabled():
            return False
        key = hashlib.sha1(trace.encode("utf-8", "replace")).hexdigest()
        now = self._clock()
        with self._lock:
            if key in self._seen or self._sent >= MAX_PER_RUN:
                return False
            if self._last_sent_at is not None and now - self._last_sent_at < MIN_GAP_SEC:
                return False
            self._seen.add(key)
            self._sent += 1
            self._last_sent_at = now
        subject = f"[Memos {APP_VERSION}] 오류: {summary}"[:150]
        body = chr(10).join([
            f"앱 버전: {APP_VERSION}",
            f"시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"Windows: {platform.platform()}",
            f"Python: {platform.python_version()}",
            "",
            trace,
        ])
        threading.Thread(target=self._send, args=(subject, body), daemon=True).start()
        return True

    def _send(self, subject: str, body: str) -> None:
        try:
            if not self.sm.drive_api.send_error_report(subject, body):
                self.sm.log_error("오류 보고 메일을 보내지 못함 (스크립트가 예전 버전이거나 연결 실패)")
        except Exception:
            pass


def install(sync_manager: Any) -> ErrorReporter:
    """처리하지 못한 오류를 받는 곳을 겁니다. (주 스레드와 다른 스레드 모두)"""
    reporter = ErrorReporter(sync_manager)

    def on_error(exc_type: Any, exc: Any, tb: Any) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc, tb)
            return
        reporter.handle(exc_type, exc, tb)

    sys.excepthook = on_error
    threading.excepthook = lambda args: on_error(args.exc_type, args.exc_value, args.exc_traceback)
    return reporter
