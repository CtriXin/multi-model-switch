"""OpenCode session-local agent roster helpers."""

from __future__ import annotations

import copy


def opencode_lite_agent_configs(model_ref):
    """Return session-local OpenCode agents for the MMS lite lane."""
    if not model_ref:
        return {}

    safe_read_bash = {
        "*": "ask",
        "pwd": "allow",
        "ls *": "allow",
        "rg *": "allow",
        "git status*": "allow",
        "git diff*": "allow",
        "git log*": "allow",
    }
    test_bash = {
        **safe_read_bash,
        "npm test*": "ask",
        "npm run *": "ask",
        "npx tsc*": "ask",
        "python* -m pytest*": "ask",
        "pytest*": "ask",
    }
    common_read_permissions = {
        "read": "allow",
        "grep": "allow",
        "glob": "allow",
        "list": "allow",
    }

    return {
        "mobius-explore": {
            "description": "Fast read-only codebase exploration for the MMS OpenCode lite lane",
            "mode": "subagent",
            "model": model_ref,
            "temperature": 0.1,
            "steps": 12,
            "permission": {
                **common_read_permissions,
                "edit": "deny",
                "bash": safe_read_bash,
                "task": "deny",
                "webfetch": "ask",
                "websearch": "ask",
                "external_directory": "deny",
            },
            "prompt": (
                "Read code and local docs only. Do not edit files. Return concise "
                "findings with paths, symbols, risks, and the next suggested action."
            ),
        },
        "mobius-builder": {
            "description": "Daily implementation agent for the MMS OpenCode lite lane",
            "mode": "primary",
            "model": model_ref,
            "variant": "high",
            "temperature": 0.2,
            "permission": {
                **common_read_permissions,
                "edit": "ask",
                "bash": test_bash,
                "task": {
                    "*": "deny",
                    "mobius-explore": "allow",
                    "mobius-reviewer": "ask",
                    "mobius-fixer": "ask",
                },
                "webfetch": "ask",
                "websearch": "ask",
                "external_directory": "ask",
            },
            "prompt": (
                "Implement scoped changes. Prefer existing project conventions. Keep "
                "edits small. Use subagents only when their result materially reduces "
                "risk. Do not claim done until validation or a clear blocker is recorded."
            ),
        },
        "mobius-reviewer": {
            "description": "Read-only review agent for code, scope, tests, and evidence",
            "mode": "subagent",
            "model": model_ref,
            "variant": "high",
            "temperature": 0.1,
            "steps": 24,
            "permission": {
                **common_read_permissions,
                "edit": "deny",
                "bash": test_bash,
                "task": "deny",
                "webfetch": "ask",
                "websearch": "ask",
                "external_directory": "deny",
            },
            "prompt": (
                "Review like a release gate. Lead with bugs, regressions, missing "
                "tests, scope drift, and evidence gaps. Do not edit files."
            ),
        },
        "mobius-fixer": {
            "description": "Focused repair agent for one known failing test, review finding, or bug",
            "mode": "subagent",
            "model": model_ref,
            "temperature": 0.2,
            "permission": {
                **common_read_permissions,
                "edit": "ask",
                "bash": test_bash,
                "task": "deny",
                "webfetch": "ask",
                "websearch": "ask",
                "external_directory": "ask",
            },
            "prompt": (
                "Fix only the named failure. Do not broaden scope. Report changed "
                "files, validation run, remaining risk, and any blocker."
            ),
        },
    }


