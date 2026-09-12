#!/usr/bin/env node
/**
 * mms-vision-mcp
 *
 * 给「本身不支持图片输入」的主模型补上视觉能力，面向说 MCP 的 harness
 * （Claude Code、OpenCode）。Pi 用的是它自己的扩展，两边的候选池规则一致：
 * 池子来自当前通道里实际被判定为能读图的模型，没有内置模型名单。
 *
 * 输入只有一个环境变量 MMS_VISION_RELAY_CONFIG，指向 mmf 写好的 models.json
 * （结构与 Pi 的完全一样）。凭据只出现在请求头里，不进工具返回、不进日志。
 *
 * 协议：MCP stdio，逐行 JSON-RPC 2.0。
 */
import fs from "node:fs";
import path from "node:path";

const PROTOCOL_VERSION = "2024-11-05";
const SERVER_INFO = { name: "mms-vision", version: "1.0.0" };

const MIME_BY_EXT = {
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".gif": "image/gif",
  ".webp": "image/webp",
  ".bmp": "image/bmp",
};

function readJson(file) {
  try {
    return JSON.parse(fs.readFileSync(file, "utf8"));
  } catch {
    return null;
  }
}

function trimTrailingSlash(s) {
  return typeof s === "string" ? s.replace(/\/+$/, "") : s;
}

// 每次识图重新洗牌：池子里的模型地位相同，没有内置优先级。
function shuffled(items) {
  const copy = [...items];
  for (let i = copy.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [copy[i], copy[j]] = [copy[j], copy[i]];
  }
  return copy;
}

function buildEndpoint(api, baseUrl) {
  const b = trimTrailingSlash(baseUrl);
  if (api === "anthropic-messages") return `${b}/v1/messages`;
  if (api === "openai-completions")
    return b.endsWith("/v1") ? `${b}/chat/completions` : `${b}/v1/chat/completions`;
  if (api === "openai-responses")
    return b.endsWith("/v1") ? `${b}/responses` : `${b}/v1/responses`;
  return null;
}

// 池子 = 这份 catalog 里 input 含 image、且 provider 有 key 的模型。
function buildPool(models) {
  const pool = [];
  for (const [provider, prov] of Object.entries(models?.providers || {})) {
    const list = Array.isArray(prov?.models) ? prov.models : [];
    for (const m of list) {
      if (!m?.id || !Array.isArray(m.input) || !m.input.includes("image")) continue;
      if (!prov.apiKey) continue;
      const endpoint = buildEndpoint(prov.api, prov.baseUrl);
      if (endpoint) pool.push({ provider, api: prov.api, endpoint, apiKey: prov.apiKey, modelId: m.id });
    }
  }
  return pool;
}

async function callAnthropic(endpoint, key, model, b64, mime, question) {
  const res = await fetch(endpoint, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "x-api-key": key,
      authorization: `Bearer ${key}`,
      "anthropic-version": "2023-06-01",
    },
    signal: AbortSignal.timeout(60000),
    body: JSON.stringify({
      model,
      max_tokens: 1024,
      messages: [
        {
          role: "user",
          content: [
            { type: "text", text: question },
            { type: "image", source: { type: "base64", media_type: mime, data: b64 } },
          ],
        },
      ],
    }),
  });
  const j = await res.json().catch(() => ({}));
  const text = Array.isArray(j?.content)
    ? j.content.map((c) => c?.text).filter(Boolean).join("\n").trim()
    : "";
  if (!res.ok || !text) {
    return { ok: false, error: `HTTP ${res.status} ${JSON.stringify(j?.error || j).slice(0, 200)}` };
  }
  return { ok: true, text };
}

// 两个流式协议只有「文本增量在哪一个字段」不同，共用一个读流函数。
async function readSseText(res, pick) {
  if (!res.ok || !res.body) {
    const t = await res.text().catch(() => "");
    return { ok: false, error: `HTTP ${res.status} ${t.slice(0, 200)}` };
  }
  const reader = res.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  let text = "";
  let streamErr = null;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let idx;
    while ((idx = buf.indexOf("\n")) >= 0) {
      const line = buf.slice(0, idx).trim();
      buf = buf.slice(idx + 1);
      if (!line.startsWith("data:")) continue;
      const d = line.slice(5).trim();
      if (d === "" || d === "[DONE]") continue;
      try {
        const o = JSON.parse(d);
        if (o.error) {
          streamErr = JSON.stringify(o.error).slice(0, 200);
          break;
        }
        text += pick(o) || "";
      } catch {
        // 单行解析失败跳过
      }
    }
    if (streamErr) break;
  }
  text = text.trim();
  if (streamErr) return { ok: false, error: streamErr };
  if (!text) return { ok: false, error: "empty stream content" };
  return { ok: true, text };
}

async function callOpenAIChat(endpoint, key, model, b64, mime, question) {
  // 统一 stream:true —— 部分通道对新模型强制要求流式，其它模型也兼容。
  const res = await fetch(endpoint, {
    method: "POST",
    headers: { "content-type": "application/json", authorization: `Bearer ${key}` },
    signal: AbortSignal.timeout(90000),
    body: JSON.stringify({
      model,
      max_tokens: 1024,
      stream: true,
      messages: [
        {
          role: "user",
          content: [
            { type: "text", text: question },
            { type: "image_url", image_url: { url: `data:${mime};base64,${b64}` } },
          ],
        },
      ],
    }),
  });
  return readSseText(res, (o) => (o.choices || []).map((ch) => ch?.delta?.content).filter((c) => typeof c === "string").join(""));
}

