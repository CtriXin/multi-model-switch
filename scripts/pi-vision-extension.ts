/**
 * pi-vision-extension
 *
 * 给「本身不支持图片输入」的主模型补上视觉能力。
 * 主模型按需调用 describe_image 工具 -> 工具内部把图片转发给当前 pi 配置里
 * 任意一个标了能读图的模型，把它返回的纯文字回灌给主模型。主模型全程不碰像素。
 * 候选池来自实际配置的 vision 能力，没有内置模型名单；每次取用随机排序，
 * 失败再依次降级。
 *
 * 设计要点：
 *  - 双启动兼容：优先 PI_CODING_AGENT_DIR（mmf 注入），回退 ~/.pi/agent（原生 pi）。
 *  - 零硬编码：模型池、base_url、apiKey、协议全部运行时动态发现。
 *  - 多模态主模型自动不注册：若当前主模型 input 含 image，直接 return，主模型自己用 read 看图。
 *  - 按需：promptGuidelines 明确「只有需要视觉理解才调用」，非图片/文本文件走 read。
 *  - 凭证安全：apiKey 仅在请求头使用，绝不进入工具返回或日志。
 */

import { Type } from "typebox";
import fs from "node:fs";
import path from "node:path";
import os from "node:os";

// 候选池。mmf 启动时按「这个模型是否真的能读图」算好，通过
// MMS_PI_VISION_POOL 传进来；原生 pi 直接启动时没有这个变量，就从 models.json
// 里挑 input 含 image 的模型。两条路都不含写死的模型名。
function visionPool(models) {
  const injected = process.env.MMS_PI_VISION_POOL;
  if (injected) {
    try {
      const parsed = JSON.parse(injected);
      // 空数组是「算过了，本通道没有能读图的模型」，不是「没算」。
      if (Array.isArray(parsed))
        return parsed.filter((m) => typeof m === "string" && m.trim());
    } catch {
      // 变量损坏时不猜，退回扫描 models.json。
    }
  }
  const found = [];
  for (const prov of Object.values(models?.providers || {})) {
    for (const m of Array.isArray(prov.models) ? prov.models : []) {
      if (m?.id && Array.isArray(m.input) && m.input.includes("image"))
        found.push(m.id);
    }
  }
  return found;
}

// 每次识图重新洗牌，让请求分散到池子里的所有模型上。
function shuffled(items) {
  const copy = [...items];
  for (let i = copy.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [copy[i], copy[j]] = [copy[j], copy[i]];
  }
  return copy;
}

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

// 在 models.json 里查找某个 modelId 挂在哪个 provider 下
function findModelProvider(models, modelId) {
  if (!models?.providers) return null;
  for (const [provider, prov] of Object.entries(models.providers)) {
    const ms = Array.isArray(prov.models) ? prov.models : [];
    if (ms.some((m) => m && m.id === modelId)) {
      return {
        provider,
        api: prov.api,
        baseUrl: prov.baseUrl,
        apiKey: prov.apiKey,
        modelId,
      };
    }
  }
  return null;
}

// 查某个 modelId 的 input 声明（判断多模态）
function findModelInput(models, modelId) {
  if (!models?.providers) return null;
  for (const prov of Object.values(models.providers)) {
    const ms = Array.isArray(prov.models) ? prov.models : [];
    const m = ms.find((x) => x && x.id === modelId);
    if (m) return Array.isArray(m.input) ? m.input : ["text"];
  }
  return null;
}

// 根据 provider api 类型构造 endpoint
function buildEndpoint(api, baseUrl) {
  const b = trimTrailingSlash(baseUrl);
  if (api === "anthropic-messages") return `${b}/v1/messages`;
  if (api === "openai-completions")
    return b.endsWith("/v1") ? `${b}/chat/completions` : `${b}/v1/chat/completions`;
  if (api === "openai-responses")
    return b.endsWith("/v1") ? `${b}/responses` : `${b}/v1/responses`;
  return null;
}

// ---- 三种协议调用，统一返回 { ok, text, error } ----

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

async function callOpenAIChat(endpoint, key, model, b64, mime, question) {
  // 统一 stream:true —— CRS 通道对 gpt-5.5 强制要求 stream，其它模型也兼容流式
  const res = await fetch(endpoint, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      authorization: `Bearer ${key}`,
    },
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
        for (const ch of o.choices || []) {
          const c = ch?.delta?.content;
          if (typeof c === "string") text += c;
        }
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

async function callOpenAIResponses(endpoint, key, model, b64, mime, question) {
  // CRS 通道的 responses 协议同样强制 stream:true
  const res = await fetch(endpoint, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      authorization: `Bearer ${key}`,
    },
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
        // responses 流式：文本增量在 type=response.output_text.delta 的 o.delta
        if (typeof o.delta === "string") text += o.delta;
      } catch {
        // 单行解析失败跳过
      }
    }
    if (streamErr) break;
  }
  text = text.trim();
  if (streamErr) return { ok: false, error: streamErr };
  if (!text) return { ok: false, error: "empty responses stream content" };
  return { ok: true, text };
}

