"""One context window, four harnesses.

Issue #230: the K3 window was changed four times across #194/#204/#209/#213
because the number lived in several places at once — a model-name table in the
launcher, a second one in Pi, per-model special cases, and the provider
profiles. These tests hold the shape that makes that impossible to repeat:

* every model a provider profile declares gets the same number from Claude
  Code, Codex, Pi and OpenCode, and that number is what the shared resolver
  says;
* none of the harness modules carries a model-name-to-window table any more;
* a `[1m]` selector resolves exactly like its base name unless something
  deliberately declares the suffixed name;
* a model nobody has heard of, whose provider listing reports a window, lands
  correctly in all four harnesses with no code change at all. That last one is
  the owner's actual requirement: new models are 1M+ now, and adding one must
  not mean editing code.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import pytest

import mms_capability_resolver
import mms_context_window
import mms_launchers
import mms_opencode_config
import mms_pi_support
import mms_provider_profiles

REPO_ROOT = Path(mms_launchers.__file__).resolve().parent
PROFILE_PATH = REPO_ROOT / "config" / "provider-profiles.json"


@pytest.fixture(autouse=True)
def isolate_capability_root(monkeypatch):
    """Answer from the repository's own data, never from this machine's root.

    The approved bundle and the override file belong to whoever is running the
    tests, so without this the same assertion passes on one laptop and fails on
    the next.
    """
    monkeypatch.setattr(mms_capability_resolver, "_load_default_approved_facts_shared", lambda: {})
    monkeypatch.setattr(mms_capability_resolver, "load_default_model_policy", lambda: {})
    monkeypatch.setattr(
        mms_context_window,
        "load_model_context_overrides",
        lambda: {"models": {}, "provider_overrides": {}},
    )
    mms_context_window.clear_context_window_caches()
    mms_provider_profiles.load_provider_profiles.cache_clear()


def _runtime(provider_id, models=()):
    return {
        "id": provider_id,
        "name": provider_id,
        "enabled": True,
        "auth_mode": "api_key",
        "api_key": "sk-test",
        "openai_base_url": "https://relay.example.com/v1",
        "protocols": ["openai_chat_completions"],
        "supported_clis": ["claude", "codex", "pi", "opencode"],
        "_models": list(models),
    }


# ── the four harness paths, driven for real ──────────────────────────────────

def claude_code_window(runtime, model):
    """What Claude Code is told, through the launcher's own env application."""
    env = {}
    window = mms_launchers._effective_context_window(model, provider_id=runtime["id"])
    mms_launchers._apply_claude_context_env_overrides(env, context_window=window, model_names=(model,))
    return int(env["CLAUDE_CODE_AUTO_COMPACT_WINDOW"])


def codex_window(runtime, model):
    """`model_context_window` in the Codex gateway config, or None when omitted."""
    return mms_launchers._codex_gateway_context_window(runtime, {"model": model})


def pi_window(monkeypatch, runtime, model):
    """`contextWindow` in the models.json entry Pi is launched with."""
    monkeypatch.setattr(
        mms_launchers,
        "_probe_models",
        lambda _runtime, emit_output=False: {"models": list(runtime.get("_models") or [model])},
    )
    return int(mms_pi_support._pi_model_entry(runtime, model)["model"]["contextWindow"])


def opencode_window(runtime, model):
    """`limit.context` in the OpenCode config payload."""
    return int(mms_launchers._opencode_model_config(runtime, model)["limit"]["context"])


def _profile_models():
    """Every (profile id, provider id, model) a profile declares a window for."""
    payload = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    for profile_id, profile in (payload.get("profiles") or {}).items():
        windows = profile.get("context_windows")
        if not isinstance(windows, dict):
            continue
        match = profile.get("match") if isinstance(profile.get("match"), dict) else {}
        provider_ids = [str(item) for item in match.get("provider_id_contains") or []]
        provider_id = provider_ids[0] if provider_ids else profile_id
        for model in windows:
            yield profile_id, provider_id, str(model)