async function callOpenAIResponses(endpoint, key, model, b64, mime, question) {
  const res = await fetch(endpoint, {
    method: "POST",
    headers: { "content-type": "application/json", authorization: `Bearer ${key}` },
    signal: AbortSignal.timeout(90000),
    body: JSON.stringify({
      model,
      stream: true,
      input: [
        {
          role: "user",
          content: [
            { type: "input_text", text: question },
            { type: "input_image", image_url: `data:${mime};base64,${b64}` },
          ],
        },
      ],
    }),
  });
  return readSseText(res, (o) => (typeof o.delta === "string" ? o.delta : ""));
}

async function callByApi(api, endpoint, key, model, b64, mime, question) {
  if (api === "anthropic-messages") return callAnthropic(endpoint, key, model, b64, mime, question);
  if (api === "openai-completions") return callOpenAIChat(endpoint, key, model, b64, mime, question);
  if (api === "openai-responses") return callOpenAIResponses(endpoint, key, model, b64, mime, question);
  return { ok: false, error: `unsupported api: ${api}` };
}

export async function describeImage(pool, imgPath, question) {
  if (!imgPath || !fs.existsSync(imgPath)) {
    return { ok: false, text: `Error: image file not found: ${imgPath}` };
  }
  const b64 = fs.readFileSync(imgPath).toString("base64");
  const mime = MIME_BY_EXT[path.extname(imgPath).toLowerCase()] || "image/png";
  const tried = [];
  for (const v of shuffled(pool)) {
    const r = await callByApi(v.api, v.endpoint, v.apiKey, v.modelId, b64, mime, question);
    if (r.ok) return { ok: true, text: `[vision via ${v.modelId}]\n${r.text}` };
    tried.push(`${v.modelId} (${v.api}): ${r.error}`);
  }
  return {
    ok: false,
    text: `Every vision-capable model on this channel failed.\nAttempts:\n${tried.map((t) => "- " + t).join("\n")}`,
  };
}

const TOOL = {
  name: "describe_image",
  description:
    "Analyze an image file (screenshot, photo, diagram, chart, UI, error popup, sketch) and return a TEXT description. " +
    "Use this ONLY when you need visual understanding and the current model cannot see images natively. " +
    "Do not call it for code, plain text, configs or logs; read those directly. " +
    "Pass a local file path, not a URL. Returns text, not pixels.",
  inputSchema: {
    type: "object",
    properties: {
      path: {
        type: "string",
        description:
          "Local file path to the image (png/jpg/jpeg/gif/webp/bmp). Relative paths resolve against the current working directory.",
      },
      question: {
        type: "string",
        description:
          "What to extract from the image. Defaults to a thorough general description. " +
          "Examples: 'Read all text verbatim', 'Describe the layout', 'What error is shown and how to fix it'.",
      },
    },
    required: ["path"],
  },
};

function send(message) {
  process.stdout.write(JSON.stringify(message) + "\n");
}

function reply(id, result) {
  if (id === undefined || id === null) return;
  send({ jsonrpc: "2.0", id, result });
}

function replyError(id, code, message) {
  if (id === undefined || id === null) return;
  send({ jsonrpc: "2.0", id, error: { code, message } });
}

export function loadPool(configPath) {
  const models = configPath ? readJson(configPath) : null;
  return models?.providers ? buildPool(models) : [];
}

async function handle(message, pool) {
  const { id, method, params } = message || {};
  if (method === "initialize") {
    reply(id, {
      protocolVersion: params?.protocolVersion || PROTOCOL_VERSION,
      capabilities: { tools: {} },
      serverInfo: SERVER_INFO,
    });
    return;
  }
  if (method === "notifications/initialized" || method === "notifications/cancelled") return;
  if (method === "ping") return reply(id, {});
  if (method === "tools/list") return reply(id, { tools: [TOOL] });
  if (method === "tools/call") {
    if (params?.name !== TOOL.name) return replyError(id, -32602, `unknown tool: ${params?.name}`);
    const args = params?.arguments || {};
    const question =
      (args.question && String(args.question).trim()) ||
      "Describe this image in detail: visible text (verbatim), layout, colors, and notable elements.";
    try {
      const result = await describeImage(pool, args.path, question);
      return reply(id, { content: [{ type: "text", text: result.text }], isError: !result.ok });
    } catch (e) {
      return reply(id, {
        content: [{ type: "text", text: `describe_image error: ${e?.message || e}` }],
        isError: true,
      });
    }
  }
  replyError(id, -32601, `method not found: ${method}`);
}

function main() {
  const pool = loadPool(process.env.MMS_VISION_RELAY_CONFIG);
  let buffer = "";
  let pending = 0;
  let ended = false;
  // A relayed image takes seconds. Closing stdin must not cut the answer off
  // before it is written, so only leave once nothing is in flight.
  const finishIfIdle = () => {
    if (ended && pending === 0) process.exit(0);
  };
  process.stdin.setEncoding("utf8");
  process.stdin.on("data", (chunk) => {
    buffer += chunk;
    let index;
    while ((index = buffer.indexOf("\n")) >= 0) {
      const line = buffer.slice(0, index).trim();
      buffer = buffer.slice(index + 1);
      if (!line) continue;
      let message;
      try {
        message = JSON.parse(line);
      } catch {
        continue;
      }
      pending += 1;
      void handle(message, pool).finally(() => {
        pending -= 1;
        finishIfIdle();
      });
    }
  });
  process.stdin.on("end", () => {
    ended = true;
    finishIfIdle();
  });
}

if (process.argv[1] && import.meta.url.endsWith(path.basename(process.argv[1]))) main();
