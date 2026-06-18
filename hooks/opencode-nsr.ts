// EXPERIMENTAL — OpenCode NSR (Non-Stop-Run) auto-continue.
//
// codex/claude implement NSR as a *Stop hook* that returns {decision:block} to
// keep the agent running while a loop has a next_action. OpenCode's plugin API
// has no stop-block hook, so this uses the only mechanism available:
//   listen for the `session.idle` bus event  ->  ask the SAME NSR decision
//   (hooks/nsr-builtin-hook.py, reused, not reimplemented)  ->  if it says
//   "block", re-prompt the session via client.session.prompt() to continue.
//
// SAFETY (this is a different, re-prompt-based mechanism with runaway risk):
//   - Opt-in only: inert unless MMS_OPENCODE_NSR=1 (the MMS overlay also gates it
//     off by default). Never auto-continues a session the user didn't enable.
//   - Hard per-session cap (MAX_AUTO_CONTINUE) on TOP of NSR's own repeat-guard,
//     so a decision bug cannot loop forever.
//   - Fail-open: any error / missing hook / unknown shape => do nothing.
//
// NOT YET VERIFIED in a live OpenCode session. The exact shapes below are best
// effort from the SDK type defs and MUST be confirmed live before enabling:
//   - the `session.idle` event field carrying the session id,
//   - the client.session.prompt() request body,
//   - MMS_HOME being present in the OpenCode process env.
import { existsSync } from "node:fs"
import type { Plugin } from "@opencode-ai/plugin"

const MAX_AUTO_CONTINUE = 4
const autoContinues = new Map<string, number>()

function nsrHookPath(): string {
  // The OpenCode child env does NOT carry MMS_HOME (confirmed in committee review),
  // so resolve the hook next to this plugin's own real file first: the overlay
  // symlinks mms-nsr.ts -> <mms>/hooks/opencode-nsr.ts, whose sibling is the hook.
  // Fall back to explicit env only when the plugin was copied, not symlinked.
  const candidates: string[] = []
  try {
    const dir = (import.meta as { dir?: string }).dir
    if (dir) candidates.push(`${dir}/nsr-builtin-hook.py`)
  } catch {
    // import.meta.dir unavailable; rely on env fallbacks below.
  }
  const explicit = process.env.MMS_OPENCODE_NSR_HOOK
  if (explicit) candidates.push(explicit)
  const home = process.env.MMS_HOME || process.env.MMS_REAL_HOME
  if (home) candidates.push(`${home}/hooks/nsr-builtin-hook.py`)
  for (const candidate of candidates) {
    try {
      if (existsSync(candidate)) return candidate
    } catch {
      // ignore and try the next candidate
    }
  }
  return ""
}

export const NsrOpenCodePlugin: Plugin = async ({ $, client, directory }) => {
  // Opt-in + reachable hook are hard preconditions; otherwise stay completely inert.
  if (process.env.MMS_OPENCODE_NSR !== "1") return {}
  const hook = nsrHookPath()
  if (!hook) return {}

  return {
    event: async ({ event }) => {
      try {
        const ev = event as { type?: string; properties?: Record<string, unknown> }
        if (!ev || ev.type !== "session.idle") return
        const props = ev.properties || {}
        const sessionID = String(props.sessionID || props.sessionId || props.session_id || "")
        if (!sessionID) return

        const used = autoContinues.get(sessionID) || 0
        if (used >= MAX_AUTO_CONTINUE) return // runaway backstop

        // Reuse the exact NSR decision used for claude/codex (Stop event contract).
        // KNOWN (committee finding, needs live design): a bare synthesized "Stop"
        // can trip NSR's builtin repeat-guard (identical signature -> allowed after
        // STOP_BLOCK_REPEAT_LIMIT), so the local MAX_AUTO_CONTINUE cap above is the
        // effective budget. `host` lets a future NSR build special-case opencode.
        const payload = JSON.stringify({
          hook_event_name: "Stop",
          host: "opencode",
          session_id: sessionID,
          cwd: directory || "",
        })
        const res = await $`echo ${payload} | python3 ${hook} opencode`.quiet().nothrow()
        const out = (res && res.stdout ? res.stdout.toString() : "").trim()
        if (!out) return

        let decision: { decision?: string; reason?: string; continue?: boolean }
        try {
          decision = JSON.parse(out)
        } catch {
          return
        }
        if (decision.decision !== "block" || !decision.reason) return // allow stop

        autoContinues.set(sessionID, used + 1)
        // Re-prompt to continue. Body shape is best-effort; verify live.
        await client.session.prompt({
          path: { id: sessionID },
          body: { parts: [{ type: "text", text: String(decision.reason) }] },
        } as never)
      } catch {
        // fail-open: never break an OpenCode turn
      }
    },
  }
}

export default NsrOpenCodePlugin