def _profile_cases():
    cases = []
    for profile_id, provider_id, model in _profile_models():
        # Anthropic's own models are the one family with harness-specific rules
        # left on purpose: Claude Code decides 1M by its shell model name and
        # OpenCode deliberately asks with 1M off. Everything else must agree.
        if mms_context_window.is_claude_family_model(model):
            continue
        resolved, _profile = mms_provider_profiles.resolve_provider_profile(
            provider_id=provider_id, model_name=model
        )
        if resolved != profile_id:
            # A provider hint that selects a different profile is not this
            # test's business; it would be asserting the matcher, not the chain.
            continue
        cases.append(pytest.param(provider_id, model, id=f"{profile_id}-{model}"))
    return cases


PROFILE_CASES = _profile_cases()


def test_the_profile_corpus_is_not_empty():
    assert len(PROFILE_CASES) > 30


@pytest.mark.parametrize("provider_id,model", PROFILE_CASES)
def test_every_profile_model_gets_one_window_in_every_harness(monkeypatch, provider_id, model):
    runtime = _runtime(provider_id, models=[model])
    expected = mms_context_window.resolve_context_window(model, provider_id=provider_id)
    assert expected, f"{model} on {provider_id} has a profile entry but no resolved window"

    assert claude_code_window(runtime, model) == expected
    assert pi_window(monkeypatch, runtime, model) == expected
    assert opencode_window(runtime, model) == expected

    codex = codex_window(runtime, model)
    # Codex ships a catalog for OpenAI's own models and its own floor for the
    # rest; it states a window only where it would otherwise be wrong. When it
    # states one it must be the same number.
    if codex is not None:
        assert codex == expected


def test_kimi_k3_is_one_million_everywhere(monkeypatch):
    """The model whose window was flipped four times. Pin it, once."""
    runtime = _runtime("kimi-code", models=["k3", "k3[1m]", "kimi-k3"])
    for model in ("k3", "k3[1m]", "kimi-k3"):
        assert mms_context_window.resolve_context_window(model, provider_id="kimi-code") == 1_048_576
        assert claude_code_window(runtime, model) == 1_048_576
        assert codex_window(runtime, model) == 1_048_576
        assert pi_window(monkeypatch, runtime, model) == 1_048_576
        assert opencode_window(runtime, model) == 1_048_576


# ── `[1m]` is input normalization ────────────────────────────────────────────

def test_selector_resolves_like_the_base_name():
    for model in ("k3", "qwen3.6-flash", "glm-5.1", "minimax-m3"):
        assert mms_context_window.resolve_context_window(
            f"{model}[1m]"
        ) == mms_context_window.resolve_context_window(model), model


def test_an_explicit_selector_entry_still_wins(monkeypatch):
    """Where a source really declares the suffixed name, it is not stripped."""
    monkeypatch.setattr(
        mms_context_window,
        "load_context_window_data",
        lambda: {"vendor-x": 262_144, "vendor-x[1m]": 1_000_000},
    )
    assert mms_context_window.resolve_context_window("vendor-x") == 262_144
    assert mms_context_window.resolve_context_window("vendor-x[1m]") == 1_000_000


def test_the_user_file_outranks_everything(monkeypatch):
    monkeypatch.setattr(
        mms_context_window,
        "load_model_context_overrides",
        lambda: {"models": {"k3": 123_456}, "provider_overrides": {}},
    )
    answer = mms_context_window.context_window_sources("k3", provider_id="kimi-code")
    assert answer["context_window_tokens"] == 123_456
    assert answer["source"] == "user_override"
    # And the selector inherits it, because it is the same model.
    assert mms_context_window.resolve_context_window("k3[1m]", provider_id="kimi-code") == 123_456


def test_a_context_the_user_set_in_pilot_is_final(monkeypatch):
    """The owner's rule (2026-09-12): a context set on the Pilot model page is
    the user's confirmed knowledge. Nothing calibrates it, nothing caps it, no
    `[1m]` is added to the wire name, and every harness carries it as given.
    """
    # The profile says 262144 for this variant; the user says otherwise.
    monkeypatch.setattr(
        mms_capability_resolver,
        "load_default_model_policy",
        lambda: {"models": {"k3-256k": {"capabilities": {"context_window_tokens": 1_048_576}}}},
    )
    mms_context_window.clear_context_window_caches()
    answer = mms_context_window.context_window_sources("k3-256k", provider_id="kimi-code")
    assert answer["context_window_tokens"] == 1_048_576
    assert answer["source"] == "model_policy"

    runtime = _runtime("kimi-code", models=["k3-256k"])
    assert claude_code_window(runtime, "k3-256k") == 1_048_576
    assert codex_window(runtime, "k3-256k") == 1_048_576
    assert pi_window(monkeypatch, runtime, "k3-256k") == 1_048_576
    assert opencode_window(runtime, "k3-256k") == 1_048_576

    # No harness renames the model to carry the window.
    assert mms_launchers._with_1m_suffix("k3-256k", enable_1m=True, provider_id="kimi-code") == "k3-256k"
    assert "[1m]" not in json.dumps(mms_pi_support._pi_model_entry(runtime, "k3-256k"))
    assert "[1m]" not in json.dumps(mms_launchers._opencode_model_config(runtime, "k3-256k"))


