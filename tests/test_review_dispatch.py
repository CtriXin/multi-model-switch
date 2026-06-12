from __future__ import annotations

import json
import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))


def _write_model_bundle(config_root: Path, models: list[str]) -> None:
    generated = config_root / "generated"
    generated.mkdir(parents=True)
    lineup_path = generated / "model-routes.lineup.json"
    lineup_payload = {
        "version": 1,
        "generated_at": "2026-06-12T00:00:00Z",
        "routes": {model: {"primary": {"model_id": model}} for model in models},
    }
    lineup_path.write_text(json.dumps(lineup_payload, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    lineup_hash = hashlib.sha256(lineup_path.read_bytes()).hexdigest()
    manifest = {
        "schema": "mms.model_registry.latest_approved.v1",
        "generated_at": "2026-06-12T00:00:00Z",
        "files": {
            "lineup": {
                "canonical_path": "generated/model-routes.lineup.json",
                "sha256": lineup_hash,
                "sensitivity": "non-secret",
            }
        },
    }
    (generated / "model-registry.latest-approved.json").write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _mission_root(
    tmp_path: Path,
    *,
    state: str = "ready-for-agent",
    brief: str = "# Agent Brief\n",
    prd: str = "# Mission PRD\n",
    check_description: str = "review dispatch",
) -> Path:
    root = tmp_path / "mission-root"
    (root / ".mission").mkdir(parents=True)
    (root / ".work-gate" / "state").mkdir(parents=True)
    (root / ".mission" / "readiness.json").write_text(
        json.dumps({"state": state}) + "\n",
        encoding="utf-8",
    )
    (root / ".mission" / "agent-brief.md").write_text(brief, encoding="utf-8")
    (root / ".mission" / "mission-prd.md").write_text(prd, encoding="utf-8")
    (root / ".work-gate" / "state" / "check-spec.json").write_text(
        json.dumps({"checks": [{"id": "WD-1", "description": check_description}]}) + "\n",
        encoding="utf-8",
    )
    return root


def test_review_dispatch_dry_run_is_codex_claude_callable(tmp_path, capsys):
    from mms_review_dispatch import handle_review_dispatch_command

    root = _mission_root(tmp_path)
    code = handle_review_dispatch_command(
        [
            "--root",
            str(root),
            "--request-id",
            "dry-run-review",
            "--model",
            "gpt-5.4",
            "--model",
            "qwen3.7-max",
            "--dry-run",
            "--json",
        ],
        command_name="mms",
    )

    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["ok"] is True
    assert payload["dry_run"] is True
    assert payload["models"] == ["gpt-5.4", "qwen3.7-max"]
    assert payload["model_selection_source"] == "explicit"
    assert payload["model_selection_profile"] == "explicit"
    assert payload["opencode_profile"] == "review"
    assert payload["opencode_launch_command"][:5] == [
        sys.executable,
        str(REPO_ROOT / "mms"),
        "opencode",
        "--profile",
        "review",
    ]
    assert payload["review_hub_prompt"].startswith("/review-hub ")
    assert not Path(payload["request_root"]).exists()


def test_review_dispatch_blocks_unready_mission_root(tmp_path, capsys):
    from mms_review_dispatch import handle_review_dispatch_command

    root = _mission_root(tmp_path, state="needs-info")
    code = handle_review_dispatch_command(["--root", str(root), "--json"], command_name="mms")

    payload = json.loads(capsys.readouterr().out)
    assert code == 2
    assert payload["ok"] is False
    assert "readiness state blocks dispatch: needs-info" in payload["errors"]


def test_review_dispatch_auto_selects_code_review_default(tmp_path, capsys):
    from mms_review_dispatch import REVIEW_MODEL_PRESETS, handle_review_dispatch_command

    root = _mission_root(tmp_path)
    code = handle_review_dispatch_command(
        ["--root", str(root), "--request-id", "auto-code-review", "--dry-run", "--json"],
        command_name="mms",
    )

    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["ok"] is True
    assert payload["model_selection_source"] == "auto"
    assert payload["model_selection_profile"] == "code_review"
    assert payload["models"] == REVIEW_MODEL_PRESETS["code_review"]
    assert not any("claude" in model.lower() for model in payload["models"])
    assert "gpt-5.5" not in payload["models"]


def test_review_dispatch_auto_selects_design_visual_for_ui_artifacts(tmp_path, capsys):
    from mms_review_dispatch import REVIEW_MODEL_PRESETS, handle_review_dispatch_command

    root = _mission_root(
        tmp_path,
        brief="# Agent Brief\nReview the Figma screenshot, UI layout, image states, and visual polish.\n",
    )
    code = handle_review_dispatch_command(
        ["--root", str(root), "--request-id", "auto-design-review", "--dry-run", "--json"],
        command_name="mms",
    )

    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["model_selection_source"] == "auto"
    assert payload["model_selection_profile"] == "design_visual"
    assert payload["models"] == REVIEW_MODEL_PRESETS["design_visual"]


def test_review_dispatch_auto_selects_large_arch_for_high_risk_work(tmp_path, capsys):
    from mms_review_dispatch import REVIEW_MODEL_PRESETS, handle_review_dispatch_command

    root = _mission_root(
        tmp_path,
        prd="# Mission PRD\nHigh-risk architecture migration touching routing, bridge, config, and cache.\n",
    )
    code = handle_review_dispatch_command(
        ["--root", str(root), "--request-id", "auto-arch-review", "--dry-run", "--json"],
        command_name="mms",
    )

    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["model_selection_source"] == "auto"
    assert payload["model_selection_profile"] == "large_arch"
    assert payload["models"] == REVIEW_MODEL_PRESETS["large_arch"]


def test_review_dispatch_model_preset_selects_fast_cheap(tmp_path, capsys):
    from mms_review_dispatch import REVIEW_MODEL_PRESETS, handle_review_dispatch_command

    root = _mission_root(tmp_path)
    code = handle_review_dispatch_command(
        [
            "--root",
            str(root),
            "--request-id",
            "preset-fast-review",
            "--model-preset",
            "quick",
            "--dry-run",
            "--json",
        ],
        command_name="mms",
    )

    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["model_selection_source"] == "preset"
    assert payload["model_selection_profile"] == "fast_cheap"
    assert payload["models"] == REVIEW_MODEL_PRESETS["fast_cheap"]


def test_review_dispatch_explicit_models_normalize_aliases_and_override_auto(tmp_path, capsys):
    from mms_review_dispatch import handle_review_dispatch_command

    root = _mission_root(
        tmp_path,
        brief="# Agent Brief\nThis screenshot UI review would auto-select design models.\n",
    )
    code = handle_review_dispatch_command(
        [
            "--root",
            str(root),
            "--request-id",
            "alias-review",
            "--model",
            "minimax-m3",
            "--model",
            "mimo-2.5",
            "--model",
            "kimi-2.6",
            "--model",
            "glm5-turbo",
            "--dry-run",
            "--json",
        ],
        command_name="mms",
    )

    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["model_selection_source"] == "explicit"
    assert payload["model_selection_profile"] == "explicit"
    assert payload["models"] == ["MiniMax-M3", "mimo-v2.5", "kimi-k2.6", "glm-5-turbo"]


def test_review_dispatch_explicit_model_value_can_be_fuzzy_phrase(tmp_path, capsys):
    from mms_review_dispatch import handle_review_dispatch_command

    root = _mission_root(tmp_path)
    code = handle_review_dispatch_command(
        [
            "--root",
            str(root),
            "--request-id",
            "fuzzy-model-review",
            "--model",
            "glm5turobo kimi2.6",
            "--dry-run",
            "--json",
        ],
        command_name="mms",
    )

    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["model_selection_source"] == "explicit"
    assert payload["models"] == ["glm-5-turbo", "kimi-k2.6"]


def test_review_dispatch_model_text_accepts_freeform_host_instruction(tmp_path, capsys):
    from mms_review_dispatch import handle_review_dispatch_command

    root = _mission_root(tmp_path)
    code = handle_review_dispatch_command(
        [
            "--root",
            str(root),
            "--request-id",
            "freeform-model-review",
            "--model-text",
            "这次用 glm5turobo 和 kimi2.6，再加 minimaxm3",
            "--dry-run",
            "--json",
        ],
        command_name="mms",
    )

    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["model_selection_source"] == "explicit"
    assert payload["models"] == ["glm-5-turbo", "kimi-k2.6", "MiniMax-M3"]


def test_review_dispatch_resolves_fuzzy_models_from_selected_bundle(tmp_path, monkeypatch, capsys):
    from mms_review_dispatch import handle_review_dispatch_command

    config_root = tmp_path / "mms-next"
    _write_model_bundle(config_root, ["kimi-k2.5", "MiniMax-M3"])
    monkeypatch.setenv("MMS_CONFIG_ROOT", str(config_root))
    root = _mission_root(tmp_path)

    code = handle_review_dispatch_command(
        [
            "--root",
            str(root),
            "--request-id",
            "bundle-model-review",
            "--dry-run",
            "--json",
            "使用",
            "kimi2.5",
            "minimaxm3",
        ],
        command_name="mmf",
    )

    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["model_selection_source"] == "explicit"
    assert payload["models"] == ["kimi-k2.5", "MiniMax-M3"]


def test_mmf_review_dispatch_entrypoint_uses_preview_bundle(tmp_path, monkeypatch):
    config_root = tmp_path / "mms-next"
    _write_model_bundle(config_root, ["kimi-k2.5", "MiniMax-M3"])
    root = _mission_root(tmp_path)
    env = {
        **os.environ,
        "MMS_CONFIG_ROOT": str(config_root),
        "MMS_SKIP_VENV_REEXEC": "1",
        "PYTHONPATH": str(REPO_ROOT),
    }
    completed = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "mmf"),
            "review-dispatch",
            "--root",
            str(root),
            "--request-id",
            "mmf-bundle-review",
            "--dry-run",
            "--json",
            "使用",
            "kimi2.5",
            "minimaxm3",
        ],
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["ok"] is True
    assert payload["models"] == ["kimi-k2.5", "MiniMax-M3"]


