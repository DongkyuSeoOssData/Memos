import sys
import os
from PyQt6.QtWidgets import QApplication, QMessageBox
from ui_manager import UIManager
from sync_manager import SyncManager
from drive_api import DriveAPI
from pathlib import Path

def is_already_running() -> bool:
    """락 파일을 사용하여 이미 실행 중인지 확인"""
    lock_file = Path.home() / ".memoit_custom" / "memo.lock"
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    
    if lock_file.exists():
        try:
            # 기존 락 파일 삭제 시도 (프로세스가 죽었을 경우 대비)
            lock_file.unlink()
        except:
            return True
            
    try:
        with open(lock_file, "w") as f:
            f.write(str(os.getpid()))
        return False
    except:
        return True

def main() -> None:
    """
    애플리케이션의 엔트리 포인트.
    """
    app = QApplication(sys.argv)
    
    # 마지막 창이 닫혀도 트레이 아이콘이 있으므로 종료되지 않도록 설정
    app.setQuitOnLastWindowClosed(False)
    
    # 중복 실행 방지
    if is_already_running():
        sys.exit(0)

    # 1. 각 모듈 인스턴스화
    drive_api = DriveAPI()
    sync_manager = SyncManager(drive_api)
    ui_manager = UIManager(sync_manager)
    
    # 2. 애플리케이션 실행
    ui_manager.show_all_memos()
    
    code = app.exec()
    
    # 종료 시 락 파일 삭제
    try:
        (Path.home() / ".memoit_custom" / "memo.lock").unlink()
    except:
        pass
        
    sys.exit(code)

if __name__ == "__main__":
    main()
