from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REFERENCE_JSON = ROOT / "docs/reference/model-capability-calibration/2026-05-21-mms-model-capability-calibration.json"
CONTRACT_DOCS = [
    ROOT / "docs/MODEL_CONFIG_CONTRACT.md",
    ROOT / "docs/REGISTRY_ARCHITECTURE.md",
]
MMF_V2_DOC = ROOT / "docs/MMF_CONFIG_ROOT_V2_DB_TRUTH.md"
DOWNSTREAM_CONSUMER_RUNBOOK = ROOT / "docs/DOWNSTREAM_CONSUMER_BUNDLE_RUNBOOK.md"
RESCUE_DOC = ROOT / "docs/RESCUE_FALLBACK.md"
LLM_OPERATION_GUIDE = ROOT / "docs/LLM_OPERATION_GUIDE.md"
ARCHITECTURE_DOCS = [
    ROOT / "docs/images/architecture-mainline.mmd",
    ROOT / "docs/images/architecture-mainline-en.html",
    ROOT / "docs/images/architecture-mainline-cn.html",
]
README_DOCS = [
    ROOT / "README.md",
    ROOT / "README.zh-CN.md",
]


def _contract_text() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in CONTRACT_DOCS)


def _mmf_v2_text() -> str:
    return MMF_V2_DOC.read_text(encoding="utf-8")


def _downstream_consumer_runbook_text() -> str:
    return DOWNSTREAM_CONSUMER_RUNBOOK.read_text(encoding="utf-8")


def _rescue_text() -> str:
    return RESCUE_DOC.read_text(encoding="utf-8")


def _llm_operation_text() -> str:
    return LLM_OPERATION_GUIDE.read_text(encoding="utf-8")


def _architecture_text() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in ARCHITECTURE_DOCS)


def _readme_text() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in README_DOCS)


def test_registry_contract_docs_define_latest_approved_bundle_terms() -> None:
    text = _contract_text()

    required_terms = [
        "latest-approved bundle",
        "bundle_revision",
        "capability_revision",
        "route_revision",
        "policy_revision",
        "profile_revision",
        "generated_at",
        "per-file hashes",
        "atomic temp-file + rename",
        "generated/model-registry.latest-approved.json",
        "legacy root files",
        "mms:latest-approved:<bundle_revision>",
    ]

    missing = [term for term in required_terms if term not in text]
    assert missing == []


def test_registry_contract_docs_make_latest_approved_downstream_entrypoint() -> None:
    text = _contract_text()

    required_terms = [
        "<MMS_CONFIG_ROOT>/generated/model-registry.latest-approved.json",
        "Hive / Pilot / Ant / Moebius / Mobius and future downstream consumers MUST use",
        "from the config root as primary truth",
        "Verify latest-approved manifest",
        "mms config bundle --json",
        "mmf config bundle --json",
        "Legacy route/policy/profile files remain compatibility",
    ]

    missing = [term for term in required_terms if term not in text]
    assert missing == []


def test_registry_contract_docs_do_not_make_legacy_root_files_primary() -> None:
    text = _contract_text()

    forbidden_guidance = [
        "| How do I call a model? | Read `model-routes.json`;",
        "| What is the model context window? | Read `model-routes.lineup.json`;",
        "| Why does a provider need a special body/header/model alias? | Read `provider-profiles.json`.",
        "| Should this model be visible or preferred in a specific project? | Read `model-policy.json`.",
        "is maintained in `model-policy.json`",
        "Sync server-private copies of Router/Lineup/Profile/Policy during deploy",
    ]

    present = [phrase for phrase in forbidden_guidance if phrase in text]
    assert present == []


def test_registry_contract_docs_define_truth_layers_and_privacy_boundary() -> None:
    text = _contract_text()

    required_terms = [
        "source_truth",
        "candidate_truth",
        "approved_truth",
        "runtime_truth",
        "health_overlay",
        "privacy_boundary",
        "private",
        "team",
        "public",
        "conservative `private`",
        "Refresh absence is not deletion",
        "Tombstone must come from an explicit TUI/action event",
    ]

    missing = [term for term in required_terms if term not in text]
    assert missing == []


def test_registry_contract_docs_forbid_direct_downstream_sqlite_dependency() -> None:
    text = _contract_text()

    assert "MUST NOT query SQLite tables" in text
    assert "must not read the\nSQLite schema directly" in text
    assert "cache_transport_evidence.v1" in text


