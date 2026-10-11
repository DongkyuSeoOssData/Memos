// mobile/Index.html 의 동기화 흐름을, mobile/Code.gs 를 가짜 드라이브에 올려 둔 것과 맞물려 돌려 보는 검사.
// 화면(DOM)은 아무 값이나 받아 주는 가짜로 대신하고, 메모를 어떻게 받아 두는지(cache)만 봅니다.
// 쓰는 법: node index_html_check.js <Index.html 경로> <Code.gs 경로>   → 통과하면 "OK"
const fs = require("fs");
const vm = require("vm");
const assert = require("assert");

// ── 가짜 드라이브 + Code.gs ───────────────────────────────────────────────────
let clock = 1000;
const calls = [];            // 화면이 서버에 보낸 요청의 action
function makeFile(folder, name, content) {
  return {
    id: "id-" + name, name, content, updated: ++clock, folder,
    getName() { return this.name; }, getId() { return this.id; },
    getLastUpdated() { return {getTime: () => this.updated}; },
    getBlob() { return {getDataAsString: () => this.content}; },
    setContent(text) { this.content = text; this.updated = ++clock; },
    getParents() { let done = false; return {hasNext: () => !done, next: () => { done = true; return this.folder; }}; },
    moveTo(target) { this.folder.files = this.folder.files.filter((f) => f !== this); target.files.push(this); this.folder = target; },
  };
}
function makeFolder(id) {
  return {
    id, files: [], subs: {},
    getId() { return this.id; },
    getFiles() { let i = 0; const list = this.files.slice(); return {hasNext: () => i < list.length, next: () => list[i++]}; },
    getFilesByName(name) { const hit = this.files.filter((f) => f.name === name); let i = 0; return {hasNext: () => i < hit.length, next: () => hit[i++]}; },
    createFile(name, content) { const f = makeFile(this, name, content); this.files.push(f); return f; },
    getFoldersByName(name) { const hit = this.subs[name] ? [this.subs[name]] : []; let i = 0; return {hasNext: () => i < hit.length, next: () => hit[i++]}; },
    createFolder(name) { this.subs[name] = makeFolder(this.id + "/" + name); return this.subs[name]; },
  };
}
const main = makeFolder("main");
const server = {
  DriveApp: {
    getFoldersByName(name) { const hit = name === "Memos" ? [main] : []; let i = 0; return {hasNext: () => i < hit.length, next: () => hit[i++]}; },
    createFolder() { return main; },
    getFileById(id) { const f = main.files.find((x) => x.id === id); if (!f) throw new Error("no file"); return f; },
  },
  PropertiesService: {getScriptProperties: () => ({getProperty: () => null})},
  LockService: {getScriptLock: () => ({tryLock: () => true, waitLock() {}, releaseLock() {}})},
  ContentService: {createTextOutput: (s) => ({text: s, setMimeType() { return this; }}), MimeType: {JSON: "json"}},
  CacheService: {}, MailApp: {}, Session: {}, HtmlService: {}, console,
};
vm.createContext(server);
vm.runInContext(fs.readFileSync(process.argv[3], "utf8"), server);
let oldScript = false;       // true 면 색인을 모르는 예전 스크립트처럼 답함
let offline = false;
function serve(req) {
  calls.push(req.action);
  if (offline) throw new Error("offline");
  if (oldScript && req.action === "index") return {error: "name"};
  const res = JSON.parse(JSON.stringify(vm.runInContext("api", server)(req)));
  if (oldScript && res.files) res.files.forEach((f) => { delete f.id; });
  return res;
}

// ── 가짜 화면 ─────────────────────────────────────────────────────────────────
function fakeNode() {
  const own = {value: "", textContent: "", hidden: false, className: "", style: {}, children: []};
  return new Proxy(function () {}, {
    get(target, key) {
      if (key in own) return own[key];
      if (key === Symbol.toPrimitive) return () => "";
      if (key === "then") return undefined;
      return fakeNode();
    },
    set(target, key, value) { own[key] = value; return true; },
    apply() { return fakeNode(); },
  });
}
const nodes = {};
const storage = {};
const page = {
  document: {
    getElementById: (id) => (nodes[id] = nodes[id] || fakeNode()),
    createElement: () => fakeNode(), addEventListener() {}, hidden: false, body: fakeNode(),
    querySelector: () => fakeNode(), querySelectorAll: () => [],
  },
  localStorage: {getItem: (k) => (k in storage ? storage[k] : null), setItem: (k, v) => { storage[k] = String(v); }, removeItem: (k) => { delete storage[k]; }},
  location: {search: ""}, navigator: {}, URLSearchParams, setTimeout, clearTimeout, console, Promise, JSON, Date, Math, Map, Set, Array, Object, String, Number,
  crypto: {getRandomValues: (a) => a, subtle: {}}, TextEncoder, TextDecoder, atob: (s) => Buffer.from(s, "base64").toString("binary"),
  btoa: (s) => Buffer.from(s, "binary").toString("base64"),
  fetch: async (url, init) => ({json: async () => serve(JSON.parse(init.body))}),
};
page.window = page;
vm.createContext(page);
const html = fs.readFileSync(process.argv[2], "utf8");
const script = /<script>([\s\S]*?)<\/script>/.exec(html)[1];
const get = (expr) => vm.runInContext(expr, page);
const settle = () => new Promise((resolve) => setTimeout(resolve, 30));
const memo = (id, title, content, extra) => JSON.stringify(Object.assign({id, title, content, updated_at: "2026-01-01T00:00:00"}, extra || {}));
const plain = (x) => JSON.parse(JSON.stringify(x));

