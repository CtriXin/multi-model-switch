/** Optional Web session controls. Disabled by default; no host configuration writes. */
export default function (pi: any) {
  let planning = false;
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
    description: "MMS Web 的只读规划开关",
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
  pi.on("before_agent_start", async (event: any) => {
    if (planning) return {systemPrompt:event.systemPrompt + "\n当前用户选择了只读规划模式。先阅读必要资料并给出方案；不要写入文件、执行 shell 或调用其他会产生副作用的工具。只有用户通过 Web 控件切换到执行模式后才能执行。"};
  });
}
