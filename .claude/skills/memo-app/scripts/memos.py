#!/usr/bin/env python3
"""Memos 앱의 메모 파일을 직접 읽고 쓰는 명령줄 도구. (Claude 스킬용, 표준 라이브러리만 사용)

앱의 저장 규칙(core/sync_manager.py, core/memo_trash.py, core/memo_history.py)을 그대로 따릅니다.
 - 메모 하나 = 메모 폴더의 {id}.json 하나. 쓰기는 임시 파일에 쓴 뒤 바꿔치기합니다.
 - 본문·제목을 바꾸면 updated_at, 폴더·즐겨찾기 같은 속성만 바꾸면 meta_updated_at 을 갱신합니다.
 - 본문·제목을 덮어쓰기 전의 내용은 history_bin/{id}.json 에 남깁니다. (최근 20개)
 - 지우기는 trash_bin 으로 옮기고 deleted_at 을 적고, 드라이브 삭제 대기열(pending_deletes.json)에 넣습니다.
 - 암호 메모의 본문(암호문)과 서식(HTML) 본문은 손대지 않습니다.

경로: 환경 변수 MEMOS_HOME(기본 ~/.memoit_custom), MEMOS_DIR(기본: settings.json 의 local_memo_path → MEMOS_HOME/memos)
"""
import argparse
import json
import os
import re
import sys
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path

UNCHECKED, CHECKED = "☐", "☑"
HISTORY_KEEP = 20
REPEATS = ("none", "daily", "weekdays", "weekly", "monthly", "cron")
DEVICE_ONLY_KEYS = {"position_x", "position_y", "width", "height", "is_visible", "is_rolled_up", "reminder"}
SAFE_ID = re.compile(r"[A-Za-z0-9_-]{1,80}")
HASHTAG = re.compile(r"(?<!\S)#([^\s#]+)")
HEX_COLOR = re.compile(r"[0-9a-fA-F]{6}(?:[0-9a-fA-F]{2})?")
COLORS = {"white": "#FFFFFF", "blue": "#E0F2FE", "green": "#DCFCE7", "yellow": "#FEF9C3", "pink": "#FCE7F3"}

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


class Fail(Exception):
    pass


# ── 경로·설정 ────────────────────────────────────────────────────────────────
def base_path() -> Path:
    return Path(os.environ.get("MEMOS_HOME") or Path.home() / ".memoit_custom")


