from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from typing import Any


STORE_VERSION = 1
STORE_DIR = ".mms/context-store"
INDEX_NAME = "index.json"
ITEMS_DIR = "items"
REF_PREFIX = "mmsctx://"
DEFAULT_SHOW_CHARS = 4000
DEFAULT_SNIPPET_CHARS = 360
DEFAULT_STATS_LIMIT = 10
DEFAULT_STATS_STORE_LIMIT = 12


@dataclass(frozen=True)
class ContextRecord:
    id: str
    created_at: str
    title: str
    kind: str
    tags: list[str]
    path: str
    chars: int
    lines: int
    sha256: str
    snippet: str
    visible_chars: int
    saved_chars: int
    gain_pct: float


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _slug(text: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(text or "").strip()).strip("-._").lower()
    return value[:40] or "context"


def _default_store_dir() -> Path:
    explicit = str(os.environ.get("MMS_CONTEXT_DIR") or "").strip()
    if explicit:
        return Path(explicit).expanduser()

    session_home = str(os.environ.get("MMS_SESSION_HOME") or "").strip()
    if session_home:
        return Path(session_home).expanduser() / STORE_DIR

    return Path.cwd() / STORE_DIR


def _store_dir(path: str | None = None) -> Path:
    return Path(path).expanduser() if path else _default_store_dir()


def _explicit_store_selected(path: str | None = None) -> bool:
    if str(path or "").strip():
        return True
    if str(os.environ.get("MMS_CONTEXT_DIR") or "").strip():
        return True
    if str(os.environ.get("MMS_SESSION_HOME") or "").strip():
        return True
    return False


def _real_home_candidates() -> list[Path]:
    candidates: list[Path] = []
    for key in ("MMS_REAL_HOME", "REAL_HOME", "ORIGINAL_HOME", "HOME"):
        value = str(os.environ.get(key) or "").strip()
        if value:
            candidates.append(Path(value).expanduser())
    try:
        candidates.append(Path.home())
    except RuntimeError:
        pass

    unique: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        unique.append(candidate)
    return unique


def _load_records(root: Path) -> list[dict[str, Any]]:
    return list(_load_index(root)["records"])


def _discover_context_store_dirs(primary: Path, *, limit: int = DEFAULT_STATS_STORE_LIMIT) -> list[Path]:
    """Find recent MMS session context stores for human-facing gain checks."""
    candidates: list[Path] = []
    for home in _real_home_candidates():
        config_root = home / ".config" / "mms"
        if not config_root.exists():
            continue
        try:
            matches = config_root.glob("*/s/*/.mms/context-store")
            for root in matches:
                if root == primary:
                    continue
                index_path = _index_path(root)
                if not index_path.exists():
                    continue
                if not _load_records(root):
                    continue
                candidates.append(root)
        except OSError:
            continue

    unique: dict[str, Path] = {}
    for root in candidates:
        unique.setdefault(str(root.resolve()), root)

    def _sort_key(root: Path) -> float:
        try:
            return _index_path(root).stat().st_mtime
        except OSError:
            return 0.0

    return sorted(unique.values(), key=_sort_key, reverse=True)[: max(0, limit)]


def _index_path(root: Path) -> Path:
    return root / INDEX_NAME


def _items_root(root: Path) -> Path:
    return root / ITEMS_DIR


