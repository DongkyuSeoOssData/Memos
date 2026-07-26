import sys
import os
from pathlib import Path
from PyQt6.QtWidgets import QApplication
from ui.ui_manager import UIManager
from core.sync_manager import SyncManager
from drive_api import DriveAPI

def is_already_running() -> bool:
    """
    락(Lock) 파일을 사용하여 애플리케이션의 중복 실행 여부를 확인합니다.
    
    Returns:
        bool: 이미 다른 인스턴스가 실행 중인 경우 True, 그렇지 않은 경우 False.
    """
    lock_file = Path.home() / ".memoit_custom" / "memo.lock"
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    
    if lock_file.exists():
        try:
            # 기존 락 파일 삭제 시도 (프로세스가 강제 종료되었을 경우 대비)
            lock_file.unlink()
        except Exception:
            return True
            
    try:
        with open(lock_file, "w", encoding="utf-8") as f:
            f.write(str(os.getpid()))
        return False
    except Exception:
        return True

def main() -> None:
    """
    애플리케이션의 엔트리 포인트.
    모듈 초기화, 중복 실행 방지 처리 및 Qt 메인 이벤트 루프를 구동합니다.
    """
    app = QApplication(sys.argv)
    
    # 마지막 창이 닫혀도 시스템 트레이 아이콘이 존재하므로 앱이 종료되지 않도록 설정
    app.setQuitOnLastWindowClosed(False)
    
    # 중복 실행 방지
    if is_already_running():
        sys.exit(0)

    # 1. 각 모듈 인스턴스화
    drive_api = DriveAPI()
    sync_manager = SyncManager(drive_api)
    ui_manager = UIManager(sync_manager)
    
    # 2. 애플리케이션 메모 화면 복원 및 실행
    ui_manager.show_all_memos()
    
    code = app.exec()
    
    # 정상 종료 시 락 파일 삭제
    try:
        (Path.home() / ".memoit_custom" / "memo.lock").unlink()
    except Exception:
        pass
        
    sys.exit(code)

if __name__ == "__main__":
    main()

