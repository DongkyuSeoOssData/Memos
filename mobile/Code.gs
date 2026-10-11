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
 *
 * 오류 보고 메일
 *  PC 앱에서 처리하지 못한 오류가 나면 이 스크립트가 메일로 알립니다.
 *  받는 주소는 스크립트 속성 ERROR_MAIL_TO 이고, 없으면 이 스크립트 주인의 구글 계정 주소입니다.
 *  받는 주소를 요청에서 받지 않으므로, 주소를 아는 사람이 이 스크립트로 다른 곳에 메일을 보낼 수는 없습니다.
 *  ACCESS_TOKEN 을 설정해 둔 경우에만 받고, 한 시간에 REPORTS_PER_HOUR 통까지만 보냅니다.
 *
 * 색인 (_index.json)
 *  모바일 화면이 처음 열릴 때 메모 파일을 하나하나 내려받지 않고도 목록을 바로 그릴 수 있게, 메모마다의 요약
 *  (제목·수정시각·폴더·종류·본문 앞부분·해시태그)을 파일 하나에 모아 둡니다.
 *  - 이 파일을 쓰는 것은 이 스크립트뿐입니다. PC 앱도 모바일 화면도 읽기만 하므로, 여러 기기가 서로 덮어쓰는 일이 없습니다.
 *  - 메모 파일에서 만들어 낸 것입니다. 요청을 받을 때마다 폴더의 파일 목록과 견주어 바뀐 메모만 다시 읽어 고칩니다.
 *    지워지거나 깨져도 다시 만들어집니다.
 *  - 암호 메모는 제목 같은 겉 정보만 들어가고, 본문에서 나오는 것(앞부분·해시태그)은 들어가지 않습니다.
 */
const MAIN_FOLDER = "Memos";
const TRASH_FOLDER = "trash_bin";
const SAFE_NAME = /^[A-Za-z0-9_-]{1,80}\.json$/;
const INDEX_FILE = "_index.json";
const INDEX_VERSION = 1;
const INDEX_BUDGET_MS = 20000;      // 색인을 고치느라 한 번의 요청에서 쓰는 시간의 한도 (넘으면 다음 요청에서 이어서)
const PREVIEW_CHARS = 300;          // 색인에 넣는 본문 앞부분의 길이

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

// ── 색인 ─────────────────────────────────────────────────────────────────────
/** PC 앱의 편집기(Qt)가 만든 서식 문서인지. (모바일 화면의 isRichHtml 과 같은 기준) */
function isRichHtml_(content) {
  const head = String(content).replace(/^\s+/, "").slice(0, 400).toLowerCase();
  return head.indexOf("<!doctype html public") === 0 && head.indexOf("qrichtext") >= 0;
}

/** 본문에서 글자만 뽑습니다. 목록에 보일 앞부분과 해시태그를 얻는 용도라, 줄 나눔 정도만 살립니다. */
function toPlain_(content) {
  if (typeof content !== "string") return "";
  if (!isRichHtml_(content)) return content;
  return content
    .replace(/<head[\s\S]*?<\/head>/gi, "")
    .replace(/<style[^>]*>[\s\S]*?<\/style>/gi, "")
    .replace(/<br\s*\/?>/gi, "\n")
    .replace(/<\/(p|li|div|h[1-6]|tr)>/gi, "\n")
    .replace(/<[^>]+>/g, "")
    .replace(/&nbsp;/g, " ").replace(/&lt;/g, "<").replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"').replace(/&#39;|&apos;/g, "'").replace(/&amp;/g, "&")
    .replace(/\n{2,}/g, "\n")
    .trim();
}

/** 본문의 #태그. (모바일 화면의 tagsOf 와 같은 규칙: 낱말 첫머리의 # 만, 색상 코드는 제외) */
function tagsOf_(text) {
  const out = [];
  const re = /(?:^|\s)#([^\s#]+)/g;
  let m;
  while ((m = re.exec(text))) if (!/^[0-9a-fA-F]{6}([0-9a-fA-F]{2})?$/.test(m[1])) out.push(m[1]);
  return out;
}