async function callByApi(api, endpoint, key, model, b64, mime, question) {
  if (api === "anthropic-messages") return callAnthropic(endpoint, key, model, b64, mime, question);
  if (api === "openai-completions") return callOpenAIChat(endpoint, key, model, b64, mime, question);
  if (api === "openai-responses") return callOpenAIResponses(endpoint, key, model, b64, mime, question);
  return { ok: false, error: `unsupported api: ${api}` };
}

export default async function (pi) {
  const piDir = process.env.PI_CODING_AGENT_DIR || path.join(os.homedir(), ".pi", "agent");
  const modelsFile = path.join(piDir, "models.json");
  const settingsFile = path.join(piDir, "settings.json");
  const models = readJson(modelsFile);
  if (!models?.providers) {
    // 当前 pi 无 provider 配置，静默不注册
    return;
  }

  // 主模型是否多模态。mmf 用 --model 启动 pi，扩展看不到这个参数，所以由
  // mmf 在启动前用统一的能力真值算好结果注入；原生 pi 才退回自己查 models.json。
  const injectedVision = process.env.MMS_PI_MAIN_MODEL_VISION;
  if (injectedVision === "1") {
    // 主模型自己能看图，不注册本工具。
    return;
  }
  if (injectedVision !== "0") {
    const settings = readJson(settingsFile) || {};
    const currentModel =
      process.env.MMS_PI_SELECTED_MODEL || process.env.PI_MODEL || settings.defaultModel;
    if (currentModel) {
      const input = findModelInput(models, currentModel);
      if (input && input.includes("image")) {
        return;
      }
    }
  }

  // 构建候选池（只保留 models.json 里能找到 provider 且有 key 的）
  const pool = [];
  for (const m of visionPool(models)) {
    const p = findModelProvider(models, m);
    if (p && p.apiKey) {
      const endpoint = buildEndpoint(p.api, p.baseUrl);
      if (endpoint) pool.push({ ...p, endpoint });
    }
  }
  if (pool.length === 0) {
    // 本通道没有能读图的模型，不注册
    return;
  }

  pi.registerTool({
    name: "describe_image",
    label: "Describe Image",
    description:
      "Analyze an image file (screenshot, photo, diagram, chart, UI, error popup, sketch) and return a TEXT description. " +
      "Use this ONLY when you need visual understanding and the current model cannot see images natively. " +
      "Pass a local file path; do not pass URLs. Returns text, not pixels.",
    promptSnippet:
      "Relay image to a configured vision-capable model when the main model has no image input",
    promptGuidelines: [
      "Call describe_image ONLY for genuine visual content: screenshots, photos, diagrams, charts, UI captures, error popups, sketches.",
      "Do NOT call it for code, plain text, configs, logs, or any file whose content is text — use the read tool instead.",
      "If the main model already supports image input (multimodal), do not call this tool; read the image directly.",
      "Pass a precise `question` (e.g. 'Read all visible text', 'Describe the UI layout and colors', 'Diagnose the error in this screenshot').",
    ],
    parameters: Type.Object({
      path: Type.String({
        description: "Local file path to the image (png/jpg/jpeg/gif/webp/bmp). Relative paths resolve against the current working directory.",
      }),
      question: Type.Optional(
        Type.String({
          description:
            "What to extract from the image. Defaults to a thorough general description. " +
            "Examples: 'Read all text verbatim', 'Describe the layout', 'What error is shown and how to fix it'.",
        })
      ),
    }),
    async execute(_toolCallId, params, _signal) {
      const imgPath = params?.path;
      const question =
        (params?.question && String(params.question).trim()) ||
        "Describe this image in detail: visible text (verbatim), layout, colors, and notable elements.";
      try {
        if (!imgPath || !fs.existsSync(imgPath)) {
          return {
            content: [{ type: "text", text: `Error: image file not found: ${imgPath}` }],
            details: { ok: false },
          };
        }
        const buf = fs.readFileSync(imgPath);
        const b64 = buf.toString("base64");
        const ext = path.extname(imgPath).toLowerCase();
        const mime = MIME_BY_EXT[ext] || "image/png";

        const tried = [];
        // 随机顺序：池子里的模型地位相同，没有内置优先级。
        for (const v of shuffled(pool)) {
          const r = await callByApi(v.api, v.endpoint, v.apiKey, v.modelId, b64, mime, question);
          if (r.ok) {
            return {
              content: [{ type: "text", text: `[vision via ${v.modelId}]\n${r.text}` }],
              details: { ok: true, model: v.modelId, provider: v.provider, tried },
            };
          }
          tried.push(`${v.modelId} (${v.api}): ${r.error}`);
        }
        return {
          content: [
            {
              type: "text",
              text: `Every vision-capable model on this channel failed.\nAttempts:\n${tried.map((t) => "- " + t).join("\n")}`,
            },
          ],
          details: { ok: false, tried },
        };
      } catch (e) {
        return {
          content: [{ type: "text", text: `describe_image error: ${e?.message || e}` }],
          details: { ok: false },
        };
      }
    },
  });
}