def opencode_lite_pro_agent_configs(agent_models, *, orchestrated=False, roster_config=None):
    """Return deterministic Lite Pro roster with named fallback agents."""
    agent_models = agent_models if isinstance(agent_models, dict) else {}
    roster_config = roster_config if isinstance(roster_config, dict) else {}
    builder_model = agent_models.get("mobius-builder-pro") or next(iter(agent_models.values()), "")
    if not builder_model:
        return {}

    safe_read_bash = {
        "*": "ask",
        "pwd": "allow",
        "ls *": "allow",
        "rg *": "allow",
        "git status*": "allow",
        "git diff*": "allow",
        "git log*": "allow",
    }
    test_bash = {
        **safe_read_bash,
        "npm test*": "ask",
        "npm run *": "ask",
        "npx tsc*": "ask",
        "python* -m pytest*": "ask",
        "pytest*": "ask",
    }
    common_read_permissions = {
        "read": "allow",
        "grep": "allow",
        "glob": "allow",
        "list": "allow",
    }

    def _agent_model(name, fallback=builder_model):
        return str(agent_models.get(name) or fallback or builder_model)

    def _roster_entry(name):
        entry = roster_config.get(name)
        return entry if isinstance(entry, dict) else {}

    def _agent_enabled(name):
        if name == "mobius-builder-pro":
            return True
        return _roster_entry(name).get("enabled") is not False

    def _agent_preset(name):
        raw = str(_roster_entry(name).get("preset") or "").strip().lower()
        if raw:
            return raw
        lowered = str(name or "").lower()
        if "vision" in lowered:
            return "vision"
        if "bughunt" in lowered:
            return "bughunt"
        if "explore" in lowered:
            return "explore"
        if "review" in lowered or "compliance" in lowered:
            return "reviewer"
        if "spec" in lowered:
            return "spec"
        if "executor" in lowered:
            return "executor"
        if "fixer" in lowered:
            return "fixer"
        return "builder"

    direct_builder_task_permission = {
        "*": "deny",
        "mobius-builder-stable": "ask",
        "mobius-spec-writer": "ask",
        "mobius-spec-compliance-reviewer": "ask",
        "mobius-explore-glm": "allow",
        "mobius-explore-kimi": "ask",
        "mobius-bughunt-deepseek": "ask",
        "mobius-bughunt-glm": "ask",
        "mobius-bughunt-qwen": "ask",
        "mobius-vision-mimo": "ask",
        "mobius-vision-kimi": "ask",
        "mobius-vision-qwen": "ask",
        "mobius-reviewer-gpt55": "ask",
        "mobius-reviewer-gpt54": "ask",
        "mobius-reviewer-mimo": "ask",
        "mobius-fixer-gpt54": "ask",
    }
    orchestrator_task_permission = {
        "*": "deny",
        "mobius-spec-writer": "allow",
        "mobius-spec-compliance-reviewer": "allow",
        "mobius-explore-glm": "allow",
        "mobius-explore-kimi": "ask",
        "mobius-explore-qwen": "ask",
        "mobius-bughunt-deepseek": "ask",
        "mobius-bughunt-glm": "ask",
        "mobius-bughunt-qwen": "ask",
        "mobius-vision-mimo": "ask",
        "mobius-vision-kimi": "ask",
        "mobius-vision-qwen": "ask",
        "mobius-executor-gpt54": "allow",
        "mobius-reviewer-gpt55": "ask",
        "mobius-reviewer-gpt54": "ask",
        "mobius-reviewer-mimo": "ask",
        "mobius-fixer-gpt54": "ask",
    }
    read_only_permission = {
        **common_read_permissions,
        "edit": "deny",
        "bash": safe_read_bash,
        "task": "deny",
        "webfetch": "ask",
        "websearch": "ask",
        "external_directory": "deny",
    }
    fix_permission = {
        **common_read_permissions,
        "edit": "ask",
        "bash": test_bash,
        "task": "deny",
        "webfetch": "ask",
        "websearch": "ask",
        "external_directory": "ask",
    }
    spec_writer_permission = {
        **common_read_permissions,
        "edit": "ask",
        "bash": safe_read_bash,
        "task": "deny",
        "webfetch": "ask",
        "websearch": "ask",
        "external_directory": "ask",
    }
    builder_permission = {
        **common_read_permissions,
        "edit": "deny" if orchestrated else "ask",
        "bash": test_bash,
        "task": orchestrator_task_permission if orchestrated else direct_builder_task_permission,
        "webfetch": "ask",
        "websearch": "ask",
        "external_directory": "ask",
    }
    builder_prompt = (
        "You are the orchestrator only. Do not edit files directly. For non-trivial, "
        "architecture, product, or multi-agent work, first call mobius-spec-writer to "
        "produce or update an OpenSpec/SpecBridge-style contract: intent, non-goals, "
        "task slices, acceptance criteria, validation commands, and reviewer checklist. "
        "Treat that contract as authoritative; do not let executors reinterpret the "
        "architecture. Gather context with mobius-explore-glm, mobius-explore-kimi, or "
        "mobius-explore-qwen as needed, and use domestic bug-hunt agents only for "
        "read-only counterexamples, missing tests, and risk discovery. If images are "
        "present, delegate visual inspection to mobius-vision-mimo, mobius-vision-kimi, "
        "or mobius-vision-qwen before implementation. Then delegate implementation to "
        "mobius-executor-gpt54 with a bounded packet containing target files, exact "
        "acceptance criteria, validation commands, and blockers. Do not split normal "
        "implementation across domestic executor chains. Inspect the actual git diff and "
        "validation evidence, not only executor summaries. If acceptance fails or "
        "confidence is low, send one focused failure packet to mobius-fixer-gpt54; if the "
        "architecture itself is suspect, escalate back to the user instead of cycling "
        "agents. Before release-gate review, call mobius-spec-compliance-reviewer to "
        "check implementation against the contract item by item. Use "
        "mobius-reviewer-gpt55 as the final release gate; use mobius-reviewer-gpt54 only "
        "for reviewer-route outage. Do not let an executor/fixer self-approve its own "
        "work. When direct MiMo is available, use mobius-reviewer-mimo for additional "
        "CN/vision critique, not as the final gate. Record which executor/reviewer was "
        "used."
    ) if orchestrated else (
        "Primary path: for non-trivial or architecture-sensitive work, ask "
        "mobius-spec-writer for an OpenSpec/SpecBridge-style contract before editing; "
        "then implement directly against that contract. Use domestic explore and "
        "bug-hunt agents only for read-only context, counterexamples, and risk checks. "
        "When images are present and the active model is not image-capable, ask "
        "mobius-vision-mimo, mobius-vision-kimi, or mobius-vision-qwen for a structured "
        "visual read. Before claiming done, ask mobius-spec-compliance-reviewer to check "
        "the implementation against the contract, then review with mobius-reviewer-gpt55. "
        "Use mobius-fixer-gpt54 for focused fixes when needed. Keep GPT as the final "
        "release gate. Use mobius-reviewer-gpt54 only for reviewer-route outage. Use "
        "mobius-builder-stable only when the primary model/channel is suspect or the "
        "final result remains unstable. Record which contract, fallback, and validation "
        "were used."
    )
    stable_prompt = (
        "Fallback orchestrator. Do not edit files directly. Take over only after primary "
        "orchestration fails or is low confidence. Delegate implementation to the executor "
        "chain, inspect contract compliance and validation evidence, and keep scope small."
    ) if orchestrated else (
        "Fallback builder. Take over only after primary path fails or is low confidence. "
        "Keep scope small, preserve existing edits, validate against the contract, and report exact changed files."
    )
    stable_permission = builder_permission if orchestrated else fix_permission

    agents = {
        "mobius-builder-pro": {
            "description": "Lite Pro primary builder with deterministic fallback policy",
            "mode": "primary",
            "model": _agent_model("mobius-builder-pro"),
            "variant": "high",
            "temperature": 0.2,
            "permission": builder_permission,
            "prompt": builder_prompt,
        },
        "mobius-builder-stable": {
            "description": "Stable GPT fallback builder for Lite Pro",
            "mode": "primary",
            "model": _agent_model("mobius-builder-stable"),
            "variant": "high",
            "temperature": 0.2,
            "permission": stable_permission,
            "prompt": stable_prompt,
        },
        "mobius-spec-writer": {
            "description": "OpenSpec/SpecBridge contract writer for non-trivial work",
            "mode": "subagent",
            "model": _agent_model("mobius-spec-writer"),
            "variant": "high",
            "temperature": 0.1,
            "steps": 24,
            "permission": spec_writer_permission,
            "prompt": (
                "Create or update the minimal OpenSpec/SpecBridge-style contract for "
                "this task. Prefer existing openspec/ or .ai/plan conventions; do not "
                "invent a global framework. Capture intent, non-goals, task slices, "
                "acceptance criteria, validation commands, changed-file boundaries, and "
                "blockers. Keep it short enough for executors to follow exactly."
            ),
        },
        "mobius-spec-compliance-reviewer": {
            "description": "Read-only reviewer that checks implementation against the spec contract",
            "mode": "subagent",
            "model": _agent_model("mobius-spec-compliance-reviewer", _agent_model("mobius-reviewer-gpt55")),
            "variant": "high",
            "temperature": 0.1,
            "steps": 24,
            "permission": read_only_permission,
            "prompt": (
                "Review only spec compliance. Compare the OpenSpec/SpecBridge contract, "
                "acceptance criteria, git diff, and validation output item by item. Return "
                "PASS/FAIL/UNKNOWN for each criterion, then list blockers and evidence gaps. "
                "Do not perform general style review and do not edit files."
            ),
        },
        "mobius-explore-glm": {
            "description": "Lite Pro primary read-only explorer",
            "mode": "subagent",
            "model": _agent_model("mobius-explore-glm"),
            "temperature": 0.1,
            "steps": 12,
            "permission": read_only_permission,
            "prompt": "Read code/docs only. Return concise map: files, symbols, risks, next action. No edits.",
        },
        "mobius-explore-kimi": {
            "description": "Lite Pro fallback read-only explorer",
            "mode": "subagent",
            "model": _agent_model("mobius-explore-kimi", _agent_model("mobius-explore-glm")),
            "temperature": 0.1,
            "steps": 12,
            "permission": read_only_permission,
            "prompt": "Fallback explorer. Re-check unclear areas and contradictions. No edits.",
        },
        "mobius-explore-qwen": {
            "description": "Lite Pro long-context read-only Qwen explorer",
            "mode": "subagent",
            "model": _agent_model("mobius-explore-qwen", _agent_model("mobius-explore-glm")),
            "temperature": 0.1,
            "steps": 12,
            "permission": read_only_permission,
            "prompt": "Qwen explorer. Use for broad repo context, API surfaces, and missing cross-file links. No edits.",
        },
        "mobius-reviewer-gpt55": {
            "description": "Lite Pro high-risk release-gate reviewer",
            "mode": "subagent",
            "model": _agent_model("mobius-reviewer-gpt55"),
            "variant": "high",
            "temperature": 0.1,
            "steps": 24,
            "permission": read_only_permission,
            "prompt": (
                "Review as the release gate. Lead with bugs, regressions, missing tests, "
                "and evidence gaps. Confirm spec-compliance review ran when a contract exists. Do not self-approve executor/fixer output. No edits."
            ),
        },
        "mobius-reviewer-gpt54": {
            "description": "Lite Pro stable fallback read-only reviewer",
            "mode": "subagent",
            "model": _agent_model("mobius-reviewer-gpt54", _agent_model("mobius-reviewer-gpt55")),
            "variant": "high",
            "temperature": 0.1,
            "steps": 24,
            "permission": read_only_permission,
            "prompt": (
                "Fallback reviewer for primary reviewer outage. Focus on findings missed by "
                "the release gate and validation gaps. If mobius-executor-gpt54 made the "
                "edits, prefer the gpt-5.5 reviewer when available. No edits."
            ),
        },
        "mobius-bughunt-deepseek": {
            "description": "Lite Pro domestic read-only bug hunter",
            "mode": "subagent",
            "model": _agent_model("mobius-bughunt-deepseek"),
            "temperature": 0.1,
            "steps": 12,
            "permission": read_only_permission,
            "prompt": (
                "Read-only bug hunt. Look for concrete defects, missing tests, edge cases, "
                "and risky assumptions. Return file paths and evidence. Do not edit files."
            ),
        },
        "mobius-bughunt-glm": {
            "description": "Lite Pro domestic fallback bug hunter",
            "mode": "subagent",
            "model": _agent_model("mobius-bughunt-glm", _agent_model("mobius-bughunt-deepseek")),
            "temperature": 0.1,
            "steps": 12,
            "permission": read_only_permission,
            "prompt": "Fallback read-only bug hunt. Re-check defects and counterexamples. No edits.",
        },
        "mobius-fixer-gpt54": {
            "description": "Lite Pro GPT focused fixer",
            "mode": "subagent",
            "model": _agent_model("mobius-fixer-gpt54", _agent_model("mobius-builder-stable")),
            "variant": "high",
            "temperature": 0.2,
            "permission": fix_permission,
            "prompt": "Focused GPT fixer. Fix only the named failure. Keep scope tight, validate, and report exact diff risk.",
        },
    }
    if not orchestrated:
        agents.pop("mobius-explore-qwen", None)
    optional_vision_agents = {
        "mobius-vision-mimo": {
            "description": "Lite Pro MiMo image understanding helper",
            "prompt": "Read attached images/screenshots only. Return structured observations, visible text, UI risks, and uncertainties. No edits.",
        },
        "mobius-vision-kimi": {
            "description": "Lite Pro Kimi image understanding fallback",
            "prompt": "Fallback vision helper. Read attached images/screenshots and return concise structured observations. No edits.",
        },
        "mobius-vision-qwen": {
            "description": "Lite Pro Qwen image understanding fallback",
            "prompt": "Qwen vision helper. Use for screenshots, diagrams, and visual UI context. Return observations only. No edits.",
        },
    }
    for name, config in optional_vision_agents.items():
        if name not in agent_models:
            continue
        agents[name] = {
            "description": config["description"],
            "mode": "subagent",
            "model": _agent_model(name),
            "temperature": 0.1,
            "steps": 12,
            "permission": read_only_permission,
            "prompt": config["prompt"],
        }
    if "mobius-reviewer-mimo" in agent_models:
        agents["mobius-reviewer-mimo"] = {
            "description": "Lite Pro direct MiMo critique reviewer",
            "mode": "subagent",
            "model": _agent_model("mobius-reviewer-mimo"),
            "temperature": 0.1,
            "steps": 12,
            "permission": read_only_permission,
            "prompt": (
                "Supplemental reviewer. Focus on Chinese reasoning, multimodal/visual "
                "risks, counterexamples, and product-quality concerns. No edits. Do not "
                "act as the final release gate."
            ),
        }
    if orchestrated:
        if "mobius-bughunt-qwen" in agent_models:
            agents["mobius-bughunt-qwen"] = {
                "description": "Lite Pro Qwen read-only bug hunter",
                "mode": "subagent",
                "model": _agent_model("mobius-bughunt-qwen"),
                "temperature": 0.1,
                "steps": 12,
                "permission": read_only_permission,
                "prompt": "Qwen read-only bug hunt. Focus on long-context consistency, missed edge cases, and test gaps. No edits.",
            }
        executor_prompt = (
            "Implement only the assigned scope from the contract packet. Edit files "
            "directly if needed, but do not reinterpret the architecture, broaden design, "
            "or start unrelated refactors. If acceptance criteria are unclear, return a "
            "blocker instead of guessing. Run listed validation commands when available. "
            "Keep going until the acceptance criteria pass or a real blocker is reached. "
            "Return changed files, commands, results, risks, and any blocker."
        )
        agents["mobius-executor-gpt54"] = {
            "description": "Lite Pro long-running GPT implementation executor",
            "mode": "subagent",
            "model": _agent_model("mobius-executor-gpt54", _agent_model("mobius-builder-stable")),
            "variant": "high",
            "temperature": 0.2,
            "permission": fix_permission,
            "prompt": "Primary implementation executor. " + executor_prompt,
        }

    custom_prompt_by_preset = {
        "vision": "Custom vision helper. Read attached images/screenshots only. Return structured observations, visible text, UI risks, and uncertainties. No edits.",
        "explore": "Custom read-only explorer. Read code/docs only and return concise files, symbols, risks, and next action. No edits.",
        "bughunt": "Custom read-only bug hunter. Look for concrete defects, missing tests, edge cases, and risky assumptions. No edits.",
        "reviewer": "Custom read-only reviewer. Lead with bugs, regressions, missing tests, scope drift, and evidence gaps. No edits.",
        "executor": "Custom implementation executor. Edit only the assigned scope, run listed validation when available, and report changed files and risks.",
        "fixer": "Custom focused fixer. Fix only the named failure, keep scope tight, validate, and report exact diff risk.",
        "spec": "Custom spec writer. Capture intent, non-goals, task slices, acceptance criteria, validation commands, and blockers.",
    }
    for name, entry in sorted(roster_config.items()):
        if name in agents or name not in agent_models or not isinstance(entry, dict):
            continue
        if entry.get("enabled") is False:
            continue
        if entry.get("custom") is not True and not str(name).startswith("mobius-"):
            continue
        preset = _agent_preset(name)
        if preset in {"executor", "fixer"}:
            permission = fix_permission
            variant = "high"
            steps = None
        elif preset == "spec":
            permission = spec_writer_permission
            variant = "high"
            steps = 24
        elif preset == "reviewer":
            permission = read_only_permission
            variant = "high"
            steps = 24
        else:
            permission = read_only_permission
            variant = ""
            steps = 12
        agent = {
            "description": str(entry.get("description") or f"Lite Pro custom {preset} agent"),
            "mode": "subagent",
            "model": _agent_model(name),
            "temperature": 0.2 if preset in {"executor", "fixer"} else 0.1,
            "permission": permission,
            "prompt": str(entry.get("prompt") or custom_prompt_by_preset.get(preset) or custom_prompt_by_preset["explore"]),
        }
        if variant:
            agent["variant"] = variant
        if steps:
            agent["steps"] = steps
        agents[name] = agent

    for name, entry in roster_config.items():
        if name not in agents or not isinstance(entry, dict):
            continue
        if entry.get("description"):
            agents[name]["description"] = str(entry.get("description"))
        if entry.get("prompt"):
            agents[name]["prompt"] = str(entry.get("prompt"))

    for name in list(agents):
        if not _agent_enabled(name):
            agents.pop(name, None)

    task_preference = {
        "spec": "allow",
        "explore": "allow",
        "executor": "allow" if orchestrated else "ask",
        "vision": "allow" if orchestrated else "ask",
        "bughunt": "ask",
        "reviewer": "ask",
        "fixer": "ask",
        "builder": "ask",
    }
    existing_agents = set(agents)
    for config in agents.values():
        permission = config.get("permission") if isinstance(config, dict) else None
        if not isinstance(permission, dict) or not isinstance(permission.get("task"), dict):
            continue
        task_permission = {
            key: value for key, value in permission["task"].items()
            if key == "*" or key in existing_agents
        }
        for name in sorted(existing_agents):
            if name in task_permission:
                continue
            entry = _roster_entry(name)
            if entry.get("custom") is True:
                task_permission[name] = task_preference.get(_agent_preset(name), "ask")
        permission["task"] = task_permission
    return agents