/** 메모 파일의 내용(글자)에서 색인에 넣을 요약을 만듭니다. 메모로 읽을 수 없으면 {bad: true}. */
function summarize_(text, updated) {
  let memo = null;
  try { memo = JSON.parse(text); } catch (e) { /* 깨진 파일 */ }
  if (!memo || typeof memo !== "object" || typeof memo.id !== "string") return {updated: updated, bad: true};
  const content = memo.content;
  const meta = {};
  Object.keys(memo).forEach(function (key) { if (key !== "content") meta[key] = memo[key]; });
  const locked = !!content && typeof content === "object" && !!content.is_encrypted;
  const plain = locked ? "" : toPlain_(content);
  return {
    updated: updated, meta: meta, locked: locked,
    preview: plain.slice(0, PREVIEW_CHARS),
    tags: (meta.is_code_memo || locked) ? [] : tagsOf_(plain),
  };
}

/**
 * 파일 목록(files)에 맞춰 색인을 고칩니다. 수정시각이 그대로인 메모는 예전 요약(stored)을 그대로 쓰고,
 * 바뀌었거나 새로 생긴 메모만 readFile(file) 로 읽어 다시 요약합니다. 없어진 메모는 빠집니다.
 * budgetMs 를 넘기면 남은 것은 다음으로 미루고 pending 에 그 수를 적습니다.
 */
function buildIndex_(files, stored, readFile, budgetMs) {
  const entries = {};
  let changed = false, pending = 0;
  const started = Date.now();
  files.forEach(function (f) {
    if (f.name.charAt(0) === "_") return;
    const old = stored[f.name];
    if (old && old.updated === f.updated) { entries[f.name] = old; return; }
    if (Date.now() - started >= budgetMs) { pending++; return; }
    let text = null;
    try { text = readFile(f); } catch (e) { /* 그사이 지워진 파일 등 */ }
    if (text === null) { pending++; return; }
    entries[f.name] = summarize_(text, f.updated);
    changed = true;
  });
  if (!changed && Object.keys(stored).length !== Object.keys(entries).length) changed = true;    // 없어진 메모가 있음
  return {entries: entries, changed: changed, pending: pending};
}

/** 색인을 최신으로 맞춰 돌려줍니다. → {files, entries, pending} */
function refreshIndex_(mainFolder) {
  const all = listFiles_(mainFolder).filter(function (f) { return SAFE_NAME.test(f.name); });
  const files = all.filter(function (f) { return f.name !== INDEX_FILE; });
  // 색인을 고쳐 쓰는 것은 한 번에 한 요청만. 다른 요청이 쓰는 중이면 지금 있는 색인을 읽기만 합니다.
  const lock = LockService.getScriptLock();
  const mine = lock.tryLock(10000);
  try {
    const listed = all.filter(function (f) { return f.name === INDEX_FILE; })[0];
    const indexFile = listed ? DriveApp.getFileById(listed.id) : null;
    let stored = {};
    if (indexFile) {
      try {
        const parsed = JSON.parse(indexFile.getBlob().getDataAsString());
        if (parsed && parsed.v === INDEX_VERSION && parsed.entries && typeof parsed.entries === "object") stored = parsed.entries;
      } catch (e) { /* 깨진 색인: 처음부터 다시 */ }
    }
    const built = buildIndex_(files, stored, function (f) {
      return DriveApp.getFileById(f.id).getBlob().getDataAsString();
    }, mine ? INDEX_BUDGET_MS : 0);
    if (mine && built.changed) {
      const text = JSON.stringify({v: INDEX_VERSION, entries: built.entries});
      if (indexFile) indexFile.setContent(text); else mainFolder.createFile(INDEX_FILE, text);
    }
    return {files: files, entries: built.entries, pending: built.pending};
  } finally {
    if (mine) lock.releaseLock();
  }
}