def load_settings() -> dict:
    try:
        with open(base_path() / "settings.json", "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def memo_dir() -> Path:
    env = os.environ.get("MEMOS_DIR")
    if env:
        return Path(env)
    custom = load_settings().get("local_memo_path")
    return Path(custom) if custom else base_path() / "memos"


def trash_dir() -> Path:
    return memo_dir() / "trash_bin"


def history_dir() -> Path:
    return memo_dir() / "history_bin"


def now_iso() -> str:
    return datetime.now().isoformat()


# ── 파일 입출력 ──────────────────────────────────────────────────────────────
def atomic_write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.flush()
        try:
            os.fsync(f.fileno())
        except OSError:
            pass
    for _ in range(5):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            time.sleep(0.05)
    raise Fail(f"파일을 쓰지 못했습니다: {path}")


def read_json(path: Path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def load_memos(folder: Path) -> list:
    memos = []
    if not folder.exists():
        return memos
    for p in sorted(folder.glob("*.json")):
        m = read_json(p)
        if isinstance(m, dict):
            m.setdefault("id", p.stem)
            m["_file"] = p
            memos.append(m)
    return memos


def save_memo(m: dict) -> None:
    path = m.get("_file") or memo_dir() / f"{m['id']}.json"
    atomic_write_json(path, {k: v for k, v in m.items() if not str(k).startswith("_")})


# ── 본문 해석 ────────────────────────────────────────────────────────────────
def is_locked(m: dict) -> bool:
    return bool(m.get("is_locked")) or isinstance(m.get("content"), dict)


def is_html(content) -> bool:
    if not isinstance(content, str):
        return False
    head = content.lstrip()[:400].lower()
    return head.startswith("<!doctype html public") and "qrichtext" in head


def html_to_text(html: str) -> str:
    import html as html_lib
    s = re.sub(r"<(style|script)[^>]*>.*?</\1>", "", html, flags=re.S | re.I)
    body = re.search(r"<body[^>]*>(.*)</body>", s, flags=re.S | re.I)
    s = body.group(1) if body else s
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
    s = re.sub(r"</(p|li|div|h[1-6]|tr|pre)>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    return html_lib.unescape(s).replace(" ", " ").strip("\n")


def text_of(m: dict) -> str:
    if is_locked(m):
        return ""
    c = m.get("content", "")
    if not isinstance(c, str):
        return str(c)
    return html_to_text(c) if is_html(c) else c


def tags_of(m: dict) -> list:
    return [t for t in HASHTAG.findall(text_of(m)) if not HEX_COLOR.fullmatch(t)]


def box_lines(text: str) -> list:
    """(줄 번호, 체크됨, 줄 내용) 목록. 줄 맨 앞(공백 뒤)의 ☐/☑ 만 체크 항목입니다."""
    out = []
    for i, line in enumerate(text.split("\n")):
        s = line.lstrip(" \t")
        if s[:1] in (UNCHECKED, CHECKED):
            out.append((i, s[0] == CHECKED, s[1:].strip()))
    return out


def progress(text: str) -> str:
    boxes = box_lines(text)
    if not boxes:
        return ""
    done = sum(1 for _, c, _ in boxes if c)
    return f"{CHECKED if done == len(boxes) else UNCHECKED} {done}/{len(boxes)}"


def folder_norm(path) -> str:
    if not isinstance(path, str):
        return ""
    return "/".join(p.strip() for p in path.replace("\\", "/").split("/") if p.strip())


def in_folder(selected: str, memo_folder: str) -> bool:
    if selected in ("", None):
        return True
    if selected == "/unfiled":
        return memo_folder == ""
    selected = folder_norm(selected)
    return memo_folder == selected or memo_folder.startswith(selected + "/")


# ── 메모 찾기 ────────────────────────────────────────────────────────────────
def resolve(memos: list, key: str) -> dict:
    """id → id 앞부분 → 제목(정확히) → 제목(일부) 순서로 메모 하나를 찾습니다."""
    for rule in (
        lambda m: m["id"] == key,
        lambda m: m["id"].startswith(key) and len(key) >= 4,
        lambda m: str(m.get("title", "")).strip() == key.strip(),
        lambda m: key.casefold() in str(m.get("title", "")).casefold(),
    ):
        found = [m for m in memos if rule(m)]
        if len(found) == 1:
            return found[0]
        if len(found) > 1:
            lines = "\n".join(f"  {m['id']}  {m.get('title', '')}" for m in found[:20])
            raise Fail(f"'{key}'에 맞는 메모가 여러 개입니다. id로 지정하세요.\n{lines}")
    raise Fail(f"'{key}'에 맞는 메모가 없습니다.")


def require_editable(m: dict, allow_html: bool = False) -> None:
    if is_locked(m):
        raise Fail("암호 메모입니다. 본문은 앱에서 암호를 풀고 다뤄야 합니다. (제목·폴더 같은 속성만 바꿀 수 있음)")
    if not allow_html and is_html(m.get("content", "")):
        raise Fail("서식(HTML)이 들어간 메모입니다. 본문을 고치면 서식이 깨지므로 건드리지 않습니다. "
                   "서식을 버리고 순수 텍스트로 바꿔도 되면 --plain 을 붙이세요.")


# ── 변경 기록·휴지통 ─────────────────────────────────────────────────────────
def snapshot(m: dict, reason: str = "Claude") -> None:
    path = m.get("_file") or memo_dir() / f"{m['id']}.json"
    old = read_json(path)
    if not isinstance(old, dict):
        return
    hfile = history_dir() / f"{m['id']}.json"
    entries = read_json(hfile, [])
    entries = [e for e in entries if isinstance(e, dict)] if isinstance(entries, list) else []
    if entries and entries[-1].get("content") == old.get("content") and entries[-1].get("title") == old.get("title"):
        return
    entries.append({
        "saved_at": now_iso(), "reason": reason, "title": old.get("title", ""),
        "content": old.get("content", ""), "updated_at": old.get("updated_at", ""),
        "is_locked": isinstance(old.get("content"), dict),
    })
    atomic_write_json(hfile, entries[-HISTORY_KEEP:])


def write_content(m: dict, new_content: str = None, new_title: str = None) -> None:
    snapshot(m)
    if new_content is not None:
        m["content"] = new_content
    if new_title is not None:
        m["title"] = new_title
    m["updated_at"] = now_iso()
    m["is_draft"] = False
    m["is_manually_saved"] = True
    save_memo(m)


def write_meta(m: dict, **changes) -> None:
    for k, v in changes.items():
        if v is None:
            m.pop(k, None)
        else:
            m[k] = v
    m["meta_updated_at"] = now_iso()
    save_memo(m)


# ── 출력 ─────────────────────────────────────────────────────────────────────
def summary(m: dict) -> dict:
    text = text_of(m)
    return {
        "id": m["id"],
        "title": m.get("title", ""),
        "folder": folder_norm(m.get("folder", "")),
        "updated_at": m.get("updated_at", ""),
        "favorite": bool(m.get("is_favorite")),
        "protected": bool(m.get("is_protected")),
        "locked": is_locked(m),
        "open_in_app": bool(m.get("is_visible")),
        "code": m.get("code_lang") if m.get("is_code_memo") else None,
        "formatted": is_html(m.get("content", "")),
        "checklist": progress(text),
        "reminder": m.get("reminder"),
        "tags": tags_of(m),
        "preview": "" if is_locked(m) else " ".join(text.split())[:80],
    }


def print_rows(rows: list, as_json: bool) -> None:
    if as_json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return
    if not rows:
        print("(없음)")
        return
    for r in rows:
        marks = "".join([
            "★" if r["favorite"] else "", "🔒" if r["locked"] else "", "⏰" if r["reminder"] else "",
            "🛡" if r["protected"] else "", "👁" if r.get("open_in_app") else "", f"[{r['code']}]" if r["code"] else "",
        ])
        folder = f" ({r['folder']})" if r["folder"] else ""
        check = f" {r['checklist']}" if r["checklist"] else ""
        print(f"{r['id']}  {marks}{r['title'] or '(제목 없음)'}{folder}{check}  · {r['updated_at'][:16]}")
        if r["preview"]:
            print(f"    {r['preview']}")


def sort_rows(memos: list) -> list:
    return sorted(memos, key=lambda m: (bool(m.get("is_favorite")), str(m.get("updated_at", ""))), reverse=True)


def read_body(args) -> str:
    if getattr(args, "text", None) is not None:
        return args.text
    if getattr(args, "file", None):
        return Path(args.file).read_text(encoding="utf-8")
    if not sys.stdin.isatty():
        return sys.stdin.read()
    return ""


# ── 명령 ─────────────────────────────────────────────────────────────────────
def cmd_info(args):
    d = memo_dir()
    memos = load_memos(d)
    print(json.dumps({
        "settings_dir": str(base_path()), "memo_dir": str(d), "exists": d.exists(),
        "memo_count": len(memos), "trash_count": len(load_memos(trash_dir())),
        "sync_configured": bool(load_settings().get("drive_folder_id")),
    }, ensure_ascii=False, indent=2))


def cmd_list(args):
    memos = load_memos(memo_dir())
    if args.folder is not None:
        memos = [m for m in memos if in_folder(args.folder, folder_norm(m.get("folder", "")))]
    if args.tag:
        tag = args.tag.lstrip("#").casefold()
        memos = [m for m in memos if tag in (t.casefold() for t in tags_of(m))]
    if args.fav:
        memos = [m for m in memos if m.get("is_favorite")]
    if args.todo:
        memos = [m for m in memos if any(not c for _, c, _ in box_lines(text_of(m)))]
    rows = [summary(m) for m in sort_rows(memos)][: args.limit or None]
    print_rows(rows, args.json)


def cmd_search(args):
    q = args.query.casefold()
    hits = []
    for m in load_memos(memo_dir()):
        title, text = str(m.get("title", "")), text_of(m)
        if q in title.casefold() or q in text.casefold():
            row = summary(m)
            lines = [ln.strip() for ln in text.split("\n") if q in ln.casefold()]
            row["matches"] = lines[:5]
            hits.append((m, row))
    hits.sort(key=lambda x: (q in str(x[0].get("title", "")).casefold(), str(x[0].get("updated_at", ""))), reverse=True)
    rows = [r for _, r in hits][: args.limit or None]
    if args.json or not rows:
        print_rows(rows, args.json)
        return
    for r in rows:
        print_rows([{**r, "preview": ""}], False)
        for ln in r["matches"]:
            print(f"    … {ln[:120]}")


def cmd_show(args):
    m = resolve(load_memos(memo_dir()), args.memo)
    if args.json:
        out = summary(m)
        out["text"] = text_of(m)
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return
    s = summary(m)
    print(f"# {s['title'] or '(제목 없음)'}")
    meta = [f"id: {s['id']}", f"폴더: {s['folder'] or '미분류'}", f"수정: {s['updated_at'][:16]}"]
    if s["code"]:
        meta.append(f"코드: {s['code']}")
    if s["formatted"]:
        meta.append("서식 있음(HTML)")
    if s["open_in_app"]:
        meta.append("앱 화면에 열려 있음")
    if s["reminder"]:
        meta.append(f"알림: {s['reminder'].get('at')} ({s['reminder'].get('repeat')})")
    print(" · ".join(meta))
    print()
    print("(암호 메모 — 본문은 앱에서만 볼 수 있습니다)" if s["locked"] else text_of(m))


def cmd_new(args):
    body = read_body(args)
    memo_id = str(uuid.uuid4())
    is_code = bool(args.code)
    m = {
        "id": memo_id,
        "title": args.title or (body.strip().split("\n", 1)[0][:40] if body.strip() else "새 메모"),
        "content": body.rstrip("\n"),
        "folder": folder_norm(args.folder or ""),
        "is_code_memo": is_code,
        "is_pinned": False,
        "is_visible": bool(args.show),
        "is_draft": False,
        "is_manually_saved": True,
        "position_x": 120, "position_y": 120,
        "font_size": 11,
        "updated_at": now_iso(),
    }
    settings = load_settings()
    if is_code:
        theme = settings.get("default_code_theme", "dark")
        m.update({
            "bg_color": "#2E3440" if theme == "dark" else "#FFFFFF",
            "font_family": settings.get("default_code_font_family", "D2Coding"),
            "code_lang": args.code, "code_theme": theme,
            "width": settings.get("default_code_memo_width", 700),
            "height": settings.get("default_code_memo_height", 380),
            "show_line_numbers": settings.get("default_code_line_numbers", True),
            "show_line_bg": settings.get("default_code_line_bg", False),
        })
    else:
        color = COLORS.get(args.color, args.color) if args.color else settings.get("default_memo_color", "#FFFFFF")
        if color == "random":
            color = "#FEF9C3"
        m.update({
            "bg_color": color,
            "font_family": settings.get("default_font_family", "D2Coding"),
            "width": settings.get("default_memo_width", 350),
            "height": settings.get("default_memo_height", 380),
        })
    if args.fav:
        m["is_favorite"] = True
    d = memo_dir()
    d.mkdir(parents=True, exist_ok=True)
    atomic_write_json(d / f"{memo_id}.json", m)
    print(f"만들었습니다: {memo_id}  {m['title']}")


def cmd_append(args):
    m = resolve(load_memos(memo_dir()), args.memo)
    require_editable(m)
    add = read_body(args).rstrip("\n")
    if not add:
        raise Fail("덧붙일 내용이 없습니다. (--text, --file, 또는 표준 입력)")
    if args.todo:
        add = "\n".join(f"{UNCHECKED} {ln.strip()}" if ln.strip() and ln.lstrip()[:1] not in (UNCHECKED, CHECKED) else ln
                        for ln in add.split("\n"))
    old = m.get("content", "") or ""
    old = html_to_text(old) if is_html(old) else old
    write_content(m, (old.rstrip("\n") + "\n" + add) if old.strip() else add)
    print(f"덧붙였습니다: {m['id']}  {m.get('title', '')}")


def cmd_write(args):
    m = resolve(load_memos(memo_dir()), args.memo)
    require_editable(m, allow_html=args.plain)
    body = read_body(args)
    if not body and not args.allow_empty:
        raise Fail("새 본문이 비어 있습니다. 비우려면 --allow-empty 를 붙이세요.")
    write_content(m, body.rstrip("\n"))
    print(f"본문을 바꿨습니다: {m['id']}  {m.get('title', '')} (이전 내용은 앱의 '이전 내용'에서 되돌릴 수 있음)")


def cmd_replace(args):
    m = resolve(load_memos(memo_dir()), args.memo)
    require_editable(m)
    old = m.get("content", "") or ""
    count = old.count(args.old)
    if count == 0:
        raise Fail("바꿀 글자를 찾지 못했습니다.")
    if count > 1 and not args.all:
        raise Fail(f"바꿀 글자가 {count}군데 있습니다. 더 길게 지정하거나 --all 을 붙이세요.")
    write_content(m, old.replace(args.old, args.new) if args.all else old.replace(args.old, args.new, 1))
    print(f"{count if args.all else 1}군데 바꿨습니다: {m['id']}  {m.get('title', '')}")


def cmd_check(args):
    m = resolve(load_memos(memo_dir()), args.memo)
    if is_locked(m):
        raise Fail("암호 메모입니다.")
    content = m.get("content", "") or ""
    text = text_of(m)
    boxes = box_lines(text)
    if not boxes:
        raise Fail("체크리스트 항목이 없는 메모입니다.")
    targets = []
    for item in args.items:
        if item.isdigit():
            n = int(item)
            if not 1 <= n <= len(boxes):
                raise Fail(f"항목 번호는 1~{len(boxes)} 입니다.")
            targets.append(n - 1)
        else:
            found = [i for i, (_, _, t) in enumerate(boxes) if item.casefold() in t.casefold()]
            if len(found) != 1:
                raise Fail(f"'{item}'에 맞는 항목이 {len(found)}개입니다. 번호로 지정하세요.")
            targets.append(found[0])
    want = {"on": True, "off": False}.get(args.state)
    if is_html(content):
        # 서식 메모: 줄 맨 앞이 아닌 곳에 ☐/☑ 가 없을 때만, n번째 상자 글자를 바로 바꿉니다.
        if text.count(UNCHECKED) + text.count(CHECKED) != len(boxes):
            raise Fail("서식 메모의 상자 위치를 확실히 알 수 없어 바꾸지 않았습니다. 앱에서 체크하세요.")
        positions = [i for i, ch in enumerate(content) if ch in (UNCHECKED, CHECKED)]
        if len(positions) != len(boxes):
            raise Fail("서식 메모의 상자 위치를 확실히 알 수 없어 바꾸지 않았습니다. 앱에서 체크하세요.")
        chars = list(content)
        for t in targets:
            state = (not boxes[t][1]) if want is None else want
            chars[positions[t]] = CHECKED if state else UNCHECKED
        new_content = "".join(chars)
    else:
        lines = content.split("\n")
        for t in targets:
            ln = lines[boxes[t][0]]
            idx = len(ln) - len(ln.lstrip(" \t"))
            state = (not boxes[t][1]) if want is None else want
            lines[boxes[t][0]] = ln[:idx] + (CHECKED if state else UNCHECKED) + ln[idx + 1:]
        new_content = "\n".join(lines)
    write_content(m, new_content)
    print(f"{progress(text_of(m))}  {m.get('title', '')}")
    for _, c, t in box_lines(text_of(m)):
        print(f"  {CHECKED if c else UNCHECKED} {t}")


def cmd_set(args):
    m = resolve(load_memos(memo_dir()), args.memo)
    meta, did = {}, []
    if args.title is not None:
        if is_locked(m):
            m["title"] = args.title
            m["updated_at"] = now_iso()
            save_memo(m)
        else:
            write_content(m, new_title=args.title)
        did.append(f"제목 → {args.title}")
    if args.folder is not None:
        meta["folder"] = folder_norm(args.folder)
        did.append(f"폴더 → {meta['folder'] or '미분류'}")
    for flag, key, label in ((args.fav, "is_favorite", "즐겨찾기"), (args.protect, "is_protected", "삭제 방지")):
        if flag is not None:
            meta[key] = flag == "on"
            did.append(f"{label} {'켬' if flag == 'on' else '끔'}")
    if args.color:
        meta["bg_color"] = COLORS.get(args.color, args.color)
        did.append(f"색 → {meta['bg_color']}")
    if meta:
        write_meta(m, **meta)
    if not did:
        raise Fail("바꿀 것을 지정하세요. (--title, --folder, --fav, --protect, --color)")
    print(f"{m['id']}  " + ", ".join(did))


def parse_when(text: str) -> datetime:
    t = text.strip()
    rel = re.fullmatch(r"\+?(\d+)\s*(m|min|분|h|시간|d|일)", t)
    if rel:
        n, unit = int(rel.group(1)), rel.group(2)
        delta = timedelta(minutes=n) if unit in ("m", "min", "분") else timedelta(hours=n) if unit in ("h", "시간") else timedelta(days=n)
        return datetime.now() + delta
    if re.fullmatch(r"\d{1,2}:\d{2}", t):
        h, mi = map(int, t.split(":"))
        at = datetime.now().replace(hour=h, minute=mi, second=0, microsecond=0)
        return at if at > datetime.now() else at + timedelta(days=1)
    try:
        return datetime.fromisoformat(t.replace(" ", "T"))
    except ValueError:
        raise Fail("시각 형식: 2026-11-20T09:00, '2026-11-20 09:00', 15:30, +30m, +2h, +1d")


def app_reminders():
    """앱 소스의 core/reminders.py (표준 라이브러리만 씀). 찾으면 앱과 똑같은 규칙으로 알림을 만듭니다."""
    import importlib.util
    here = Path(__file__).resolve()
    candidates = [Path(os.environ["MEMOS_REPO"])] if os.environ.get("MEMOS_REPO") else []
    candidates += list(here.parents)
    for root in candidates:
        f = root / "core" / "reminders.py"
        if f.is_file() and (root / "main.py").is_file():
            spec = importlib.util.spec_from_file_location("memos_app_reminders", f)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod
    return None


def _cron_field(text: str, low: int, high: int) -> set:
    out = set()
    for part in text.split(","):
        step = 1
        if "/" in part:
            part, st = part.split("/", 1)
            step = int(st)
        if part == "*":
            a, b = low, high
        elif "-" in part:
            a, b = map(int, part.split("-", 1))
        else:
            a = b = int(part)
        if not (low <= a <= high and low <= b <= high and a <= b and step > 0):
            raise Fail(f"크론식 값이 범위를 벗어났습니다: {text}")
        out.update(range(a, b + 1, step))
    return out


def next_cron_fallback(expr: str, after: datetime) -> datetime:
    f = expr.split()
    if len(f) != 5:
        raise Fail("--cron 에 '분 시 일 월 요일' 다섯 칸을 적으세요. 예: '0 9 * * 1-5'")
    mins, hours, days, months = (_cron_field(f[0], 0, 59), _cron_field(f[1], 0, 23),
                                 _cron_field(f[2], 1, 31), _cron_field(f[3], 1, 12))
    wdays = {d % 7 for d in _cron_field(f[4], 0, 7)}
    day_any, wd_any = f[2] == "*", f[4] == "*"
    t = after.replace(second=0, microsecond=0) + timedelta(minutes=1)
    end = t + timedelta(days=366 * 5)
    while t < end:
        cw = (t.weekday() + 1) % 7
        by_d, by_w = t.day in days, cw in wdays
        day_ok = True if (day_any and wd_any) else by_w if day_any else by_d if wd_any else (by_d or by_w)
        if t.month in months and day_ok:
            if t.hour in hours and t.minute in mins:
                return t
            t += timedelta(minutes=1)
        else:
            t = (t + timedelta(days=1)).replace(hour=0, minute=0)
    raise Fail("크론식에 맞는 시각을 찾지 못했습니다.")


def build_reminder(at, repeat: str, cron: str, weekdays, days) -> dict:
    now = datetime.now().replace(microsecond=0)
    lib = app_reminders()
    if lib is not None:
        try:
            if repeat == "cron":
                return lib.make(now, "cron", cron)
            if repeat in ("daily", "weekdays", "weekly", "monthly"):
                return lib.make_repeating(repeat, at.hour, at.minute, now,
                                          weekdays=weekdays or [at.weekday()], days=days or [at.day])
            return lib.make(at, "none")
        except ValueError as e:
            raise Fail(str(e))
    # 앱 소스를 못 찾았을 때: 같은 형식으로 직접 만듭니다.
    if repeat == "cron":
        return {"at": next_cron_fallback(cron, now).isoformat(), "repeat": "cron", "cron": cron.strip()}
    rem = {"at": at.replace(second=0, microsecond=0).isoformat(), "repeat": repeat, "cron": ""}
    if repeat == "weekly":
        rem["weekdays"] = weekdays or [at.weekday()]
    if repeat == "monthly":
        rem["days"] = days or [at.day]
    if repeat != "none":
        # 지금 이후 처음 돌아오는 날로 맞춥니다.
        t = now.replace(hour=at.hour, minute=at.minute, second=0)
        for _ in range(400):
            ok = (repeat == "daily" or (repeat == "weekdays" and t.weekday() < 5)
                  or (repeat == "weekly" and t.weekday() in rem.get("weekdays", []))
                  or (repeat == "monthly" and t.day in rem.get("days", [])))
            if ok and t > now:
                break
            t += timedelta(days=1)
        rem["at"] = t.isoformat()
    return rem


def cmd_remind(args):
    m = resolve(load_memos(memo_dir()), args.memo)
    if args.off:
        m.pop("reminder", None)
        save_memo(m)
        print(f"알림을 풀었습니다: {m.get('title', '')}")
        return
    if args.repeat == "cron" and not args.cron:
        raise Fail("--cron 에 '분 시 일 월 요일' 다섯 칸을 적으세요. 예: '0 9 * * 1-5'")
    if args.repeat != "cron" and not args.at:
        raise Fail("--at 으로 시각을 지정하세요. (반복 알림은 시·분만 쓰입니다)")
    at = parse_when(args.at) if args.at else datetime.now()
    weekdays = [int(x) for x in args.weekdays.split(",")] if args.weekdays else None
    days = [int(x) for x in args.days.split(",")] if args.days else None
    rem = build_reminder(at, args.repeat, args.cron or "", weekdays, days)
    if not rem:
        raise Fail("알림을 만들지 못했습니다. 값을 확인하세요.")
    # 알림은 이 PC에만 두는 값이라 수정일시를 건드리지 않습니다. (앱과 같음)
    m["reminder"] = rem
    save_memo(m)
    print(f"알림을 걸었습니다: {m.get('title', '')} → {rem['at']} ({rem['repeat']}{' ' + rem['cron'] if rem.get('cron') else ''})")


def cmd_reminders(args):
    rows = [(m["reminder"].get("at", ""), m) for m in load_memos(memo_dir()) if isinstance(m.get("reminder"), dict)]
    rows.sort(key=lambda x: x[0])
    if args.json:
        print(json.dumps([{"at": a, "repeat": m["reminder"].get("repeat"), "id": m["id"], "title": m.get("title", "")}
                          for a, m in rows], ensure_ascii=False, indent=2))
        return
    for a, m in rows:
        r = m["reminder"]
        extra = r.get("cron") or r.get("weekdays") or r.get("days") or ""
        print(f"{a[:16]}  [{r.get('repeat')}{' ' + str(extra) if extra else ''}]  {m.get('title', '')}  ({m['id']})")
    if not rows:
        print("(예약된 알림 없음)")


def cmd_folders(args):
    memos = load_memos(memo_dir())
    counts = {}
    for m in memos:
        f = folder_norm(m.get("folder", ""))
        parts = f.split("/") if f else []
        for lv in range(1, len(parts) + 1):
            key = "/".join(parts[:lv])
            counts[key] = counts.get(key, 0) + 1
    saved = [folder_norm(f) for f in load_settings().get("folders", []) if folder_norm(f)]
    names = list(dict.fromkeys(saved + sorted(counts)))
    print(f"전체 {len(memos)} · 미분류 {sum(1 for m in memos if not folder_norm(m.get('folder', '')))}")
    for n in names:
        print(f"{'  ' * n.count('/')}{n.rsplit('/', 1)[-1]}  {counts.get(n, 0)}")


def cmd_tags(args):
    counts = {}
    for m in load_memos(memo_dir()):
        for t in set(tags_of(m)):
            counts[t] = counts.get(t, 0) + 1
    for t, n in sorted(counts.items(), key=lambda x: (-x[1], x[0])):
        print(f"#{t}  {n}")
    if not counts:
        print("(해시태그 없음)")


def cmd_trash(args):
    m = resolve(load_memos(memo_dir()), args.memo)
    if m.get("is_protected"):
        raise Fail("삭제 방지가 걸린 메모입니다. (set --protect off 로 먼저 풀어야 함)")
    if not is_safe_memo_id(m["id"]):
        raise Fail("파일 이름으로 쓸 수 없는 id 입니다.")
    src = m["_file"]
    dst = trash_dir() / f"{m['id']}.json"
    data = {k: v for k, v in m.items() if not str(k).startswith("_")}
    data.setdefault("deleted_at", now_iso())
    atomic_write_json(dst, data)
    src.unlink()
    pending_path = base_path() / "pending_deletes.json"
    pending = read_json(pending_path, [])
    pending = [str(x) for x in pending] if isinstance(pending, list) else []
    if load_settings().get("drive_folder_id") and m["id"] not in pending:
        atomic_write_json(pending_path, pending + [m["id"]])
    print(f"휴지통으로 옮겼습니다: {m['id']}  {m.get('title', '')} (restore 로 되살릴 수 있음)")


def cmd_restore(args):
    m = resolve(load_memos(trash_dir()), args.memo)
    dst = memo_dir() / f"{m['id']}.json"
    if dst.exists():
        raise Fail("같은 id의 메모가 이미 있습니다.")
    data = {k: v for k, v in m.items() if not str(k).startswith("_")}
    data["updated_at"] = now_iso()
    data.pop("deleted_at", None)
    atomic_write_json(dst, data)
    m["_file"].unlink()
    pending_path = base_path() / "pending_deletes.json"
    pending = read_json(pending_path, [])
    if isinstance(pending, list) and m["id"] in pending:
        atomic_write_json(pending_path, [x for x in pending if x != m["id"]])
    print(f"되살렸습니다: {m['id']}  {m.get('title', '')}")


def cmd_trash_list(args):
    memos = sorted(load_memos(trash_dir()), key=lambda m: str(m.get("deleted_at", "")), reverse=True)
    for m in memos:
        print(f"{m['id']}  {m.get('title', '') or '(제목 없음)'}  · 지운 때 {str(m.get('deleted_at', ''))[:16]}")
    if not memos:
        print("(휴지통 비어 있음)")


def cmd_history(args):
    m = resolve(load_memos(memo_dir()), args.memo)
    entries = read_json(history_dir() / f"{m['id']}.json", [])
    entries = [e for e in entries if isinstance(e, dict)] if isinstance(entries, list) else []
    if args.index is not None:
        if not 0 <= args.index < len(entries):
            raise Fail(f"번호는 0~{len(entries) - 1} 입니다.")
        e = entries[args.index]
        if isinstance(e.get("content"), dict):
            print("(잠긴 기록)")
        else:
            c = e.get("content", "")
            print(html_to_text(c) if is_html(c) else c)
        return
    for i, e in reversed(list(enumerate(entries))):
        locked = isinstance(e.get("content"), dict)
        c = e.get("content", "")
        prev = "(잠김)" if locked else " ".join((html_to_text(c) if is_html(c) else str(c)).split())[:60]
        print(f"[{i}] {str(e.get('saved_at', ''))[:16]}  {e.get('title', '')}  {prev}")
    if not entries:
        print("(이전 내용 없음)")


def is_safe_memo_id(memo_id) -> bool:
    return isinstance(memo_id, str) and SAFE_ID.fullmatch(memo_id) is not None


# ── 명령줄 ───────────────────────────────────────────────────────────────────
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="memos", description="Memos 앱의 메모를 읽고 씁니다.")
    sub = p.add_subparsers(dest="cmd", required=True)

    def body_args(sp):
        sp.add_argument("--text", help="내용 (없으면 --file 또는 표준 입력)")
        sp.add_argument("--file", help="내용을 읽을 파일 (UTF-8)")

    sub.add_parser("info", help="메모 폴더 위치와 개수").set_defaults(fn=cmd_info)

    sp = sub.add_parser("list", help="메모 목록 (즐겨찾기 → 최근 수정 순)")
    sp.add_argument("--folder", help="폴더 (하위 폴더 포함). 미분류는 /unfiled")
    sp.add_argument("--tag", help="해시태그")
    sp.add_argument("--fav", action="store_true", help="즐겨찾기만")
    sp.add_argument("--todo", action="store_true", help="안 끝낸 체크 항목이 있는 메모만")
    sp.add_argument("--limit", type=int, default=30)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(fn=cmd_list)

    sp = sub.add_parser("search", help="제목·본문 검색")
    sp.add_argument("query")
    sp.add_argument("--limit", type=int, default=20)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(fn=cmd_search)

    sp = sub.add_parser("show", help="메모 하나 보기")
    sp.add_argument("memo", help="id, id 앞부분(4자 이상), 또는 제목")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(fn=cmd_show)

    sp = sub.add_parser("new", help="새 메모")
    sp.add_argument("--title")
    sp.add_argument("--folder")
    sp.add_argument("--code", metavar="LANG", help="코드 메모로 (JSON, Python, SQL, …)")
    sp.add_argument("--color", help="white/blue/green/yellow/pink 또는 #RRGGBB")
    sp.add_argument("--fav", action="store_true")
    sp.add_argument("--show", action="store_true", help="앱을 다음에 켤 때 화면에 띄움")
    body_args(sp)
    sp.set_defaults(fn=cmd_new)

    sp = sub.add_parser("append", help="본문 끝에 덧붙이기")
    sp.add_argument("memo")
    sp.add_argument("--todo", action="store_true", help="줄마다 ☐ 를 붙여 체크 항목으로")
    body_args(sp)
    sp.set_defaults(fn=cmd_append)

    sp = sub.add_parser("write", help="본문 전체 바꾸기")
    sp.add_argument("memo")
    sp.add_argument("--plain", action="store_true", help="서식 메모를 순수 텍스트로 바꿔도 됨")
    sp.add_argument("--allow-empty", action="store_true")
    body_args(sp)
    sp.set_defaults(fn=cmd_write)

    sp = sub.add_parser("replace", help="본문의 글자 바꾸기")
    sp.add_argument("memo")
    sp.add_argument("old")
    sp.add_argument("new")
    sp.add_argument("--all", action="store_true")
    sp.set_defaults(fn=cmd_replace)

    sp = sub.add_parser("check", help="체크 항목 켜기/끄기 (번호는 1부터, 또는 항목 글자 일부)")
    sp.add_argument("memo")
    sp.add_argument("items", nargs="+")
    sp.add_argument("--state", choices=("on", "off", "toggle"), default="on")
    sp.set_defaults(fn=cmd_check)

    sp = sub.add_parser("set", help="제목·폴더·즐겨찾기·삭제 방지·색 바꾸기")
    sp.add_argument("memo")
    sp.add_argument("--title")
    sp.add_argument("--folder", help="폴더 경로 ('업무/프로젝트A'). 빈 문자열이면 미분류")
    sp.add_argument("--fav", choices=("on", "off"))
    sp.add_argument("--protect", choices=("on", "off"))
    sp.add_argument("--color")
    sp.set_defaults(fn=cmd_set)

    sp = sub.add_parser("remind", help="알림 걸기/풀기")
    sp.add_argument("memo")
    sp.add_argument("--at", help="2026-11-20T09:00 / 15:30 / +30m / +2h / +1d")
    sp.add_argument("--repeat", choices=REPEATS, default="none")
    sp.add_argument("--weekdays", help="weekly: 0(월)~6(일), 쉼표로")
    sp.add_argument("--days", help="monthly: 1~31, 쉼표로")
    sp.add_argument("--cron", help="cron: '분 시 일 월 요일'")
    sp.add_argument("--off", action="store_true")
    sp.set_defaults(fn=cmd_remind)

    sp = sub.add_parser("reminders", help="예약된 알림 목록")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(fn=cmd_reminders)

    sub.add_parser("folders", help="폴더와 메모 개수").set_defaults(fn=cmd_folders)
    sub.add_parser("tags", help="해시태그와 메모 개수").set_defaults(fn=cmd_tags)

    sp = sub.add_parser("trash", help="휴지통으로 옮기기")
    sp.add_argument("memo")
    sp.set_defaults(fn=cmd_trash)

    sp = sub.add_parser("restore", help="휴지통에서 되살리기")
    sp.add_argument("memo")
    sp.set_defaults(fn=cmd_restore)

    sub.add_parser("trash-list", help="휴지통 목록").set_defaults(fn=cmd_trash_list)

    sp = sub.add_parser("history", help="이전 내용 목록 / --index N 으로 그 내용 보기")
    sp.add_argument("memo")
    sp.add_argument("--index", type=int)
    sp.set_defaults(fn=cmd_history)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        args.fn(args)
        return 0
    except Fail as e:
        print(f"오류: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
