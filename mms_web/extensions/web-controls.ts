import { createHash } from "node:crypto";
import { realpathSync } from "node:fs";
/** Optional Web session controls. Disabled by default; no host configuration writes. */
export default function (pi: any) {
  let planning = false;
  const hash = (text: string) => createHash("sha256").update(text).digest("hex");
  const realPath = (path: string) => { try { return realpathSync(path); } catch { return path; } };
  const skillInputs: { name: string; hash: string }[] = [];
  pi.on("input", async (event: any) => {
    const name = /^\/skill:([^\s]+)(?: |$)/.exec(event.text)?.[1];
    if (name) { skillInputs.push({name, hash: hash(event.text)}); if (skillInputs.length > 32) skillInputs.shift(); }
  });
  const readonly = new Set(["read", "grep", "find", "ls"]);
  const publish = (ctx: any) => ctx.ui.notify("MMS_WEB_STATE:" + JSON.stringify({planning}), "info");
  pi.on("session_start", async (_event: any, ctx: any) => {
    planning = false;
    for (const entry of ctx.sessionManager.getBranch()) {
      if (entry.type === "custom" && entry.customType === "mms-web-mode") planning = entry.data?.planning === true;
    }
    publish(ctx);
  });
  pi.registerCommand("mms-web-plan", {
    description: "MMS Pilot 的只读规划开关",
    handler: async (args: string, ctx: any) => {
      if (args !== "on" && args !== "off") {publish(ctx); return}
      planning = args === "on";
      pi.appendEntry("mms-web-mode", {planning});
      publish(ctx);
    },
  });
  pi.on("tool_call", async (event: any) => {
    if (planning && !readonly.has(event.toolName)) {
      return {block:true, reason:"当前为只读规划模式，只允许 read、grep、find、ls。请先给出方案，等待用户在网页切换到执行模式。"};
    }
  });
  pi.on("before_agent_start", async (event: any, ctx: any) => {
    const options = event.systemPromptOptions;
    const rules = Array.isArray(options?.contextFiles) ? options.contextFiles : [];
    const skills = Array.isArray(options?.skills) ? options.skills : [];
    const command = skills.find((s: any) => event.prompt.startsWith(`<skill name="${s.name}" location="${s.filePath}">`));
    const inputs = command ? skillInputs.filter(s => s.name === command.name) : [];
    // Ambiguous queued expansions stay uncorrelated rather than attributed to a wrong turn.
    const source = inputs.length === 1 ? inputs[0].hash : undefined;
    skillInputs.length = 0;
    ctx.ui.notify("MMS_WEB_CONTEXT:" + JSON.stringify({
      version: 1, available: !!options, promptSha256: hash(event.prompt), sourcePromptSha256: source,
      systemPromptSha256: hash(event.systemPrompt), truncated: rules.length > 200 || skills.length > 200,
      rules: rules.slice(0, 200).map((r: any) => ({path: String(r.path).slice(0, 2048), sha256: hash(r.content), source: "Pi contextFiles"})),
      skills: skills.slice(0, 200).map((s: any) => ({name: s.name, path: String(s.filePath).slice(0, 2048),
        sourcePath: realPath(s.filePath).slice(0, 2048), source: s.sourceInfo?.scope || "Pi skills", listed: !s.disableModelInvocation && event.systemPrompt.includes(s.filePath),
        invoked: !!source && command === s})),
    }), "info");
    if (planning) return {systemPrompt:event.systemPrompt + "\n当前用户选择了只读规划模式。先阅读必要资料并给出方案；不要写入文件、执行 shell 或调用其他会产生副作用的工具。只有用户通过 Web 控件切换到执行模式后才能执行。"};
  });
}
