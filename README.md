
# Memos - 구글 드라이브 연동 맞춤형 스마트 메모 시스템 (v1.5)

로컬 환경의 초경량 속도와 구글 드라이브 클라우드의 무결성을 결합한 대표님 맞춤형 데스크톱 메모 애플리케이션입니다. 사용자 중심의 디테일한 UI/UX 개편과 상태 기억 메커니즘이 완벽하게 반영된 최신 버전(v1.5) 명세서입니다.

---

## ✨ v1.5 핵심 기능 (업데이트 내역)

### 1. 실시간 본문 미리보기 및 빠른 수정 (Live Quick-Edit)
* 탐색기 하단의 본문 미리보기 창이 '보기 전용'에서 **'직접 수정 가능'** 구조로 업그레이드되었습니다.
* 미리보기 창에서 내용을 수정하면 실시간으로 로컬에 자동 저장되며, 해당 메모장 창이 켜져 있을 경우 본문 내용이 실시간으로 동기화(Event Broadcasting)됩니다.

### 2. 위치·크기·활성화 상태 완벽 기억 (State Persistence)
* **메모장 개별 기억:** 각 메모장마다 닫힐 때의 `X/Y 좌표`, `가로/세로 크기`, 그리고 `켜짐 상태(is_visible)`를 완벽히 기억합니다. 프로그램 재시작 시 마지막까지 화면에 켜두었던 메모만 정확히 제자리에 로드되며, 꺼둔 메모는 꺼진 채로 안전하게 유지됩니다.
* **탐색기 기억:** 메모 탐색기(`MemoExplorerWindow`) 역시 닫힐 때의 화면 위치와 사이즈를 기억하여 재시작 시 동일한 비주얼로 복원됩니다.

### 3. 초슬림 50px 롤업 최소화 (Smart Roll-up)
* 메모장의 최소화(`_`) 버튼 클릭 시, 작업표시줄로 내려가는 대신 **딱 제목만 보이는 50px 높이의 초슬림 툴바 박스** 형태로 접힙니다.
* **가로 리사이징 지원:** 접힌 상태에서도 우측 하단 핸들(Size Grip)을 통해 가로 크기를 자유자재로 조절할 수 있습니다. 
* 접힌 상태로 끄거나 조작하더라도, 펼쳐졌을 때의 원래 정상 높이를 안전하게 격리 기억하므로 크기가 깨지지 않습니다.

### 4. 스마트 트레이 아이콘 토글 및 기본 핀 고정
* 코드로 직접 렌더링한 하늘색 배경의 **'Memos' 전용 커스텀 트레이 아이콘**이 적용되었습니다.
* 트레이 아이콘을 왼쪽 마우스로 클릭할 때마다 탐색기 창이 **켜져 있으면 즉시 숨기고(Hide), 숨겨져 있으면 화면 맨 앞으로 활성화(Show/Raise/Activate)** 시키는 직관적인 토글 기능이 탑재되었습니다.
* 탐색기 첫 실행 시 압정(항상 위 고정) 기능이 기본값으로 켜진 상태로 시작되어 조작 편의성을 높였습니다.

### 5. 무중단 백그라운드 침묵 동기화 (Silent Sync)
* 지긋지긋한 윈도우 우측 하단의 투박한 알림을 제어합니다. 타이머 기반의 백그라운드 동기화나 수동 동기화 성공 시, **윈도우 알림창을 띄우지 않고 완전히 침묵(Silent)** 하여 사용자의 업무 몰입을 보장합니다.
* 오직 네트워크 단절, URL 누락 등 **동기화 실패(False) 상황에서만** 트레이 알림 경고를 띄우도록 Fail-Safe 알림 정책을 픽스했습니다.
* 탐색기 창이 열려 있을 때는 타이틀바 제목 옆 공간에 파란색 인라인 텍스트(`✓ 동기화 완료`)로 조용히 표시되어 화면 밀림(Layout Shift) 현상을 완벽히 차단했습니다.

### 6. 스마트 서식 바 및 직관적 환경설정
* 본문 하단 미니 서식 바를 통해 글머리 기호(`•`), 숫자 매기기(`1.`)를 지원하며 내부 데이터가 HTML 포맷으로 안전하게 빌드됩니다. 
* 대표님의 방어막 지시대로 **들여쓰기(`⇥`)는 최대 2단계까지만 허용**되도록 하드웨어 제약 로직을 심었습니다.
* 환경설정(`SettingsWindow`) 내 기본 색상 선택 콤보박스에 각 텍스트별 실제 배경색(하늘색, 연두색 등)이 직관적으로 렌더링되도록 시각화했습니다.

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