def test_downstream_consumer_bundle_runbook_is_fail_closed() -> None:
    text = _downstream_consumer_runbook_text()

    required_terms = [
        "Hive, Pilot, Ant, Mobius/Moebius",
        "MMS_CONFIG_ROOT -> <root>",
        "<MMS_CONFIG_ROOT>/generated/model-registry.latest-approved.json",
        "Do not read these as primary truth",
        "<MMS_CONFIG_ROOT>/registry/model-registry.sqlite",
        "schema == \"mms.model_registry.latest_approved.v1\"",
        "compute sha256",
        "Do not silently fallback to stable",
        "global OAuth state",
        "cache_transport_evidence.v1",
        "route_source=mms:latest-approved:<bundle_revision>",
        "mmf config bundle --json",
        "mms config bundle --json",
        "from mms_registry.consumer_bundle import load_verified_consumer_bundle",
        "Falling back to stable `~/.config/mms` is opt-in",
        "missing manifest -> fail closed",
        "hash mismatch -> fail closed",
        "SQLite not queried",
        "secrets redacted from logs/artifacts",
    ]
    forbidden_terms = [
        "read SQLite",
        "fallback to ~/.config/mms",
        "read root model-routes.json first",
    ]

    missing = [term for term in required_terms if term not in text]
    present = [term for term in forbidden_terms if term in text]
    assert missing == []
    assert present == []


def test_mmf_v2_docs_record_current_preview_boundaries() -> None:
    text = _mmf_v2_text()

    required_terms = [
        "respects `MMS_CONFIG_ROOT` and `MMS_CONFIG_DIR`",
        "explicit selected roots (`MMS_CONFIG_ROOT` / `MMS_CONFIG_DIR`) require the latest-approved bundle",
        "MMS_WATCHDOG_REQUIRE_BUNDLE=0",
        "backfill only `anthropic_base_url` / `openai_base_url` from legacy `model-routes.json`",
        "must not import plaintext route-artifact API keys",
        "enabled providers only",
        "missing route base URLs",
        "single preview rebuild command `mmf preview prepare --from ~/.config/mms --json`",
        "if keys are missing too, the command includes `--include-secrets`",
        "Ready-state watchdog hints use the concrete selected config root instead of `$MMS_CONFIG_ROOT`",
        "`mms config doctor --strict-exit`",
        "`--dry-run` is read-only for watchdog persistence",
        "`latest_approved_invalid`",
        "every route leaf has an `anthropic_base_url` or `openai_base_url`",
        "`stable_legacy_writes`",
        "`preview_v2_writes`",
        "same-`candidate_id` route/policy/profile revisions",
        "The plan itself is read-only",
        "writes require the preview-gated WebUI",
        "Preview usage writes no longer trigger the legacy background `model-routes.json` export",
        "Preview startup-safe route refresh also skips legacy `model-routes.json` export",
        "TUI Settings labels direct `model-routes.json` export as `Legacy",
        "not presented as the v2 truth/publish path",
        "./mmf config apply-plan --plan-json <webui-plan.json> --apply --confirm-preview-apply --json",
        "rolls back DB/secret/generated files on failure",
        "`mmf promote [--json]`",
        "`mms config promote-plan [--json]`",
        "`mms registry promotion-plan [--json]`",
        "`mms config release-readiness [--json]`",
        "`READY_FOR_4_0_HUMAN_GATE`",
        "`release_complete=false`",
        "`completion_blocker=stable_promotion_human_gate`",
        "`READY_FOR_HUMAN_PROMOTION_REVIEW`",
        "`apply_enabled=false`",
        "`promotion_apply_not_implemented`",
        "stable root write approval",
        "Actual stable-root migration remains a future human-gated flow",
    ]

    missing = [term for term in required_terms if term not in text]
    assert "does not enable DB writes yet" not in text
    assert missing == []


def test_public_readmes_explain_config_v2_preview_gate() -> None:
    text = _readme_text()

    required_terms = [
        "Config V2 Preview Root",
        "mms -> ~/.config/mms",
        "mmf -> ~/.config/mms-next",
        "mmf preview doctor --json",
        "mmf preview prepare --from ~/.config/mms --include-secrets --json",
        "mmf config bundle --json",
        "generated/model-registry.latest-approved.json",
        "mms migrate config-v2 --json",
        "mms config release-readiness --json",
        "apply_enabled=false",
        "READY_FOR_4_0_HUMAN_GATE",
        "release_complete=false",
        "stable_root_human_only",
        "promotion_apply_not_implemented",
        "silent fallback",
        "Claude config",
    ]

    missing = [term for term in required_terms if term not in text]
    assert missing == []


def test_rescue_docs_record_latest_approved_route_boundary() -> None:
    text = _rescue_text()

    required_terms = [
        "generated/model-registry.latest-approved.json",
        "verified Router payload",
        "invalid manifests fail closed",
        "legacy generated/root `model-routes.json` files remain compatibility fallbacks",
    ]

    missing = [term for term in required_terms if term not in text]
    assert missing == []