def opencode_review_hub_agent_configs(agent_models, *, roster_config=None):
    """Return a Review Hub-focused OpenCode roster."""
    agent_models = agent_models if isinstance(agent_models, dict) else {}
    roster_config = roster_config if isinstance(roster_config, dict) else {}
    host_model = (
        agent_models.get("review-hub-host")
        or agent_models.get("review-hub-host-stable")
        or next(iter(agent_models.values()), "")
    )
    if not host_model:
        return {}

    safe_read_bash = {
        "*": "ask",
        "pwd": "allow",
        "ls *": "allow",
        "rg *": "allow",
        "git status*": "allow",
        "git diff*": "allow",
        "git log*": "allow",
        "review-hub *": "allow",
        "node */review-hub.js *": "allow",
    }
    artifact_bash = {
        **safe_read_bash,
        "mkdir *": "ask",
        "cat *": "ask",
        "python*": "ask",
        "node *": "ask",
    }
    common_permissions = {
        "read": "allow",
        "grep": "allow",
        "glob": "allow",
        "list": "allow",
    }
    reviewer_names = sorted(
        name for name in agent_models
        if str(name).startswith("review-") and name not in {"review-hub-host", "review-hub-host-stable"}
    )
    available_reviewers = [
        name for name in reviewer_names
        if name in agent_models
    ]
    reviewer_list_text = ", ".join(available_reviewers) or "no review-* subagents"

    def _agent_model(name, fallback=host_model):
        return str(agent_models.get(name) or fallback or host_model)

    def _reviewer_prompt(label):
        return (
            f"You are the {label} Review Hub reviewer. When given a request root, "
            "run `review-hub reviewer <request-root>` with your model identity when "
            "needed, read the returned PROMPT.md and manifest.json, then execute that "
            "prompt. Do environment preflight first. If required MCP/tools/skills/auth "
            "are missing, write the blocked preflight artifact and stop. Do not edit "
            "source files; write review artifacts only inside your assigned slot_root. "
            "Lead with concrete findings, evidence, uncertainty, and missing tests."
        )

    host_task_permission = {"*": "deny"}
    for name in available_reviewers:
        host_task_permission[name] = "allow" if name != "review-hub-host-stable" else "ask"

    agents = {
        "review-hub-host": {
            "description": "Review Hub host that asks for reviewer models and fans out independent reviews",
            "mode": "primary",
            "model": _agent_model("review-hub-host"),
            "variant": "high",
            "temperature": 0.1,
            "permission": {
                **common_permissions,
                "edit": "ask",
                "bash": artifact_bash,
                "task": host_task_permission,
                "webfetch": "ask",
                "websearch": "ask",
                "external_directory": "ask",
            },
            "prompt": (
                "You are a Review Hub execution host, not the original dispatcher. "
                "Default host route prefers fast domestic GLM/Kimi/Qwen and falls back through MMS route "
                "resolution. Start by asking the user for a Review Hub request root "
                "or short command such as `/review-hub <request-root>` if it was not "
                "already provided. Use the preloaded reviewer agents in this session "
                f"unless the user narrows them: {reviewer_list_text}. If the user "
                "does ask to narrow, only use agents already available in this "
                "session; do not invent new model aliases inside OpenCode. Send every "
                "selected reviewer the same request-root task, including its model name. "
                "Each reviewer must hydrate its own slot with `review-hub reviewer`, "
                "read PROMPT.md, run preflight first, and write only inside slot_root. "
                "MCP and skills are session-local runner capabilities; do not claim a "
                "tool exists unless the reviewer preflight confirms it. After reviewers "
                "finish, run `review-hub aggregate --request <request-root>` when "
                "available, then report blockers, consensus findings, disagreements, "
                "and the aggregate path. Do not edit product/source files."
            ),
        },
        "review-hub-host-stable": {
            "description": "Stable fallback Review Hub host",
            "mode": "primary",
            "model": _agent_model("review-hub-host-stable"),
            "variant": "high",
            "temperature": 0.1,
            "permission": {
                **common_permissions,
                "edit": "ask",
                "bash": artifact_bash,
                "task": host_task_permission,
                "webfetch": "ask",
                "websearch": "ask",
                "external_directory": "ask",
            },
            "prompt": (
                "Fallback Review Hub host. Continue only if the primary host is "
                "unavailable or low-confidence. Preserve the same request root, model "
                "selection, preflight-first behavior, and slot-only write boundary."
            ),
        },
    }

    default_reviewer_descriptions = {
        "review-qwen": "Qwen long-context independent reviewer",
        "review-kimi": "Kimi independent reviewer",
        "review-glm": "GLM independent reviewer",
        "review-deepseek": "DeepSeek independent reviewer",
        "review-mimo": "MiMo multimodal reviewer",
        "review-mimo-pro": "MiMo Pro large-project/product critique reviewer",
    }
    for name in available_reviewers:
        if name not in agent_models:
            continue
        roster_entry = roster_config.get(name) if isinstance(roster_config.get(name), dict) else {}
        description = (
            str(roster_entry.get("description") or "").strip()
            or default_reviewer_descriptions.get(name)
            or f"Review Hub reviewer {name}"
        )
        agents[name] = {
            "description": description,
            "mode": "subagent",
            "model": _agent_model(name),
            "temperature": 0.1,
            "permission": {
                **common_permissions,
                "edit": "ask",
                "bash": artifact_bash,
                "task": "deny",
                "webfetch": "ask",
                "websearch": "ask",
                "external_directory": "ask",
            },
            "prompt": _reviewer_prompt(description),
        }
    return agents


