"""Static guards for known-bad MMS config-root fallback patterns."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

KNOWN_BAD_PATTERNS = {
    "mms_bridge.py": [
        'return os.path.expanduser("~/.config/mms")',
    ],
    "mms_broker.py": [
        'PRIMARY_CREDENTIALS_PATH = os.path.expanduser("~/.config/mms/credentials.sh")',
        'BROKER_CACHE_DIR = os.path.expanduser("~/.config/mms/cache/broker")',
    ],
    "mms_events.py": [
        'EVENT_DIR = Path.home() / ".config" / "mms" / "events"',
    ],
    "mms_health_cache.py": [
        'HEALTH_CACHE_DIR = Path(_real_home()) / ".config" / "mms"',
    ],
    "mms_speed_stats.py": [
        'PRIMARY_CONFIG_DIR = Path(os.path.expanduser("~/.config/mms"))',
    ],
}


def test_no_known_bad_stable_root_fallback_patterns() -> None:
    hits: list[str] = []
    for relative_path, patterns in KNOWN_BAD_PATTERNS.items():
        text = (ROOT / relative_path).read_text(encoding="utf-8")
        for pattern in patterns:
            if pattern in text:
                hits.append(f"{relative_path}: {pattern}")

    assert hits == []