def test_review_dispatch_rejects_claude_review_models(tmp_path, capsys):
    from mms_review_dispatch import handle_review_dispatch_command

    root = _mission_root(tmp_path)
    code = handle_review_dispatch_command(
        [
            "--root",
            str(root),
            "--request-id",
            "claude-review",
            "--model",
            "claude-sonnet-4.5",
            "--dry-run",
            "--json",
        ],
        command_name="mms",
    )

    payload = json.loads(capsys.readouterr().out)
    assert code == 2
    assert payload["ok"] is False
    assert "Claude models are not allowed" in payload["errors"][0]


def test_mms_review_dispatch_entrypoint_works_for_codex_claude(tmp_path):
    root = _mission_root(tmp_path)
    completed = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "mms"),
            "review-dispatch",
            "--root",
            str(root),
            "--request-id",
            "entrypoint-review",
            "--model",
            "gpt-5.4",
            "--model",
            "qwen3.7-max",
            "--dry-run",
            "--json",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["ok"] is True
    assert payload["request_id"] == "entrypoint-review"
    assert payload["opencode_profile"] == "review"


def test_review_dispatch_fake_run_writes_multi_model_results(tmp_path, capsys):
    if shutil.which("review-hub") is None:
        pytest.skip("review-hub CLI is not installed")

    from mms_review_dispatch import handle_review_dispatch_command

    root = _mission_root(tmp_path)
    code = handle_review_dispatch_command(
        [
            "--root",
            str(root),
            "--request-id",
            "fake-review",
            "--title",
            "Fake multi-model review",
            "--model",
            "gpt-5.4",
            "--model",
            "qwen3.7-max",
            "--fake-run",
            "--json",
        ],
        command_name="mms",
    )

    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["ok"] is True
    assert payload["fake_run"] is True
    assert payload["worker_plan"]["worker_count"] == 2
    assert payload["aggregate"]["reviewers_complete"] == 2
    request_root = Path(payload["request_root"])
    assert (request_root / "mms-review-dispatch.json").exists()
    assert (request_root / "aggregate" / "aggregate.json").exists()
    for result in payload["fake_results"]:
        verify_root = Path(result["verify_root"])
        assert (verify_root / "04-final-verdict.md").exists()