# ── a model nobody has heard of ──────────────────────────────────────────────

def test_a_new_model_from_a_provider_listing_needs_no_code_change(monkeypatch, tmp_path):
    """The owner's requirement: a 2M model appears, every harness sizes it right.

    Nothing in this repository knows `nova-9-ultra`. The provider's own /models
    listing reported its window, MMS cached that, and all four harnesses follow.
    """
    monkeypatch.delenv("MMS_CONFIG_ROOT", raising=False)
    monkeypatch.setenv("MMS_CONFIG_DIR", str(tmp_path))
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir(parents=True)
    (cache_dir / "models_nova-relay.json").write_text(
        json.dumps(
            {
                "raw_models": ["nova-9-ultra"],
                "base_source": "remote",
                "model_details": {"nova-9-ultra": {"context_length": 2_000_000}},
            }
        ),
        encoding="utf-8",
    )

    runtime = _runtime("nova-relay", models=["nova-9-ultra"])
    answer = mms_context_window.context_window_sources("nova-9-ultra", provider_id="nova-relay")
    assert answer == {
        "model": "nova-9-ultra",
        "provider_id": "nova-relay",
        "context_window_tokens": 2_000_000,
        "source": "remote_listing",
    }

    assert claude_code_window(runtime, "nova-9-ultra") == 2_000_000
    assert codex_window(runtime, "nova-9-ultra") == 2_000_000
    assert pi_window(monkeypatch, runtime, "nova-9-ultra") == 2_000_000
    assert opencode_window(runtime, "nova-9-ultra") == 2_000_000


def test_a_listing_number_that_cannot_be_a_window_is_ignored(monkeypatch, tmp_path):
    monkeypatch.delenv("MMS_CONFIG_ROOT", raising=False)
    monkeypatch.setenv("MMS_CONFIG_DIR", str(tmp_path))
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir(parents=True)
    (cache_dir / "models_nova-relay.json").write_text(
        json.dumps(
            {
                "raw_models": ["nova-9-mini"],
                "model_details": {"nova-9-mini": {"context_length": 12}},
            }
        ),
        encoding="utf-8",
    )
    assert mms_context_window.resolve_context_window("nova-9-mini", provider_id="nova-relay") is None


def test_an_unknown_model_stays_unknown():
    """`None`, not a guess: the caller applies its own default."""
    assert mms_context_window.resolve_context_window("totally-made-up-model-name") is None
    assert mms_launchers._effective_context_window("totally-made-up-model-name") == 200_000


def test_claude_family_is_a_rule_not_a_list():
    for model in ("claude-opus-4-6", "claude-sonnet-9-9", "claude-opus-4-6[1m]"):
        assert mms_context_window.resolve_context_window(model) == 1_000_000, model
    for model in ("claude-haiku-4-5", "claude-haiku-9-9-20991231"):
        assert mms_context_window.resolve_context_window(model) == 200_000, model


# ── no model-name context tables in code ─────────────────────────────────────

SCANNED_MODULES = (
    "mms_launchers.py",
    "mms_pi_support.py",
    "mms_core.py",
    "mms_opencode_env.py",
    "mms_opencode_config.py",
    "mms_context_window.py",
)

# Max output tokens, not context. Issue #230 left that mechanism alone; the
# entry is named here so a context table cannot be smuggled back in under it.
NON_CONTEXT_TABLES = {"_PI_MODEL_MAX_TOKENS_HINTS"}

