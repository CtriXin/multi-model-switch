"""OpenCode config file and environment materialization helpers."""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import time
from pathlib import Path

from mms_opencode_config import opencode_config_slug


def opencode_write_config(path, runtime, model, *, build_config_content, atomic_write_text):
    config_content = build_config_content(runtime, model)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    atomic_write_text(path, config_content + "\n", mode=0o600)
    return config_content


_OPENCODE_SHARED_STATE_MIGRATION_MARKER = ".mms-shared-state-migration-v1"
_OPENCODE_PROFILE_MARKER = ".mms/opencode-profile"
_OPENCODE_ISOLATE_DATA_MARKER = ".mms/opencode-isolate-data"
_OPENCODE_INCREMENTAL_SKIP_DIRS = {"log"}
_BOOL_TRUE_VALUES = {"1", "true", "yes", "on", "enable", "enabled"}
_BOOL_FALSE_VALUES = {"0", "false", "no", "off", "disable", "disabled"}
_OPENCODE_SHARED_CACHE_ENV = "MMS_OPENCODE_SHARED_CACHE"


def _write_opencode_profile_marker(session_home, profile_slug):
    marker = Path(session_home) / _OPENCODE_PROFILE_MARKER
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(profile_slug + "\n", encoding="utf-8")


def _write_opencode_isolate_data_marker(session_home):
    marker = Path(session_home) / _OPENCODE_ISOLATE_DATA_MARKER
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("1\n", encoding="utf-8")


def opencode_profile_state_slug(profile_id):
    raw = str(profile_id or "").strip().lower()
    slug = re.sub(r"[^a-z0-9._-]+", "-", raw).strip("._-")
    if not slug:
        raise ValueError("opencode profile_id is required for shared OpenCode state")
    if slug == "default":
        raise ValueError("opencode profile_id must not use the reserved default namespace")
    return slug


