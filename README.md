# Memos - 구글 드라이브 동기화 및 로컬 하이브리드 메모 시스템 (v1.7.1)

로컬 환경의 초경량 반응 속도와 구글 드라이브 클라우드의 데이터 무결성을 완벽하게 결합한 데스크톱 메모 애플리케이션입니다.
v1.7 버전에서는 성능이 대폭 강화된 커스텀 행 번호 엔진, 비동기 스레드 최적화, 제로-렉(Zero-Lag) 코드 메모, 그리고 다크/라이트 픽셀 퍼펙트 UI가 새롭게 탑재되었습니다.

---

## ✨ v1.7.x 핵심 기능 및 대규모 업데이트 내역

### 1. 코드 메모 성능 대폭 향상 (Zero-Lag Code Memo) ➔ [Hotfix]
* **저장 및 종료 딜레이 제거:** 기존 코드 메모에서 발생하던 무거운 HTML 렌더링 부하를 순수 텍스트(Plain Text) 추출 기반으로 최적화하여 0.5초 이상의 렉을 완벽하게 제거했습니다.
* **손상된 메모 자가 치유(Self-Healing):** 과거 버그로 인해 무거운 HTML 형태로 저장되었던 코드 메모를 열 때, 불필요한 태그를 씻어내어 원본 텍스트로 자동 치유하는 로직이 적용되었습니다.

### 2. 다크/라이트 모드 픽셀 퍼펙트 동기화 (Pixel-Perfect UI) ➔ [Hotfix]
* 테마 전환 시 버튼 폰트 크기, 테이블 헤더의 대문자 표기(`uppercase`), 체크박스의 둥글기 및 마진값이 어긋나던 미세한 레이아웃 차이를 100% 동일한 규격으로 통일하여, 테마 변경 시 레이아웃 엇갈림이 전혀 발생하지 않습니다.

### 3. 일괄 정렬 시 화면 프리징(UI Freezing) 완벽 해결 ➔ [Hotfix]
* 다수의 메모를 한 번에 정렬(펼친 메모, 접은 메모 화면 우측 정렬 등)할 때 메인 스레드에서 파일 저장이 연쇄적으로 일어나며 앱이 멈추던 현상을 **비동기 백그라운드 스레드 저장 방식**으로 개선하여 완벽히 해결했습니다.

### 4. 시스템 트레이 아이콘 개선 및 앱 좀비화 버그 해결 ➔ [Hotfix]
* `Memos.spec` 설정 오류로 인해 아이콘 리소스가 누락되어 앱이 사용자 눈에 띄지 않는 "좀비 프로세스"로 실행되던 치명적 빌드 버그를 해결했습니다.
* 트레이 아이콘의 렌더링 방식을 개선하여, 강제적인 흰색 배경 없이 `memo.svg` 벡터 아이콘 고유의 깔끔한 투명 배경을 지원합니다.

### 5. 커스텀 행 번호 엔진(`MemoTextEdit`) 및 스마트 탭 연동
* **VS Code 스타일 동적 행 번호:** `QTextEdit` 기반의 커스텀 라인 넘버 영역(`LineNumberArea`)을 탑재하여 줄 번호 출력을 지원합니다.
* **스마트 탭 및 들여쓰기 동기화:** 키보드 `Tab` 및 `Shift + Tab` 입력 시 포맷바의 들여쓰기(`⇥`) 및 내어쓰기(`⇤`) 기능과 연동됩니다.

### 6. 초슬림 50px 롤업 최소화 및 가로 리사이징 개방
* 창 최소화(`_`) 버튼 클릭 시 50px 높이의 슬림한 툴바 박스 형태로 접힙니다.
* 접힌 상태에서도 우측 하단 크기 조절 핸들(`QSizeGrip`)을 통해 자유롭게 가로 너비를 변경할 수 있습니다.

### 7. 실시간 본문 미리보기 및 빠른 수정 (Live Quick-Edit)
* 탐색기 하단 미리보기 뷰어에서 직접 텍스트 수정이 가능하며, 수정 즉시 로컬에 저장되고 바탕화면에 열려 있는 메모장 창으로도 즉각 동기화됩니다.

