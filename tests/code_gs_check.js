// mobile/Code.gs 를 가짜 드라이브 위에서 돌려 보는 검사. (구글 서비스는 흉내만 냄)
// 쓰는 법: node code_gs_check.js <Code.gs 경로> [요약 견줄 입력.json]
//  - 인자가 하나면 색인·내려받기 동작을 검사하고, 통과하면 "OK" 를 찍습니다.
//  - 입력 파일을 주면 그 안의 글자들을 summarize_ 로 요약해 JSON 으로 찍습니다. (파이썬 구현과 견주는 용도)
const fs = require("fs");
const vm = require("vm");
const assert = require("assert");

let clock = 1000;
const reads = [];            // 내용을 읽은 파일 이름 (색인이 바뀐 메모만 다시 읽는지 보려고)
let lockFree = true;

function makeFile(folder, name, content) {
  const file = {
    id: "id-" + name, name, content, updated: ++clock, folder,
    getName() { return this.name; },
    getId() { return this.id; },
    getLastUpdated() { return {getTime: () => this.updated}; },
    getBlob() { reads.push(this.name); return {getDataAsString: () => this.content}; },
    setContent(text) { this.content = text; this.updated = ++clock; },
    getParents() { let done = false; return {hasNext: () => !done, next: () => { done = true; return this.folder; }}; },
    moveTo(target) { this.folder.files = this.folder.files.filter((f) => f !== this); target.files.push(this); this.folder = target; },
  };
  return file;
}
function makeFolder(id) {
  const folder = {
    id, files: [], subs: {},
    getId() { return this.id; },
    getFiles() { let i = 0; const list = this.files.slice(); return {hasNext: () => i < list.length, next: () => list[i++]}; },
    getFilesByName(name) { const hit = this.files.filter((f) => f.name === name); let i = 0; return {hasNext: () => i < hit.length, next: () => hit[i++]}; },
    createFile(name, content) { const f = makeFile(this, name, content); this.files.push(f); return f; },
    getFoldersByName(name) { const hit = this.subs[name] ? [this.subs[name]] : []; let i = 0; return {hasNext: () => i < hit.length, next: () => hit[i++]}; },
    createFolder(name) { this.subs[name] = makeFolder(this.id + "/" + name); return this.subs[name]; },
  };
  return folder;
}
const main = makeFolder("main");
const elsewhere = makeFolder("elsewhere");
const allFiles = () => main.files.concat(elsewhere.files);

const sandbox = {
  DriveApp: {
    getFoldersByName(name) { const hit = name === "Memos" ? [main] : []; let i = 0; return {hasNext: () => i < hit.length, next: () => hit[i++]}; },
    createFolder() { return main; },
    getFileById(id) { const f = allFiles().find((x) => x.id === id); if (!f) throw new Error("no file"); return f; },
  },
  PropertiesService: {getScriptProperties: () => ({getProperty: () => null})},
  LockService: {getScriptLock: () => ({tryLock: () => lockFree, waitLock() {}, releaseLock() {}})},
  ContentService: {createTextOutput: (s) => ({text: s, setMimeType() { return this; }}), MimeType: {JSON: "json"}},
  CacheService: {}, MailApp: {}, Session: {}, HtmlService: {}, console,
};
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(process.argv[2], "utf8"), sandbox);
const run = (expr) => vm.runInContext(expr, sandbox);
const api = (req) => JSON.parse(JSON.stringify(run("api")(req)));

if (process.argv[3]) {
  const inputs = JSON.parse(fs.readFileSync(process.argv[3], "utf8"));
  process.stdout.write(JSON.stringify(inputs.map((text) => run("summarize_")(text, 7))));
  process.exit(0);
}

const memo = (id, title, content, extra) => JSON.stringify(Object.assign({id, title, content, updated_at: "2026-01-01T00:00:00"}, extra || {}));
main.createFile("a.json", memo("a", "첫 메모", "hello #work and more"));
main.createFile("b.json", memo("b", "코드", "#include <x>", {is_code_memo: true}));
main.createFile("c.json", memo("c", "비밀", {is_encrypted: true, version: 4, ciphertext: "zzz"}, {is_locked: true}));
main.createFile("broken.json", "not json");
main.createFile("_settings.json", JSON.stringify({updated_at: "x", settings: {}}));

