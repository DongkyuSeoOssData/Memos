
---

# Memos - 구글 드라이브 동기화 및 로컬 하이브리드 메모 시스템 (v2.0.1)

로컬 환경의 초경량 반응 속도와 구글 드라이브 클라우드의 데이터 무결성을 완벽하게 결합한 데스크톱 메모 애플리케이션입니다.
빠르고 직관적인 UI, 전역 단축키 기반의 압도적인 생산성, 완벽한 보안 암호화, 그리고 개발자를 위한 코드 하이라이팅 기능을 제공합니다.

---

## ✨ v2.0.1 핵심 업데이트 내역

### 1. 전면적인 아키텍처 리팩토링 및 모듈화 (Architecture Refactoring)

* **클린 구조 설계:** 단일 파일로 비대했던 코드를 역할에 따라 `core/`, `ui/`, `utils/` 폴더 구조로 철저히 분리하여 유지보수성과 확장성을 극대화했습니다.
* **UI 컴포넌트 세분화:** `memo_window.py`, `memo_explorer.py`, `settings_window.py` 등 역할별로 책임을 분리하여 메모리 관리와 렌더링 성능을 향상시켰습니다.

### 2. 강력한 사용자 편의성 및 UX 혁신 (New UX Features)

* **윈도우 전역 글로벌 단축키 (Global Hotkey):** 파이썬 `keyboard` 백그라운드 후킹 기술을 도입하여, 앱이 포커스를 잃거나 백그라운드에 숨어있을 때도 윈도우 OS 어디서나 단축키로 즉시 메모를 소환할 수 있습니다. (메인 스레드 안전성 확보)
* **디스플레이 반응형 창 초기화:** 탐색기와 환경설정 창 최초 실행 시 모니터 해상도를 자동 감지하여 화면의 약 1/6(가로세로 40%) 비율로 예쁘게 배치되며, 80% 맥스 사이즈 방어 로직으로 멀티모니터 환경을 완벽 지원합니다.
* **Shift + 마우스 휠 폰트 스케일링:** 메모장 본문뿐만 아니라 탐색기와 설정창에서도 `Shift + 휠` 조작을 통해 전체 폰트 크기를 직관적으로 키우고 줄일 수 있으며, 변경된 크기는 `settings.json`에 영구 저장됩니다.
* **트레이 메뉴 미니멀리즘:** 트레이 아이콘 컨텍스트 메뉴에서 중복되던 '모든 메모 켜기' 항목을 과감히 제거하고 '모두 숨기기/보이기' 토글 중심으로 깔끔하게 정돈했습니다.

### 3. 치명적 버그 수정 및 테마 일관성 확보

* **메모 무한 증식 및 동기화 안정화:** 구형 ID를 가진 레거시 파일들이 저장될 때 발생하던 무한 복제 버그를 해결하고, 휴지통 연동 시 파생 파일들이 함께 정리되도록 개선했습니다.
* **개별 메모 테마 독립성 복구:** 전역 다크/라이트 모드와 별개로, 일반 메모의 제목과 코드 메모의 언어 선택/테마 버튼들이 각 개별 메모의 자체 테마 팔레트를 정확히 추종하도록 격리했습니다.
* **핀 고정 및 토스트 레이아웃 안정화:** 네이티브 API 우회로 인한 핀 풀림 현상을 PyQt 정석 방식으로 바로잡고, 탐색기 하단 토스트 알림을 Floating UI로 분리하여 창 크기 흔들림을 원천 차단했습니다.

---

## 🚀 주요 기능 및 특징 (Key Features)

1. **초경량 제로-렉(Zero-Lag) 메모 에디터**
* 무거운 HTML 렌더링 부하를 제거한 순수 텍스트(Plain Text) 및 스마트 파싱 기반으로 최적화하여 렉 없는 쾌적한 타이핑을 지원합니다.
* **VS Code 스타일 동적 행 번호**와 다크/라이트 코드 하이라이팅를 지원합니다.


2. **스마트 리스트 포맷 및 들여쓰기**
* 불릿(•) 및 넘버(1.) 리스트 자동 생성과 토글(Toggle Off) 해제 기능을 지원합니다.
* 단축키(`Tab`, `Shift + Tab`)를 통한 스마트 들여쓰기를 지원하며, 리스트 해제 시에도 사용자의 수동 들여쓰기 범위가 그대로 유지됩니다.


3. **완벽한 상태 기억 및 롤업(Roll-up) 모드**
* 창이 닫힐 때의 좌표, 크기, 핀 고정 여부뿐만 아니라 조절된 폰트 스케일 값까지 기억하여 다음 실행 시 완벽하게 복원됩니다.
* 제목 표시줄을 더블클릭하거나 최소화(`_`) 버튼 클릭 시 50px 높이의 얇은 툴바 형태로 접히는 **초슬림 롤업 기능**을 제공합니다.


4. **비동기 침묵 동기화 (Silent Sync)**
* 구글 드라이브 업로드/다운로드 과정이 비동기 백그라운드 스레드로 동작하여 작업 중 UI 멈춤(Freezing)이 전혀 발생하지 않습니다.
* 동기화 완료 시 방해되는 팝업 알림 없이 탐색기 상단에 파란색 텍스트로 조용히 상태를 알려줍니다.



---

## 🔒 강력한 보안 (Security Features)

