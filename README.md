
# Memos - 구글 드라이브 동기화 메모장

로컬 환경에서 빠르고 가볍게 작동하며, 구글 드라이브와 완벽하게 연동되는 데스크톱 메모 애플리케이션입니다.

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
