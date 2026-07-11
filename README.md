# Memos - 구글 드라이브 동기화 및 로컬 하이브리드 메모 시스템 (v1.6)

로컬 환경의 초경량 반응 속도와 구글 드라이브 클라우드의 데이터 무결성을 완벽하게 결합한 데스크톱 메모 애플리케이션입니다. 
v1.6 버전에서는 사용자의 피드백을 적극 반영하여 오프라인 환경을 위한 '로컬 전용 모드'와 OS 제어권 권한 복구가 완벽하게 탑재되었습니다.

---

## ✨ v1.6 핵심 기능 및 업데이트 내역

### 1. 하이브리드 모드 지원 (구글 동기화 ON/OFF 선택 옵션) ➔ [New]
* **구글 클라우드 모드:** 환경설정에서 동기화를 켜두면 기존처럼 구글 드라이브와 백그라운드 스레드로 연동되어 실시간 영속성 백업이 진행됩니다.
* **100% 로컬 전용 모드:** 환경설정에서 `구글 드라이브 동기화 사용` 체크를 해제하면 백그라운드 타이머가 완전히 정지됩니다. 어떠한 외부 통신도 발생하지 않고 오직 대표님의 PC 메모리 내에서만 작동하는 순수 오프라인 메모장으로 변환되어 시스템 리소스를 극도로 절약합니다.

### 2. OS 작업표시줄 최소화 및 시스템 제어권 권한 복구 ➔ [New]
* 프레임리스 테두리 없는 창(`FramelessWindowHint`) 특성상 윈도우 OS단에서 작업표시줄 제어 권한을 상실했던 문제를 통제했습니다.
* 윈도우 OS 가이드에 맞춰 시스템 메뉴 및 최소화 버튼 플래그(`WindowMinimizeButtonHint`, `WindowSystemMenuHint`)를 강제 주입하여, 이제 **윈도우 하단 작업표시줄에서 앱 아이콘을 누를 때마다 탐색기 창이 정상적으로 최소화/복귀**됩니다.

### 3. 초슬림 50px 롤업 최소화 및 가로 리사이징 개방
* 메모장의 최소화(`_`) 버튼 클릭 시, 작업표시줄로 꺼지는 대신 딱 제목 글씨만 보이는 **50px 높이의 초슬림 툴바 박스** 형태로 접힙니다.
* **구조적 개선:** 접힌 상태에서도 우측 하단의 크기 조절 핸들(`QSizeGrip`)을 통해 가로 너비를 자유자재로 변경할 수 있습니다. 접힌 상태에서 프로그램을 종료하거나 마우스를 놓더라도, 펼쳐졌을 때의 원래 정상 높이를 격리 기억하므로 레이아웃이 깨지지 않습니다.

### 4. 실시간 본문 미리보기 및 빠른 수정 (Live Quick-Edit)
* 탐색기 하단의 미리보기 화면이 수정 가능하게 개편되었습니다. 목록을 보며 하단에서 바로 타이핑해 수정할 수 있으며, 수정 즉시 실시간 로컬 저장 및 열려 있는 해당 메모장 창으로 본문 내용이 즉각 브로드캐스팅(동기화)됩니다.

### 5. 위치·크기·활성화 상태 완벽 기억 (State Persistence)
* **메모장:** 각 메모장마다 닫힐 때의 `X/Y 좌표`, `가로/세로 크기`, 그리고 `켜짐 상태(is_visible)`를 완벽히 기억합니다. 프로그램 재시작 시 마지막까지 켜두었던 메모만 정확히 제자리에 로드되며, 꺼둔 메모는 꺼진 채로 안전하게 유지됩니다.
* **탐색기:** 메모 탐색기(`MemoExplorerWindow`) 또한 닫힐 때의 화면 위치와 사이즈를 환경설정에 세이브하여 재시작 시 동일한 비주얼로 복원됩니다.

### 6. 무중단 백그라운드 침묵 동기화 (Silent Sync)
* 타이머 기반의 백그라운드 자동 동기화나 수동 동기화가 성공(True)했을 때는 윈도우 알림창을 띄우지 않고 완전히 침묵(Silent)하여 업무 몰입을 보장합니다.
* 오직 네트워크 단절, URL 누락 등 동기화 실패(False) 상황에서만 트레이 알림 경고를 발생시킵니다. 탐색기 활성화 상태에서는 타이틀바 제목 옆 공간에 파란색 인라인 텍스트(`✓ 동기화 완료`)로 조용히 표시되어 레이아웃 밀림(Layout Shift)을 차단합니다.

