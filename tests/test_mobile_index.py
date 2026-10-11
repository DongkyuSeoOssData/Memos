"""모바일 색인: 스크립트(Code.gs)가 만드는 요약과, 모바일 화면(Index.html)이 그것으로 목록을 먼저 그리는 흐름.

Code.gs 와 Index.html 은 node 로 돌려 봅니다. (구글 서비스와 화면은 가짜로 대신함. node 가 없으면 그 검사는 건너뜀)
같은 규칙을 따르는 시험용 서버(tools/mobile_dev_server.py)는 파이썬으로 바로 검사합니다.
"""
import importlib.util
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TESTS = Path(__file__).resolve().parent
NODE = shutil.which("node")

RICH = ('<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.0//EN"><html><head><meta name="qrichtext" content="1" />'
        '<style>p { margin:0 }</style></head><body><p>first &amp; line</p><p>second #tag &lt;b&gt;</p>'
        '<ul><li>item one</li><li>item #two</li></ul></body></html>')
SAMPLES = [
    json.dumps({"id": "a", "title": "plain", "content": "hello #work\nsecond line #FFFFFF #home", "folder": "업무"}, ensure_ascii=False),
    json.dumps({"id": "b", "title": "rich", "content": RICH, "is_favorite": True}),
    json.dumps({"id": "c", "title": "code", "content": "#include <x>\n#define Y", "is_code_memo": True}),
    json.dumps({"id": "d", "title": "locked", "content": {"is_encrypted": True, "version": 4, "ciphertext": "zz"}, "is_locked": True}),
    json.dumps({"id": "e", "title": "long", "content": "가나다 " * 300}, ensure_ascii=False),
    json.dumps({"id": "f", "title": "empty", "content": ""}),
    json.dumps({"title": "no id", "content": "x"}),
    "not json at all",
    "[1, 2, 3]",
]