def test_llm_operation_guide_points_profile_and_policy_to_registry_v2() -> None:
    text = _llm_operation_text()

    required_terms = [
        "Registry v2 Profile through TUI / `mms config` / WebUI",
        "legacy `provider-profiles.json` overlays are import/export compatibility",
        "Registry v2 Policy through TUI / `mms config` / WebUI",
        "legacy `model-policy.json` is compatibility/import-export only",
        "downstream consumers read the latest-approved bundle",
    ]
    forbidden_guidance = [
        "| Model visibility / favorite / project policy | `model-policy.json` |",
        "Use `~/.config/mms/provider-profiles.json` or `~/.config/mms/model-profiles.json` only as human-managed local overlays.",
    ]

    missing = [term for term in required_terms if term not in text]
    present = [phrase for phrase in forbidden_guidance if phrase in text]
    assert missing == []
    assert present == []


def test_architecture_images_show_latest_approved_bundle_not_legacy_route_truth() -> None:
    text = _architecture_text()

    required_terms = [
        "generated/model-registry.latest-approved.json",
        "compatibility exports",
        "latest-approved",
    ]
    forbidden_guidance = [
        "persistent truth",
        "`model-routes.json`, route keyword files, gateway slots, and speed stats expose the current runtime picture.",
        "<code>model-routes.json</code>, route keyword files, gateway slots, and speed stats expose the current runtime picture.",
        "<code>model-routes.json</code>、route keyword 文件、gateway slots、speed stats 共同暴露当前 runtime picture。",
    ]

    missing = [term for term in required_terms if term not in text]
    present = [phrase for phrase in forbidden_guidance if phrase in text]
    assert missing == []
    assert present == []


def test_readmes_describe_registry_v2_profile_boundary() -> None:
    text = _readme_text()

    required_terms = [
        "Registry v2 is the preferred path for local changes",
        "TUI / `mms config` / WebUI",
        "creates DB candidates",
        "`generated/model-registry.latest-approved.json` bundle",
        "generated Profile it references is the runtime boundary",
        "本地修改优先走 Registry v2",
        "TUI / `mms config` / WebUI 先创建 DB candidate",
        "它引用的 generated Profile 就是 runtime boundary",
    ]
    forbidden_guidance = [
        "User overlays can live in the MMS config directory as read-only profile inputs.",
        "用户自己的 overlay 可以作为只读 profile 输入放在 MMS config 目录。",
    ]

    missing = [term for term in required_terms if term not in text]
    present = [phrase for phrase in forbidden_guidance if phrase in text]
    assert missing == []
    assert present == []


def test_reference_snapshot_schema_and_source_keys_are_readable() -> None:
    payload = json.loads(REFERENCE_JSON.read_text(encoding="utf-8"))

    assert payload["schema"] == "mobius.mms_model_capability_calibration.v1"
    for key in [
        "generated_at",
        "policy",
        "mms_source",
        "summary",
        "models",
        "sources",
        "official_thinking_budget_parameters",
    ]:
        assert key in payload

    assert isinstance(payload["models"], list)
    assert payload["models"]
    assert isinstance(payload["sources"], dict)
    assert payload["sources"]


def test_reference_snapshot_keeps_provider_catalog_separate_from_official_truth() -> None:
    payload = json.loads(REFERENCE_JSON.read_text(encoding="utf-8"))
    policy = payload["policy"]

    assert "OpenRouter" in policy["provider_catalog_rule"]
    assert "do not silently overwrite official" in policy["provider_catalog_rule"]
    assert "provider_catalog_references" in policy["capability_field_contract"]
    assert "OpenRouter" in policy["capability_field_contract"]["provider_catalog_references"]

    referenced = [model for model in payload["models"] if model.get("provider_catalog_references")]
    assert referenced
    for model in referenced:
        assert "official_context_window_tokens" in model
        assert "provider_catalog_references" in model


def test_reference_snapshot_preserves_thinking_control_semantics() -> None:
    payload = json.loads(REFERENCE_JSON.read_text(encoding="utf-8"))
    rule = payload["policy"]["thinking_control_rule"]

    assert "Gemini 3/3.1/3.5 use thinkingLevel" in rule
    assert "Gemini 2.5 uses numeric thinkingBudget" in rule
    assert "GLM uses thinking.type" in rule

    controls = {
        item["family"]: item["official_control"]
        for item in payload["official_thinking_budget_parameters"]
    }
    assert controls["google_gemini_3_family"] == "thinkingConfig.thinkingLevel"
    assert controls["google_gemini_2_5"] == "thinkingConfig.thinkingBudget"
    assert "thinking.type" in controls["zai_glm_native"]

    models = {model["alias"]: model for model in payload["models"]}
    assert models["gemini-3.1-pro-low"]["thinking_control"]["control_type"] == "thinkingLevel"
    assert models["gemini-3.1-pro-low"]["thinking_control"]["numeric_budget_tokens"] is None
    assert models["glm-5.1"]["thinking_control"]["control_type"] == "thinking.type"
    assert models["glm-5.1"]["thinking_control"]["numeric_budget_tokens"] is None
