/**
 * Memos - 구글 앱스 스크립트 (동기화 저장소 + 모바일 웹 화면)
 *
 * 하는 일
 *  1. PC 앱의 동기화 요청 처리 (doGet / doPost)  ← 기존과 동일한 응답 형식
 *  2. 모바일 웹 화면 제공 (주소를 브라우저로 열면 Index.html 이 뜸)
 *  3. 모바일 화면의 요청 처리 (api)
 *
 * 접근 암호(권장)
 *  프로젝트 설정 → 스크립트 속성에 ACCESS_TOKEN 을 추가하면, 그 값을 아는 요청만 처리합니다.
 *  PC 앱은 환경설정의 '동기화 접근 암호'에, 모바일은 첫 화면에 같은 값을 넣습니다.
 *  ACCESS_TOKEN 이 없으면 주소를 아는 누구나 메모를 읽고 쓸 수 있습니다.
 */
const MAIN_FOLDER = "Memos";
const TRASH_FOLDER = "trash_bin";
const SAFE_NAME = /^[A-Za-z0-9_-]{1,80}\.json$/;

// ── 공통 ─────────────────────────────────────────────────────────────────────
function tokenOk_(token) {
  const expected = PropertiesService.getScriptProperties().getProperty("ACCESS_TOKEN");
  return !expected || token === expected;
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

function findFile_(folder, name) {
  const files = folder.getFilesByName(name);
  return files.hasNext() ? files.next() : null;
}

/** 방금 쓴 파일의 수정시각. (같은 객체에서 읽으면 예전 값이 나올 수 있어 다시 조회) */
function freshUpdated_(file) {
  return DriveApp.getFileById(file.getId()).getLastUpdated().getTime();
}

function listFiles_(folder) {
  const files = folder.getFiles();
  const list = [];
  while (files.hasNext()) {
    const f = files.next();
    // updated: 지난번 이후 바뀐 파일만 내려받는 데 사용합니다.
    list.push({name: f.getName(), id: f.getId(), updated: f.getLastUpdated().getTime()});
  }
  return list;
}

function text_(s) {
  return ContentService.createTextOutput(s);
}

function json_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}

// ── PC 앱 동기화 ─────────────────────────────────────────────────────────────
function doPost(e) {
  const data = JSON.parse(e.postData.contents);
  if (!tokenOk_(data.token)) return text_("Unauthorized");
  if (!SAFE_NAME.test(String(data.filename || ""))) return text_("Bad filename");

  const mainFolder = getOrCreateFolder(MAIN_FOLDER);
  if (data.action === "upload") {
    const file = findFile_(mainFolder, data.filename);
    if (file) file.setContent(data.content);
    else mainFolder.createFile(data.filename, data.content);
    return text_("Success");
  }
  if (data.action === "delete") {
    const file = findFile_(mainFolder, data.filename);
    if (file) file.moveTo(getOrCreateSubFolder(mainFolder, TRASH_FOLDER));
    return text_("Moved to Trash");
  }
  return text_("Unknown action");
}

function doGet(e) {
  const action = e.parameter.action;
  if (!action) {
    // 주소를 브라우저로 열었을 때: 모바일 웹 화면
    return HtmlService.createHtmlOutputFromFile("Index")
      .setTitle("Memos")
      .addMetaTag("viewport", "width=device-width, initial-scale=1, viewport-fit=cover");
  }
  if (!tokenOk_(e.parameter.token)) return text_("Unauthorized");

  const mainFolder = getOrCreateFolder(MAIN_FOLDER);
  if (action === "list") {
    return json_({files: listFiles_(mainFolder)});
  }
  if (action === "download") {
    const file = SAFE_NAME.test(String(e.parameter.filename || "")) ? findFile_(mainFolder, e.parameter.filename) : null;
    if (file) return json_({content: file.getBlob().getDataAsString()});
    return json_({});
  }
  return text_("Unknown action");
}

// ── 모바일 화면 ──────────────────────────────────────────────────────────────
/**
 * 모바일 화면(Index.html)이 google.script.run 으로 부르는 단일 창구.
 *   {action: "list"}                                → {files: [{name, updated}]}
 *   {action: "getMany", names: [...]}               → {items: [{name, updated, content}]}
 *   {action: "save", name, content, ifUpdated?}     → {ok, updated} 또는 {conflict: true, updated}
 *   {action: "remove", name}                        → {ok}
 * 접근 암호가 틀리면 {error: "auth"}.
 */
function api(req) {
  req = req || {};
  if (!tokenOk_(req.token)) return {error: "auth"};
  const mainFolder = getOrCreateFolder(MAIN_FOLDER);

  if (req.action === "list") {
    return {files: listFiles_(mainFolder).filter(function (f) { return SAFE_NAME.test(f.name); })};
  }

  if (req.action === "getMany") {
    const items = [];
    (req.names || []).forEach(function (name) {
      if (!SAFE_NAME.test(String(name))) return;
      const file = findFile_(mainFolder, name);
      if (file) items.push({name: name, updated: file.getLastUpdated().getTime(), content: file.getBlob().getDataAsString()});
    });
    return {items: items};
  }

  if (!SAFE_NAME.test(String(req.name || ""))) return {error: "name"};

  if (req.action === "save") {
    // 동시에 들어온 저장이 서로 덮어쓰지 않도록 한 번에 하나씩 처리합니다.
    const lock = LockService.getScriptLock();
    lock.waitLock(20000);
    try {
      let file = findFile_(mainFolder, req.name);
      if (file) {
        const current = file.getLastUpdated().getTime();
        // 화면에서 열어 본 뒤 다른 기기가 고쳤으면 덮어쓰지 않고 알려 줍니다.
        if (req.ifUpdated && current !== req.ifUpdated) return {conflict: true, updated: current};
        file.setContent(req.content);
      } else {
        file = mainFolder.createFile(req.name, req.content);
      }
      return {ok: true, updated: freshUpdated_(file)};
    } finally {
      lock.releaseLock();
    }
  }

  if (req.action === "remove") {
    const file = findFile_(mainFolder, req.name);
    if (file) file.moveTo(getOrCreateSubFolder(mainFolder, TRASH_FOLDER));
    return {ok: true};
  }

  return {error: "action"};
}