### 8. 완벽한 상태 기억 및 무중단 침묵 동기화 (State Persistence & Silent Sync)
* **메모장 & 탐색기:** 닫힐 때의 좌표, 크기, 활성화 상태를 완벽히 기억하여 재시작 시 동일하게 복원됩니다.
* **Silent Sync:** 백그라운드 동기화 성공 시 방해되는 팝업 알림 없이 탐색기 상단에 파란색 텍스트로 조용히 상태를 알려줍니다.
* **실시간 화면 제어 단축키:** `Ctrl + 마우스 휠`로 폰트 크기, `Shift + 마우스 휠`로 투명도를 제어할 수 있습니다.

---

## 🔒 보안 특징 (Security Features)

1. **사용자 지정 키 기반 로컬 암호화**
* 앱 최초 실행 시 사용자가 직접 입력한 개인 비밀번호를 기반으로 `PBKDF2`(SHA-256) 대칭키를 유도하여 로컬 메모(`.json`)를 안전하게 암·복호화합니다.
* 사용자의 개인 키는 내부 설정 파일(`settings.json`)에 안전하게 보호되며, 소스코드가 유출되더라도 키가 없으면 메모를 열어볼 수 없습니다.

2. **비상용 마스터 키 볼트 (`secure_vault.py`) 분리**
* 긴급 상황이나 깃허브 오픈소스로 배포할 때를 대비하여 비상용 마스터 키 로직은 별도의 로컬 전용 모듈(`secure_vault.py`)로 분리되어 **Git 관리 대상(`.gitignore`)에서 제외**됩니다.

---

## 🛠️ 프로젝트 구조

```text
📦 260602_MeMo_GoogleDrive
 ┣ 📂 memos             # 암호화된 로컬 메모 저장 폴더 (자동 생성)
 ┣ 📂 icons             # 테마별 SVG 아이콘 및 시스템 트레이 리소스
 ┣ 📜 main.py           # 애플리케이션 진입점 및 중복 실행 방지(Lock)
 ┣ 📜 ui_manager.py     # UI 이벤트 루프 및 Qt 컴포넌트 총괄 매니저
 ┣ 📜 sync_manager.py   # 동기화 및 사용자 지정 키 암/복호화 백그라운드 매니저
 ┣ 📜 drive_api.py      # Google Apps Script 통신 및 클라우드 연동
 ┣ 📜 Memos.spec        # PyInstaller 실행 파일 빌드 설정
 ┗ 📜 README.md         # 프로젝트 설명서
```

---

## 🚀 설치 및 실행 방법 (개발자용)

### 1. 필수 패키지 설치
프로젝트 폴더에서 터미널을 열고 아래 명령어를 입력하여 필요한 라이브러리를 설치합니다.
```bash
pip install -r requirements.txt
```
*(필수 라이브러리: `PyQt6`, `cryptography`, `pynput` 등)*

### 2. 프로그램 실행
```bash
python main.py
```
*최초 실행 시 메모를 암호화할 비밀번호를 설정하는 팝업 창이 나타납니다.*

### 3. 실행 파일(.exe) 빌드 (PyInstaller)
파이썬 환경 없이 바로 실행 가능한 단일 파일로 만들고 싶다면 아래 명령어를 입력하세요.
```bash
pyinstaller Memos.spec
```
*(빌드 완료 후 `dist` 폴더 내에 아이콘과 UI 리소스가 모두 포함된 `Memos.exe`가 생성됩니다.)*

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

1. 앱 실행 후 시스템 트레이 아이콘 우클릭 -> [⚙ 환경설정]을 클릭합니다.
2. 복사한 **웹 앱 URL**을 `GAS URL:` 칸에 붙여넣고 [설정 저장]을 누릅니다.
3. [구글 동기화 연결 테스트] 버튼을 눌러 연동 상태를 확인합니다.
