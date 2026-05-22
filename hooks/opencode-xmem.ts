import type { Plugin } from "@opencode-ai/plugin"

declare const process: {
  once(event: "beforeExit", listener: () => void): void
}

// Silent xmem bootstrap for MMS OpenCode sessions. Missing xmem is pass-through.
export const XmemOpenCodePlugin: Plugin = async ({ $ }) => {
  try {
    await $`xmem hook start`.quiet().nothrow()
  } catch {
    // Keep plugin startup fail-open.
  }

  let closed = false
  const close = async () => {
    if (closed) return
    closed = true
    try {
      await $`xmem hook finish`.quiet().nothrow()
    } catch {
      // Keep plugin shutdown fail-open and silent.
    }
  }

  process.once("beforeExit", () => {
    void close()
  })

  return {}
}