---

## 🚀 설치 및 실행 방법 (개발자용)

### 1. 필수 패키지 설치
프로젝트 폴더에서 터미널을 열고 아래 명령어를 입력하여 필요한 라이브러리를 설치합니다.
```bash
pip install -r requirements.txt

```

### 2. 프로그램 실행

```bash
python main.py

```

### 3. 실행 파일(.exe) 빌드

파이썬 환경 없이 바로 실행 가능한 파일로 만들고 싶다면 아래 명령어를 입력하세요.

```bash
pyinstaller --noconsole --onefile --name="Memos" main.py

```

*(빌드 완료 후 생성된 `dist` 폴더 안에 `Memos.exe`가 생성됩니다.)*

---

## ☁️ 구글 드라이브 동기화 셋팅 방법 (필수)

### Step 1. 구글 앱스 스크립트(GAS) 생성

1. [구글 드라이브](https://drive.google.com)에 접속하여 [새로 만들기] -> [더보기] -> [Google Apps Script]를 클릭합니다.
2. 편집기 창의 기존 코드를 모두 지우고, 아래 코드를 복사해서 붙여넣습니다.

```javascript
function doPost(e) {
  const data = JSON.parse(e.postData.contents);
  const mainFolder = getOrCreateFolder("Memos");
  const trashFolder = getOrCreateSubFolder(mainFolder, "trash_bin");
  
  if (data.action === "upload") {
    const files = mainFolder.getFilesByName(data.filename);
    if (files.hasNext()) {
      files.next().setContent(data.content);
    } else {
      mainFolder.createFile(data.filename, data.content);
    }
    return ContentService.createTextOutput("Success");
  } else if (data.action === "delete") {
    const files = mainFolder.getFilesByName(data.filename);
    if (files.hasNext()) {
      files.next().moveTo(trashFolder);
    }
    return ContentService.createTextOutput("Moved to Trash");
  } else if (data.action === "permanentDelete") {
    const files = trashFolder.getFilesByName(data.filename);
    if (files.hasNext()) {
      files.next().setTrashed(true);
    }
    return ContentService.createTextOutput("Permanently Deleted");
  }
}

function doGet(e) {
  const action = e.parameter.action;
  const mainFolder = getOrCreateFolder("Memos");
  
  if (action === "list") {
    const files = mainFolder.getFiles();
    const list = [];
    while (files.hasNext()) {
      const file = files.next();
      list.push({name: file.getName(), id: file.getId()});
    }
    return ContentService.createTextOutput(JSON.stringify({files: list})).setMimeType(ContentService.MimeType.JSON);
  } else if (action === "download") {
    const files = mainFolder.getFilesByName(e.parameter.filename);
    if (files.hasNext()) {
      return ContentService.createTextOutput(JSON.stringify({content: files.next().getBlob().getDataAsString()})).setMimeType(ContentService.MimeType.JSON);
    }
  }
}

function getOrCreateFolder(name) {
  const folders = DriveApp.getFoldersByName(name);
  if (folders.hasNext()) return folders.next();
  return DriveApp.createFolder(name);
}

function getOrCreateSubFolder(parentFolder, name) {
  const folders = parentFolder.getFoldersByName(name);
  if (folders.hasNext()) return folders.next();
  return parentFolder.createFolder(name);
}

```

### Step 2. 웹 앱으로 배포하기

1. 코드 저장(`Ctrl + S`) 후, 우측 상단 [배포] -> [새 배포]를 클릭합니다.
2. 톱니바퀴 아이콘 -> '웹 앱'을 선택합니다.
3. 접근 승인(Who has access)을 '모든 사용자(Anyone)'로 변경 후 [배포]를 누릅니다.
4. 화면에 나타나는 '웹 앱 URL'을 복사합니다.

### Step 3. 메모 앱 연결

1. 시스템 트레이 아이콘 우클릭 -> [⚙ 환경설정]을 클릭합니다.
2. 복사한 **웹 앱 URL**을 `GAS URL:` 칸에 붙여넣고 [설정 저장]을 누릅니다.
