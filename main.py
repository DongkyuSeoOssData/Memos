import sys
import ctypes
import ctypes.wintypes
from PyQt6.QtWidgets import QApplication
from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from ui.ui_manager import UIManager
from core.sync_manager import SyncManager
from drive_api import DriveAPI

ERROR_ALREADY_EXISTS = 183
IPC_NAME = "MemoitApp_SingleInstance_IPC"
# 프로세스가 살아 있는 동안 뮤텍스 핸들을 붙잡아 둡니다. (종료·강제 종료 시 OS가 자동 해제)
_instance_mutex = None

def is_already_running() -> bool:
    """
    명명된 뮤텍스를 사용하여 애플리케이션의 중복 실행 여부를 확인합니다.

    Returns:
        bool: 이미 다른 인스턴스가 실행 중인 경우 True, 그렇지 않은 경우 False.
    """
    global _instance_mutex
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.restype = ctypes.wintypes.HANDLE
        kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.wintypes.BOOL, ctypes.wintypes.LPCWSTR]
        handle = kernel32.CreateMutexW(None, False, "Local\\MemoitApp_SingleInstance")
        already_exists = ctypes.get_last_error() == ERROR_ALREADY_EXISTS
    except Exception:
        return False

    if not handle:
        return False
    if already_exists:
        kernel32.CloseHandle(ctypes.wintypes.HANDLE(handle))
        return True
    _instance_mutex = handle
    return False

def notify_running_instance() -> None:
    """이미 떠 있는 인스턴스에게 탐색기를 보여 달라고 알립니다."""
    sock = QLocalSocket()
    sock.connectToServer(IPC_NAME)
    if sock.waitForConnected(500):
        sock.write(b"show")
        sock.waitForBytesWritten(500)
        sock.disconnectFromServer()

def start_ipc_server(on_show) -> QLocalServer:
    """다른 인스턴스가 실행을 시도하면 on_show를 호출하는 서버를 엽니다."""
    QLocalServer.removeServer(IPC_NAME)
    server = QLocalServer()

    def _on_connection() -> None:
        conn = server.nextPendingConnection()
        if conn:
            conn.close()
        on_show()

    server.newConnection.connect(_on_connection)
    server.listen(IPC_NAME)
    return server

def main() -> None:
    """
    애플리케이션의 엔트리 포인트.
    모듈 초기화, 중복 실행 방지 처리 및 Qt 메인 이벤트 루프를 구동합니다.
    """
    app = QApplication(sys.argv)

    from PyQt6.QtGui import QFont
    app.setFont(QFont("D2Coding", 10))

    # 마지막 창이 닫혀도 시스템 트레이 아이콘이 존재하므로 앱이 종료되지 않도록 설정
    app.setQuitOnLastWindowClosed(False)

    # 중복 실행 방지
    if is_already_running():
        notify_running_instance()
        sys.exit(0)

    # 1. 각 모듈 인스턴스화
    drive_api = DriveAPI()
    sync_manager = SyncManager(drive_api)
    ui_manager = UIManager(sync_manager)

    # 2. 애플리케이션 메모 화면 복원 및 실행
    ui_manager.show_all_memos()
    ipc_server = start_ipc_server(ui_manager.open_memo_explorer)

    sys.exit(app.exec())

if __name__ == "__main__":
    main()
