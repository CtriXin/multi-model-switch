from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.gateway_config import generate_gateway_token, hash_gateway_token


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate an internal gateway token snippet.")
    parser.add_argument("--id", required=True, help="Stable token id stored in config")
    parser.add_argument("--name", required=True, help="Human readable token name")
    parser.add_argument("--provider", default="openrouter", help="Provider id referenced by the token")
    parser.add_argument("--daily-limit", type=int, default=200, help="Daily request quota for /v1/chat/completions")
    parser.add_argument("--models", default="*", help="Comma-separated allowed model patterns")
    args = parser.parse_args()

    raw_token = generate_gateway_token()
    config_snippet = {
        "id": args.id,
        "name": args.name,
        "tokenHash": hash_gateway_token(raw_token),
        "providerId": args.provider,
        "enabled": True,
        "allowedModels": [item.strip() for item in args.models.split(",") if item.strip()],
        "dailyRequestLimit": args.daily_limit,
    }

    print("Raw token (only shown once):")
    print(raw_token)
    print("\nConfig snippet:")
    print(json.dumps(config_snippet, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