// 1. 처음: 메모를 모두 읽어 색인을 만든다. 설정 파일과 깨진 파일은 메모로 넣지 않는다.
let res = api({action: "index"});
assert.deepStrictEqual(res.files.map((f) => f.name).sort(), ["_settings.json", "a.json", "b.json", "broken.json", "c.json"]);
assert.strictEqual(res.pending, 0);
assert.deepStrictEqual(Object.keys(res.entries).sort(), ["a.json", "b.json", "broken.json", "c.json"]);
assert.strictEqual(res.entries["a.json"].meta.title, "첫 메모");
assert.ok(!("content" in res.entries["a.json"].meta));
assert.strictEqual(res.entries["a.json"].preview, "hello #work and more");
assert.deepStrictEqual(res.entries["a.json"].tags, ["work"]);
assert.deepStrictEqual(res.entries["b.json"].tags, []);                      // 코드 메모의 # 은 태그가 아님
assert.strictEqual(res.entries["c.json"].locked, true);
assert.strictEqual(res.entries["c.json"].preview, "");                       // 암호 메모는 본문에서 나오는 것을 넣지 않음
assert.ok(!JSON.stringify(res.entries["c.json"]).includes("zzz"));
assert.strictEqual(res.entries["broken.json"].bad, true);
assert.ok(main.files.some((f) => f.name === "_index.json"));
assert.ok(res.files.every((f) => f.id));

// 2. 바뀐 것이 없으면 메모 파일을 다시 읽지 않는다. (색인 파일 하나만 읽음)
reads.length = 0;
const indexUpdated = main.files.find((f) => f.name === "_index.json").updated;
res = api({action: "index"});
assert.deepStrictEqual(reads, ["_index.json"]);
assert.strictEqual(main.files.find((f) => f.name === "_index.json").updated, indexUpdated);     // 고쳐 쓰지도 않음

// 2-1. 화면이 가진 메모(이름 → 수정시각)를 알려 주면, 그 수정시각이 그대로인 메모의 요약은 다시 보내지 않는다.
const haveAll = {};
api({action: "index"}).files.forEach((f) => { haveAll[f.name] = f.updated; });
assert.deepStrictEqual(Object.keys(api({action: "index", have: haveAll}).entries), []);
assert.deepStrictEqual(Object.keys(api({action: "index", have: Object.assign({}, haveAll, {"a.json": 1})}).entries), ["a.json"]);
assert.strictEqual(Object.keys(api({action: "index", have: {}}).entries).length, 4);
assert.strictEqual(api({action: "index", have: haveAll}).files.length, 5);       // 파일 목록은 언제나 전부

// 3. 메모 하나를 고치고, 하나를 지우고, 하나를 새로 만들면 그것만 반영한다.
main.files.find((f) => f.name === "a.json").setContent(memo("a", "고친 메모", "changed"));
main.files = main.files.filter((f) => f.name !== "b.json");
main.createFile("d.json", memo("d", "새 메모", "fresh"));
reads.length = 0;
res = api({action: "index"});
assert.deepStrictEqual(reads.sort(), ["_index.json", "a.json", "d.json"]);
assert.deepStrictEqual(Object.keys(res.entries).sort(), ["a.json", "broken.json", "c.json", "d.json"]);
assert.strictEqual(res.entries["a.json"].meta.title, "고친 메모");
assert.strictEqual(res.entries["a.json"].updated, main.files.find((f) => f.name === "a.json").updated);

// 4. 다른 요청이 색인을 쓰는 중이면 있는 것만 읽어 주고, 못 넣은 메모 수를 알려 준다.
main.createFile("e.json", memo("e", "나중 메모", "later"));
lockFree = false;
reads.length = 0;
res = api({action: "index"});
assert.strictEqual(res.pending, 1);
assert.ok(!("e.json" in res.entries));
assert.deepStrictEqual(reads, ["_index.json"]);
lockFree = true;
res = api({action: "index"});
assert.strictEqual(res.pending, 0);
assert.ok("e.json" in res.entries);

