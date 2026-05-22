import type { Plugin } from "@opencode-ai/plugin"

// Silent xmem bootstrap for MMS OpenCode sessions. Missing xmem is pass-through.
export const XmemOpenCodePlugin: Plugin = async ({ $ }) => {
  try {
    await $`xmem hook start`.quiet().nothrow()
  } catch {
    // Keep plugin startup fail-open.
  }

  return {}
}
