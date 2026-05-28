from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REFERENCE_JSON = ROOT / "docs/reference/model-capability-calibration/2026-05-21-mms-model-capability-calibration.json"
CONTRACT_DOCS = [
    ROOT / "docs/MODEL_CONFIG_CONTRACT.md",
    ROOT / "docs/REGISTRY_ARCHITECTURE.md",
]


def _contract_text() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in CONTRACT_DOCS)


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