1. **사용자 지정 키 기반 로컬 암호화**
* 앱 최초 실행 시 설정한 개인 비밀번호를 기반으로 `PBKDF2`(SHA-256) 대칭키를 유도하여 로컬 메모 데이터를 안전하게 암호화(`.json`)합니다.
* 파일 유출 시에도 개인 키가 없으면 절대 열어볼 수 없습니다.


2. **비상용 마스터 키 볼트 분리**
* 긴급 상황 및 오픈소스 배포를 대비하여 비상용 마스터 키 로직은 별도 모듈(`secure_vault.py`)로 분리되어 `.gitignore` 처리됩니다.



---

## 🛠️ 프로젝트 구조

```text
📦 260602_MeMo_GoogleDrive
  ┣ 📂 memos             # 암호화된 로컬 메모 저장 폴더 (자동 생성)
  ┣ 📂 icons             # 테마별 SVG 아이콘 및 시스템 트레이 리소스
  ┣ 📂 core              # 핵심 비즈니스 로직 및 백그라운드 관리
  ┃ ┣ 📜 sync_manager.py # 동기화 및 전반적인 데이터 관리 매니저
  ┃ ┗ 📜 sync_worker.py  # 비동기 구글 드라이브 업로드/다운로드 워커
  ┣ 📂 ui                # 분리된 UI 컴포넌트 및 모듈
  ┃ ┣ 📜 ui_manager.py   # UI 컴포넌트 총괄, 트레이 및 글로벌 단축키 제어
  ┃ ┣ 📜 memo_window.py  # 개별 메모 창 UI (일반/코드 메모 독립 테마)
  ┃ ┣ 📜 memo_explorer.py# 메모 탐색기 UI (반응형 및 Shift+휠 스케일링)
  ┃ ┣ 📜 memo_editor.py  # 커스텀 텍스트 에디터 및 행 번호 엔진
  ┃ ┣ 📜 settings_window.py # 환경 설정 UI
  ┃ ┣ 📜 dialogs.py      # 패스워드 및 알림 다이얼로그
  ┃ ┗ 📜 themes.py, ui_utils.py # UI 유틸리티 및 테마 팔레트
  ┣ 📂 utils             # 공통 유틸리티 (암복호화, 텍스트 처리 등)
  ┃ ┣ 📜 crypto_utils.py # AES/PBKDF2 등 암호화 처리
  ┃ ┗ 📜 text_utils.py   # 텍스트 추출 및 스마트 언어 파싱 유틸
  ┣ 📜 main.py           # 애플리케이션 진입점 및 중복 실행 방지(Lock)
  ┣ 📜 drive_api.py      # Google Apps Script 통신 및 클라우드 연동
  ┣ 📜 Memos.spec        # PyInstaller 빌드 설정
  ┗ 📜 README.md         # 프로젝트 설명서

```

---

## 📦 설치 및 실행 방법

### 1. 패키지 설치

프로젝트 폴더 터미널에서 다음 명령어로 의존성 패키지를 설치합니다 (`keyboard` 글로벌 단축키 모듈 포함).

```bash
pip install -r requirements.txt

```

### 2. 프로그램 실행

```bash
python main.py

```

### 3. 단일 실행 파일(.exe) 빌드

다른 PC에서도 파이썬 설치 없이 백그라운드 단축키가 포함된 독립 실행 파일로 빌드할 수 있습니다.

```bash
pyinstaller Memos.spec

```

---

## ☁️ 구글 드라이브 동기화 셋팅 방법 (필수)

### Step 1. 구글 앱스 스크립트(GAS) 생성

1. [구글 드라이브](https://drive.google.com) -> [새로 만들기] -> [Google Apps Script]
2. 기존 코드를 지우고 `drive_api.py` 내의 주석 또는 하단의 코드를 복사해 붙여넣습니다.

```javascript
function doPost(e) {
  const data = JSON.parse(e.postData.contents);
  const mainFolder = getOrCreateFolder("Memos");
  const trashFolder = getOrCreateSubFolder(mainFolder, "trash_bin");
  
  if (data.action === "upload") {
    const files = mainFolder.getFilesByName(data.filename);
    if (files.hasNext()) files.next().setContent(data.content);
    else mainFolder.createFile(data.filename, data.content);
    return ContentService.createTextOutput("Success");
  } else if (data.action === "delete") {
    const files = mainFolder.getFilesByName(data.filename);
    if (files.hasNext()) files.next().moveTo(trashFolder);
    return ContentService.createTextOutput("Moved to Trash");
  }
}

function doGet(e) {
  const action = e.parameter.action;
  const mainFolder = getOrCreateFolder("Memos");
  if (action === "list") {
    const files = mainFolder.getFiles();
    const list = [];
    while (files.hasNext()) {
      const f = files.next();
      list.push({name: f.getName(), id: f.getId()});
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

### Step 2. 웹 앱 배포 및 연결

1. 코드 저장(`Ctrl + S`) 후, 우측 상단 **[배포] -> [새 배포]** 클릭
2. 톱니바퀴 아이콘 -> **'웹 앱'** 선택, 접근 승인을 '모든 사용자(Anyone)'로 변경 후 배포
3. 생성된 '웹 앱 URL'을 복사
4. 앱의 시스템 트레이 우클릭 -> **[⚙ 환경설정]** -> `GAS URL:` 에 붙여넣고 저장
5. [테스트] 버튼을 눌러 연동 확인 완료!