# A model name as these tables wrote them: lower case, carries a version digit,
# separators optional. `k3`, `glm-5.1`, `moonshotai/kimi-k3`, `k3[1m]`.
_MODEL_NAME = re.compile(r"^[a-z][a-z0-9]*([._/\-][a-z0-9._/\-]*)*(\[1m\])?$")
_SMALLEST_WINDOW = 4_096


def _model_name_key(value):
    if not isinstance(value, str):
        return False
    candidate = value.strip().lower()
    return bool(_MODEL_NAME.match(candidate)) and any(char.isdigit() for char in candidate)


def _looks_like_a_window(value):
    return isinstance(value, int) and not isinstance(value, bool) and value >= _SMALLEST_WINDOW


def _context_tables(source, filename):
    """Dict literals in this file that map model names to window-sized ints."""
    found = []
    for node in ast.walk(ast.parse(source, filename=filename)):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        value = node.value
        if not isinstance(value, ast.Dict) or len(value.keys) < 2:
            continue
        try:
            keys = [ast.literal_eval(key) for key in value.keys if key is not None]
            values = [ast.literal_eval(item) for item in value.values]
        except (ValueError, SyntaxError):
            continue
        if len(keys) != len(values):
            continue
        if not all(_model_name_key(key) for key in keys):
            continue
        if not all(isinstance(item, int) and not isinstance(item, bool) for item in values):
            continue
        if not any(_looks_like_a_window(item) for item in values):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        names = [target.id for target in targets if isinstance(target, ast.Name)]
        found.append((names[0] if names else "<anonymous>", node.lineno))
    return found


def test_no_module_maps_a_model_name_to_a_context_window():
    """A model's window is data. A dict of them in code is how #230 happened."""
    offenders = []
    for filename in SCANNED_MODULES:
        path = REPO_ROOT / filename
        if not path.exists():
            continue
        for name, lineno in _context_tables(path.read_text(encoding="utf-8"), filename):
            if name in NON_CONTEXT_TABLES:
                continue
            offenders.append(f"{filename}:{lineno} {name}")
    assert offenders == [], (
        "model-name context tables are not allowed; put the number in "
        "config/provider-profiles.json or config/model-context-windows.json: "
        + ", ".join(offenders)
    )


def test_the_removed_tables_stay_removed():
    gone = (
        "_MODEL_CONTEXT_WINDOWS",
        "_ONE_M_SUFFIX_CONTEXT_WINDOWS",
        "_ONE_M_SUFFIX_BASE_SAFE_CONTEXT_WINDOWS",
        "_MIMO_PLAIN_ONE_M_CONTEXT_WINDOWS",
        "_MIMO_PLAIN_ONE_M_PROVIDER_HINTS",
        "_PI_MODEL_CONTEXT_WINDOW_HINTS",
        "_plain_kimi_k3_profile_context_window",
        "_is_kimi_k3_claude_env_model",
    )
    for filename in SCANNED_MODULES:
        source = (REPO_ROOT / filename).read_text(encoding="utf-8")
        for name in gone:
            assert name not in source, f"{name} is back in {filename}"


def test_the_data_file_is_data():
    """Every row says where its number came from, and the number is plausible."""
    payload = json.loads((REPO_ROOT / "config" / "model-context-windows.json").read_text(encoding="utf-8"))
    models = payload["models"]
    assert models
    for model, row in models.items():
        assert row.get("source"), model
        window = row.get("context_window_tokens")
        assert isinstance(window, int) and 4_096 <= window <= 10_000_000, model
        assert model == model.strip().lower(), model


def test_a_profile_entry_outranks_the_data_file():
    """The data file is the last resort, not a second opinion."""
    table = mms_context_window.load_context_window_data()
    assert "glm-5.1" in table
    answer = mms_context_window.context_window_sources("glm-5.1", provider_id="glm")
    assert answer["source"] == "provider_profile"


def test_max_output_never_exceeds_the_context_window():
    """The invariant that made a stale max-tokens hint visible in the first place."""
    for provider_id, model in {(case.values[0], case.values[1]) for case in PROFILE_CASES}:
        window = mms_context_window.resolve_context_window(model, provider_id=provider_id)
        output = mms_launchers._capability_max_output_tokens(model, provider_id=provider_id)
        if window and output:
            assert output <= window, f"{model} on {provider_id}: output {output} > context {window}"
