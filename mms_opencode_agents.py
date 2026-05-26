"""OpenCode session-local agent roster helpers."""

from __future__ import annotations


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


def opencode_lite_pro_agent_configs(agent_models, *, orchestrated=False):
    """Return deterministic Lite Pro roster with named fallback agents."""
    agent_models = agent_models if isinstance(agent_models, dict) else {}
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
        agents.update({
            "mobius-executor-gpt54": {
                "description": "Lite Pro long-running GPT implementation executor",
                "mode": "subagent",
                "model": _agent_model("mobius-executor-gpt54", _agent_model("mobius-builder-stable")),
                "variant": "high",
                "temperature": 0.2,
                "permission": fix_permission,
                "prompt": "Primary implementation executor. " + executor_prompt,
            },
        })
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
    "opencode_lite_agent_configs",
    "opencode_lite_pro_agent_configs",
    "opencode_permission_bypass_value",
]