// 5. 시간 한도를 넘기면 남은 것은 다음 요청으로 미룬다.
const many = [];
for (let i = 0; i < 5; i++) many.push({name: `m${i}.json`, id: `x${i}`, updated: i + 1});
let built = run("buildIndex_")(many, {}, () => memo("m", "t", "body"), 0);
assert.strictEqual(built.pending, 5);
assert.deepStrictEqual(Object.keys(built.entries), []);
built = run("buildIndex_")(many, {}, () => memo("m", "t", "body"), 60000);
assert.strictEqual(built.pending, 0);
assert.strictEqual(Object.keys(built.entries).length, 5);
assert.strictEqual(run("buildIndex_")(many, built.entries, () => { throw new Error("should not read"); }, 60000).changed, false);
assert.strictEqual(run("buildIndex_")(many.slice(1), built.entries, () => "", 60000).changed, true);        // 없어진 메모

// 6. 깨진 색인은 버리고 다시 만든다.
main.files.find((f) => f.name === "_index.json").setContent("{broken");
res = api({action: "index"});
assert.deepStrictEqual(Object.keys(res.entries).sort(), ["a.json", "broken.json", "c.json", "d.json", "e.json"]);

// 7. 내려받기: id 를 주면 이름으로 찾지 않고 바로 연다. 이 폴더의 그 이름 파일이 아니면 id 를 믿지 않는다.
const idOf = (name) => main.files.find((f) => f.name === name).id;
let searched = 0;
const realSearch = main.getFilesByName.bind(main);
main.getFilesByName = (name) => { searched++; return realSearch(name); };
res = api({action: "getMany", names: ["a.json", "d.json"], ids: {"a.json": idOf("a.json"), "d.json": idOf("d.json")}});
assert.strictEqual(res.items.length, 2);
assert.strictEqual(searched, 0);
assert.ok(res.items[0].content.includes("고친 메모"));
const secret = elsewhere.createFile("a.json", "SECRET FROM ANOTHER FOLDER");
res = api({action: "getMany", names: ["a.json"], ids: {"a.json": secret.id}});
assert.ok(!res.items[0].content.includes("SECRET"));                         // 다른 폴더의 파일은 열지 않고, 이름으로 다시 찾음
res = api({action: "getMany", names: ["a.json"], ids: {"a.json": idOf("d.json")}});
assert.ok(res.items[0].content.includes("고친 메모"));                         // 이름이 다른 id 도 믿지 않음
res = api({action: "getMany", names: ["a.json"], ids: {"a.json": "no-such-id"}});
assert.strictEqual(res.items.length, 1);
res = api({action: "getMany", names: ["a.json"]});                           // id 없이도 전처럼 동작
assert.strictEqual(res.items.length, 1);

// 8. 색인 파일은 화면에서 읽거나 고치거나 지울 수 없고, 목록에도 나오지 않는다.
assert.deepStrictEqual(api({action: "getMany", names: ["_index.json"]}).items, []);
assert.deepStrictEqual(api({action: "save", name: "_index.json", content: "{}"}), {error: "name"});
assert.deepStrictEqual(api({action: "remove", name: "_index.json"}), {error: "name"});
assert.ok(!api({action: "list"}).files.some((f) => f.name === "_index.json"));
assert.ok(!api({action: "index"}).files.some((f) => f.name === "_index.json"));

// 9. 서식 문서(Qt)는 글자만 뽑아 앞부분과 태그를 만든다.
const rich = '<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.0//EN"><html><head><meta name="qrichtext" content="1" /><style>p { x }</style></head>'
  + '<body><p>first &amp; line</p><p>second #tag &lt;b&gt;</p><ul><li>item</li></ul></body></html>';
const sum = run("summarize_")(memo("r", "rich", rich), 1);
assert.strictEqual(sum.preview, "first & line\nsecond #tag <b>\nitem");
assert.deepStrictEqual(Array.from(sum.tags), ["tag"]);
assert.strictEqual(run("summarize_")(memo("p", "plain", "<p>not rich</p> #a #FFFFFF"), 1).preview, "<p>not rich</p> #a #FFFFFF");
assert.deepStrictEqual(Array.from(run("summarize_")(memo("p", "plain", "<p>not rich</p> #a #FFFFFF"), 1).tags), ["a"]);
assert.strictEqual(run("summarize_")(memo("l", "long", "x".repeat(1000)), 1).preview.length, 300);

console.log("OK");