/** id 로 파일을 바로 엽니다. 이름으로 폴더를 찾는 것보다 빠릅니다. 이 폴더의 그 이름 파일이 아니면 null. */
function fileById_(folder, id, name) {
  try {
    const file = DriveApp.getFileById(String(id));
    if (file.getName() !== name) return null;
    const parents = file.getParents();
    while (parents.hasNext()) if (parents.next().getId() === folder.getId()) return file;
  } catch (e) { /* 없는 id */ }
  return null;
}

// ── 오류 보고 메일 ───────────────────────────────────────────────────────────
const REPORTS_PER_HOUR = 10;

function sendReport_(data) {
  const props = PropertiesService.getScriptProperties();
  // 접근 암호 없이 열어 둔 주소로는 받지 않습니다. (주소만 알면 누구나 메일을 보내게 할 수 있게 되므로)
  if (!props.getProperty("ACCESS_TOKEN")) return "Token required";
  // 앱 쪽에서도 수를 제한하지만, 여기서도 한 시간에 보내는 수를 막아 둡니다.
  const cache = CacheService.getScriptCache();
  const sent = Number(cache.get("report_count") || 0);
  if (sent >= REPORTS_PER_HOUR) return "Too many";
  cache.put("report_count", String(sent + 1), 3600);
  const to = props.getProperty("ERROR_MAIL_TO") || Session.getEffectiveUser().getEmail();
  if (!to) return "No recipient";
  if (MailApp.getRemainingDailyQuota() < 1) return "Quota exceeded";
  const subject = String(data.subject || "Memos 오류").slice(0, 150);
  const body = String(data.body || "").slice(0, 20000);
  MailApp.sendEmail(to, subject, body);
  return "Reported";
}

// ── PC 앱 동기화 ─────────────────────────────────────────────────────────────
function doPost(e) {
  const data = JSON.parse(e.postData.contents);
  if (!tokenOk_(data.token)) return text_("Unauthorized");
  if (data.action === "report") return text_(sendReport_(data));
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
 *   {action: "list"}                                → {files: [{name, id, updated}]}
 *   {action: "index"}                               → {files, entries: {name: {updated, meta, locked, preview, tags}}, pending}
 *                                                     entries 는 색인(위 설명). pending 은 아직 색인에 넣지 못한 메모 수.
 *   {action: "getMany", names: [...], ids?: {name: id}} → {items: [{name, updated, content}]}
 *                                                     ids 를 함께 주면 이름으로 찾지 않고 바로 엽니다.
 *   {action: "save", name, content, ifUpdated?}     → {ok, updated} 또는 {conflict: true, updated}
 *   {action: "remove", name}                        → {ok}
 * 접근 암호가 틀리면 {error: "auth"}.
 */
function api(req) {
  req = req || {};
  if (!tokenOk_(req.token)) return {error: "auth"};
  const mainFolder = getOrCreateFolder(MAIN_FOLDER);

  if (req.action === "list") {
    return {files: listFiles_(mainFolder).filter(function (f) { return SAFE_NAME.test(f.name) && f.name !== INDEX_FILE; })};
  }

  if (req.action === "index") {
    return refreshIndex_(mainFolder);
  }

  if (req.action === "getMany") {
    const items = [];
    const ids = req.ids && typeof req.ids === "object" ? req.ids : {};
    (req.names || []).forEach(function (name) {
      if (!SAFE_NAME.test(String(name)) || name === INDEX_FILE) return;
      const file = (ids[name] && fileById_(mainFolder, ids[name], name)) || findFile_(mainFolder, name);
      if (file) items.push({name: name, updated: file.getLastUpdated().getTime(), content: file.getBlob().getDataAsString()});
    });
    return {items: items};
  }

  // 색인은 이 스크립트만 씁니다. 화면에서 고치거나 지울 수 없습니다.
  if (!SAFE_NAME.test(String(req.name || "")) || req.name === INDEX_FILE) return {error: "name"};

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