(async () => {
  for (let i = 0; i < 20; i++) main.createFile(`m${i}.json`, memo(`m${i}`, `메모 ${i}`, `body ${i} ` + "x".repeat(400) + " #tail" + i));
  main.createFile("lock.json", memo("lock", "비밀", {is_encrypted: true, version: 4, ciphertext: "zz"}, {is_locked: true}));
  main.createFile("broken.json", "not json");

  // 1. 처음 열 때: 색인 한 번으로 목록이 채워지고, 본문은 그 뒤에 받는다.
  let seenPartial = 0;
  page.__spy = () => { seenPartial = Math.max(seenPartial, Object.values(get("cache")).filter((e) => e.partial).length); };
  vm.runInContext(script + "\n;const __render = renderList; renderList = function () { __spy(); return __render.apply(this, arguments); };", page);
  for (let i = 0; i < 40 && get("syncing"); i++) await settle();
  await settle();
  assert.strictEqual(calls[0], "index");
  assert.strictEqual(seenPartial, 21);                           // 목록을 처음 그릴 때는 21개 모두 색인만으로
  let cache = plain(get("cache"));
  assert.strictEqual(Object.keys(cache).length, 21);             // 깨진 파일은 넣지 않음
  assert.ok(Object.values(cache).every((e) => !e.partial));      // 뒤에서 본문까지 다 받음
  assert.ok(cache["m3.json"].memo.content.includes("#tail3"));
  assert.strictEqual(calls.filter((a) => a === "getMany").length, 2);          // 21개를 15개씩
  assert.ok(JSON.parse(storage["memos.cache.v1"])["m3.json"].memo.content);    // 기기에도 저장해 둠

  // 2. 바뀐 것이 없으면 다시 받지 않는다.
  calls.length = 0;
  await get("sync")(false);
  assert.deepStrictEqual(calls, ["index"]);

  // 3. 메모 하나가 바뀌면 그것만 색인으로 갈아 끼우고, 본문도 그것만 받는다.
  main.files.find((f) => f.name === "m5.json").setContent(memo("m5", "고친 제목", "new body #fresh"));
  main.files = main.files.filter((f) => f.name !== "m6.json");
  calls.length = 0;
  await get("sync")(false);
  cache = plain(get("cache"));
  assert.deepStrictEqual(calls, ["index", "getMany"]);
  assert.strictEqual(cache["m5.json"].memo.title, "고친 제목");
  assert.strictEqual(cache["m5.json"].memo.content, "new body #fresh");
  assert.ok(!("m6.json" in cache));

  // 4. 본문을 받기 전의 메모: 목록은 색인의 앞부분·태그·암호 표시로 그리고, 열 때 본문부터 받는다.
  vm.runInContext(`cache["m7.json"] = {updated: cache["m7.json"].updated, memo: {id: "m7", title: "메모 7"}, partial: true,
                                       locked: false, preview: "body 7 preview", tags: ["tail7"]};`, page);
  assert.strictEqual(get('plainOf("m7.json")'), "body 7 preview");
  assert.strictEqual(get('isSealedEntry(cache["m7.json"])'), false);
  assert.strictEqual(get('isSealedEntry({partial: true, locked: true, memo: {}})'), true);
  assert.strictEqual(get('isSealedEntry(cache["lock.json"])'), true);
  calls.length = 0;
  await get("openMemo")("m7.json");
  assert.deepStrictEqual(calls, ["getMany"]);
  assert.ok(!get('cache["m7.json"].partial'));
  assert.ok(get("editing.contentPlain").includes("#tail7"));     // 편집 화면에는 받은 본문이 들어감
  vm.runInContext("editing = null;", page);

  // 5. 연결이 끊긴 채로 본문 없는 메모를 열면 열지 않는다. (본문 없이 열어 저장하면 내용이 지워지므로)
  vm.runInContext(`cache["m8.json"] = {updated: cache["m8.json"].updated, memo: {id: "m8", title: "메모 8"}, partial: true, preview: "", tags: []};`, page);
  offline = true;
  await get("openMemo")("m8.json");
  assert.strictEqual(get("editing"), null);
  assert.ok(get('cache["m8.json"].partial'));
  offline = false;

  // 6. 뒤에서 받은 본문이, 그사이 이 화면에서 저장해 더 새로워진 메모를 덮어쓰지 않는다.
  vm.runInContext(`cache["m9.json"] = {updated: cache["m9.json"].updated + 100000, memo: {id: "m9", title: "방금 저장", content: "newer here"}};`, page);
  await get("fetchBodies")(["m9.json", "m8.json"]);
  assert.strictEqual(get('cache["m9.json"].memo.content'), "newer here");
  assert.ok(!get('cache["m8.json"].partial'));

  // 7. 색인을 모르는 예전 스크립트에서는 전처럼 목록을 받고 파일을 모두 받는다.
  oldScript = true;
  vm.runInContext("cache = {}; fileIds = {};", page);
  calls.length = 0;
  await get("sync")(false);
  cache = plain(get("cache"));
  assert.deepStrictEqual(calls.slice(0, 2), ["index", "list"]);
  assert.strictEqual(Object.keys(cache).length, 20);
  assert.ok(Object.values(cache).every((e) => !e.partial && typeof e.memo.id === "string"));
  assert.deepStrictEqual(plain(get("fileIds")), {});
  oldScript = false;

  console.log("OK");
})().catch((e) => { console.error(e); process.exit(1); });
