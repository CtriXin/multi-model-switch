"""Codex hook trust helpers for MMS launcher sessions."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from time import perf_counter


def _launchers():
    import mms_launchers as _module

    return _module


def _toml_quote(value):
    return _launchers()._toml_quote(value)


def _real_user_home():
    return _launchers()._real_user_home()


def _safe_getcwd():
    return _launchers()._safe_getcwd()


def _is_mms_managed_hook_command(command_text):
    return _launchers()._is_mms_managed_hook_command(command_text)


def _load_json_dict_unlocked(path):
    return _launchers()._load_json_dict_unlocked(path)


def _real_user_path(*parts):
    return _launchers()._real_user_path(*parts)


def atomic_write_text(path, text, mode=0o600):
    return _launchers().atomic_write_text(path, text, mode=mode)


def atomic_write_json(path, data, mode=0o600):
    return _launchers().atomic_write_json(path, data, mode=mode)


def _codex_hook_event_state_key(event_name):
    import re

    raw = str(event_name or "").strip()
    if not raw:
        return ""
    raw = raw.replace("-", "_").replace(" ", "_")
    raw = re.sub(r"(?<=[a-z0-9])([A-Z])", r"_\1", raw)
    raw = re.sub(r"(?<=[A-Z])([A-Z][a-z])", r"_\1", raw)
    raw = re.sub(r"[^A-Za-z0-9]+", "_", raw)
    return raw.strip("_").lower()


def _codex_hook_fingerprint(hook):
    if not isinstance(hook, dict):
        return ""
    try:
        return json.dumps(hook, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    except Exception:
        return ""


def _codex_hook_index(hooks_payload):
    positions = {}
    by_fingerprint = {}
    by_command = {}
    payload = hooks_payload if isinstance(hooks_payload, dict) else {}
    hooks_data = payload.get("hooks") if isinstance(payload.get("hooks"), dict) else {}
    for event_name, groups in hooks_data.items():
        event_key = _codex_hook_event_state_key(event_name)
        if not event_key or not isinstance(groups, list):
            continue
        for group_index, group in enumerate(groups):
            if not isinstance(group, dict):
                continue
            hook_items = group.get("hooks")
            if not isinstance(hook_items, list):
                continue
            for hook_index, hook in enumerate(hook_items):
                if not isinstance(hook, dict):
                    continue
                command = str(hook.get("command") or "").strip()
                if not command:
                    continue
                record = {
                    "event": event_key,
                    "group_index": group_index,
                    "hook_index": hook_index,
                    "command": command,
                    "fingerprint": _codex_hook_fingerprint(hook),
                }
                positions[(event_key, group_index, hook_index)] = record
                if record["fingerprint"]:
                    by_fingerprint.setdefault((event_key, record["fingerprint"]), []).append(record)
                by_command.setdefault((event_key, command), []).append(record)
    return {
        "positions": positions,
        "by_fingerprint": by_fingerprint,
        "by_command": by_command,
    }


def _decode_toml_basic_key(value):
    try:
        return json.loads(f'"{value}"')
    except Exception:
        return str(value or "").replace('\\"', '"').replace("\\\\", "\\")


def _codex_hook_trust_records_from_config(config_text):
    import re

    text = _normalize_codex_hook_trust_toml_layout(config_text)
    header_pattern = re.compile(
        r'^\[hooks\.state\."((?:\\.|[^"\\])*)"\]\s*$',
        flags=re.MULTILINE,
    )
    records = []
    for match in header_pattern.finditer(text):
        raw_key = _decode_toml_basic_key(match.group(1))
        try:
            hooks_path, event_key, group_index, hook_index = raw_key.rsplit(":", 3)
            group_index = int(group_index)
            hook_index = int(hook_index)
        except Exception:
            continue
        next_header = re.search(r"^\[", text[match.end():], flags=re.MULTILINE)
        block_end = match.end() + next_header.start() if next_header else len(text)
        block = text[match.end():block_end]
        hash_match = re.search(r'^\s*trusted_hash\s*=\s*"([^"]+)"\s*$', block, flags=re.MULTILINE)
        if not hash_match:
            continue
        records.append(
            {
                "key": raw_key,
                "hooks_path": hooks_path,
                "event": event_key,
                "group_index": group_index,
                "hook_index": hook_index,
                "trusted_hash": hash_match.group(1),
            }
        )
    return records


def _normalize_codex_hook_trust_toml_layout(config_text):
    import re

    text = str(config_text or "")
    if not text:
        return text
    text = re.sub(
        r'(?m)^(?P<hash>\s*trusted_hash\s*=\s*"[^"\n]*")(?=\[hooks\.state\.)',
        r'\g<hash>' + "\n\n",
        text,
    )
    text = re.sub(
        r'(?m)^(?P<header>\[hooks\.state\."(?:\\.|[^"\\])*"\])(?=[ \t]*trusted_hash\s*=)',
        r'\g<header>' + "\n",
        text,
    )
    text = re.sub(
        r'(?m)^(?P<header>\[hooks\.state\."(?:\\.|[^"\\])*"\]\n)(?:[ \t]*\n)+(?P<hash>[ \t]*trusted_hash\s*=)',
        r'\g<header>\g<hash>',
        text,
    )
    return text


def _replace_codex_hook_trust_hashes(config_text, trusted_hashes_by_key):
    import re

    text = _normalize_codex_hook_trust_toml_layout(config_text)
    replacements = {
        str(key): str(value)
        for key, value in (trusted_hashes_by_key or {}).items()
        if str(key or "").strip() and str(value or "").strip()
    }
    if not text or not replacements:
        return text

    header_pattern = re.compile(
        r'^\[hooks\.state\."((?:\\.|[^"\\])*)"\]\s*$',
        flags=re.MULTILINE,
    )
    matches = list(header_pattern.finditer(text))
    for match in reversed(matches):
        raw_key = _decode_toml_basic_key(match.group(1))
        if raw_key not in replacements:
            continue
        next_header = re.search(r"^\[", text[match.end():], flags=re.MULTILINE)
        block_end = match.end() + next_header.start() if next_header else len(text)
        block = text[match.end():block_end]
        new_hash = replacements[raw_key]

        def _replace_hash(hash_match):
            if hash_match.group(2) == new_hash:
                return hash_match.group(0)
            return f'{hash_match.group("prefix")}{_toml_quote(new_hash)}'

        block = re.sub(
            r'^(?P<prefix>\s*trusted_hash\s*=\s*)"([^"]+)"\s*$',
            _replace_hash,
            block,
            count=1,
            flags=re.MULTILINE,
        )
        text = text[:match.end()] + block + text[block_end:]
    return _normalize_codex_hook_trust_toml_layout(text)


def _append_codex_exact_hook_trust_hashes(config_text, trusted_hashes_by_key):
    text = _normalize_codex_hook_trust_toml_layout(config_text)
    replacements = {
        str(key): str(value)
        for key, value in (trusted_hashes_by_key or {}).items()
        if str(key or "").strip() and str(value or "").strip()
    }
    if not replacements:
        return text

    existing_hashes = {
        record["key"]: record["trusted_hash"]
        for record in _codex_hook_trust_records_from_config(text)
    }
    updates = {
        key: trusted_hash
        for key, trusted_hash in replacements.items()
        if key in existing_hashes and existing_hashes.get(key) != trusted_hash
    }
    if updates:
        text = _replace_codex_hook_trust_hashes(text, updates)

    missing = [
        (key, trusted_hash)
        for key, trusted_hash in replacements.items()
        if key not in existing_hashes
    ]
    if not missing:
        return _normalize_codex_hook_trust_toml_layout(text)

    if text and not text.endswith("\n"):
        text += "\n"
    for key, trusted_hash in missing:
        if text and not text.endswith("\n\n"):
            text += "\n"
        text += f"[hooks.state.{_toml_quote(key)}]\n"
        text += f"trusted_hash = {_toml_quote(trusted_hash)}\n"
    return _normalize_codex_hook_trust_toml_layout(text)


def _codex_hook_trust_refresh_enabled():
    raw = str(os.environ.get("MMS_CODEX_HOOK_TRUST_REFRESH", "1") or "").strip().lower()
    return raw not in {"0", "false", "no", "off", "disable", "disabled"}


def _codex_app_server_hooks_list(codex_home, *, cwds=None, timeout=4.0):
    import select

    codex_home = str(codex_home or "").strip()
    if not codex_home:
        return []
    codex_bin = shutil.which("codex")
    if not codex_bin and os.path.isfile("/opt/homebrew/bin/codex"):
        codex_bin = "/opt/homebrew/bin/codex"
    if not codex_bin:
        return []

    env = os.environ.copy()
    env["CODEX_HOME"] = codex_home
    env["HOME"] = _real_user_home()
    env.setdefault("LANG", "zh_CN.UTF-8")
    env.setdefault("LC_ALL", "zh_CN.UTF-8")
    cwds = [str(cwd) for cwd in (cwds or []) if str(cwd or "").strip()]
    if not cwds:
        cwds = [_safe_getcwd()]

    proc = None

    def _send(method, *, request_id=None, params=None):
        message = {"method": method}
        if request_id is not None:
            message["id"] = request_id
        if params is not None:
            message["params"] = params
        proc.stdin.write(json.dumps(message, separators=(",", ":")) + "\n")
        proc.stdin.flush()

    def _recv(request_id, deadline):
        while True:
            time_left = deadline - perf_counter()
            if time_left <= 0:
                break
            ready, _, _ = select.select([proc.stdout], [], [], min(0.25, max(0.01, time_left)))
            if not ready:
                continue
            line = proc.stdout.readline()
            if not line:
                break
            try:
                message = json.loads(line)
            except Exception:
                continue
            if message.get("id") == request_id:
                return message
        return {}

    try:
        proc = subprocess.Popen(
            [codex_bin, "app-server", "--listen", "stdio://"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
            env=env,
        )
        deadline = perf_counter() + max(1.0, float(timeout or 4.0))
        _send(
            "initialize",
            request_id=1,
            params={"clientInfo": {"name": "mms-hook-trust", "version": "1"}, "capabilities": {}},
        )
        _recv(1, deadline)
        _send("initialized")
        _send("hooks/list", request_id=2, params={"cwds": cwds})
        response = _recv(2, deadline)
        data = ((response.get("result") or {}).get("data") or []) if isinstance(response, dict) else []
        hooks = []
        for entry in data:
            if isinstance(entry, dict) and isinstance(entry.get("hooks"), list):
                hooks.extend(entry.get("hooks") or [])
        return hooks
    except Exception:
        return []
    finally:
        if proc is not None:
            try:
                proc.terminate()
            except Exception:
                pass
            try:
                proc.wait(timeout=1)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass


def _refresh_codex_current_hook_trust_cache(
    target_codex_dir,
    *,
    cwds=None,
    managed_only=False,
    timeout=4.0,
    allow_non_real_home=False,
):
    """Use the installed Codex app-server as source of truth for hook hashes."""
    if not _codex_hook_trust_refresh_enabled():
        return {"status": "disabled"}

    target_codex_dir = str(target_codex_dir or "").strip()
    if not target_codex_dir:
        return {}
    if not allow_non_real_home:
        try:
            real_home = os.path.realpath(_real_user_home())
            target_real = os.path.realpath(target_codex_dir)
            if real_home and not (target_real == real_home or target_real.startswith(real_home + os.sep)):
                return {"status": "skipped-non-real-home"}
        except OSError:
            return {"status": "skipped-non-real-home"}
    target_hooks_path = os.path.join(target_codex_dir, "hooks.json")
    target_config_path = os.path.join(target_codex_dir, "config.toml")
    if not os.path.isfile(target_hooks_path):
        return {}

    try:
        target_hooks_real = os.path.realpath(target_hooks_path)
    except OSError:
        target_hooks_real = target_hooks_path

    exact_hashes = {}
    for hook in _launchers()._codex_app_server_hooks_list(target_codex_dir, cwds=cwds, timeout=timeout):
        if not isinstance(hook, dict):
            continue
        try:
            source_real = os.path.realpath(str(hook.get("sourcePath") or ""))
        except OSError:
            source_real = str(hook.get("sourcePath") or "")
        if source_real != target_hooks_real:
            continue
        command = str(hook.get("command") or "")
        if managed_only and not _is_mms_managed_hook_command(command):
            continue
        key = str(hook.get("key") or "").strip()
        current_hash = str(hook.get("currentHash") or "").strip()
        if key and current_hash:
            exact_hashes[key] = current_hash

    if not exact_hashes:
        return {"status": "no-current-hashes"}

    try:
        with open(target_config_path, "r", encoding="utf-8") as handle:
            config_text = handle.read()
    except Exception:
        config_text = ""
    rendered = _append_codex_exact_hook_trust_hashes(config_text, exact_hashes)
    if rendered == _normalize_codex_hook_trust_toml_layout(config_text):
        return {"status": "fresh", "trusted_entries": len(exact_hashes)}
    try:
        atomic_write_text(target_config_path, rendered, mode=0o600)
    except Exception:
        return {"status": "write-failed"}
    before_hashes = {
        record["key"]: record["trusted_hash"]
        for record in _codex_hook_trust_records_from_config(config_text)
    }
    return {
        "status": "refreshed",
        "trusted_entries": len(exact_hashes),
        "updated_entries": sum(1 for key, value in exact_hashes.items() if before_hashes.get(key) != value),
        "scope": "mms-managed" if managed_only else "all-target-hooks",
    }


def _collect_codex_hook_trust_seed_sources(codex_roots):
    config_texts = []
    hook_payloads = {}
    seen_roots = set()
    for root in codex_roots or []:
        root = str(root or "").strip()
        if not root:
            continue
        try:
            real_root = os.path.realpath(root)
        except OSError:
            real_root = root
        if real_root in seen_roots:
            continue
        seen_roots.add(real_root)
        config_path = os.path.join(root, "config.toml")
        try:
            with open(config_path, "r", encoding="utf-8") as handle:
                config_texts.append(handle.read())
        except Exception:
            pass
        hooks_path = os.path.join(root, "hooks.json")
        hooks_payload = _load_json_dict_unlocked(hooks_path)
        if hooks_payload:
            hook_payloads[hooks_path] = hooks_payload
    return config_texts, hook_payloads


def _append_codex_session_hook_trust_states(
    config_text,
    *,
    target_hooks_path,
    target_hooks,
    trust_config_texts=None,
    source_hook_payloads_by_path=None,
):
    text = _normalize_codex_hook_trust_toml_layout(config_text)
    target_hooks_path = str(target_hooks_path or "").strip()
    if not target_hooks_path or not isinstance(target_hooks, dict):
        return text
    target_index = _codex_hook_index(target_hooks)
    if not target_index["positions"]:
        return text

    source_payloads = {}
    for path, payload in (source_hook_payloads_by_path or {}).items():
        path = str(path or "").strip()
        if path and isinstance(payload, dict):
            source_payloads[path] = payload
    source_payloads[target_hooks_path] = target_hooks
    source_indexes = {}

    def _source_index(path):
        path = str(path or "").strip()
        if not path:
            return _codex_hook_index({})
        if path not in source_indexes:
            payload = source_payloads.get(path)
            if not isinstance(payload, dict) and os.path.isfile(path):
                payload = _load_json_dict_unlocked(path)
            source_indexes[path] = _codex_hook_index(payload if isinstance(payload, dict) else {})
        return source_indexes[path]

    seed_texts = [text]
    for seed_text in trust_config_texts or []:
        if seed_text:
            seed_texts.append(_normalize_codex_hook_trust_toml_layout(seed_text))

    existing_hashes = {
        record["key"]: record["trusted_hash"]
        for record in _codex_hook_trust_records_from_config(text)
    }
    pending = {}
    pending_updates = {}
    pending_quality = {}

    # Contract: sibling per-PID sessions may seed missing trust, but they must
    # never override the user's real ~/.codex/hooks.json trust for the same hook.
    real_hooks_path = os.path.realpath(_real_user_path(".codex", "hooks.json"))

    def _trust_source_quality(hooks_path, match_quality):
        quality = int(match_quality) * 10
        try:
            if os.path.realpath(str(hooks_path or "")) == real_hooks_path:
                quality += 2
            elif str(hooks_path or "").strip() == target_hooks_path:
                quality += 1
        except OSError:
            pass
        return quality

    def _remember(target_key, trusted_hash, quality):
        if not target_key or not trusted_hash:
            return
        if target_key in existing_hashes:
            if existing_hashes[target_key] != trusted_hash:
                previous_quality = pending_quality.get(target_key, -1)
                if quality >= previous_quality:
                    pending_updates[target_key] = trusted_hash
                    pending_quality[target_key] = quality
            return
        previous_quality = pending_quality.get(target_key, -1)
        if target_key not in pending or quality >= previous_quality:
            pending[target_key] = trusted_hash
            pending_quality[target_key] = quality

    for seed_text in seed_texts:
        for trust_record in _codex_hook_trust_records_from_config(seed_text):
            source_record = _source_index(trust_record["hooks_path"])["positions"].get(
                (
                    trust_record["event"],
                    trust_record["group_index"],
                    trust_record["hook_index"],
                )
            )
            if not source_record:
                continue
            candidates = []
            match_quality = 1
            if source_record.get("fingerprint"):
                candidates = target_index["by_fingerprint"].get(
                    (trust_record["event"], source_record["fingerprint"]),
                    [],
                )
                if candidates:
                    match_quality = 2
            if not candidates:
                candidates = target_index["by_command"].get(
                    (trust_record["event"], source_record["command"]),
                    [],
                )
            for target_record in candidates:
                target_key = (
                    f"{target_hooks_path}:{target_record['event']}:"
                    f"{target_record['group_index']}:{target_record['hook_index']}"
                )
                # A same-path, same-position record in the existing target config
                # is not evidence that its hash is still valid after hooks changed.
                if trust_record["hooks_path"] == target_hooks_path and trust_record["key"] == target_key:
                    continue
                _remember(
                    target_key,
                    trust_record["trusted_hash"],
                    _trust_source_quality(trust_record["hooks_path"], match_quality),
                )

    if pending_updates:
        text = _replace_codex_hook_trust_hashes(text, pending_updates)
    if not pending:
        return _normalize_codex_hook_trust_toml_layout(text)
    if text and not text.endswith("\n"):
        text += "\n"
    for target_key, trusted_hash in pending.items():
        if text and not text.endswith("\n\n"):
            text += "\n"
        text += f"[hooks.state.{_toml_quote(target_key)}]\n"
        text += f"trusted_hash = {_toml_quote(trusted_hash)}\n"
    return _normalize_codex_hook_trust_toml_layout(text)


def _write_codex_hook_trust_cache(
    target_codex_dir,
    hooks_payload,
    *,
    trust_config_texts=None,
    source_hook_payloads_by_path=None,
):
    target_codex_dir = str(target_codex_dir or "").strip()
    if not target_codex_dir or not isinstance(hooks_payload, dict) or not hooks_payload:
        return {}
    os.makedirs(target_codex_dir, exist_ok=True)
    target_hooks_path = os.path.join(target_codex_dir, "hooks.json")
    target_config_path = os.path.join(target_codex_dir, "config.toml")
    existing_target_hooks = _load_json_dict_unlocked(target_hooks_path)
    try:
        with open(target_config_path, "r", encoding="utf-8") as handle:
            target_config_text = handle.read()
    except Exception:
        target_config_text = ""

    source_payloads = {
        str(path): payload
        for path, payload in (source_hook_payloads_by_path or {}).items()
        if str(path or "").strip() and isinstance(payload, dict)
    }
    if existing_target_hooks:
        source_payloads[target_hooks_path] = existing_target_hooks
    rendered_config = _append_codex_session_hook_trust_states(
        target_config_text,
        target_hooks_path=target_hooks_path,
        target_hooks=hooks_payload,
        trust_config_texts=[target_config_text] + [str(text) for text in (trust_config_texts or []) if text],
        source_hook_payloads_by_path=source_payloads,
    )
    before_hashes = {
        record["key"]: record["trusted_hash"]
        for record in _codex_hook_trust_records_from_config(target_config_text)
    }
    after_hashes = {
        record["key"]: record["trusted_hash"]
        for record in _codex_hook_trust_records_from_config(rendered_config)
    }
    before_keys = set(before_hashes)
    after_keys = set(after_hashes)
    try:
        atomic_write_json(target_hooks_path, hooks_payload, mode=0o600)
        atomic_write_text(target_config_path, rendered_config, mode=0o600)
    except Exception:
        return {}
    return {
        "status": "synced",
        "trusted_entries": len(after_keys),
        "added_entries": max(0, len(after_keys - before_keys)),
        "updated_entries": sum(
            1
            for key in before_keys & after_keys
            if before_hashes.get(key) != after_hashes.get(key)
        ),
    }


def _sync_codex_hook_trust_back(session_codex_dir, target_codex_dir):
    session_codex_dir = str(session_codex_dir or "").strip()
    target_codex_dir = str(target_codex_dir or "").strip()
    if not session_codex_dir or not target_codex_dir:
        return {}
    session_hooks_path = os.path.join(session_codex_dir, "hooks.json")
    session_config_path = os.path.join(session_codex_dir, "config.toml")
    if not os.path.isfile(session_hooks_path) or not os.path.isfile(session_config_path):
        return {}
    session_hooks = _load_json_dict_unlocked(session_hooks_path)
    if not session_hooks:
        return {}

    try:
        with open(session_config_path, "r", encoding="utf-8") as handle:
            session_config_text = handle.read()
    except Exception:
        return {}

    return _write_codex_hook_trust_cache(
        target_codex_dir,
        session_hooks,
        trust_config_texts=[session_config_text],
        source_hook_payloads_by_path={session_hooks_path: session_hooks},
    )