def load_dev_server():
    spec = importlib.util.spec_from_file_location("mobile_dev_server", ROOT / "tools" / "mobile_dev_server.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_node(*args: str) -> str:
    done = subprocess.run([NODE, *args], capture_output=True, text=True, encoding="utf-8", timeout=120)
    if done.returncode != 0:
        raise AssertionError(done.stderr[-3000:] or done.stdout[-3000:])
    return done.stdout


@unittest.skipUnless(NODE, "node 가 없어 건너뜀")
class ScriptAndPageTest(unittest.TestCase):
    def test_script_builds_and_serves_the_index(self) -> None:
        self.assertEqual(run_node(str(TESTS / "code_gs_check.js"), str(ROOT / "mobile" / "Code.gs")).strip(), "OK")

    def test_page_shows_the_list_from_the_index_and_fetches_bodies_after(self) -> None:
        out = run_node(str(TESTS / "index_html_check.js"), str(ROOT / "mobile" / "Index.html"), str(ROOT / "mobile" / "Code.gs"))
        self.assertEqual(out.strip(), "OK")

    def test_test_server_summarizes_exactly_like_the_script(self) -> None:
        srv = load_dev_server()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "samples.json"
            path.write_text(json.dumps(SAMPLES, ensure_ascii=False), encoding="utf-8")
            from_script = json.loads(run_node(str(TESTS / "code_gs_check.js"), str(ROOT / "mobile" / "Code.gs"), str(path)))
        self.assertEqual(from_script, [srv.summarize(text, 7) for text in SAMPLES])


class TestServerIndexTest(unittest.TestCase):
    def setUp(self) -> None:
        self.srv = load_dev_server()
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.folder = Path(self._tmp.name)

    def call(self, **req):
        return self.srv.handle_api(self.folder, "", req)

    def put(self, name: str, text: str) -> None:
        self.assertTrue(self.call(action="save", name=name, content=text)["ok"])

    def test_summary_rules(self) -> None:
        plain, rich, code, locked, long_one, empty, no_id, garbage, not_memo = [self.srv.summarize(t, 7) for t in SAMPLES]
        self.assertEqual(plain["tags"], ["work", "home"])                    # 색상 코드는 태그가 아님
        self.assertEqual(plain["meta"], {"id": "a", "title": "plain", "folder": "업무"})      # 본문은 넣지 않음
        self.assertEqual(rich["preview"], "first & line\nsecond #tag <b>\nitem one\nitem #two")
        self.assertEqual(rich["tags"], ["tag", "two"])
        self.assertEqual(code["tags"], [])
        self.assertTrue(locked["locked"])
        self.assertEqual((locked["preview"], locked["tags"]), ("", []))      # 암호 메모는 본문에서 나오는 것이 없음
        self.assertNotIn("zz", json.dumps(locked))
        self.assertEqual(len(long_one["preview"]), 300)
        self.assertEqual(empty["preview"], "")
        for bad in (no_id, garbage, not_memo):
            self.assertEqual(bad, {"updated": 7, "bad": True})

    def test_index_follows_the_files(self) -> None:
        self.put("a.json", SAMPLES[0])
        self.put("d.json", SAMPLES[3])
        self.put("_settings.json", json.dumps({"updated_at": "x", "settings": {}}))
        first = self.call(action="index")
        self.assertEqual(sorted(first["entries"]), ["a.json", "d.json"])                     # 설정 파일은 메모가 아님
        self.assertEqual(sorted(f["name"] for f in first["files"]), ["_settings.json", "a.json", "d.json"])
        self.assertEqual(first["pending"], 0)
        self.assertEqual(first["entries"]["a.json"]["updated"], next(f["updated"] for f in first["files"] if f["name"] == "a.json"))
        self.assertTrue((self.folder / "_index.json").exists())

        self.put("a.json", SAMPLES[1])                                                       # 고침
        self.assertTrue(self.call(action="remove", name="d.json")["ok"])                     # 지움
        self.put("e.json", SAMPLES[4])                                                       # 새로 만듦
        second = self.call(action="index")
        self.assertEqual(sorted(second["entries"]), ["a.json", "e.json"])
        self.assertEqual(second["entries"]["a.json"]["meta"]["title"], "rich")

    def test_unchanged_memos_are_not_read_again(self) -> None:
        self.put("a.json", SAMPLES[0])
        self.call(action="index")
        stamp = (self.folder / "_index.json").stat().st_mtime_ns
        real, seen = self.srv.summarize, []
        self.srv.summarize = lambda text, updated: (seen.append(updated), real(text, updated))[1]
        self.call(action="index")
        self.assertEqual(seen, [])
        self.assertEqual((self.folder / "_index.json").stat().st_mtime_ns, stamp)            # 색인을 다시 쓰지도 않음

    def test_index_file_is_owned_by_the_server(self) -> None:
        self.put("a.json", SAMPLES[0])
        self.call(action="index")
        self.assertEqual(self.call(action="save", name="_index.json", content="{}"), {"error": "name"})
        self.assertEqual(self.call(action="remove", name="_index.json"), {"error": "name"})
        self.assertEqual(self.call(action="getMany", names=["_index.json"]), {"items": []})
        self.assertNotIn("_index.json", [f["name"] for f in self.call(action="list")["files"]])
        (self.folder / "_index.json").write_text("{broken", encoding="utf-8")                # 깨져도 다시 만듦
        self.assertEqual(sorted(self.call(action="index")["entries"]), ["a.json"])

    def test_download_accepts_ids_but_still_works_without(self) -> None:
        self.put("a.json", SAMPLES[0])
        listed = self.call(action="list")["files"]
        self.assertTrue(all(f.get("id") for f in listed))
        with_ids = self.call(action="getMany", names=["a.json"], ids={"a.json": listed[0]["id"]})
        self.assertEqual(with_ids, self.call(action="getMany", names=["a.json"]))


class DesktopIgnoresTheIndexTest(unittest.TestCase):
    """드라이브에 색인 파일이 생겨도 PC 앱의 동기화는 그것을 메모로 보지 않습니다."""

    def test_pc_sync_neither_pulls_nor_deletes_because_of_the_index(self) -> None:
        import test_core
        case = test_core.SyncManagerTestCase("setUp")
        case.setUp()
        self.addCleanup(case.doCleanups)
        case.sm.save_memo_locally(case._memo("memo-aaaa", "one"))
        case._sync()
        case.drive.put("_index.json", {"v": 1, "entries": {"memo-aaaa.json": {"updated": 1, "meta": {"id": "memo-aaaa"}}}})
        case.drive.downloads.clear()
        case._sync()
        self.assertNotIn("_index.json", case.drive.downloads)
        self.assertEqual(case._contents(), ["one"])
        self.assertFalse((case.memo_dir / "_index.json").exists())
        self.assertIn("_index.json", case.drive.files)                       # 지우지도 않음


if __name__ == "__main__":
    unittest.main()
