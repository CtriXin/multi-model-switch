import type { Plugin } from "@opencode-ai/plugin"

// Silent RTK plugin for MMS OpenCode sessions. Missing/failed rtk is pass-through.
export const RtkOpenCodePlugin: Plugin = async ({ $ }) => {
  try {
    await $`rtk --version`.quiet()
  } catch {
    return {}
  }

  return {
    "tool.execute.before": async (input, output) => {
      const tool = String(input?.tool ?? "").toLowerCase()
      if (tool !== "bash" && tool !== "shell") return
      const args = output?.args
      if (!args || typeof args !== "object") return

      const command = (args as Record<string, unknown>).command
      if (typeof command !== "string" || !command) return

      try {
        const result = await $`rtk rewrite ${command}`.quiet().nothrow()
        const rewritten = String(result.stdout).trim()
        if (rewritten && rewritten !== command) {
          ;(args as Record<string, unknown>).command = rewritten
        }
      } catch {
        // Keep hooks silent and fail-open for command execution.
      }
    },
  }
}
