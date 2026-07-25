# Memos - 구글 드라이브 동기화 및 로컬 하이브리드 메모 시스템 (v1.7)

로컬 환경의 초경량 반응 속도와 구글 드라이브 클라우드의 데이터 무결성을 완벽하게 결합한 데스크톱 메모 애플리케이션입니다.
v1.7 버전에서는 성능이 대폭 강화된 커스텀 행 번호 엔진 및 스마트 탭 연동 기능, 그리고 실시간 화면 제어 단축키가 새롭게 탑재되었습니다.

---

## ✨ v1.7 핵심 기능 및 업데이트 내역

### 1. 커스텀 행 번호 엔진(`MemoTextEdit`) 및 스마트 탭 연동 ➔ [New]

* **VS Code 스타일 동적 행 번호:** `QTextEdit` 기반의 커스텀 라인 넘버 영역(`LineNumberArea`)을 탑재하여 줄 번호 출력을 지원합니다.
* **스마트 탭 및 들여쓰기 동기화:** 키보드 `Tab` 및 `Shift + Tab` 입력 시 포맷바의 들여쓰기(`⇥`) 및 내어쓰기(`⇤`) 기능과 연동됩니다.
* **가로 줄노트 배경선 개편:** `QPainter`를 통해 에디터 뷰포트에 가로 줄노트 배경선이 렌더링되도록 개선되었습니다.

### 2. OS 작업표시줄 최소화 및 시스템 제어권 권한 복구

* 프레임리스 테두리 없는 창 환경에서 윈도우 OS 시스템 메뉴 및 최소화 버튼 플래그가 주입되었습니다.
* 하단 작업표시줄에서 앱 아이콘을 클릭할 때 창이 정상적으로 최소화 및 복귀됩니다.

### 3. 초슬림 50px 롤업 최소화 및 가로 리사이징 개방

* 최소화(`_`) 버튼 클릭 시 50px 높이의 툴바 박스 형태로 접힙니다.
* 접힌 상태에서도 우측 하단 크기 조절 핸들(`QSizeGrip`)을 통해 가로 너비를 변경할 수 있습니다.

### 4. 실시간 본문 미리보기 및 빠른 수정 (Live Quick-Edit)

* 탐색기 하단 미리보기 화면에서 직접 수정이 가능합니다.
* 수정 즉시 로컬 저장 및 열려 있는 메모장 창으로 내용이 동기화됩니다.

### 5. 위치·크기·활성화 상태 완벽 기억 (State Persistence)

* **메모장:** 닫힐 때의 좌표, 크기, 켜짐 상태를 기억하여 재시작 시 동일하게 복원됩니다.
* **탐색기:** 창의 위치와 사이즈를 환경설정에 저장하여 동일한 비주얼로 유지됩니다.

### 6. 무중단 백그라운드 침묵 동기화 (Silent Sync)

* 자동 및 수동 동기화 성공 시 알림창을 띄우지 않고 백그라운드에서 조용히 처리됩니다.
* 탐색기 활성화 상태에서는 타이틀바 제목 옆 공간에 파란색 인라인 텍스트로 표시됩니다.

### 7. 실시간 화면 제어 단축키 및 환경설정 연동 보완 ➔ [New]

* **실시간 휠 단축키:** `Ctrl + 마우스 휠`로 폰트 크기를 조절하고, `Shift + 마우스 휠`로 투명도를 제어할 수 있습니다.
* **환경설정 상태 유지:** 최초 메모 실행 시 행번호 및 줄노트 배경 표시 옵션 상태가 설정 창 재접속 시에도 유지됩니다.

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