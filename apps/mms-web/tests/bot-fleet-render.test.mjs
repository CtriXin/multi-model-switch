import test from "node:test";
import assert from "node:assert/strict";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { registerHooks } from "node:module";
import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath, pathToFileURL } from "node:url";
import ts from "typescript";
import { dirname, join, resolve } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));

if (typeof globalThis.location === "undefined") {
  globalThis.location = { search: "", href: "http://127.0.0.1/" };
}

registerHooks({
  resolve(specifier, context, nextResolve) {
    if (context.parentURL && specifier.startsWith(".") && !/[.][a-z0-9]+$/i.test(specifier.split("/").pop() || "")) {
      const parent = dirname(fileURLToPath(context.parentURL));
      for (const ext of [".ts", ".tsx"]) {
        const candidate = join(parent, specifier + ext);
        if (existsSync(candidate)) {
          return { url: pathToFileURL(candidate).href, shortCircuit: true };
        }
      }
    }
    return nextResolve(specifier, context);
  },
  load(url, context, nextLoad) {
    if (url.endsWith(".css")) {
      return { format: "module", shortCircuit: true, source: "export default '';" };
    }
    if ((url.endsWith(".tsx") || url.endsWith(".ts")) && url.includes("/apps/mms-web/src/")) {
      const file = fileURLToPath(url);
      const raw = readFileSync(file, "utf8");
      const result = ts.transpileModule(raw, {
        compilerOptions: {
          jsx: ts.JsxEmit.ReactJSX,
          module: ts.ModuleKind.ESNext,
          target: ts.ScriptTarget.ES2022,
        },
        fileName: file,
      });
      return { format: "module", shortCircuit: true, source: result.outputText };
    }
    return nextLoad(url, context);
  },
});


test("Fleet proposed plans retain approval and rejection actions", async () => {
  const { BotPlan } = await import("../src/BotPlan.tsx");
  const html = renderToStaticMarkup(createElement(BotPlan, { bots: [], task: {
    id: "task-fleet", coordinatorPlan: { mode: "fleet", status: "proposed", steps: [
      { id: "a", kind: "fleet", family: "Kimi", label: "Kimi", status: "pending" },
      { id: "b", kind: "fleet", family: "GLM", label: "GLM", status: "pending" },
    ] },
  } }));
  assert.match(html, /<button[^>]*class="bot-plan-approve"/);
  assert.match(html, /确认，问问他们/);
  assert.match(html, /拒绝，自己做/);
});

test("Fleet keeps an unavailable family removable and offers automatic model recovery", async () => {
  const { BotFleetBar } = await import("../src/BotFleetBar.tsx");
  const { normalizeFleetPolicy } = await import("../src/bot-fleet.ts");
  const html = renderToStaticMarkup(createElement(BotFleetBar, {
    policy: normalizeFleetPolicy({families:["Kimi","GPT"], models:{Kimi:"old-id"}}),
    families:["Kimi"], presets:[{id:"replacement",name:"k3",family:"Kimi",harness:"pi",available:true}],
    onChange() {},
  }));
  assert.match(html, /GPT（已失效）/);
  assert.match(html, /Kimi（已失效）/);
  assert.match(html, /自动选择/);
});

test("same-name Fleet options show their channel", async () => {
  const { BotFleetBar } = await import("../src/BotFleetBar.tsx");
  const { normalizeFleetPolicy } = await import("../src/bot-fleet.ts");
  const html = renderToStaticMarkup(createElement(BotFleetBar, {
    policy: normalizeFleetPolicy(), families:["Kimi"],
    presets:["Alpha","Beta"].map(channel=>({id:channel,name:"k3",channel,family:"Kimi",harness:"pi",available:true})),
    onChange() {},
  }));
  assert.match(html, /k3 · Alpha/);
  assert.match(html, /k3 · Beta/);
});