def _write_text_secure(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(path.name + ".tmp")
    tmp_path.write_text(text, encoding="utf-8")
    os.chmod(tmp_path, 0o600)
    os.replace(tmp_path, path)


def _write_json_secure(path: Path, value: Any) -> None:
    _write_text_secure(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def _ensure_store(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    _items_root(root).mkdir(parents=True, exist_ok=True)


def _load_index(root: Path) -> dict[str, Any]:
    path = _index_path(root)
    if not path.exists():
        return {"version": STORE_VERSION, "records": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": STORE_VERSION, "records": []}
    if not isinstance(data, dict):
        return {"version": STORE_VERSION, "records": []}
    records = data.get("records")
    if not isinstance(records, list):
        records = []
    return {"version": STORE_VERSION, "records": [item for item in records if isinstance(item, dict)]}


def _save_index(root: Path, records: list[dict[str, Any]]) -> None:
    _write_json_secure(
        _index_path(root),
        {
            "version": STORE_VERSION,
            "updated_at": _utc_now(),
            "records": records,
        },
    )


def _normalize_ref(ref: str) -> str:
    value = str(ref or "").strip()
    if value.startswith(REF_PREFIX):
        value = value[len(REF_PREFIX):]
    return value


def _read_input(path: str | None) -> str:
    if path and path != "-":
        return Path(path).expanduser().read_text(encoding="utf-8", errors="replace")
    return sys.stdin.read()


def _trim_snippet(text: str, limit: int = DEFAULT_SNIPPET_CHARS) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) <= limit:
        return compact
    return compact[: max(0, limit - 1)].rstrip() + "…"


def _record_ref(record_id: str) -> str:
    return f"{REF_PREFIX}{record_id}"


def _find_record(root: Path, ref: str) -> dict[str, Any] | None:
    target = _normalize_ref(ref)
    for record in _load_index(root)["records"]:
        if str(record.get("id") or "") == target:
            return record
    return None


def put_context(
    text: str,
    *,
    title: str = "",
    kind: str = "text",
    tags: list[str] | None = None,
    store_dir: str | None = None,
    visible_chars: int | None = None,
) -> ContextRecord:
    root = _store_dir(store_dir)
    _ensure_store(root)
    body = str(text or "")
    sha = hashlib.sha256(body.encode("utf-8")).hexdigest()
    created_at = _utc_now()
    record_id = f"ctx_{created_at.replace('-', '').replace(':', '').replace('Z', '').replace('T', '_')}_{sha[:8]}"
    display_title = str(title or "").strip() or _slug(kind)
    item_name = f"{record_id}-{_slug(display_title)}.txt"
    item_path = _items_root(root) / item_name
    _write_text_secure(item_path, body)

    snippet = _trim_snippet(body)
    body_chars = len(body)
    estimated_visible_chars = len(snippet) if visible_chars is None else max(0, int(visible_chars))
    estimated_visible_chars = min(body_chars, estimated_visible_chars)
    saved_chars = max(0, body_chars - estimated_visible_chars)
    gain_pct = round((saved_chars / body_chars * 100), 1) if body_chars else 0.0
    record = ContextRecord(
        id=record_id,
        created_at=created_at,
        title=display_title,
        kind=str(kind or "text").strip() or "text",
        tags=[str(tag).strip() for tag in (tags or []) if str(tag).strip()],
        path=str(item_path.relative_to(root)),
        chars=body_chars,
        lines=body.count("\n") + (1 if body else 0),
        sha256=sha,
        snippet=snippet,
        visible_chars=estimated_visible_chars,
        saved_chars=saved_chars,
        gain_pct=gain_pct,
    )
    index = _load_index(root)
    records = [asdict(record), *index["records"]]
    _save_index(root, records)
    return record


def read_record_text(root: Path, record: dict[str, Any]) -> str:
    rel_path = str(record.get("path") or "").strip()
    if not rel_path:
        return ""
    path = (root / rel_path).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError:
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def _search_snippet(text: str, query: str, limit: int = DEFAULT_SNIPPET_CHARS) -> str:
    haystack = text.lower()
    needle = query.lower()
    index = haystack.find(needle) if needle else 0
    if index < 0:
        return _trim_snippet(text, limit)
    half = max(40, limit // 2)
    start = max(0, index - half)
    end = min(len(text), index + len(query) + half)
    prefix = "…" if start else ""
    suffix = "…" if end < len(text) else ""
    return _trim_snippet(prefix + text[start:end] + suffix, limit)


def search_context(query: str, *, store_dir: str | None = None, limit: int = 5) -> list[dict[str, Any]]:
    root = _store_dir(store_dir)
    needle = str(query or "").strip().lower()
    results: list[dict[str, Any]] = []
    if not needle:
        return results
    for record in _load_index(root)["records"]:
        text = read_record_text(root, record)
        searchable = "\n".join(
            [
                str(record.get("title") or ""),
                str(record.get("kind") or ""),
                " ".join(str(tag) for tag in record.get("tags") or []),
                text,
            ]
        ).lower()
        if needle not in searchable:
            continue
        item = dict(record)
        item["ref"] = _record_ref(str(record.get("id") or ""))
        item["match_snippet"] = _search_snippet(text, query)
        results.append(item)
        if len(results) >= limit:
            break
    return results


def _print_record(record: dict[str, Any], *, snippet_key: str = "snippet") -> None:
    print(f"ref: {_record_ref(str(record.get('id') or ''))}")
    print(f"title: {record.get('title') or ''}")
    print(f"kind: {record.get('kind') or ''}")
    print(f"chars: {record.get('chars') or 0}")
    print(f"lines: {record.get('lines') or 0}")
    snippet = str(record.get(snippet_key) or record.get("snippet") or "").strip()
    if snippet:
        print("snippet:")
        print(snippet)


def _record_visible_chars(record: dict[str, Any]) -> int:
    """Estimate how much text entered chat for this stored item."""
    snippet = str(record.get("snippet") or "")
    return len(snippet)


def _record_gain(record: dict[str, Any], *, store_dir: Path | None = None) -> dict[str, Any]:
    chars = max(0, int(record.get("chars") or 0))
    visible_value = record.get("visible_chars")
    if visible_value is None:
        visible_chars = min(chars, max(0, _record_visible_chars(record)))
    else:
        visible_chars = min(chars, max(0, int(visible_value or 0)))
    saved_chars = max(0, chars - visible_chars)
    gain_pct = round((saved_chars / chars * 100), 1) if chars else 0.0
    item = {
        "ref": _record_ref(str(record.get("id") or "")),
        "title": record.get("title") or "",
        "kind": record.get("kind") or "",
        "chars": chars,
        "lines": max(0, int(record.get("lines") or 0)),
        "visible_chars": visible_chars,
        "saved_chars": saved_chars,
        "gain_pct": gain_pct,
    }
    if store_dir is not None:
        item["store_dir"] = str(store_dir)
    return item


def context_stats(
    *,
    store_dir: str | None = None,
    limit: int = DEFAULT_STATS_LIMIT,
    kind: str = "",
    tag: str = "",
    all_stores: bool = False,
) -> dict[str, Any]:
    root = _store_dir(store_dir)
    primary_records = _load_records(root)
    explicit_store = _explicit_store_selected(store_dir)
    roots_and_records: list[tuple[Path, list[dict[str, Any]]]] = [(root, primary_records)]
    scope = "active"
    if not explicit_store and (all_stores or not primary_records):
        discovered = _discover_context_store_dirs(root)
        if discovered:
            if all_stores:
                roots_and_records.extend((item, _load_records(item)) for item in discovered)
                scope = "all"
            else:
                roots_and_records = [(discovered[0], _load_records(discovered[0]))]
                root = discovered[0]
                scope = "auto-discovered"

    kind_filter = str(kind or "").strip()
    tag_filter = str(tag or "").strip()
    gains: list[dict[str, Any]] = []
    active_roots: list[Path] = []
    seen_roots: set[str] = set()
    for item_root, records in roots_and_records:
        root_key = str(item_root)
        if root_key not in seen_roots:
            seen_roots.add(root_key)
            active_roots.append(item_root)
        filtered = records
        if kind_filter:
            filtered = [record for record in filtered if str(record.get("kind") or "") == kind_filter]
        if tag_filter:
            filtered = [
                record
                for record in filtered
                if tag_filter in {str(item) for item in (record.get("tags") or [])}
            ]
        gains.extend(_record_gain(record, store_dir=item_root) for record in filtered)
    stored_chars = sum(item["chars"] for item in gains)
    visible_chars = sum(item["visible_chars"] for item in gains)
    saved_chars = sum(item["saved_chars"] for item in gains)
    stored_lines = sum(item["lines"] for item in gains)
    gain_pct = round((saved_chars / stored_chars * 100), 1) if stored_chars else 0.0
    top_records = sorted(gains, key=lambda item: item["saved_chars"], reverse=True)[: max(0, limit)]
    return {
        "store_dir": str(root),
        "store_dirs": [str(item) for item in active_roots],
        "scope": scope,
        "records": len(gains),
        "stored_chars": stored_chars,
        "stored_lines": stored_lines,
        "visible_chars": visible_chars,
        "saved_chars": saved_chars,
        "gain_pct": gain_pct,
        "filters": {"kind": kind_filter, "tag": tag_filter},
        "top_records": top_records,
    }


def _print_stats(payload: dict[str, Any]) -> None:
    print("mms-context stats")
    print(f"store_dir: {payload.get('store_dir') or ''}")
    scope = str(payload.get("scope") or "active")
    if scope != "active":
        print(f"scope: {scope}")
    store_dirs = [str(item) for item in (payload.get("store_dirs") or []) if str(item)]
    if len(store_dirs) > 1:
        print(f"store_dirs: {len(store_dirs)}")
    print(f"records: {payload.get('records') or 0}")
    print(f"stored_chars: {payload.get('stored_chars') or 0}")
    print(f"visible_chars: {payload.get('visible_chars') or 0}")
    print(f"saved_chars: {payload.get('saved_chars') or 0}")
    print(f"gain: {payload.get('gain_pct') or 0}%")
    print(f"stored_lines: {payload.get('stored_lines') or 0}")
    top_records = payload.get("top_records") or []
    if top_records:
        print("top_records:")
        for index, item in enumerate(top_records, 1):
            print(
                f"[{index}] {item.get('ref')} "
                f"saved={item.get('saved_chars')} "
                f"gain={item.get('gain_pct')}% "
                f"title={item.get('title')}"
            )


def _cmd_put(args: argparse.Namespace) -> int:
    text = _read_input(args.path)
    record = put_context(
        text,
        title=args.title or "",
        kind=args.kind or "text",
        tags=args.tag or [],
        store_dir=args.store_dir,
    )
    payload = asdict(record)
    payload["ref"] = _record_ref(record.id)
    payload["store_dir"] = str(_store_dir(args.store_dir))
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    print("mms-context: stored")
    _print_record(payload)
    print(f"path: {Path(payload['store_dir']) / record.path}")
    return 0


def _cmd_search(args: argparse.Namespace) -> int:
    results = search_context(args.query, store_dir=args.store_dir, limit=args.limit)
    if args.json:
        print(json.dumps({"results": results}, ensure_ascii=False, indent=2))
        return 0
    print(f"mms-context search: {len(results)} result(s)")
    for index, record in enumerate(results, 1):
        if index > 1:
            print("")
        print(f"[{index}]")
        _print_record(record, snippet_key="match_snippet")
    return 0


def _cmd_show(args: argparse.Namespace) -> int:
    root = _store_dir(args.store_dir)
    record = _find_record(root, args.ref)
    if not record:
        print(f"mms-context: ref not found: {args.ref}", file=sys.stderr)
        return 2
    text = read_record_text(root, record)
    max_chars = None if args.full else max(0, int(args.max_chars or DEFAULT_SHOW_CHARS))
    body = text if max_chars is None else text[:max_chars]
    truncated = max_chars is not None and len(text) > max_chars
    if args.json:
        payload = dict(record)
        payload["ref"] = _record_ref(str(record.get("id") or ""))
        payload["text"] = body
        payload["truncated"] = truncated
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    _print_record(record)
    print("content:")
    print(body, end="" if body.endswith("\n") else "\n")
    if truncated:
        print(f"\n[mms-context: truncated at {max_chars} chars; use --full to print all]")
    return 0


def _cmd_list(args: argparse.Namespace) -> int:
    root = _store_dir(args.store_dir)
    records = _load_index(root)["records"][: max(0, args.limit)]
    if args.json:
        payload = [dict(record, ref=_record_ref(str(record.get("id") or ""))) for record in records]
        print(json.dumps({"records": payload}, ensure_ascii=False, indent=2))
        return 0
    print(f"mms-context list: {len(records)} item(s)")
    for index, record in enumerate(records, 1):
        if index > 1:
            print("")
        print(f"[{index}]")
        _print_record(record)
    return 0


def _cmd_path(args: argparse.Namespace) -> int:
    print(str(_store_dir(args.store_dir)))
    return 0


def _cmd_stats(args: argparse.Namespace) -> int:
    payload = context_stats(
        store_dir=args.store_dir,
        limit=args.limit,
        kind=args.kind or "",
        tag=args.tag or "",
        all_stores=bool(args.all_stores),
    )
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    _print_stats(payload)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mms-context",
        description="Store large agent-facing context outside chat and pass refs/snippets instead.",
    )
    parser.add_argument("--store-dir", help="Override context store directory.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    put = subparsers.add_parser("put", help="Store text from a file or stdin.")
    put.add_argument("path", nargs="?", default="-", help="Text file path, or '-' / omitted for stdin.")
    put.add_argument("--title", default="", help="Human-readable title.")
    put.add_argument("--kind", default="text", help="Payload kind, e.g. tool-output, handoff, log.")
    put.add_argument("--tag", action="append", default=[], help="Repeatable search tag.")
    put.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    put.set_defaults(func=_cmd_put)

    search = subparsers.add_parser("search", help="Search stored context.")
    search.add_argument("query", help="Search query.")
    search.add_argument("--limit", type=int, default=5, help="Maximum results.")
    search.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    search.set_defaults(func=_cmd_search)

    show = subparsers.add_parser("show", help="Show a stored context ref.")
    show.add_argument("ref", help="Context ref, e.g. mmsctx://ctx_...")
    show.add_argument("--max-chars", type=int, default=DEFAULT_SHOW_CHARS, help="Chars to print unless --full is used.")
    show.add_argument("--full", action="store_true", help="Print full stored text.")
    show.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    show.set_defaults(func=_cmd_show)

    list_cmd = subparsers.add_parser("list", help="List recent stored context refs.")
    list_cmd.add_argument("--limit", type=int, default=20, help="Maximum records.")
    list_cmd.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    list_cmd.set_defaults(func=_cmd_list)

    path = subparsers.add_parser("path", help="Print active context store directory.")
    path.set_defaults(func=_cmd_path)

    for name in ("stats", "gain"):
        stats = subparsers.add_parser(name, help="Show estimated context-saving gain for stored refs.")
        stats.add_argument("--limit", type=int, default=DEFAULT_STATS_LIMIT, help="Top records to show.")
        stats.add_argument("--kind", default="", help="Only include records with this kind.")
        stats.add_argument("--tag", default="", help="Only include records with this tag.")
        stats.add_argument("--all-stores", action="store_true", help="Include discovered MMS session stores.")
        stats.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
        stats.set_defaults(func=_cmd_stats)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except (OSError, ValueError) as exc:
        print(f"mms-context: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
