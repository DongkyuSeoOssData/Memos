"""모바일 화면(mobile/Index.html)을 구글에 올리지 않고 PC 브라우저에서 시험하는 서버.

구글 앱스 스크립트(mobile/Code.gs)의 api() 와 같은 요청·응답을 흉내 냅니다.
메모는 임시 폴더에 만든 견본을 쓰며, 실제 메모 폴더는 건드리지 않습니다.

    python tools/mobile_dev_server.py                  # 견본 메모로 시작 (http://127.0.0.1:8765)
    python tools/mobile_dev_server.py --token 1234     # 접근 암호를 요구하도록
    python tools/mobile_dev_server.py --dir <폴더>     # 지정한 폴더의 메모 파일로 (복사본으로 시험하세요)
"""
import argparse
import json
import re
import shutil
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SAFE_NAME = re.compile(r"[A-Za-z0-9_-]{1,80}\.json")
LOCK = threading.Lock()

RICH_SAMPLE = (
    '<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.0//EN" "http://www.w3.org/TR/REC-html40/strict.dtd">\n'
    '<html><head><meta name="qrichtext" content="1" /><style type="text/css">p, li { white-space: pre-wrap; }</style></head>'
    '<body><p><span style=" font-weight:600;">주간 회의</span> 정리 #업무</p>'
    '<ul><li>일정 확인</li><li>배포 준비</li></ul><ol><li>첫째</li><li>둘째</li></ol></body></html>'
)


def seed_demo(folder: Path) -> None:
    """견본 메모: 일반·서식·코드·암호(v4)·암호(v3)."""
    import base64
    import os

    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    import utils.crypto_manager as cm
    from utils.crypto_manager import CryptoManager

    crypto = CryptoManager()
    salt = crypto.new_salt()
    key = crypto.derive_key("1234", salt)
    nonce = os.urandom(12)
    b64 = lambda b: base64.b64encode(b).decode()
    v3_payload = {
        "is_encrypted": True, "version": 3, "iterations": cm.MEMO_LOCK_ITERATIONS, "salt": b64(salt), "nonce": b64(nonce),
        "ciphertext": b64(AESGCM(key).encrypt(nonce, "예전 형식(v3) 비밀 메모".encode("utf-8"), None)),
    }
    samples = [
        ("demo-plain", "장보기", "우유, 계란, 사과 #생활", {"bg_color": "#DCFCE7", "is_favorite": True, "folder": "개인"}),
        ("demo-rich", "회의 메모", RICH_SAMPLE, {"bg_color": "#FEF9C3", "folder": "업무/프로젝트A"}),
        ("demo-code", "API 응답", '{\n    "name": "memo",\n    "tags": ["<b>", "#FFFFFF"]\n}',
         {"is_code_memo": True, "code_lang": "JSON", "bg_color": "#2E3440", "folder": "업무"}),
        ("demo-lock4", "비밀 메모", crypto.encrypt_locked("PC 앱에서 잠근 메모 (암호 1234) #비밀", key, salt),
         {"is_locked": True, "bg_color": "#FCE7F3"}),
        ("demo-lock3", "옛 비밀 메모", v3_payload, {"is_locked": True}),
    ]
    # PC 앱이 올려 두는 공유 설정 (폴더 순서, 새 메모 기본값)
    shared = {"updated_at": "2026-10-01T09:00:00.000000",
              "settings": {"folders": ["업무", "업무/프로젝트A", "개인", "빈 폴더"], "default_memo_color": "#E0F2FE",
                           "default_code_lang": "Python", "default_code_theme": "dark"}}
    (folder / "_settings.json").write_text(json.dumps(shared, ensure_ascii=False, indent=2), encoding="utf-8")
    for i, (memo_id, title, content, extra) in enumerate(samples):
        memo = {"id": memo_id, "title": title, "content": content, "updated_at": f"2026-10-0{i + 1}T09:30:00.000000",
                "position_x": 100, "position_y": 100, "is_visible": False}
        memo.update(extra)
        (folder / f"{memo_id}.json").write_text(json.dumps(memo, ensure_ascii=False, indent=2), encoding="utf-8")


def updated_of(path: Path) -> int:
    return path.stat().st_mtime_ns // 1_000_000


def handle_api(folder: Path, token: str, req: dict) -> dict:
    if token and req.get("token") != token:
        return {"error": "auth"}
    action = req.get("action")
    if action == "list":
        return {"files": [{"name": p.name, "updated": updated_of(p)} for p in sorted(folder.glob("*.json"))
                          if SAFE_NAME.fullmatch(p.name)]}
    if action == "getMany":
        items = []
        for name in req.get("names") or []:
            path = folder / str(name)
            if SAFE_NAME.fullmatch(str(name)) and path.exists():
                items.append({"name": name, "updated": updated_of(path), "content": path.read_text(encoding="utf-8")})
        return {"items": items}

    name = str(req.get("name") or "")
    if not SAFE_NAME.fullmatch(name):
        return {"error": "name"}
    path = folder / name
    if action == "save":
        with LOCK:
            if path.exists() and req.get("ifUpdated") and updated_of(path) != req["ifUpdated"]:
                return {"conflict": True, "updated": updated_of(path)}
            path.write_text(str(req.get("content", "")), encoding="utf-8")
            return {"ok": True, "updated": updated_of(path)}
    if action == "remove":
        if path.exists():
            trash = folder / "trash_bin"
            trash.mkdir(exist_ok=True)
            shutil.move(str(path), str(trash / name))
        return {"ok": True}
    return {"error": "action"}


def make_handler(folder: Path, token: str):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            if self.path.split("?")[0] in ("/", "/index.html"):
                self._send(200, (ROOT / "mobile" / "Index.html").read_bytes(), "text/html; charset=utf-8")
            else:
                self._send(404, b"not found", "text/plain")

        def do_POST(self) -> None:
            if self.path.split("?")[0] != "/api":
                self._send(404, b"not found", "text/plain")
                return
            try:
                req = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))).decode("utf-8"))
                res = handle_api(folder, token, req if isinstance(req, dict) else {})
            except Exception as e:
                res = {"error": f"server: {e}"}
            self._send(200, json.dumps(res, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

        def log_message(self, fmt: str, *args) -> None:
            pass

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--token", default="", help="접근 암호 (비우면 확인하지 않음)")
    parser.add_argument("--dir", default="", help="메모 폴더 (비우면 임시 폴더에 견본을 만듦)")
    args = parser.parse_args()

    if args.dir:
        folder = Path(args.dir)
        folder.mkdir(parents=True, exist_ok=True)
    else:
        folder = Path(tempfile.mkdtemp(prefix="memos_mobile_demo_"))
        seed_demo(folder)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(folder, args.token))
    print(f"모바일 화면 시험 서버: http://127.0.0.1:{args.port}  (메모 폴더: {folder})", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