def opencode_committee_agent_configs(agent_models, *, roster_config=None, agent_policies=None):
    """Return a general-purpose committee roster without per-agent step caps."""
    agent_models = agent_models if isinstance(agent_models, dict) else {}
    roster_config = roster_config if isinstance(roster_config, dict) else {}
    agent_policies = agent_policies if isinstance(agent_policies, dict) else {}
    host_model = (
        agent_models.get("committee-host")
        or agent_models.get("committee-host-pro")
        or next(iter(agent_models.values()), "")
    )
    if not host_model:
        return {}

    safe_read_bash = {
        "*": "ask",
        "pwd": "allow",
        "ls *": "allow",
        "rg *": "allow",
        "git status*": "allow",
        "git diff*": "allow",
        "git log*": "allow",
    }
    common_permissions = {
        "read": "allow",
        "grep": "allow",
        "glob": "allow",
        "list": "allow",
    }
    member_permission = {
        **common_permissions,
        "edit": "deny",
        "bash": safe_read_bash,
        "task": "deny",
        "webfetch": "ask",
        "websearch": "ask",
        "external_directory": "ask",
    }
    host_permission = {
        **common_permissions,
        "edit": "ask",
        "bash": safe_read_bash,
        "task": {"*": "deny"},
        "webfetch": "ask",
        "websearch": "ask",
        "external_directory": "ask",
    }
    member_names = sorted(
        name for name in agent_models
        if str(name).startswith("committee-") and name not in {"committee-host", "committee-host-pro"}
    )
    for name in member_names:
        host_permission["task"][name] = "allow"

    def _agent_model(name, fallback=host_model):
        return str(agent_models.get(name) or fallback or host_model)

    def _merge_dict(base, override):
        merged = dict(base or {})
        for key, value in (override or {}).items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key] = _merge_dict(merged[key], value)
            else:
                merged[key] = value
        return merged

    def _agent_policy(name):
        policy = agent_policies.get(name) if isinstance(agent_policies.get(name), dict) else {}
        roster_entry = roster_config.get(name) if isinstance(roster_config.get(name), dict) else {}
        roster_policy = roster_entry.get("opencode_policy")
        if isinstance(roster_policy, dict):
            policy = _merge_dict(policy, roster_policy)
        return policy

    def _search_tools_fallback_only(policy):
        raw = str((policy or {}).get("builtin_search_tools") or "").strip().lower()
        return raw in {"disabled", "deny", "off", "shell", "shell_only", "fallback_only"}

    def _permission_for_agent(base_permission, policy):
        permission = copy.deepcopy(base_permission)
        if not _search_tools_fallback_only(policy):
            return permission
        for tool_name in ("grep", "glob", "list"):
            permission[tool_name] = "deny"
        bash_permission = permission.get("bash")
        if isinstance(bash_permission, dict):
            bash_permission = dict(bash_permission)
            bash_permission.update({
                "pwd": "allow",
                "ls *": "allow",
                "rg *": "allow",
            })
            permission["bash"] = bash_permission
        return permission

    def _prompt_with_tool_policy(prompt, policy):
        if not _search_tools_fallback_only(policy):
            return prompt
        return (
            f"{prompt} "
            "Tool policy: do not call built-in grep/glob/list for search or file "
            "listing on this route; use shell commands instead (`rg --files`, "
            "`rg -n`, `ls`, `pwd`; request `find` only when needed). If a "
            "built-in search tool returns a "
            "schema error, do not retry it; switch to the shell fallback."
        )

    committee_policy_contract = (
        "Committee policy contract: before non-trivial delegation, declare "
        "committee_policy with decision_mode, playbook, artifact_mode, "
        "permission_profile, selected_members, non_dispatched_members, and reason. "
        "Decision modes are advisory, gate, estimate, review, and execution_packet. "
        "Use advisory for opinions without formal vote; Gate mode for "
        "approve/reject/modify/veto decisions; Estimate mode for risk, effort, "
        "confidence, cost, or scores; review for finding-first bugs, regressions, "
        "missing tests, security gaps, and release risks; execution_packet only "
        "to prepare implementation tasks, not to execute by default. "
        "Playbooks are domain checklists, not decision modes: general, "
        "git_ci_security, pr_review, docs_policy, architecture, and release_gate. "
        "Use general for unspecialized tasks that do not need a narrower domain "
        "checklist; it still requires the declared decision_mode output contract. "
        "For Git, CI, GitHub Actions, token scopes, workflow permissions, or "
        "security-flow tasks, use playbook git_ci_security with Gate mode or "
        "review mode; do not invent a hidden Git mode. "
        "Artifact modes are chat_only, artifact_advisory, formal_vote_files, "
        "decision_file, and checker_only. Permission profiles are readonly, "
        "artifact_write, checker_run, and implementation_ask. Default to "
        "chat_only plus readonly; member edits are denied in the generated default "
        "permissions, and any artifact or implementation write needs an explicit "
        "scoped escalation outside the default readonly profile. Keep this separate from Debate: do not run blind "
        "rounds, crossfire, stance-shift tracking, or debate resolution states "
        "inside committee."
    )
    member_list_text = ", ".join(member_names) or "no committee-* subagents"
    host_prompt = (
        "You are a general committee host, not a specialized review dispatcher. "
        "For any user request, restate the goal, classify the request type, and "
        "choose the right committee mode. "
        + committee_policy_contract + " "
        "When dispatching, include the declared committee policy in each member "
        "brief and adapt the requested output to that decision mode and playbook. "
        "For checker_only or checker_run work, treat command exits and provided "
        "checker output as deterministic evidence that model votes must not "
        "override without explicit human direction. "
        "Use Gate mode for approve/reject/modify "
        "decisions: collect one independent ballot per delegated member with "
        "model, verdict, veto, cited evidence, and reason. Use Estimate mode for "
        "scores, risk, effort, or confidence: collect estimates, aggregate by "
        "median, and do not use veto as a scoring tool. For verifiable facts such "
        "as tests, compile results, or command exits, verify them directly instead "
        "of asking members to vote. "
        "Split the goal into a compact brief and delegate to selected committee "
        "subagents. For non-trivial work, prefer at least 2-4 members; for "
        "high-risk Gate decisions, prefer at least 3 or all relevant available "
        "members. If you delegate to fewer members, explain why. "
        f"Available committee members: {member_list_text}. Do not invent missing agents. "
        "Before choosing mode or dispatching, inspect and obey the target project's "
        "local instructions when present: AGENTS.md, CLAUDE.md, SKILL.md, README.md, "
        "governance/README.md, docs/how-to-raise-amendment-pr.md, or an explicit "
        "checker/runbook. Local project rules and user instructions override generic "
        "committee defaults, including whether members must write durable formal "
        "artifacts such as vote files. If local rules define host/secretary and "
        "juror/member duties, follow those duties exactly. "
        "Members are general-purpose and may request edits only for explicitly "
        "assigned artifacts or implementation work; otherwise keep them read-first. "
        "By default, the host only dispatches, verifies facts, collects ballots, "
        "tallies, and synthesizes. Unless the user explicitly grants execution "
        "authority, the host must not write or update votes/<model>.vote.md, must "
        "not update decision.md or ratification markers, must not promote "
        "advisory/chat ballots into formal quorum votes, and must not ask members "
        "to write formal vote files. If a prior dispatch did not explicitly assign "
        "a formal vote-file artifact, treat returned ballots as advisory review "
        "evidence only. If the user explicitly asks for formal durable ballots, "
        "assign each member its own vote-file path; a member may write only its "
        "own assigned vote file when write permission is granted. The host may "
        "update decision.md or run a quorum checker only when the user explicitly "
        "grants that artifact/checker task; never ratify, merge, or mark final "
        "approval unless the user explicitly asks. Never pretend a member wrote a "
        "file it did not write. If an external gate checker is provided, call that "
        "checker instead of reimplementing project-specific quorum rules. "
        "For long ballots, audits, or multi-section answers, use artifact-first "
        "dispatch: assign each member an output file path, ask it to write the "
        "full artifact there, and require the chat reply to contain only the path, "
        "a compact summary, and any blocked/missing sections. "
        "Synthesize only after member outputs are in. The final answer or packet "
        "must include assignments, member findings, disagreements, risks, a "
        "subagent scorecard, and a recommended next action. In the scorecard, "
        "rate each delegated member for this task only on a 1-5 scale for "
        "usefulness, evidence quality, relevance, and independence; include one "
        "objective sentence of rationale. Mark selected but non-dispatched members "
        "as not dispatched, and never present these scores as a global model "
        "ranking. Preserve real disagreement; do not treat a majority as truth "
        "when evidence is weak. If the request asks for implementation, produce "
        "an execution packet or ask before editing; this profile is for "
        "deliberation and dispatch. If a member output is truncated, re-dispatch "
        "only the missing sections and instruct the member not to repeat already "
        "received content. Do not assume a request-root workflow unless the user "
        "explicitly asks for that external workflow."
    )
    agents = {
        "committee-host": {
            "description": "General committee host that delegates to selected subagents and summarizes",
            "mode": "primary",
            "model": _agent_model("committee-host"),
            "variant": "high",
            "temperature": 0.1,
            "permission": _permission_for_agent(host_permission, _agent_policy("committee-host")),
            "prompt": _prompt_with_tool_policy(host_prompt, _agent_policy("committee-host")),
        },
        "committee-host-pro": {
            "description": "Higher-depth fallback committee host",
            "mode": "primary",
            "model": _agent_model("committee-host-pro"),
            "variant": "high",
            "temperature": 0.1,
            "permission": _permission_for_agent(host_permission, _agent_policy("committee-host-pro")),
            "prompt": _prompt_with_tool_policy(
                (
                    "Fallback committee host. Continue the same deliberation flow, "
                    "preserve selected members, re-read and obey target project local "
                    "instructions before dispatching, apply all committee decision "
                    "mode contracts (advisory, gate, estimate, review, and "
                    "execution_packet) plus the committee_policy fields "
                    "(decision_mode, playbook, artifact_mode, permission_profile), "
                    "preserve the same host boundary by default "
                    "(dispatch, verify, collect, tally, synthesize only), do not "
                    "write votes/<model>.vote.md, decision.md, or ratification "
                    "markers unless the user explicitly grants that artifact task, "
                    "do not promote advisory/chat ballots into formal quorum votes, "
                    "keep durable ballot provenance honest, include the same "
                    "separation from Debate semantics, include the same "
                    "task-local subagent scorecard, and summarize only "
                    "evidence-backed conclusions."
                ),
                _agent_policy("committee-host-pro"),
            ),
        },
    }

    def _member_prompt(name, model_ref):
        lower = f"{name} {model_ref}".lower()
        if "deepseek" in lower:
            focus = "deep reasoning, edge cases, algorithmic risk, and counterexamples"
        elif "glm" in lower:
            focus = "structured reasoning, Chinese technical nuance, and clear synthesis"
        elif "mimo" in lower:
            focus = "divergent critique, product risk, visual/multimodal concerns when present"
        elif "kimi" in lower or "k2" in lower:
            focus = "repo reading, context reconstruction, documentation, and codebase navigation"
        elif "minimax" in lower:
            focus = "pragmatic low-cost sanity checks, simple-path alternatives, and product feel"
        elif "5.5" in lower:
            focus = "highest-risk architecture, planning, and final-quality judgment"
        else:
            focus = "deep engineering judgment, implementation risk, and validation strategy"
        return (
            f"You are {name}, an independent committee member focused on {focus}. "
            "Obey target project local instructions and the host-assigned artifact "
            "contract; if those local rules require a durable formal artifact, write "
            "that artifact exactly as assigned. "
            "Follow the host-declared committee_policy, including decision_mode, "
            "playbook, artifact_mode, and permission_profile. Treat playbooks such "
            "as git_ci_security as evidence checklists, not as hidden decision "
            "modes. Do not use Debate behavior: no blind rounds, crossfire, "
            "stance-shift tracking, or debate resolution states. "
            "Read only what is needed first, do not call other agents, and do not "
            "edit files under the default readonly profile. If the host or user "
            "assigns artifact or implementation work, request the explicit scoped "
            "permission/profile escalation instead of assuming write authority. "
            "For Gate mode, return ballot fields: model, verdict "
            "(approve|reject|modify), veto (yes|no), cited evidence, and reason; "
            "if assigned a vote file path, write only your own assigned vote file "
            "and do not update decision.md, ratification markers, or any other "
            "member's vote file. "
            "For Estimate mode, return your estimate, confidence, evidence, and "
            "uncertainty. For Review mode, return findings ordered by severity, "
            "file/path references when available, missing validation, residual "
            "risk, and recommended fix or escalation; do not ratify approval from "
            "review mode alone. For Advisory mode, return concise findings, "
            "assumptions, evidence, disagreements with likely other models, and "
            "your recommended next action. For Execution Packet mode, provide "
            "objective, constraints, ordered tasks, validation, open questions, "
            "and non-goals without editing by default. Otherwise return concise "
            "findings, assumptions, evidence, disagreements with likely other "
            "models, and your recommended next action. "
            "For long structured outputs, write the assigned artifact instead of "
            "sending the full content through chat; return only path, compact "
            "summary, and blocked/missing sections. If asked to continue, resume "
            "at the next missing section and do not repeat prior content."
        )

    for name in member_names:
        roster_entry = roster_config.get(name) if isinstance(roster_config.get(name), dict) else {}
        model_ref = _agent_model(name)
        policy = _agent_policy(name)
        agents[name] = {
            "description": str(roster_entry.get("description") or f"Committee member {name}"),
            "mode": "subagent",
            "model": model_ref,
            "temperature": 0.1,
            "permission": _permission_for_agent(member_permission, policy),
            "prompt": _prompt_with_tool_policy(
                str(roster_entry.get("prompt") or _member_prompt(name, model_ref)),
                policy,
            ),
        }
    return agents