def _opencode_isolate_data_enabled(env):
    raw = str(env.get("MMS_OPENCODE_ISOLATE_DATA") or os.environ.get("MMS_OPENCODE_ISOLATE_DATA") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _boolish(value, default=False):
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    raw = str(value).strip().lower()
    if raw in _BOOL_TRUE_VALUES:
        return True
    if raw in _BOOL_FALSE_VALUES:
        return False
    return default


def _opencode_external_skills_enabled(runtime, env):
    runtime = runtime if isinstance(runtime, dict) else {}
    if "opencode_external_skills" in runtime:
        return _boolish(runtime.get("opencode_external_skills"), default=False)
    return _boolish(env.get("MMS_OPENCODE_EXTERNAL_SKILLS"), default=False)


def _opencode_real_home_enabled(runtime, env):
    runtime = runtime if isinstance(runtime, dict) else {}
    if "opencode_real_home" in runtime:
        return _boolish(runtime.get("opencode_real_home"), default=False)
    return _boolish(env.get("MMS_OPENCODE_REAL_HOME"), default=False)


def _opencode_shared_cache_enabled(runtime, env):
    runtime = runtime if isinstance(runtime, dict) else {}
    if "opencode_shared_cache" in runtime:
        return _boolish(runtime.get("opencode_shared_cache"), default=True)
    if _OPENCODE_SHARED_CACHE_ENV in env:
        return _boolish(env.get(_OPENCODE_SHARED_CACHE_ENV), default=True)
    if _OPENCODE_SHARED_CACHE_ENV in os.environ:
        return _boolish(os.environ.get(_OPENCODE_SHARED_CACHE_ENV), default=True)
    return True


def opencode_apply_external_skill_policy(env, runtime):
    """Keep MMS-managed OpenCode from scanning global Claude/agent skills by default."""
    if _opencode_external_skills_enabled(runtime, env):
        env.pop("OPENCODE_DISABLE_EXTERNAL_SKILLS", None)
        env.pop("OPENCODE_DISABLE_CLAUDE_CODE_SKILLS", None)
        env["MMS_OPENCODE_EXTERNAL_SKILLS"] = "1"
        return env
    env["OPENCODE_DISABLE_EXTERNAL_SKILLS"] = "1"
    env["OPENCODE_DISABLE_CLAUDE_CODE_SKILLS"] = "1"
    env["MMS_OPENCODE_EXTERNAL_SKILLS"] = "0"
    return env


def _copy_missing_tree(src, dst):
    src = Path(src)
    dst = Path(dst)
    if not src.is_dir():
        return False
    copied = False
    for path in sorted(src.rglob("*")):
        rel = path.relative_to(src)
        target = dst / rel
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        if target.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        copied = True
    return copied


def _opencode_profile_slug_from_config(session_dir):
    session_dir = Path(session_dir)
    config_path = session_dir / ".config" / "opencode" / "opencode.json"
    if not config_path.is_file():
        return ""
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    if not isinstance(payload, dict):
        return ""

    default_agent = str(payload.get("default_agent") or payload.get("agent") or "").strip()
    agent_map = {
        "mobius-builder-pro": "lite_pro_orchestrated",
        "mobius-builder-stable": "lite_pro_orchestrated",
        "mobius-builder": "lite",
        "review-hub-host": "review_hub",
        "review-hub-host-stable": "review_hub",
        "committee-host": "committee",
        "committee-host-pro": "committee",
    }
    if default_agent in agent_map:
        return agent_map[default_agent]

    agents = payload.get("agent")
    agent_keys = set(agents) if isinstance(agents, dict) else set()
    if any(str(key).startswith("review-") for key in agent_keys):
        return "review_hub"
    if any(str(key).startswith("committee-") for key in agent_keys):
        return "committee"
    if any(str(key).startswith("mobius-") for key in agent_keys):
        return "lite_pro_orchestrated"
    if not default_agent and not agent_keys:
        return "raw"
    return ""


def _opencode_profile_slug_from_session(session_dir):
    session_dir = Path(session_dir)
    marker = session_dir / _OPENCODE_PROFILE_MARKER
    if marker.is_file():
        try:
            return opencode_profile_state_slug(marker.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return ""
    return _opencode_profile_slug_from_config(session_dir)


def _opencode_legacy_profile_slug_from_session(session_dir):
    session_dir = Path(session_dir)
    if (session_dir / _OPENCODE_PROFILE_MARKER).exists():
        return ""
    if (session_dir / _OPENCODE_ISOLATE_DATA_MARKER).exists():
        return ""
    return _opencode_profile_slug_from_config(session_dir)


def _opencode_profile_state_root(real_user_path, profile_slug):
    return Path(real_user_path(".local", "share", "mms-opencode", "state", profile_slug))


def _opencode_profile_cache_root(real_user_path, profile_slug):
    return Path(real_user_path(".local", "share", "mms-opencode", "cache", profile_slug))


def _opencode_link_shared_cache_dir(session_home, relative_path, target_dir):
    link_path = Path(session_home, *Path(relative_path).parts)
    target_dir = Path(target_dir)
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        if link_path.is_symlink():
            if link_path.resolve() == target_dir.resolve():
                return True
            link_path.unlink()
        elif link_path.exists():
            if link_path.is_dir():
                try:
                    next(link_path.iterdir())
                    return False
                except StopIteration:
                    link_path.rmdir()
            else:
                return False
        link_path.parent.mkdir(parents=True, exist_ok=True)
        link_path.symlink_to(target_dir, target_is_directory=True)
        return True
    except OSError:
        return False


def _materialize_opencode_shared_cache(env, session_home, cache_root, *, use_real_home):
    """Share cold-start caches without exposing the real HOME tree."""
    cache_root = Path(cache_root)
    cache_root.mkdir(parents=True, exist_ok=True)
    env[_OPENCODE_SHARED_CACHE_ENV] = "1"
    env["MMS_OPENCODE_CACHE_ROOT"] = str(cache_root)

    xdg_opencode_cache = cache_root / "xdg-cache" / "opencode"
    if _opencode_link_shared_cache_dir(session_home, ".cache/opencode", xdg_opencode_cache):
        env["MMS_OPENCODE_XDG_CACHE_SHARED"] = "1"
    else:
        env["MMS_OPENCODE_XDG_CACHE_SHARED"] = "0"

    # With isolated HOME, OpenCode/Bun/npm otherwise rebuild per-session caches.
    if use_real_home:
        env["MMS_OPENCODE_HOME_CACHE_SHARED"] = "0"
        return env

    npm_cache = cache_root / "npm"
    bun_cache = cache_root / "bun-install-cache"
    darwin_cache = cache_root / "darwin-caches"
    home_cache_shared = [
        _opencode_link_shared_cache_dir(session_home, ".npm", npm_cache),
        _opencode_link_shared_cache_dir(session_home, ".bun/install/cache", bun_cache),
        _opencode_link_shared_cache_dir(session_home, "Library/Caches", darwin_cache),
    ]
    env["MMS_OPENCODE_HOME_CACHE_SHARED"] = "1" if all(home_cache_shared) else "0"
    for key, value in (
        ("npm_config_cache", str(npm_cache)),
        ("NPM_CONFIG_CACHE", str(npm_cache)),
        ("BUN_INSTALL_CACHE_DIR", str(bun_cache)),
    ):
        if not str(env.get(key) or "").strip():
            env[key] = value
    return env


def _write_opencode_shared_state_marker(state_root, *, migrated, covered_mtime_ns=0):
    state_root.mkdir(parents=True, exist_ok=True)
    marker = state_root / _OPENCODE_SHARED_STATE_MIGRATION_MARKER
    marker.write_text("migrated=1\n" if migrated else "migrated=0\n", encoding="utf-8")
    if migrated and covered_mtime_ns:
        try:
            os.utime(marker, ns=(int(covered_mtime_ns), int(covered_mtime_ns)))
        except OSError:
            marker.write_text("migrated=0\n", encoding="utf-8")


def _opencode_shared_state_marker_mtime_ns(state_root):
    marker = Path(state_root) / _OPENCODE_SHARED_STATE_MIGRATION_MARKER
    try:
        if marker.read_text(encoding="utf-8").strip() != "migrated=1":
            return 0
        return marker.stat().st_mtime_ns
    except OSError:
        return 0


def _opencode_migration_cutoff_mtime_ns():
    try:
        return time.time_ns()
    except Exception:
        return 0


def _opencode_data_checkpoint_mtime_ns(data_dir):
    data_dir = Path(data_dir)
    newest = 0
    stack = [data_dir]
    while stack:
        current = stack.pop()
        try:
            newest = max(newest, current.stat().st_mtime_ns)
        except OSError:
            continue
        try:
            children = sorted(current.iterdir())
        except OSError:
            return 0
        for path in children:
            if _opencode_incremental_path_skipped(data_dir, path):
                continue
            try:
                newest = max(newest, path.stat().st_mtime_ns)
            except OSError:
                continue
            if path.is_dir():
                stack.append(path)
    return newest


def _opencode_incremental_path_skipped(root, path):
    try:
        rel = Path(path).relative_to(root)
    except ValueError:
        return False
    return bool(rel.parts and rel.parts[0] in _OPENCODE_INCREMENTAL_SKIP_DIRS)


def _is_sqlite_db(path):
    try:
        with Path(path).open("rb") as handle:
            return handle.read(16) == b"SQLite format 3\x00"
    except OSError:
        return False


def _sqlite_quote_ident(name):
    return '"' + str(name).replace('"', '""') + '"'


def _sqlite_table_names(conn):
    return [
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
    ]


def _sqlite_table_info(conn, table_name):
    table_sql = _sqlite_quote_ident(table_name)
    return conn.execute(f"PRAGMA table_info({table_sql})").fetchall()


def _sqlite_table_exists(conn, table_name):
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone() is not None


def _sqlite_ensure_table(dst_conn, src_conn, table_name):
    if _sqlite_table_exists(dst_conn, table_name):
        return False
    create_row = src_conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    create_sql = str(create_row[0] or "").strip() if create_row else ""
    if not create_sql:
        return False
    dst_conn.execute(create_sql)
    return True


def _sqlite_column_default_sql(table_name, info_row):
    column_name = str(info_row[1] or "")
    column_type = str(info_row[2] or "")
    default_sql = info_row[4]
    if default_sql is not None:
        return str(default_sql)
    if table_name == "session":
        if column_name == "project_id":
            return "'legacy-migrated-project'"
        if column_name == "slug":
            return "''"
        if column_name == "version":
            return "'1'"
    normalized_type = column_type.upper()
    if any(token in normalized_type for token in ("INT", "REAL", "NUM")):
        return "0"
    return "''"


def _sqlite_sync_existing_table_columns(dst_conn, src_conn, table_name):
    src_info = _sqlite_table_info(src_conn, table_name)
    dst_columns = {row[1] for row in _sqlite_table_info(dst_conn, table_name)}
    changed = False
    table_sql = _sqlite_quote_ident(table_name)
    for info_row in src_info:
        column_name = str(info_row[1] or "")
        if not column_name or column_name in dst_columns:
            continue
        if int(info_row[5] or 0) > 0:
            continue
        column_type = str(info_row[2] or "").strip() or "TEXT"
        column_sql = f"{_sqlite_quote_ident(column_name)} {column_type}"
        not_null = int(info_row[3] or 0) > 0
        if not_null:
            column_sql += f" NOT NULL DEFAULT {_sqlite_column_default_sql(table_name, info_row)}"
        elif info_row[4] is not None:
            column_sql += f" DEFAULT {info_row[4]}"
        dst_conn.execute(f"ALTER TABLE {table_sql} ADD COLUMN {column_sql}")
        changed = True
    if changed and table_name == "session" and _sqlite_table_exists(dst_conn, "project"):
        project_table_info = _sqlite_table_info(dst_conn, "project")
        project_columns = [row[1] for row in project_table_info]
        legacy_values = {
            "id": "legacy-migrated-project",
            "worktree": "",
            "name": "Legacy Migrated Project",
            "sandboxes": "[]",
            "time_created": 0,
            "time_updated": 0,
            "time_initialized": 0,
        }
        insert_columns = []
        insert_values = []
        for info_row in project_table_info:
            column_name = str(info_row[1] or "")
            if not column_name:
                continue
            insert_columns.append(_sqlite_quote_ident(column_name))
            if column_name in legacy_values:
                insert_values.append(legacy_values[column_name])
                continue
            if int(info_row[3] or 0) > 0:
                column_type = str(info_row[2] or "").upper()
                insert_values.append(0 if any(token in column_type for token in ("INT", "REAL", "NUM")) else "")
                continue
            insert_values.append(None)
        dst_conn.execute(
            f"INSERT OR IGNORE INTO project ({', '.join(insert_columns)}) VALUES ({', '.join('?' for _ in insert_values)})",
            tuple(insert_values),
        )
        dst_conn.execute(
            "UPDATE session SET project_id = COALESCE(NULLIF(project_id, ''), ?), slug = COALESCE(NULLIF(slug, ''), id), version = COALESCE(NULLIF(version, ''), ?) WHERE project_id IS NULL OR project_id = '' OR slug IS NULL OR slug = '' OR version IS NULL OR version = ''",
            ("legacy-migrated-project", "1"),
        )
    return changed


def _sqlite_row_signature(row):
    return tuple(row) if row is not None else None


def _sqlite_time_updated_value(columns, row):
    try:
        idx = columns.index("time_updated")
    except ValueError:
        return None
    return int(row[idx] or 0)


def _sync_sqlite_table_rows(src_conn, dst_conn, table_name):
    schema_changed = _sqlite_sync_existing_table_columns(dst_conn, src_conn, table_name)
    src_table_info = _sqlite_table_info(src_conn, table_name)
    dst_table_info = _sqlite_table_info(dst_conn, table_name)
    dst_columns = {row[1] for row in dst_table_info}
    table_info = [row for row in src_table_info if row[1] in dst_columns]
    columns = [row[1] for row in table_info]
    if not columns:
        return schema_changed
    pk_columns = [
        info_row[1]
        for info_row in sorted(table_info, key=lambda item: item[5] or 0)
        if int(info_row[5] or 0) > 0
    ]
    table_sql = _sqlite_quote_ident(table_name)
    column_sql = ", ".join(_sqlite_quote_ident(column) for column in columns)
    src_rows = src_conn.execute(f"SELECT {column_sql} FROM {table_sql}").fetchall()
    if not src_rows:
        return schema_changed

    changed = schema_changed
    select_existing_sql = ""
    if pk_columns:
        where_sql = " AND ".join(f"{_sqlite_quote_ident(column)} = ?" for column in pk_columns)
        select_existing_sql = f"SELECT {column_sql} FROM {table_sql} WHERE {where_sql}"
    insert_sql = f"INSERT INTO {table_sql} ({column_sql}) VALUES ({', '.join('?' for _ in columns)})"
    non_pk_columns = [column for column in columns if column not in pk_columns]
    if pk_columns and non_pk_columns:
        set_sql = ", ".join(f"{_sqlite_quote_ident(column)} = ?" for column in non_pk_columns)
        where_sql = " AND ".join(f"{_sqlite_quote_ident(column)} = ?" for column in pk_columns)
        update_sql = f"UPDATE {table_sql} SET {set_sql} WHERE {where_sql}"
    else:
        update_sql = ""

    for row in src_rows:
        existing = None
        if select_existing_sql:
            pk_values = tuple(row[columns.index(column)] for column in pk_columns)
            existing = dst_conn.execute(select_existing_sql, pk_values).fetchone()
        if existing is None:
            dst_conn.execute(insert_sql, row)
            changed = True
            continue
        if _sqlite_row_signature(existing) == _sqlite_row_signature(row):
            continue
        src_updated = _sqlite_time_updated_value(columns, row)
        dst_updated = _sqlite_time_updated_value(columns, existing)
        if src_updated is not None and dst_updated is not None and src_updated < dst_updated:
            continue
        if update_sql:
            non_pk_values = [row[columns.index(column)] for column in non_pk_columns]
            dst_conn.execute(update_sql, tuple(non_pk_values) + pk_values)
            changed = True
            continue
    return changed


def _sync_opencode_sqlite_db(src, dst):
    import sqlite3

    src = Path(src)
    dst = Path(dst)
    if not src.exists():
        return False, False, False
    if not _is_sqlite_db(src):
        return False, False, False
    if dst.exists() and not _is_sqlite_db(dst):
        return True, False, True

    changed = False
    src_conn = sqlite3.connect(str(src))
    try:
        if not dst.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst_conn = sqlite3.connect(str(dst))
            try:
                src_conn.backup(dst_conn)
                dst_conn.commit()
                return True, True, False
            finally:
                dst_conn.close()

        dst_conn = sqlite3.connect(str(dst))
        try:
            for table_name in _sqlite_table_names(src_conn):
                changed = _sqlite_ensure_table(dst_conn, src_conn, table_name) or changed
                changed = _sync_sqlite_table_rows(src_conn, dst_conn, table_name) or changed
            if changed:
                dst_conn.commit()
            return True, changed, False
        finally:
            dst_conn.close()
    except sqlite3.DatabaseError:
        return True, False, True
    finally:
        src_conn.close()


def _sync_opencode_db(src, dst):
    src = Path(src)
    dst = Path(dst)
    if not src.exists():
        return False, False
    src_is_sqlite = _is_sqlite_db(src)
    dst_is_sqlite = dst.exists() and _is_sqlite_db(dst)
    if not src_is_sqlite and dst_is_sqlite:
        return False, True
    dst.parent.mkdir(parents=True, exist_ok=True)
    handled, changed, failed = _sync_opencode_sqlite_db(src, dst)
    if handled:
        return changed, failed
    if not dst.exists():
        return _copy_opencode_file(src, dst)
    try:
        src_stat = src.stat()
        dst_stat = dst.stat()
    except OSError:
        return False, True
    if src_stat.st_mtime_ns <= dst_stat.st_mtime_ns:
        return False, False
    return _copy_opencode_file(src, dst)


def _copy_opencode_file(src, dst):
    src = Path(src)
    dst = Path(dst)
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(prefix=f".{dst.name}.", suffix=".tmp", dir=dst.parent)
        os.close(fd)
        tmp = Path(tmp_name)
        try:
            shutil.copy2(src, tmp)
            os.replace(tmp, dst)
            return True, False
        finally:
            try:
                tmp.unlink()
            except FileNotFoundError:
                pass
    except OSError:
        return False, True


def _sync_opencode_tree(src, dst):
    src = Path(src)
    dst = Path(dst)
    if not src.is_dir():
        return False, False
    changed = False
    failed = False
    for path in sorted(src.rglob("*")):
        rel = path.relative_to(src)
        target = dst / rel
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        if path.name in {"opencode.db-wal", "opencode.db-shm"}:
            continue
        if path.name == "opencode.db":
            db_changed, db_failed = _sync_opencode_db(path, target)
            changed = db_changed or changed
            failed = db_failed or failed
            continue
        if target.exists():
            try:
                if path.stat().st_mtime_ns <= target.stat().st_mtime_ns:
                    continue
            except OSError:
                continue
        file_changed, file_failed = _copy_opencode_file(path, target)
        changed = file_changed or changed
        failed = file_failed or failed
    return changed, failed


def _sync_opencode_incremental_state(src, dst):
    src = Path(src)
    dst = Path(dst)
    if not src.is_dir():
        return False, False
    changed = False
    failed = False
    stack = [src]
    while stack:
        current = stack.pop()
        try:
            children = sorted(current.iterdir())
        except OSError:
            failed = True
            continue
        for path in children:
            if _opencode_incremental_path_skipped(src, path):
                continue
            rel = path.relative_to(src)
            target = dst / rel
            if path.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                stack.append(path)
                continue
            if path.name in {"opencode.db-wal", "opencode.db-shm"}:
                continue
            if rel == Path("opencode.db"):
                db_changed, db_failed = _sync_opencode_db(path, target)
                changed = db_changed or changed
                failed = db_failed or failed
                continue
            if target.exists():
                try:
                    if path.stat().st_mtime_ns <= target.stat().st_mtime_ns:
                        continue
                except OSError:
                    failed = True
                    continue
            file_changed, file_failed = _copy_opencode_file(path, target)
            changed = file_changed or changed
            failed = file_failed or failed
    return changed, failed


def _migrate_opencode_data_to_shared_state(session_home, *, real_user_path):
    sessions_dir = Path(session_home).parent
    if not sessions_dir.is_dir():
        return False, False

    migration_cutoff_mtime_ns = _opencode_migration_cutoff_mtime_ns()
    candidates_by_profile = {}
    for session_dir in sessions_dir.iterdir():
        profile_slug = _opencode_legacy_profile_slug_from_session(session_dir)
        if not profile_slug:
            continue
        data_dir = session_dir / ".local" / "share" / "opencode"
        if not data_dir.is_dir():
            continue
        mtime = _opencode_data_checkpoint_mtime_ns(data_dir)
        candidates_by_profile.setdefault(profile_slug, []).append((mtime, data_dir))

    copied = False
    failed = False
    for profile_slug, candidates in candidates_by_profile.items():
        state_root = _opencode_profile_state_root(real_user_path, profile_slug)
        target_opencode_dir = state_root / "opencode"
        profile_migrated = False
        profile_failed = False
        profile_scanned = False
        marker_mtime_ns = _opencode_shared_state_marker_mtime_ns(state_root)
        for _mtime, data_dir in sorted(candidates, reverse=True):
            if marker_mtime_ns and _mtime and _mtime <= marker_mtime_ns:
                continue
            profile_scanned = True
            if marker_mtime_ns:
                tree_changed, tree_failed = _sync_opencode_incremental_state(data_dir, target_opencode_dir)
            else:
                tree_changed, tree_failed = _sync_opencode_tree(data_dir, target_opencode_dir)
            profile_migrated = tree_changed or profile_migrated
            profile_failed = tree_failed or profile_failed
        if profile_scanned or profile_failed or not marker_mtime_ns:
            _write_opencode_shared_state_marker(
                state_root,
                migrated=bool(candidates) and not profile_failed,
                covered_mtime_ns=migration_cutoff_mtime_ns,
            )
        copied = profile_migrated or copied
        failed = profile_failed or failed
    return copied, failed


def opencode_set_soft_home(env, session_home, *, real_user_path, set_session_home_hint, profile_id):
    """Isolate OpenCode config/home by default while sharing profile data/state."""
    profile_slug = opencode_profile_state_slug(profile_id)
    real_home = real_user_path()
    use_real_home = _boolish(env.get("MMS_OPENCODE_REAL_HOME"), default=False)
    state_root = _opencode_profile_state_root(real_user_path, profile_slug)
    cache_root = _opencode_profile_cache_root(real_user_path, profile_slug)
    _write_opencode_profile_marker(session_home, profile_slug)
    env["HOME"] = real_home if use_real_home else session_home
    env["XDG_CONFIG_HOME"] = os.path.join(session_home, ".config")
    env["XDG_CACHE_HOME"] = os.path.join(session_home, ".cache")
    if _opencode_shared_cache_enabled({}, env):
        _materialize_opencode_shared_cache(env, session_home, cache_root, use_real_home=use_real_home)
    else:
        env["MMS_OPENCODE_SHARED_CACHE"] = "0"
        env.pop("MMS_OPENCODE_CACHE_ROOT", None)
        env.pop("MMS_OPENCODE_XDG_CACHE_SHARED", None)
        env.pop("MMS_OPENCODE_HOME_CACHE_SHARED", None)
    if _opencode_isolate_data_enabled(env):
        _write_opencode_isolate_data_marker(session_home)
        env["XDG_DATA_HOME"] = os.path.join(session_home, ".local", "share")
        env["XDG_STATE_HOME"] = os.path.join(session_home, ".local", "state")
        env.pop("MMS_OPENCODE_STATE_SHARED", None)
    else:
        os.makedirs(state_root, exist_ok=True)
        _migrated, migration_failed = _migrate_opencode_data_to_shared_state(session_home, real_user_path=real_user_path)
        env["XDG_DATA_HOME"] = str(state_root)
        env["XDG_STATE_HOME"] = str(state_root)
        env["MMS_OPENCODE_STATE_SHARED"] = "1"
        if migration_failed:
            env["MMS_OPENCODE_MIGRATION_FAILED"] = "1"
        else:
            env.pop("MMS_OPENCODE_MIGRATION_FAILED", None)
    env["MMS_HOME_ISOLATION_MODE"] = "soft"
    env["MMS_SOFT_HOME"] = "1"
    env["MMS_OPENCODE_SOFT_HOME"] = "1"
    env["MMS_OPENCODE_HOME_ISOLATED"] = "0" if use_real_home else "1"
    env["MMS_OPENCODE_REAL_HOME"] = "1" if use_real_home else "0"
    env["MMS_OPENCODE_PROFILE"] = profile_slug
    set_session_home_hint(env, session_home)
    return env


def opencode_export_config_path(runtime, model, *, real_user_path):
    runtime = runtime if isinstance(runtime, dict) else {}
    provider = opencode_config_slug(runtime.get("id") or runtime.get("name"), "provider")
    model_slug = opencode_config_slug(model or runtime.get("model"), "model")
    return real_user_path(
        ".config",
        "mms",
        "opencode-gateway",
        "exports",
        f"{provider}-{model_slug}.json",
    )


def opencode_gateway_env(
    runtime,
    model_info=None,
    *,
    resolve_model,
    real_user_path,
    cleanup_stale_sessions,
    link_shared_dotfiles,
    scrub_inherited_runtime_env,
    clear_opencode_config_env,
    inject_real_home_hints,
    inject_selected_model_name,
    set_opencode_soft_home,
    write_opencode_config,
    overlay_opencode_session_assets,
    apply_route_env,
    apply_bypass_env,
    apply_runtime_network_profile,
    apply_runtime_locale_profile,
    apply_runtime_ip_stack_profile,
    install_session_command_wrappers,
    install_session_packet_env,
    runtime_caveman_enabled,
    resolve_web_access_root,
    resolve_weber_root,
    resolve_codegraph_root,
    resolve_toon_root,
    resolve_token_saver_root,
    resolve_xmem_root,
    session_skill_disabled,
    opencode_rtk_plugin_enabled,
    opencode_xmem_plugin_enabled,
    opencode_nsr_plugin_enabled=lambda runtime: False,
    environ=None,
    getpid=os.getpid,
):
    runtime = runtime if isinstance(runtime, dict) else {}
    model = resolve_model(model_info or runtime)
    opencode_profile_id = str(runtime.get("opencode_profile") or "").strip()
    if not opencode_profile_id and isinstance(model_info, dict):
        opencode_profile_id = str(model_info.get("opencode_profile") or "").strip()
    if not opencode_profile_id:
        raise ValueError("opencode_profile is required for MMS-managed OpenCode shared state")
    disabled_session_surfaces = runtime.get("disabled_session_surfaces")
    enable_caveman = runtime_caveman_enabled(runtime)
    gateway_base = real_user_path(".config", "mms", "opencode-gateway")
    os.makedirs(gateway_base, exist_ok=True)
    sessions_dir = os.path.join(gateway_base, "s")
    session_home = os.path.join(sessions_dir, str(getpid()))
    os.makedirs(session_home, exist_ok=True)

    link_shared_dotfiles(session_home)

    env = dict(os.environ if environ is None else environ)
    scrub_inherited_runtime_env(env, strip_openai=True, strip_proxy=True)
    clear_opencode_config_env(env)
    inject_real_home_hints(env)
    inject_selected_model_name(env, model, model_info=model_info)
    use_real_home = (
        _opencode_real_home_enabled(runtime, env)
        or _opencode_external_skills_enabled(runtime, env)
    )
    env["MMS_OPENCODE_REAL_HOME"] = "1" if use_real_home else "0"
    env[_OPENCODE_SHARED_CACHE_ENV] = "1" if _opencode_shared_cache_enabled(runtime, env) else "0"
    set_opencode_soft_home(env, session_home, profile_id=opencode_profile_id)
    opencode_apply_external_skill_policy(env, runtime)
    if env.get("MMS_OPENCODE_MIGRATION_FAILED") != "1":
        cleanup_stale_sessions(sessions_dir)

    config_dir = os.path.join(env["XDG_CONFIG_HOME"], "opencode")
    os.makedirs(config_dir, exist_ok=True)
    config_path = os.path.join(config_dir, "opencode.json")
    write_opencode_config(config_path, runtime, model)
    overlay_opencode_session_assets(
        config_dir,
        session_home,
        enable_caveman=enable_caveman,
        disabled_session_surfaces=disabled_session_surfaces,
        runtime=runtime,
    )

    apply_route_env(env, runtime, selected_model=model)
    env["OPENCODE_CONFIG"] = config_path
    env["OPENCODE_CONFIG_DIR"] = config_dir
    env["OPENCODE_DISABLE_AUTOUPDATE"] = "1"
    env["OPENCODE_CLIENT"] = "mms"
    apply_bypass_env(env, runtime)

    apply_runtime_network_profile(env, runtime, validate_proxy=False)
    apply_runtime_locale_profile(env, runtime)
    apply_runtime_ip_stack_profile(env, runtime)
    install_session_command_wrappers(session_home, env)
    install_session_packet_env(
        env,
        cli="opencode",
        runtime=runtime,
        model_info=model_info,
        session_home=session_home,
        features={
            "caveman": enable_caveman,
            "opencode_rtk": opencode_rtk_plugin_enabled(runtime),
            "web_access": bool(resolve_web_access_root()) and not session_skill_disabled(disabled_session_surfaces, "web-access"),
            "weber": bool(resolve_weber_root()) and not session_skill_disabled(disabled_session_surfaces, "weber"),
            "codegraph": bool(resolve_codegraph_root()) and not session_skill_disabled(disabled_session_surfaces, "codegraph"),
            "toon": bool(resolve_toon_root()) and not session_skill_disabled(disabled_session_surfaces, "toon"),
            "token_saver": bool(resolve_token_saver_root()) and not session_skill_disabled(disabled_session_surfaces, "token-saver"),
            "xmem": bool(resolve_xmem_root()) and not session_skill_disabled(disabled_session_surfaces, "xmem"),
            "opencode_xmem": opencode_xmem_plugin_enabled(runtime),
            "opencode_nsr": opencode_nsr_plugin_enabled(runtime),
        },
    )
    return env


def opencode_global_omo_env(
    runtime,
    *,
    clear_opencode_config_env,
    inject_real_home_hints,
    real_user_path,
    apply_bypass_env,
    apply_runtime_network_profile,
    apply_runtime_locale_profile,
    apply_runtime_ip_stack_profile,
    environ=None,
):
    env = dict(os.environ if environ is None else environ)
    clear_opencode_config_env(env)
    inject_real_home_hints(env, include_xdg=True)
    env["HOME"] = real_user_path()
    env["XDG_CACHE_HOME"] = real_user_path(".cache")
    env["XDG_DATA_HOME"] = real_user_path(".local", "share")
    env["XDG_STATE_HOME"] = real_user_path(".local", "state")
    env["MMS_HOME_ISOLATION_MODE"] = "raw"
    env["OPENCODE_CLIENT"] = "mms"
    env["MMS_OPENCODE_PROFILE"] = "heavy_omo"
    apply_bypass_env(env, runtime)
    apply_runtime_network_profile(env, runtime, validate_proxy=False)
    apply_runtime_locale_profile(env, runtime)
    apply_runtime_ip_stack_profile(env, runtime)
    return env


def opencode_global_export_env(runtime, *, apply_bypass_env):
    exports = {
        "OPENCODE_CLIENT": "mms",
        "MMS_OPENCODE_PROFILE": "heavy_omo",
    }
    return apply_bypass_env(exports, runtime)


def opencode_provider_export_env(
    runtime,
    model,
    *,
    export_config_path,
    write_opencode_config,
    apply_route_env,
    apply_bypass_env,
):
    exports = {}
    config_path = export_config_path(runtime, model)
    write_opencode_config(config_path, runtime, model)
    apply_route_env(exports, runtime, selected_model=model)
    exports["OPENCODE_CONFIG"] = config_path
    exports["OPENCODE_CONFIG_DIR"] = os.path.dirname(config_path)
    exports["OPENCODE_DISABLE_AUTOUPDATE"] = "1"
    exports["OPENCODE_CLIENT"] = "mms"
    apply_bypass_env(exports, runtime)
    return exports


__all__ = [
    "opencode_apply_external_skill_policy",
    "opencode_export_config_path",
    "opencode_gateway_env",
    "opencode_global_export_env",
    "opencode_global_omo_env",
    "opencode_profile_state_slug",
    "opencode_provider_export_env",
    "opencode_set_soft_home",
    "opencode_write_config",
]
