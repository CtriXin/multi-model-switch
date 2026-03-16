from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def get_gateway_state_path() -> Path:
    env_path = os.getenv("MMS_GATEWAY_STATE_PATH")
    if env_path:
        return Path(env_path).expanduser().resolve()
    return Path(__file__).resolve().parents[1] / "gateway-state.db"


def init_gateway_state() -> Path:
    path = get_gateway_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS gateway_requests (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              created_at TEXT NOT NULL,
              request_id TEXT NOT NULL,
              endpoint TEXT NOT NULL,
              token_id TEXT NOT NULL,
              token_name TEXT NOT NULL,
              provider_id TEXT NOT NULL,
              model TEXT,
              upstream_key_id TEXT,
              status_code INTEGER NOT NULL,
              latency_ms INTEGER NOT NULL,
              error_source TEXT,
              error_detail TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_gateway_requests_token_created
            ON gateway_requests (token_id, created_at)
            """
        )
        columns = {
            row[1]
            for row in conn.execute("PRAGMA table_info(gateway_requests)").fetchall()
        }
        if "request_id" not in columns:
            conn.execute("ALTER TABLE gateway_requests ADD COLUMN request_id TEXT NOT NULL DEFAULT ''")
    return path


def log_gateway_request(
    *,
    request_id: str,
    endpoint: str,
    token_id: str,
    token_name: str,
    provider_id: str,
    model: str | None,
    upstream_key_id: str | None,
    status_code: int,
    latency_ms: int,
    error_source: str | None = None,
    error_detail: str | None = None,
) -> None:
    path = init_gateway_state()
    created_at = datetime.now(timezone.utc).isoformat()

    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            INSERT INTO gateway_requests (
              created_at, request_id, endpoint, token_id, token_name, provider_id, model,
              upstream_key_id, status_code, latency_ms, error_source, error_detail
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                created_at,
                request_id,
                endpoint,
                token_id,
                token_name,
                provider_id,
                model,
                upstream_key_id,
                status_code,
                latency_ms,
                error_source,
                error_detail,
            ),
        )


def count_today_requests(token_id: str, endpoint: str) -> int:
    path = init_gateway_state()
    today_start = datetime.now(timezone.utc).strftime("%Y-%m-%dT00:00:00+00:00")

    with sqlite3.connect(path) as conn:
        row = conn.execute(
            """
            SELECT COUNT(DISTINCT request_id)
            FROM gateway_requests
            WHERE token_id = ? AND endpoint = ? AND created_at >= ?
            """,
            (token_id, endpoint, today_start),
        ).fetchone()

    return int(row[0] or 0)