def opencode_debate_agent_configs(agent_models, *, roster_config=None, agent_policies=None):
    """Return a debate-only roster with host-authored v1 artifacts."""
    agent_models = agent_models if isinstance(agent_models, dict) else {}
    roster_config = roster_config if isinstance(roster_config, dict) else {}
    agent_policies = agent_policies if isinstance(agent_policies, dict) else {}
    host_model = (
        agent_models.get("debate-host")
        or agent_models.get("debate-host-pro")
        or next(iter(agent_models.values()), "")
    )
    if not host_model:
        return {}

    safe_read_bash = {
        "*": "ask",
        "pwd": "allow",
        "ls *": "allow",
        "rg *": "allow",
        "git status*": "allow",
        "git diff*": "allow",
        "git log*": "allow",
    }
    artifact_bash = {
        **safe_read_bash,
        "mkdir *": "ask",
        "cat *": "ask",
        "python*": "ask",
        "node *": "ask",
    }
    common_permissions = {
        "read": "allow",
        "grep": "allow",
        "glob": "allow",
        "list": "allow",
    }
    member_permission = {
        **common_permissions,
        "edit": "deny",
        "bash": safe_read_bash,
        "task": "deny",
        "webfetch": "ask",
        "websearch": "ask",
        "external_directory": "ask",
    }
    host_permission = {
        **common_permissions,
        "edit": "ask",
        "bash": artifact_bash,
        "task": {"*": "deny"},
        "webfetch": "ask",
        "websearch": "ask",
        "external_directory": "ask",
    }
    member_names = sorted(
        name for name in agent_models
        if str(name).startswith("debate-") and name not in {"debate-host", "debate-host-pro"}
    )
    for name in member_names:
        host_permission["task"][name] = "allow"

    def _agent_model(name, fallback=host_model):
        return str(agent_models.get(name) or fallback or host_model)

    def _merge_dict(base, override):
        merged = dict(base or {})
        for key, value in (override or {}).items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key] = _merge_dict(merged[key], value)
            else:
                merged[key] = value
        return merged

    def _agent_policy(name):
        policy = agent_policies.get(name) if isinstance(agent_policies.get(name), dict) else {}
        roster_entry = roster_config.get(name) if isinstance(roster_config.get(name), dict) else {}
        roster_policy = roster_entry.get("opencode_policy")
        if isinstance(roster_policy, dict):
            policy = _merge_dict(policy, roster_policy)
        return policy

    def _search_tools_fallback_only(policy):
        raw = str((policy or {}).get("builtin_search_tools") or "").strip().lower()
        return raw in {"disabled", "deny", "off", "shell", "shell_only", "fallback_only"}

    def _permission_for_agent(base_permission, policy):
        permission = copy.deepcopy(base_permission)
        if not _search_tools_fallback_only(policy):
            return permission
        for tool_name in ("grep", "glob", "list"):
            permission[tool_name] = "deny"
        bash_permission = permission.get("bash")
        if isinstance(bash_permission, dict):
            bash_permission = dict(bash_permission)
            bash_permission.update({
                "pwd": "allow",
                "ls *": "allow",
                "rg *": "allow",
            })
            permission["bash"] = bash_permission
        return permission

    def _prompt_with_tool_policy(prompt, policy):
        if not _search_tools_fallback_only(policy):
            return prompt
        return (
            f"{prompt} "
            "Tool policy: do not call built-in grep/glob/list for search or file "
            "listing on this route; use shell commands instead (`rg --files`, "
            "`rg -n`, `ls`, `pwd`; request `find` only when needed). If a "
            "built-in search tool returns a schema error, switch to shell fallback."
        )

    member_list_text = ", ".join(member_names) or "no debate-* subagents"
    host_prompt = (
        "You are debate-host for the MMS OpenCode debate profile. This profile is "
        "not committee, not review-hub, and not legacy discuss. Do not use "
        "committee vote files, committee verdict vocabulary, committee decision "
        "artifacts, review-hub request roots, or legacy mms discuss semantics. "
        "Use only the selected debate subagents available in this session: "
        f"{member_list_text}. Do not invent missing agents or model aliases. "
        "If the user has not supplied a concrete question, ask for one concise "
        "debate question and a decision boundary. Otherwise start immediately. "
        "Create one thread_id and write all durable output under "
        "`.ai/debate/<thread-id>/`. The v1 required files are `brief.md`, "
        "`state.json`, `round-1-seed.json`, `round-2-clusters.json`, "
        "`round-3-crossfire.json`, `round-4-revision.json`, `resolution.json`, "
        "and `resolution.md`. The host writes these artifacts directly; there is "
        "no helper command or validator program in v1. "
        "Run the v1 regulation mechanic: blind seed -> crossfire -> revision. "
        "First, send every selected member the same compact packet and require a "
        "blind seed with stance, claim, evidence, risks, recommended_path, "
        "confidence, pushback, quality_gate, and provenance. Do not expose other "
        "members' arguments during this first pass. Then write `round-2-clusters.json` "
        "as a host-owned clustering artifact with camps, strongest evidence, and "
        "open_conflicts. Next, run crossfire by giving each member only strongest "
        "opposing-case summaries, not full transcripts, and require "
        "opponent_strongest_point, my_rebuttal, what_i_accept, "
        "what_i_still_reject, what_evidence_would_change_my_mind, quality_gate, "
        "and provenance. Finally, request revision with final_stance, stance_shift "
        "(unchanged|softened|switched), shift_reason, confidence, quality_gate, "
        "and provenance. "
        "No extra time: never auto-append more crossfire rounds after the revision "
        "round. Golden-goal early stop is allowed only with deterministic triggers: "
        "positive when all valid final stances are in the same camp and at least "
        "one stance_shift is not unchanged; negative when crossfire shows every "
        "member's what_evidence_would_change_my_mind is empty or unreachable and "
        "there are at least two camps with high-confidence members. If an early "
        "stop happens, still write the required artifact files; for a negative "
        "stop after crossfire, write `round-4-revision.json` as a skipped revision "
        "artifact with unchanged final stances and the checkable stop reason. "
        "Record the stop reason in state and resolution. "
        "Before writing `resolution.json`, perform the required v1 self-check from "
        "`docs/DEBATE_STATE_RESULT_CONTRACT_v1.md` and "
        "`docs/DEBATE_HOST_RESOLUTION_RUBRIC_v1.md`: at least 2 valid members, "
        "all required resolution fields present, `converged` is mutually exclusive "
        "with `conclusion_opposite`, unresolved `fix_conflict`, and "
        "`deterministic_vs_opinion`, deterministic facts outrank model opinion, "
        "and missing required artifacts force `insufficient_evidence` with "
        "quality_gate=fail. Use the conservative priority order "
        "insufficient_evidence > split_human_required > converged > leaning. "
        "Always set `synthesis_strategy` to `host_authored` in v1 and record "
        "`synthesized_by` and `synthesis_attempted_by` honestly. Preserve minority "
        "pushback; never flatten disagreement into fake consensus. The final chat "
        "reply should be compact: resolution_state, quality_gate, recommended_next_step, "
        "key pushback, and artifact paths."
    )
    agents = {
        "debate-host": {
            "description": "Structured debate host that runs blind seed, crossfire, revision, and host-authored resolution",
            "mode": "primary",
            "model": _agent_model("debate-host"),
            "variant": "high",
            "temperature": 0.1,
            "permission": _permission_for_agent(host_permission, _agent_policy("debate-host")),
            "prompt": _prompt_with_tool_policy(host_prompt, _agent_policy("debate-host")),
        },
        "debate-host-pro": {
            "description": "Higher-depth fallback debate host",
            "mode": "primary",
            "model": _agent_model("debate-host-pro"),
            "variant": "high",
            "temperature": 0.1,
            "permission": _permission_for_agent(host_permission, _agent_policy("debate-host-pro")),
            "prompt": _prompt_with_tool_policy(
                (
                    "Fallback debate host. Continue the same debate thread, preserve "
                    "selected debate members, keep debate separate from committee, "
                    "write only `.ai/debate/<thread-id>/` artifacts, enforce the "
                    "fixed blind seed -> crossfire -> revision mechanic, apply the "
                    "v1 self-check checklist, use host_authored synthesis only, and "
                    "preserve real disagreement instead of claiming fake convergence."
                ),
                _agent_policy("debate-host-pro"),
            ),
        },
    }

    def _member_prompt(name, model_ref):
        lower = f"{name} {model_ref}".lower()
        if "deepseek" in lower:
            lens = "counterexamples, hidden failure modes, and hard technical objections"
        elif "glm" in lower:
            lens = "structured logic, Chinese technical nuance, and explicit tradeoffs"
        elif "mimo" in lower:
            lens = "divergent critique, product risk, and multimodal/visual concerns when present"
        elif "kimi" in lower or "k2" in lower:
            lens = "long-context reading, repo/document evidence, and source provenance"
        elif "minimax" in lower:
            lens = "pragmatic alternatives, low-cost paths, and user-facing product feel"
        elif "5.5" in lower:
            lens = "highest-risk architecture, adversarial planning, and final-quality judgment"
        else:
            lens = "independent engineering judgment, implementation risk, and validation strategy"
        return (
            f"You are {name}, an independent debate member focused on {lens}. "
            "You are not a committee voter and must not write committee vote files, "
            "decision.md, or ratification markers. Do not call other agents. Do not "
            "edit product/source files unless the user explicitly assigns a separate "
            "implementation task; normal debate outputs go back to debate-host. "
            "For blind seed, answer without considering other members: stance, claim, "
            "evidence, risks, recommended_path, confidence, pushback, quality_gate, "
            "and provenance. For crossfire, engage only the strongest opposing-case "
            "summary provided by the host and return opponent_strongest_point, "
            "my_rebuttal, what_i_accept, what_i_still_reject, "
            "what_evidence_would_change_my_mind, quality_gate, and provenance. "
            "For revision, return final_stance, stance_shift "
            "(unchanged|softened|switched), shift_reason, confidence, quality_gate, "
            "and provenance. Be willing to switch when evidence warrants it, but "
            "do not soften merely to create consensus. Separate deterministic facts "
            "from model opinion and name uncertainty plainly."
        )

    for name in member_names:
        roster_entry = roster_config.get(name) if isinstance(roster_config.get(name), dict) else {}
        model_ref = _agent_model(name)
        policy = _agent_policy(name)
        agents[name] = {
            "description": str(roster_entry.get("description") or f"Debate member {name}"),
            "mode": "subagent",
            "model": model_ref,
            "temperature": 0.1,
            "permission": _permission_for_agent(member_permission, policy),
            "prompt": _prompt_with_tool_policy(
                str(roster_entry.get("prompt") or _member_prompt(name, model_ref)),
                policy,
            ),
        }
    return agents


def opencode_permission_bypass_value(value):
    if isinstance(value, dict):
        return {
            str(key): opencode_permission_bypass_value(child)
            for key, child in value.items()
        }
    if isinstance(value, list):
        return [opencode_permission_bypass_value(item) for item in value]
    if isinstance(value, str) and value.strip().lower() == "ask":
        return "allow"
    return value


def opencode_apply_agent_bypass_permissions(agents):
    """Auto-approve explicit ask permissions while preserving deny boundaries."""
    if not isinstance(agents, dict):
        return agents
    updated = {}
    for name, agent in agents.items():
        if not isinstance(agent, dict):
            updated[name] = agent
            continue
        next_agent = dict(agent)
        if "permission" in next_agent:
            next_agent["permission"] = opencode_permission_bypass_value(next_agent.get("permission"))
        updated[name] = next_agent
    return updated


__all__ = [
    "opencode_apply_agent_bypass_permissions",
    "opencode_committee_agent_configs",
    "opencode_debate_agent_configs",
    "opencode_lite_agent_configs",
    "opencode_lite_pro_agent_configs",
    "opencode_permission_bypass_value",
    "opencode_review_hub_agent_configs",
]
