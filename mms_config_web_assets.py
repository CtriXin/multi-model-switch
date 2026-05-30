"""Static HTML/JS assets for the MMS config WebUI."""

from __future__ import annotations


_HTML_PAGE = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>MMS 配置中心</title>
  <style>
    :root {
      --bg:      oklch(96.5% 0.012 210);
      --surface: oklch(100% 0 0);
      --fg:      oklch(15% 0.02 230);
      --muted:   oklch(46% 0.02 230);
      --border:  oklch(86% 0.012 220);
      --accent:  oklch(54% 0.14 157);

      --ok:      oklch(55% 0.14 145);
      --warn:    oklch(68% 0.11 80);
      --danger:  oklch(55% 0.18 25);

      --accent-soft:  color-mix(in oklch, var(--accent) 10%, transparent);
      --accent-hover: color-mix(in oklch, var(--accent) 80%, black);
      --fg-soft:      color-mix(in oklch, var(--fg) 5%, transparent);
      --fg-ghost:     color-mix(in oklch, var(--fg) 8%, transparent);
      --ok-soft:      color-mix(in oklch, var(--ok) 12%, transparent);
      --warn-soft:    color-mix(in oklch, var(--warn) 12%, transparent);
      --danger-soft:  color-mix(in oklch, var(--danger) 12%, transparent);

      --shadow-sm: 0 1px 2px oklch(0% 0 0 / 0.04);
      --shadow:    0 1px 3px oklch(0% 0 0 / 0.06), 0 1px 2px oklch(0% 0 0 / 0.04);
      --shadow-md: 0 4px 6px -1px oklch(0% 0 0 / 0.05), 0 2px 4px -2px oklch(0% 0 0 / 0.04);
      --shadow-lg: 0 10px 15px -3px oklch(0% 0 0 / 0.05), 0 4px 6px -4px oklch(0% 0 0 / 0.03);

      --font-body: 'Aptos', 'Geist', 'IBM Plex Sans', 'Noto Sans SC', ui-sans-serif, sans-serif;
      --font-mono: 'JetBrains Mono', 'IBM Plex Mono', ui-monospace, Menlo, monospace;

      --radius:    10px;
      --radius-lg: 14px;
      --radius-xl: 18px;

      --gap-xs: 6px;
      --gap-sm: 10px;
      --gap-md: 16px;
      --gap-lg: 24px;
      --gap-xl: 32px;
    }

    *, *::before, *::after { box-sizing: border-box; }
    html { -webkit-text-size-adjust: 100%; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--fg);
      font-family: var(--font-body);
      font-size: 14px;
      line-height: 1.55;
      text-rendering: optimizeLegibility;
      -webkit-font-smoothing: antialiased;
      min-height: 100vh;
      overflow-x: clip;
      background:
        radial-gradient(circle at 18% -8%, oklch(88% 0.055 164 / 0.46), transparent 31rem),
        radial-gradient(circle at 92% 10%, oklch(82% 0.035 230 / 0.32), transparent 28rem),
        linear-gradient(180deg, oklch(98% 0.01 210), var(--bg) 34rem);
    }
    img, svg { display: block; max-width: 100%; }
    a { color: inherit; text-decoration: none; }
    button { font: inherit; cursor: pointer; }
    p { text-wrap: pretty; margin: 0; }
    h1, h2, h3, h4 { text-wrap: balance; margin: 0; }
    pre { margin: 0; }

    /* ===== Header ===== */
    header {
      padding: 24px clamp(18px, 4vw, 56px) 16px;
      display: grid;
      grid-template-columns: 1.5fr .5fr;
      gap: 20px;
      align-items: end;
      border-bottom: 1px solid var(--border);
      background:
        linear-gradient(135deg, oklch(100% 0 0 / 0.92), oklch(98% 0.014 210 / 0.88)),
        var(--surface);
      box-shadow: 0 1px 0 oklch(100% 0 0 / 0.72) inset;
    }
    h1 {
      font-size: clamp(26px, 3.5vw, 42px);
      line-height: 1.15;
      letter-spacing: -0.025em;
      font-weight: 700;
      color: var(--fg);
    }
    .lead {
      color: var(--muted);
      font-size: 14px;
      line-height: 1.6;
      max-width: 560px;
      margin-top: 6px;
    }
    .statusbar {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      justify-content: flex-end;
    }

    /* ===== Shell layout ===== */
    .shell {
      display: grid;
      grid-template-columns: 260px 1fr;
      gap: 28px;
      padding: 24px clamp(18px, 4vw, 56px) 48px;
      max-width: 1440px;
      margin: 0 auto;
    }
    .side {
      position: sticky;
      top: 20px;
      align-self: start;
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius-lg);
      padding: 10px;
      box-shadow: var(--shadow-sm);
    }
    .content {
      display: grid;
      gap: 24px;
      min-width: 0;
    }

    /* ===== Sidebar nav ===== */
    .navbtn {
      width: 100%;
      border: 0;
      background: transparent;
      text-align: left;
      border-radius: var(--radius);
      padding: 10px 12px;
      margin: 3px 0;
      cursor: pointer;
      color: var(--fg);
      font-size: 14px;
      font-weight: 500;
      transition: all .15s ease;
      display: flex;
      flex-direction: column;
      gap: 1px;
    }
    .navbtn:hover {
      background: var(--fg-soft);
    }
    .navbtn.active {
      background: var(--accent);
      color: #fff;
      box-shadow: var(--shadow-sm);
    }
    .navbtn small {
      display: block;
      font-size: 11.5px;
      font-weight: 400;
      color: var(--muted);
      margin-top: 1px;
    }
    .navbtn.active small { color: rgba(255,255,255,0.82); }

    /* ===== Panels ===== */
    .panel {
      border: 1px solid var(--border);
      border-radius: var(--radius-lg);
      background: oklch(100% 0 0 / 0.86);
      padding: 28px;
      box-shadow: var(--shadow-sm);
      transition: box-shadow .2s ease;
      min-width: 0;
      backdrop-filter: saturate(1.05);
    }
    .panel:hover {
      box-shadow: var(--shadow);
    }
    .panel h2 {
      font-size: 18px;
      font-weight: 700;
      margin-bottom: 4px;
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .panel > p:first-of-type {
      color: var(--muted);
      font-size: 13.5px;
      line-height: 1.6;
      margin-bottom: 22px;
    }
    .panel h3 {
      font-size: 15px;
      font-weight: 600;
      margin-bottom: 12px;
      color: var(--fg);
    }

    /* ===== Cards ===== */
    .card {
      border: 1px solid var(--border);
      border-radius: var(--radius);
      background: oklch(99% 0.006 220);
      padding: 18px;
      transition: border-color .15s ease, box-shadow .15s ease;
      min-width: 0;
      box-shadow:
        0 1px 0 oklch(100% 0 0 / 0.72) inset,
        0 10px 28px oklch(25% 0.02 230 / 0.035);
    }
    .card:hover {
      border-color: color-mix(in oklch, var(--accent) 20%, var(--border));
      box-shadow:
        0 1px 0 oklch(100% 0 0 / 0.74) inset,
        0 16px 38px oklch(25% 0.03 230 / 0.055);
    }

    /* ===== Grid system ===== */
    .grid {
      display: grid;
      grid-template-columns: repeat(12, 1fr);
      gap: 14px;
      min-width: 0;
    }
    .span4 { grid-column: span 4; }
    .span5 { grid-column: span 5; }
    .span6 { grid-column: span 6; }
    .span7 { grid-column: span 7; }
    .span8 { grid-column: span 8; }
    .span12 { grid-column: span 12; }

    /* ===== Forms ===== */
    label {
      display: block;
      font-size: 12px;
      font-weight: 600;
      color: var(--muted);
      margin: 0 0 6px;
      letter-spacing: 0.01em;
    }
    input, select, textarea {
      width: 100%;
      border: 1.5px solid var(--border);
      background: var(--surface);
      border-radius: var(--radius);
      padding: 10px 12px;
      font: inherit;
      font-size: 14px;
      color: var(--fg);
      transition: border-color .15s ease, box-shadow .15s ease, outline .15s ease;
    }
    input:hover, select:hover, textarea:hover {
      border-color: color-mix(in oklch, var(--fg) 25%, var(--border));
    }
    input:focus, select:focus, textarea:focus {
      outline: none;
      border-color: var(--accent);
      box-shadow: 0 0 0 3px var(--accent-soft);
    }
    textarea {
      min-height: 88px;
      resize: vertical;
      font-family: var(--font-mono);
      font-size: 13px;
      line-height: 1.55;
    }
    select { cursor: pointer; }
    input[type="password"] { font-family: var(--font-mono); }

    /* ===== Checkbox groups ===== */
    .checks {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
    }
    .check {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      border: 1.5px solid var(--border);
      border-radius: 999px;
      padding: 7px 13px;
      background: var(--surface);
      font-size: 13px;
      cursor: pointer;
      transition: border-color .15s ease, background .15s ease;
      user-select: none;
    }
    .check:hover {
      border-color: color-mix(in oklch, var(--accent) 30%, var(--border));
      background: var(--accent-soft);
    }
    .check input {
      width: auto;
      cursor: pointer;
      accent-color: var(--accent);
      margin: 0;
    }

    /* ===== Buttons ===== */
    button, .button {
      border: 0;
      border-radius: 999px;
      padding: 9px 17px;
      background: var(--accent);
      color: #fff;
      font-weight: 600;
      cursor: pointer;
      text-decoration: none;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      font-size: 14px;
      transition: background .15s ease, transform .06s ease, box-shadow .15s ease;
      box-shadow: var(--shadow-sm);
    }
    button:hover, .button:hover {
      background: var(--accent-hover);
      box-shadow: var(--shadow);
    }
    button:active, .button:active { transform: translateY(1px); }
    button.secondary, .button.secondary {
      background: var(--fg-ghost);
      color: var(--fg);
      box-shadow: none;
    }
    button.secondary:hover, .button.secondary:hover {
      background: var(--fg-soft);
    }
    button.ghost, .button.ghost {
      background: transparent;
      color: var(--fg);
      border: 1.5px solid var(--border);
      box-shadow: none;
    }
    button.ghost:hover, .button.ghost:hover {
      border-color: var(--fg);
      background: var(--fg-soft);
    }
    button.danger, .button.danger { background: var(--danger); }
    button.danger:hover, .button.danger:hover {
      background: color-mix(in oklch, var(--danger) 82%, black);
    }
    button:disabled, .button:disabled { opacity: .45; cursor: not-allowed; }

    .btns {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 12px;
      align-items: center;
    }

    /* ===== Provider list ===== */
    .provider-list { display: grid; gap: 6px; }
    .provider-item {
      border: 1.5px solid var(--border);
      border-radius: var(--radius);
      padding: 12px 14px;
      background: var(--surface);
      cursor: pointer;
      font-size: 13px;
      transition: all .15s ease;
    }
    .provider-item:hover {
      border-color: color-mix(in oklch, var(--accent) 30%, var(--border));
      box-shadow: var(--shadow-sm);
    }
    .provider-item.active {
      outline: none;
      border-color: var(--accent);
      background: var(--accent-soft);
      box-shadow: 0 0 0 1px var(--accent);
    }
    .provider-item strong {
      display: block;
      font-size: 14px;
      font-weight: 600;
      margin-bottom: 2px;
    }

    /* ===== Channel layout: sidebar + main ===== */
    .channel-layout {
      display: grid;
      grid-template-columns: 260px 1fr;
      gap: 20px;
      align-items: start;
    }
    .channel-sidebar {
      position: sticky;
      top: 20px;
      max-height: calc(100vh - 120px);
      overflow: auto;
      scrollbar-gutter: stable;
      display: flex;
      flex-direction: column;
      gap: 10px;
    }
    .channel-sidebar .btns {
      margin-top: 4px;
      flex-shrink: 0;
    }
    .channel-main {
      display: flex;
      flex-direction: column;
      gap: 24px;
      min-width: 0;
    }
    .channel-main .provider-editor {
      position: static;
      max-height: none;
      overflow: visible;
      align-self: stretch;
    }

    /* ===== Provider tabs ===== */
    .provider-tabs {
      display: flex;
      gap: 2px;
      border-bottom: 1.5px solid var(--border);
      margin-bottom: 4px;
      padding: 0 2px;
    }
    .tab-btn {
      background: transparent;
      border: 0;
      border-bottom: 2.5px solid transparent;
      padding: 10px 16px;
      font-size: 14px;
      font-weight: 500;
      color: var(--muted);
      cursor: pointer;
      transition: all .15s ease;
      border-radius: var(--radius) var(--radius) 0 0;
      box-shadow: none;
      margin-bottom: -1.5px;
    }
    .tab-btn:hover {
      color: var(--fg);
      background: var(--fg-soft);
    }
    .tab-btn.active {
      color: var(--accent);
      border-bottom-color: var(--accent);
      background: var(--accent-soft);
    }
    .tab-panel {
      display: none;
      animation: fadeIn .2s ease both;
    }
    .tab-panel.active {
      display: block;
    }

    .model-section {
      display: flex;
      flex-direction: column;
      gap: 14px;
    }
    .model-section h3 {
      font-size: 18px;
      font-weight: 700;
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .model-section > p {
      color: var(--muted);
      font-size: 13.5px;
      line-height: 1.6;
    }

    /* ===== Pills ===== */
    .pill {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      border: 1px solid var(--border);
      border-radius: 999px;
      padding: 5px 11px;
      background: var(--surface);
      font-size: 12px;
      color: var(--muted);
      box-shadow: var(--shadow-sm);
    }
    .pill.ok {
      color: var(--ok);
      border-color: var(--ok-soft);
      background: var(--ok-soft);
    }
    .pill.warn {
      color: var(--warn);
      border-color: var(--warn-soft);
      background: var(--warn-soft);
    }

    /* ===== Tags ===== */
    .tag {
      display: inline-block;
      border-radius: 999px;
      background: var(--accent-soft);
      color: var(--accent);
      padding: 3px 9px;
      font-size: 11px;
      font-weight: 600;
      margin: 2px;
      letter-spacing: 0.01em;
    }
    .tag.off {
      background: var(--fg-soft);
      color: var(--muted);
      font-weight: 500;
    }

    /* ===== Tables ===== */
    .table-wrap {
      overflow: auto;
      border: 1.5px solid var(--border);
      border-radius: var(--radius);
      background: var(--surface);
      box-shadow: var(--shadow-sm);
    }
    table {
      width: 100%;
      border-collapse: collapse;
      min-width: 860px;
      font-size: 13px;
    }
    th, td {
      padding: 10px 12px;
      text-align: left;
      border-bottom: 1px solid var(--border);
    }
    th {
      position: sticky;
      top: 0;
      background: var(--bg);
      z-index: 1;
      font-weight: 600;
      font-size: 11px;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.06em;
    }
    td input[type="checkbox"] {
      width: auto;
      cursor: pointer;
      accent-color: var(--accent);
    }
    tbody tr {
      transition: background .1s ease;
    }
    tbody tr:hover {
      background: var(--fg-soft);
    }

    /* ===== Chips ===== */
    .chips {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
    }
    .chip {
      display: inline-flex;
      align-items: center;
      gap: 5px;
      border: 1.5px solid var(--border);
      border-radius: 999px;
      padding: 5px 11px;
      background: var(--surface);
      font-size: 12px;
      transition: border-color .15s ease;
    }
    .chip:hover {
      border-color: color-mix(in oklch, var(--accent) 25%, var(--border));
    }
    .chip button {
      padding: 0 4px;
      background: transparent;
      color: var(--muted);
      border: 0;
      cursor: pointer;
      font-size: 15px;
      line-height: 1;
      border-radius: 4px;
      box-shadow: none;
    }
    .chip button:hover { color: var(--danger); }

    /* ===== Result / Diff blocks ===== */
    .result, .diff {
      white-space: pre-wrap;
      font-family: var(--font-mono);
      font-size: 12px;
      line-height: 1.6;
      background: var(--bg);
      border: 1.5px solid var(--border);
      border-radius: var(--radius);
      padding: 18px;
      max-height: 420px;
      overflow: auto;
      color: var(--fg);
      box-shadow: inset var(--shadow-sm);
    }
    .diff { max-height: 320px; }

    /* ===== OpenCode metrics ===== */
    .oc-summary {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
      margin-top: 14px;
    }
    .oc-metric {
      border: 1.5px solid var(--border);
      border-radius: var(--radius);
      background: var(--surface);
      padding: 16px;
      text-align: center;
      transition: border-color .15s ease, box-shadow .15s ease;
    }
    .oc-metric:hover {
      border-color: color-mix(in oklch, var(--accent) 20%, var(--border));
      box-shadow: var(--shadow-sm);
    }
    .oc-metric strong {
      display: block;
      font-size: 22px;
      color: var(--fg);
      margin: 6px 0;
      font-weight: 700;
      font-variant-numeric: tabular-nums;
    }
    .oc-metric .muted { font-size: 11px; }
    .oc-metric .mono {
      font-size: 11px;
      color: var(--muted);
    }

    .oc-advanced {
      border: 1.5px dashed var(--border);
      border-radius: var(--radius);
      padding: 18px;
      background: var(--bg);
      transition: border-color .15s ease;
    }
    .oc-advanced:hover {
      border-color: color-mix(in oklch, var(--accent) 25%, var(--border));
    }
    .oc-advanced summary {
      cursor: pointer;
      font-weight: 600;
      color: var(--fg);
      font-size: 14px;
      user-select: none;
    }
    .oc-advanced summary::marker { color: var(--muted); }

    .oc-order-note {
      border-left: 3px solid var(--accent);
      background: var(--accent-soft);
      border-radius: 0 var(--radius) var(--radius) 0;
      padding: 12px 16px;
      margin: 14px 0;
      color: var(--fg);
      font-size: 13px;
      line-height: 1.6;
    }
    .oc-enabled {
      width: auto;
      cursor: pointer;
      accent-color: var(--accent);
    }

    /* ===== Filter bar ===== */
    .filterbar {
      display: flex;
      gap: 8px;
      align-items: center;
      flex-wrap: wrap;
      margin: 14px 0;
    }
    .filterbar button {
      background: var(--fg-ghost);
      color: var(--fg);
      box-shadow: none;
      font-size: 13px;
      padding: 7px 13px;
    }
    .filterbar button.active {
      background: var(--accent);
      color: #fff;
      box-shadow: var(--shadow-sm);
    }

    /* ===== Empty / default helpers ===== */
    .empty-row {
      padding: 22px;
      color: var(--muted);
      text-align: center;
      font-size: 14px;
    }
    .default-route {
      max-width: 300px;
      white-space: normal;
      font-size: 12px;
      color: var(--muted);
    }

    /* ===== Toast ===== */
    .toast {
      position: fixed;
      bottom: 28px;
      right: 28px;
      padding: 14px 22px;
      background: var(--fg);
      color: var(--surface);
      border-radius: var(--radius-lg);
      opacity: 0;
      transform: translateY(16px) scale(0.96);
      transition: opacity .35s cubic-bezier(.4,0,.2,1), transform .35s cubic-bezier(.4,0,.2,1);
      pointer-events: none;
      z-index: 100;
      font-size: 14px;
      font-weight: 500;
      box-shadow: var(--shadow-lg);
      max-width: 400px;
      word-break: break-word;
    }
    .toast.show {
      opacity: 1;
      transform: translateY(0) scale(1);
    }

    /* ===== Utilities ===== */
    .muted {
      color: var(--muted);
      font-size: 13px;
      line-height: 1.5;
    }
    .mono {
      font-family: var(--font-mono);
      font-size: 12px;
      font-variant-numeric: tabular-nums;
      overflow-wrap: anywhere;
      word-break: break-word;
    }
    .hide { display: none !important; }

    /* ===== Session asset manager ===== */
    .asset-hero {
      display: grid;
      grid-template-columns: minmax(0, 1.2fr) minmax(240px, .8fr);
      gap: 16px;
      margin-bottom: 16px;
    }
    .asset-hero .card {
      position: relative;
      overflow: hidden;
      background:
        linear-gradient(135deg, oklch(100% 0 0), oklch(96.5% 0.018 205));
      border-color: oklch(83% 0.026 210);
    }
    .asset-hero .card::after {
      content: "";
      position: absolute;
      inset: auto 18px 0;
      height: 3px;
      border-radius: 999px 999px 0 0;
      background: linear-gradient(90deg, var(--accent), oklch(68% 0.12 204));
      opacity: .72;
    }
    .asset-count {
      display: block;
      font-size: 30px;
      line-height: 1;
      font-weight: 750;
      letter-spacing: -0.04em;
      margin-bottom: 6px;
    }
    .asset-manager {
      display: grid;
      gap: 14px;
    }
    .asset-manager + .asset-hero {
      margin-top: 14px;
    }
    .asset-source-strip {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
      gap: 10px;
      min-width: 0;
    }
    .asset-source-mini {
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 11px 12px;
      background: oklch(100% 0 0 / 0.68);
      min-width: 0;
      overflow-wrap: anywhere;
    }
    .asset-source-mini.asset-source-intro {
      background:
        linear-gradient(135deg, oklch(98.5% 0.014 188), oklch(100% 0 0));
      border-color: color-mix(in oklch, var(--accent) 30%, var(--border));
    }
    .asset-source-mini.is-missing {
      background: oklch(98% 0.004 240 / 0.8);
      opacity: .82;
    }
    .asset-source-head,
    .asset-source-foot {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      min-width: 0;
    }
    .asset-source-title {
      min-width: 0;
      overflow-wrap: anywhere;
    }
    .asset-source-path {
      margin: 6px 0 4px;
      font-size: 12px;
      overflow-wrap: anywhere;
    }
    .asset-source-real {
      margin-top: 6px;
      font-size: 12px;
    }
    .asset-source-real summary {
      color: var(--muted);
      cursor: pointer;
    }
    .asset-source-mini strong {
      display: block;
      font-size: 13px;
      margin-bottom: 4px;
    }
    .asset-confirm-map {
      display: grid;
      gap: 12px;
      margin: 0 0 16px;
      background:
        linear-gradient(135deg, oklch(100% 0 0), oklch(97% 0.012 204));
      min-width: 0;
    }
    .asset-confirm-head {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 12px;
      min-width: 0;
    }
    .asset-confirm-grid {
      display: grid;
      grid-template-columns: minmax(0, .9fr) minmax(0, 1.1fr);
      gap: 12px;
      min-width: 0;
    }
    .asset-confirm-block {
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 12px;
      background: oklch(100% 0 0 / 0.66);
      min-width: 0;
    }
    .asset-confirm-block h4 {
      margin: 0 0 8px;
      font-size: 13px;
      letter-spacing: -0.01em;
    }
    .asset-confirm-actions,
    .asset-confirm-panels,
    .asset-confirm-constraints,
    .asset-cli-panels {
      display: flex;
      flex-wrap: wrap;
      gap: 5px;
      min-width: 0;
    }
    .asset-confirm-constraints p {
      width: 100%;
      margin: 0;
      color: var(--muted);
      font-size: 12.5px;
      line-height: 1.5;
      overflow-wrap: anywhere;
    }
    .asset-cli-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
      gap: 12px;
      margin: 0 0 16px;
      min-width: 0;
    }
    .asset-cli-card {
      display: grid;
      gap: 10px;
      padding: 14px;
      background:
        linear-gradient(180deg, oklch(100% 0 0), oklch(97.5% 0.01 220));
      min-width: 0;
    }
    .asset-cli-card.is-active {
      border-color: color-mix(in oklch, var(--accent) 45%, var(--border));
      box-shadow:
        0 0 0 1px color-mix(in oklch, var(--accent) 22%, transparent),
        0 12px 30px oklch(31% 0.045 222 / 0.07);
    }
    .asset-cli-card h3 {
      margin: 0;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      min-width: 0;
    }
    .asset-cli-title {
      min-width: 0;
      overflow-wrap: anywhere;
      letter-spacing: -0.015em;
    }
    .asset-cli-metrics,
    .asset-cli-controls,
    .asset-cli-sources {
      display: flex;
      flex-wrap: wrap;
      gap: 5px;
      min-width: 0;
    }
    .asset-cli-section {
      display: grid;
      gap: 6px;
      min-width: 0;
    }
    .asset-cli-label {
      color: var(--muted);
      font-size: 11px;
      font-weight: 750;
      letter-spacing: 0.08em;
    }
    .asset-cli-source {
      width: 100%;
      border-top: 1px dashed var(--border);
      padding-top: 8px;
      color: var(--muted);
      font-size: 12px;
      overflow-wrap: anywhere;
    }
    .asset-cli-source strong {
      color: var(--fg);
      font-weight: 650;
    }
    .asset-cli-sample,
    .asset-cli-note {
      color: var(--muted);
      font-size: 12px;
      line-height: 1.5;
      overflow-wrap: anywhere;
    }
    .asset-cli-note {
      padding: 9px 10px;
      border-radius: 12px;
      background: var(--fg-soft);
    }
    .asset-cli-action {
      justify-content: flex-start;
      margin-top: 2px;
    }
    .asset-cli-action button {
      padding: 7px 12px;
      font-size: 12px;
    }
    .asset-toolbar {
      border: 1.5px solid var(--border);
      border-radius: var(--radius-lg);
      padding: 14px;
      background:
        linear-gradient(180deg, oklch(99% 0.006 210), oklch(96.5% 0.012 210));
      display: grid;
      gap: 12px;
      min-width: 0;
      box-shadow:
        0 1px 0 oklch(100% 0 0 / 0.7) inset,
        0 10px 28px oklch(28% 0.02 230 / 0.035);
    }
    .asset-toolbar-row {
      display: flex;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
      min-width: 0;
    }
    .asset-toolbar-row strong {
      font-size: 12px;
      color: var(--muted);
      min-width: 64px;
      letter-spacing: 0.06em;
    }
    .asset-toolbar .filterbar {
      margin: 0;
    }
    .asset-toolbar .filterbar button {
      border: 1px solid transparent;
      background: oklch(100% 0 0 / 0.7);
      color: oklch(33% 0.02 230);
      display: inline-flex;
      align-items: center;
      gap: 6px;
      font-weight: 650;
      box-shadow: 0 1px 0 oklch(100% 0 0 / 0.7) inset;
    }
    .asset-toolbar .filterbar button:hover {
      border-color: color-mix(in oklch, var(--accent) 24%, var(--border));
    }
    .asset-toolbar .filterbar button.active,
    .asset-toolbar .filterbar button[aria-pressed="true"],
    .asset-toolbar .filterbar button.ghost.active {
      border-color: var(--accent);
      background: var(--accent);
      color: oklch(100% 0 0);
      box-shadow:
        0 0 0 1px color-mix(in oklch, var(--accent) 28%, transparent),
        0 6px 16px oklch(41% 0.11 168 / 0.16);
    }
    .asset-toolbar .filterbar button.active::before,
    .asset-toolbar .filterbar button[aria-pressed="true"]::before {
      content: "";
      width: 6px;
      height: 6px;
      border-radius: 999px;
      background: currentColor;
      opacity: .9;
      flex: 0 0 auto;
    }
    .asset-search {
      max-width: 340px;
      min-width: 220px;
      flex: 1 1 260px;
      background: oklch(100% 0 0 / 0.88);
    }
    .asset-list {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: 12px;
      min-width: 0;
    }
    .asset-card {
      position: relative;
      display: flex;
      flex-direction: column;
      gap: 12px;
      min-width: 0;
      padding: 16px;
      background:
        linear-gradient(180deg, oklch(100% 0 0), oklch(98% 0.006 220));
      border-color: oklch(87% 0.014 220);
      overflow: hidden;
      box-shadow:
        0 1px 0 oklch(100% 0 0 / 0.82) inset,
        0 8px 22px oklch(25% 0.02 230 / 0.038);
    }
    .asset-card::before {
      content: "";
      position: absolute;
      inset: 0 auto 0 0;
      width: 4px;
      background: linear-gradient(180deg, var(--accent), oklch(72% 0.09 178));
      opacity: .75;
    }
    .asset-card.is-disabled {
      border-color: var(--warn);
      background:
        linear-gradient(180deg, oklch(100% 0 0), color-mix(in oklch, var(--warn-soft) 38%, var(--surface)));
    }
    .asset-card.is-disabled::before {
      background: linear-gradient(180deg, var(--warn), oklch(76% 0.10 93));
    }
    .asset-card.is-global {
      background:
        linear-gradient(180deg, oklch(99% 0.003 230), color-mix(in oklch, var(--fg-soft) 58%, var(--surface)));
    }
    .asset-card.is-global::before {
      background: linear-gradient(180deg, oklch(56% 0.025 235), oklch(72% 0.02 230));
    }
    .asset-card-head {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 10px;
      align-items: start;
    }
    .asset-title {
      font-size: 16px;
      font-weight: 750;
      line-height: 1.25;
      overflow-wrap: anywhere;
      letter-spacing: -0.015em;
    }
    .asset-subline {
      color: var(--muted);
      font-size: 12px;
      margin-top: 4px;
      overflow-wrap: anywhere;
    }
    .asset-desc {
      color: var(--fg);
      font-size: 13.5px;
      line-height: 1.65;
      overflow-wrap: anywhere;
    }
    .asset-meta {
      display: flex;
      flex-wrap: wrap;
      gap: 5px;
      min-width: 0;
    }
    .asset-action {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      border-top: 1px solid var(--border);
      padding-top: 10px;
      color: var(--muted);
      font-size: 12.5px;
      min-width: 0;
    }
    .asset-switch {
      display: inline-flex;
      align-items: center;
      gap: 7px;
      flex: 0 0 auto;
      color: var(--fg);
      font-size: 12.5px;
      font-weight: 600;
      cursor: pointer;
      user-select: none;
    }
    .asset-switch input {
      width: auto;
      accent-color: var(--warn);
      cursor: pointer;
    }
    .asset-details {
      border-top: 1px dashed var(--border);
      padding-top: 10px;
      min-width: 0;
    }
    .asset-details summary {
      cursor: pointer;
      color: var(--muted);
      font-size: 12.5px;
      font-weight: 600;
      user-select: none;
      transition: color .18s cubic-bezier(.32,.72,0,1);
    }
    .asset-details summary:hover {
      color: var(--fg);
    }
    .asset-detail-grid {
      display: grid;
      gap: 8px;
      margin-top: 10px;
    }
    .asset-detail-grid p {
      overflow-wrap: anywhere;
      word-break: break-word;
    }
    .asset-empty {
      border: 1.5px dashed var(--border);
      border-radius: var(--radius);
      padding: 28px;
      text-align: center;
      color: var(--muted);
      background: var(--bg);
    }
    .asset-config-card details {
      margin-top: 12px;
    }
    .asset-config-card summary {
      cursor: pointer;
      font-weight: 650;
    }
    .asset-roots {
      display: grid;
      gap: 10px;
    }
    .asset-root {
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 12px;
      background: oklch(100% 0 0 / 0.72);
      min-width: 0;
      box-shadow: 0 1px 0 oklch(100% 0 0 / 0.72) inset;
    }

    /* ===== Section entrance animation ===== */
    [data-section] {
      animation: fadeIn .25s ease both;
    }
    @keyframes fadeIn {
      from { opacity: 0; transform: translateY(8px); }
      to   { opacity: 1; transform: translateY(0); }
    }

    /* ===== Responsive ===== */
    @media (max-width: 980px) {
      header { grid-template-columns: 1fr; }
      .statusbar { justify-content: flex-start; }
      .shell { grid-template-columns: 1fr; padding: 16px; }
      .side, .provider-editor {
        position: relative;
        top: auto;
        max-height: none;
        overflow: visible;
      }
      .channel-layout { grid-template-columns: 1fr; }
      .channel-sidebar {
        position: relative;
        top: auto;
        max-height: none;
        overflow: visible;
      }
      .span4, .span5, .span6, .span7, .span8, .span12 { grid-column: span 12; }
      .oc-summary { grid-template-columns: 1fr 1fr; }
      .asset-hero { grid-template-columns: 1fr; }
      .asset-confirm-grid { grid-template-columns: 1fr; }
      .asset-cli-grid { grid-template-columns: 1fr 1fr; }
      .panel { padding: 20px; }
    }
    @media (max-width: 560px) {
      header { padding: 18px 14px 14px; }
      .shell { padding: 12px; }
      .panel { padding: 16px; border-radius: var(--radius); }
      .asset-list { grid-template-columns: 1fr; }
      .asset-cli-grid { grid-template-columns: 1fr; }
      .asset-card-head { grid-template-columns: 1fr; }
      .asset-action { align-items: flex-start; flex-direction: column; }
      .asset-toolbar-row { align-items: stretch; flex-direction: column; }
      .asset-toolbar-row strong { min-width: 0; }
      .asset-search { min-width: 0; max-width: none; }
      .toast { left: 12px; right: 12px; bottom: 12px; max-width: none; }
    }
  </style>
</head>
<body>
<header>
  <div>
    <h1>MMS 配置中心</h1>
    <p class="lead">不是展示页：这里可以配置通道、拉取模型、隐藏/补充模型、标记能力、测试模型、设置 fallback。保存前先预览；stable legacy 走 backup + audit，preview root 走 DB candidate + latest-approved publish。</p>
  </div>
  <div class="statusbar" id="statusbar"><span class="pill warn">加载中</span></div>
</header>
<div class="shell">
  <aside class="side" id="nav"></aside>
  <main class="content">
    <section class="panel" data-section="source">
      <h2>真源状态</h2>
      <p>只读汇总当前 config root、registry DB、legacy import 冲突和 latest-approved bundle 校验状态。</p>
      <div class="grid" id="sourceStatus"></div>
    </section>


    <!-- 通道配置 -->
    <section class="panel" data-section="channel">
      <h2>通道配置</h2>
      <p>先建通道：内部 ID、显示名、OpenAI/Anthropic URL、API Key、协议和模型列表接口。Key 只会通过 POST 发送，不会回显。</p>
      <div class="channel-layout">
        <div class="channel-sidebar">
          <div class="provider-list" id="providerList"></div>
          <div class="btns">
            <button id="addProvider" class="secondary">+ 添加通道</button>
            <button id="duplicateProvider" class="ghost">复制当前</button>
          </div>
        </div>
        <div class="channel-main">
          <div class="provider-tabs">
            <button class="tab-btn active" data-tab="config" onclick="switchProviderTab('config')">通道配置</button>
            <button class="tab-btn" data-tab="models" onclick="switchProviderTab('models')">模型配置</button>
          </div>
          <div class="tab-panel active" data-tab-panel="config">
            <div class="card provider-editor" id="providerForm"></div>
          </div>
          <div class="tab-panel" data-tab-panel="models">
            <div class="model-section">
              <p class="muted">这是当前通道的模型清单，不是全局模型池。手动补充会写入当前通道的 extra_models；取消勾选「显示」会写入当前通道的 hidden_models。</p>
              <div class="card">
                <div class="btns">
                  <button id="fetchModels">拉取当前通道模型</button>
                  <button id="testList" class="secondary">测试 /models</button>
                  <label class="check"><input id="autoStaleCleanupOnFetch" type="checkbox"><span>拉取后自动标记缺失旧 route 为待清理（本页临时）</span></label>
                  <input id="modelSearch" placeholder="搜索模型" style="max-width:260px">
                </div>
                <label style="margin-top:14px">手动补充当前通道模型（extra_models，逗号或换行分隔）</label>
                <textarea id="manualModels" placeholder="例如：gpt-5.5, qwen3.6-plus, K2.6"></textarea>
                <div class="btns">
                  <button id="addManualModels" class="secondary">添加到补充模型库</button>
                  <button id="clearHidden" class="ghost">取消当前通道全部隐藏</button>
                  <button id="clearAllStaleHidden" class="ghost">移除全部通道未匹配隐藏规则</button>
                </div>
              </div>
              <div id="modelChips" class="card"></div>
              <div class="card" id="staleHiddenBox"></div>
              <div class="table-wrap"><table id="modelTable"></table></div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- 模型测试 -->
    <section class="panel" data-section="test">
      <h2>模型测试</h2>
      <p>支持模型列表 smoke、指定模型 ping/pong 和简单 chat。结果会显示脱敏 request_url/request_path evidence。</p>
      <div class="grid">
        <div class="card span5">
          <label>测试通道</label><select id="testProvider"></select>
          <label>测试模型</label><select id="testModel"></select>
          <label>协议</label>
          <select id="testProtocol">
            <option value="auto">auto</option>
            <option value="anthropic_messages">anthropic_messages</option>
            <option value="openai_chat_completions">openai_chat_completions</option>
          </select>
          <label>Prompt</label>
          <textarea id="testPrompt">只回复 pong</textarea>
          <div class="btns">
            <button id="testModelBtn">Ping 模型</button>
            <button id="chatTestBtn" class="secondary">Simple chat</button>
          </div>
        </div>
        <div class="card span7">
          <div class="result" id="testResult">暂无测试结果</div>
        </div>
      </div>
    </section>

    <!-- Fallback -->
    <section class="panel" data-section="fallback">
      <h2>Fallback 设置</h2>
      <p>stable legacy 保存写入 config.toml 的 [rescue] / [vision_sidecar]；preview root 保存为 DB candidate 并随 latest-approved bundle 发布。</p>
      <div class="grid">
        <div class="card span6">
          <h3>Rescue fallback</h3>
          <label>fallback_model</label>
          <input id="rescueModel" placeholder="deepseek-v4-flash">
          <label>fallback_cli</label>
          <select id="rescueCli">
            <option value="">不指定</option>
            <option>codex</option>
            <option>claude</option>
            <option>opencode</option>
            <option>agy</option>
          </select>
          <div class="check" style="margin-top:10px">
            <input id="rescueHot" type="checkbox"><span>开启 hot_fallback_enabled</span>
          </div>
        </div>
        <div class="card span6">
          <h3>Vision sidecar</h3>
          <div class="check">
            <input id="visionEnabled" type="checkbox"><span>启用 vision sidecar</span>
          </div>
          <label>provider_id</label>
          <select id="visionProvider"></select>
          <label>model</label>
          <select id="visionModel"></select>
          <p class="muted">模型下拉优先显示当前通道中标记为 vision/multimodal 的模型；当前值不在列表时会保留为「当前配置值」。</p>
          <label>候选列表</label>
          <div id="visionCandidates" class="grid"></div>
          <div class="btns">
            <button id="addVisionCandidate" class="secondary">+ 添加 vision 候选</button>
          </div>
        </div>
      </div>
    </section>

    <!-- 运行默认值 -->
    <section class="panel" data-section="runtime">
      <h2>运行默认值</h2>
      <p>Preferred CLI 会写入 presets.coding.cli；OpenCode profile 和 agent roster 会写入 [opencode]，launcher 会生成 session-local opencode.json；不会写全局 OpenCode 配置。</p>
      <div class="grid">
        <div class="card span5">
          <label>preferred CLI</label>
          <select id="preferredCli">
            <option>opencode</option>
            <option>codex</option>
            <option>claude</option>
            <option>agy</option>
          </select>
          <label>coding preset model（可选）</label>
          <input id="codingModel" placeholder="gpt-5.5">
        </div>
        <div class="card span7">
          <label>OpenCode default profile</label>
          <select id="opencodeProfile">
            <option>agent</option>
            <option>omo</option>
            <option>raw</option>
          </select>
          <p class="muted">推荐：5.5 总控/终审，5.4 长跑 executor，国产模型用于 explore / bug-hunt / vision。逐 agent 固定模型放在 Advanced，不作为默认必填项。</p>
        </div>
        <div class="card span12">
          <h3>OpenCode Agent Roster</h3>
          <p class="muted">默认使用 Lite Pro 自动路线；这里管理哪些 agent 进入 session-local opencode.json。Order 是 priority/fallback order, not round-robin。</p>
          <div class="oc-summary" id="opencodeOverrideSummary"></div>
          <div class="oc-order-note">
            Lean 默认只开关键链路；Balanced 适合日常；Deep 再启用第二意见。国产模型适合 explore / bughunt / vision，不默认做最终裁决。
          </div>
          <details class="oc-advanced" id="opencodeAdvanced">
            <summary>Advanced: OpenCode per-agent roster</summary>
            <div class="filterbar" id="opencodeAgentFilters"></div>
            <div class="table-wrap"><table id="opencodeAgents"></table></div>
          </details>
        </div>
      </div>
    </section>

    <!-- Session 能力面板 -->
    <section class="panel" data-section="sessionAssets">
      <h2>Skill / MCP 管理</h2>
      <p>先看当前实际加载位置和能力卡片：MMS 动态注入可生成默认关闭片段，Global 只做只读对照。</p>
      <div class="asset-manager">
        <div class="asset-source-strip" id="assetManagedRoots"></div>
        <div class="asset-toolbar">
          <div class="asset-toolbar-row">
            <strong>来源</strong>
            <div class="filterbar" id="assetTabs"></div>
          </div>
          <div class="asset-toolbar-row">
            <strong>CLI</strong>
            <div class="filterbar" id="assetCliFilters"></div>
          </div>
          <div class="asset-toolbar-row">
            <strong>类型</strong>
            <div class="filterbar" id="assetKindFilters"></div>
            <input class="asset-search" id="assetSearch" placeholder="搜索能力名称、用途、路径">
          </div>
        </div>
        <div class="asset-list" id="assetCards"></div>
      </div>
      <div class="asset-hero" id="assetSummary"></div>
      <details class="oc-advanced" id="assetCliDetails">
        <summary>展开查看各 CLI 的 TUI 确认页能力和来源</summary>
        <div class="card asset-confirm-map" id="assetConfirmMap"></div>
        <div class="asset-cli-grid" id="assetCliOverview"></div>
      </details>
      <div class="grid">
        <div class="card span6 asset-config-card">
          <h3>默认关闭草稿</h3>
          <p class="muted" id="assetConfigContract">WebUI 当前只读展示能力目录；勾选“默认关闭”只会更新下方 snippet，不会自动写真实配置。</p>
          <div class="btns">
            <button id="copyAssetPrefs" class="secondary">复制偏好片段</button>
            <button id="resetAssetPrefs" class="ghost">恢复当前偏好</button>
          </div>
          <details>
            <summary>查看要写入 preferences.toml 的片段</summary>
            <pre class="result" id="assetPreferenceSnippet"></pre>
          </details>
        </div>
        <div class="card span6">
          <h3>全局位置（只读）</h3>
          <p class="muted">这些目录/文件可能影响 MMS 之外的 CLI。本页只解释来源，不自动改用户全局配置。</p>
          <div class="asset-roots" id="assetGlobalRoots"></div>
        </div>
      </div>
    </section>

    <!-- 保存 / 审计 -->
    <section class="panel" data-section="save">
      <h2>保存 / 审计</h2>
      <p id="saveModeLead">保存前先生成 diff。preview root 走 DB candidate + latest-approved publish；stable legacy 使用 audited writer：lock、backup、audit log。API Key 不会出现在 diff 或响应里。</p>
      <div class="grid">
        <div class="card span5">
          <p class="muted" id="saveModeHint"></p>
          <div class="btns">
            <button id="previewPlan">生成保存预览</button>
            <button id="applyV2Preview" class="secondary">写入预览 DB + 发布</button>
            <button id="saveBtn" class="danger legacy-save-action">确认保存</button>
          </div>
          <details class="oc-advanced" id="advancedPlanTools" style="margin-top:14px">
            <summary>Advanced / Recovery：plan JSON 与 CLI fallback</summary>
            <p class="muted">WebUI plan JSON = “生成保存预览”的 redacted review artifact；下载 JSON 不含明文 key。CLI apply 是无 WebUI 时的 fallback，不是日常主流程。</p>
            <div class="btns">
              <button id="downloadPlanJson" class="ghost">下载 plan JSON</button>
              <button id="copyApplyCommand" class="ghost">复制 CLI apply 命令</button>
            </div>
          </details>
          <div class="check" style="margin-top:12px">
            <input id="confirmSave" type="checkbox"><span>我已检查摘要、风险和 diff，同意执行所选写入</span>
          </div>
          <label id="confirmPhraseLabel" style="margin-top:12px">输入确认文字</label>
          <input id="confirmPhrase" placeholder="保存配置 或 写入预览DB">
          <label>保存原因 / audit reason</label>
          <input id="saveReason" value="setup-web-ui:interactive-save">
          <p class="muted" id="saveCompatibilityNote">stable legacy 走 backup + audit，preview root 走 DB candidate + latest-approved publish。</p>
        </div>
        <div class="card span7">
          <div class="result" id="saveResult">尚未生成预览</div>
        </div>
        <div class="card span12">
          <h3>保存摘要</h3>
          <div id="reviewSummary">
            <p class="muted">点击“生成保存预览”后，这里会先用人话列出 URL、隐藏模型、fallback、OpenCode 和风险变化。</p>
          </div>
        </div>
        <div class="span12">
          <h3 style="margin-bottom:8px">Raw diff / 审计详情</h3>
          <div class="diff" id="diffBox">点击“生成保存预览”</div>
        </div>
      </div>
    </section>

    <!-- 本地参考 -->
    <section class="panel" data-section="refs">
      <h2>本地参考</h2>
      <p>这些是当前配置页面使用的本地参考入口；联网查最新厂商文档应作为后续显式动作，不在保存时自动外连。</p>
      <div class="grid" id="refsGrid"></div>
    </section>
  </main>
</div>
<div class="toast" id="toast"></div>
<script>
const sections=[
  ['source','真源状态','DB / legacy / bundle'],
  ['channel','通道配置','URL / Key / 协议 / 模型'],
  ['test','模型测试','ping / chat smoke'],
  ['fallback','Fallback','救援模型 / Vision'],
  ['runtime','运行默认值','preferred CLI / OpenCode'],
  ['sessionAssets','能力面板','技能 / MCP / 钩子'],
  ['save','保存审计','diff / backup / audit'],
  ['refs','本地参考','配置契约 / docs']
];
let state=null; let activeProvider=0; let activeProviderTab='config'; let lastPlan=null; let opencodeAgentFilter="all"; let opencodeOnlyOverridden=false; let editingExtraModels=false; let touchedProviders=new Set(); let staleCleanupProviders=new Set(); let assetTab='mms_dynamic'; let assetCli='all'; let assetKind='all'; let assetQuery=''; let assetDisabledDraft=null;
const $=id=>document.getElementById(id);
function toast(msg){const el=$('toast');el.textContent=msg;el.classList.add('show');setTimeout(()=>el.classList.remove('show'),3600)}
async function api(path,body){const res=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body||{})});const data=await res.json();if(!res.ok){data.ok=false;data.http_status=res.status;data.error=data.error||res.statusText}return data}
function current(){return state.providers[activeProvider]}
function touchProvider(id){if(id)touchedProviders.add(id)}
function setSection(id){document.querySelectorAll('[data-section]').forEach(el=>el.classList.toggle('hide',el.dataset.section!==id));document.querySelectorAll('.navbtn').forEach(el=>el.classList.toggle('active',el.dataset.id===id))}
function switchProviderTab(tab){activeProviderTab=tab;document.querySelectorAll('.provider-tabs .tab-btn').forEach(b=>b.classList.toggle('active',b.dataset.tab===tab));document.querySelectorAll('.tab-panel').forEach(p=>p.classList.toggle('active',p.dataset.tabPanel===tab))}
function renderNav(){ $('nav').innerHTML=sections.map(([id,title,sub])=>`<button class="navbtn" data-id="${id}">${title}<small>${sub}</small></button>`).join(''); document.querySelectorAll('.navbtn').forEach(b=>b.onclick=()=>setSection(b.dataset.id)); setSection('source') }
function renderStatus(){const providers=state.providers||[];const root=(state.model_source_status||{}).root||{};$('statusbar').innerHTML=`<span class="pill ok">${state.mode}</span><span class="pill">${escapeHtml(root.mode||'stable')}</span><span class="pill">通道 ${providers.length}</span><span class="pill">config: ${escapeHtml(state.paths.config||'-')}</span><span class="pill">policy: ${state.policy_summary.model_count} models</span>`}
function escapeHtml(s){return String(s??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]))}
function renderSaveControls(){const root=(state.model_source_status||{}).root||{};const preview=root.mode==='preview';const hasPlan=!!lastPlan;const modeName=preview?'MMF preview / DB truth':'MMS stable / legacy compatibility';if($('saveModeHint')){$('saveModeHint').innerHTML=preview?'当前是 <strong>mmf + ~/.config/mms-next</strong>：日常只需要“生成保存预览” → “写入预览 DB + 发布”。':'当前是 <strong>mms stable</strong>：使用 legacy audited save，仍会 backup + audit。'}if($('saveModeLead')){$('saveModeLead').textContent=preview?'保存前先生成 diff。写入只落到当前 preview root 的 DB candidate，并发布 latest-approved bundle；API Key 不会出现在 diff 或响应里。':'保存前先生成 diff。stable legacy 使用 audited writer：lock、backup、audit log；API Key 不会出现在 diff 或响应里。'}if($('confirmPhraseLabel')){$('confirmPhraseLabel').textContent=preview?'输入确认文字：写入预览DB':'输入确认文字：保存配置'}if($('confirmPhrase')){$('confirmPhrase').placeholder=preview?'写入预览DB':'保存配置'}if($('saveCompatibilityNote')){$('saveCompatibilityNote').textContent=preview?'旧版“确认保存”在 mmf 中已隐藏；下载 JSON / CLI apply 只在 Advanced / Recovery 里作为 fallback。':'stable legacy 保存写入 config.toml / credentials.sh / model-policy，并保留 backup + audit；preview DB 发布请用 mmf。'}document.querySelectorAll('.legacy-save-action').forEach(el=>el.classList.toggle('hide',preview));if($('saveBtn')){$('saveBtn').disabled=preview;$('saveBtn').title=preview?'MMF preview 已隐藏 legacy save，请使用写入预览 DB + 发布':''}if($('applyV2Preview')){$('applyV2Preview').classList.toggle('hide',!preview);$('applyV2Preview').disabled=!preview;$('applyV2Preview').title=preview?modeName:'Stable root 不能写 preview DB，请用 mmf preview root'}if($('advancedPlanTools')){$('advancedPlanTools').open=false}if($('downloadPlanJson')){$('downloadPlanJson').disabled=!hasPlan;$('downloadPlanJson').title=hasPlan?'下载 redacted plan JSON；不含明文 API Key':'请先生成保存预览'}if($('copyApplyCommand')){$('copyApplyCommand').disabled=!hasPlan;$('copyApplyCommand').title=hasPlan?'复制 mmf config apply-plan 命令':'请先生成保存预览'}}
function renderSourceStatus(){
  const box=$('sourceStatus');if(!box)return;
  const status=state.model_source_status||{};
  const consumer=state.consumer_bundle_status||{};
  const promotion=state.config_v2_promotion_plan||{};
  const readiness=state.config_v2_release_readiness||{};
  const root=status.root||consumer.root||{};
  const db=status.registry_db||{};
  const legacy=status.legacy_import||{};
  const candidates=legacy.candidates||db.legacy_import_candidates||{};
  const bundle=status.generated_bundle||{};
  const revisions=consumer.component_revisions||{};
  const rules=consumer.consumer_rules||[];
  const consumerFiles=consumer.files||{};
  const counts=db.counts||{};
  const safety=promotion.promotion_safety||{};
  const backup=promotion.stable_backup_plan||{};
  const compare=promotion.bundle_comparison||{};
  const comparePreview=compare.preview||{};
  const compareStable=compare.stable||{};
  const readinessNext=readiness.next_action||{};
  const readinessBlocked=Array.isArray(readiness.blocked_requirements)?readiness.blocked_requirements:[];
  const readinessReqs=Array.isArray(readiness.requirements)?readiness.requirements:[];
  const readinessOk=readiness.ready_for_human_gate?'ok':'warn';
  const okBundle=bundle.verified?'ok':'warn';
  const okConsumer=consumer.verified?'ok':'warn';
  const okPromotion=promotion.ready_for_human_review?'ok':'warn';
  const ready=bundle.runtime_ready===true?'ready':bundle.runtime_ready===false?'not ready':'unknown';
  const bundleCommand=(root.command||state.command||'mms')==='mmf'?'mmf config bundle --json':'mms config bundle --json';
  box.innerHTML=`<div class="card span6"><h3>Root</h3><p class="mono">${escapeHtml(root.config_root||status.config_root||consumer.config_root||'-')}</p><p class="muted">${escapeHtml(status.headline||'-')}</p><span class="tag ${status.ready?'':'off'}">${escapeHtml(status.status||'unknown')}</span><span class="tag">${escapeHtml(root.command||state.command||'-')}</span><span class="tag">${escapeHtml(root.mode||'-')}</span><span class="tag">${escapeHtml(root.root_source||'-')}</span></div><div class="card span6"><h3>Registry DB</h3><p class="mono">${escapeHtml(db.path||'-')}</p><span class="tag ${db.status==='ok'?'':'off'}">${escapeHtml(db.status||'missing')}</span><span class="tag">sources ${counts.source_snapshot||0}</span><span class="tag">facts ${counts.model_fact||0}</span><span class="tag">routes ${counts.provider_route||0}</span></div><div class="card span6"><h3>Legacy Import</h3><p class="muted">${escapeHtml(legacy.next_action||'-')}</p><span class="tag">providers ${legacy.provider_count||0}</span><span class="tag ${legacy.conflict_count?'off':''}">conflicts ${legacy.conflict_count||0}</span><span class="tag ${candidates.status==='imported'?'':'off'}">candidates ${escapeHtml(candidates.status||'not_imported')}</span><span class="tag">candidate routes ${candidates.provider_route_count||0}</span></div><div class="card span6"><h3>Latest Approved Bundle</h3><p class="mono">${escapeHtml(bundle.manifest_path||'-')}</p><span class="tag ${okBundle==='ok'?'':'off'}">${escapeHtml(bundle.status||'missing')}</span><span class="tag">verified ${bundle.verified?'yes':'no'}</span><span class="tag ${bundle.runtime_ready===true?'':'off'}">runtime ${ready}</span><span class="tag">missing keys ${bundle.router_missing_api_key_count||0}</span><span class="tag">files ${bundle.file_count||0}</span></div><div class="card span12"><h3>Consumer Bundle</h3><p class="mono">${escapeHtml(consumer.consumer_entrypoint||bundle.manifest_path||'-')}</p><p class="muted">${escapeHtml((rules.length?rules.join(' · '):'下游只读 latest-approved manifest；不读 SQLite；不混合不同 revision。'))}</p><span class="tag ${okConsumer==='ok'?'':'off'}">${escapeHtml(consumer.status||'missing')}</span><span class="tag">verified ${consumer.verified?'yes':'no'}</span><span class="tag">bundle ${escapeHtml(revisions.bundle||'-')}</span><span class="tag">route ${escapeHtml(revisions.route||'-')}</span><span class="tag">policy ${escapeHtml(revisions.policy||'-')}</span><span class="tag">profile ${escapeHtml(revisions.profile||'-')}</span><span class="tag">files ${Object.keys(consumerFiles).length}</span><p class="muted">CLI: <span class="mono">${escapeHtml(bundleCommand)}</span></p></div><div class="card span12"><h3>Promotion Plan / Human Gate</h3><p class="muted">stable backup + bundle comparison 是只读审查；apply 仍停在 human gate。</p><span class="tag ${okPromotion==='ok'?'':'off'}">${escapeHtml(promotion.status||'not_ready')}</span><span class="tag">review ${promotion.ready_for_human_review?'ready':'not ready'}</span><span class="tag">apply ${promotion.apply_enabled?'enabled':'disabled'}</span><span class="tag">stable ${escapeHtml(safety.stable_write_policy||'human_only')}</span><span class="tag">backup ${backup.requires_backup_before_apply?'required':'unknown'}</span><span class="tag">would backup ${backup.would_create_backup?'yes':'no'}</span><span class="tag">bundle comparison ${escapeHtml(compare.comparison_status||'-')}</span><p class="muted">preview ${escapeHtml(comparePreview.bundle_revision||comparePreview.status||'-')} → stable ${escapeHtml(compareStable.bundle_revision||compareStable.status||'-')}</p></div><div class="card span12"><h3>4.0 Release Readiness</h3><p class="muted">只读 audit：证明自动检查已到 stable promotion human gate；release_complete 仍为 false。</p><span class="tag ${readinessOk==='ok'?'':'off'}">${escapeHtml(readiness.result||'NOT_READY')}</span><span class="tag">status ${escapeHtml(readiness.status||'not_ready')}</span><span class="tag">release complete ${readiness.release_complete?'yes':'no'}</span><span class="tag">human gate ${readiness.ready_for_human_gate?'ready':'not ready'}</span><span class="tag">blocked ${readinessBlocked.length}</span><span class="tag">requirements ${readinessReqs.filter(r=>r&&r.ok).length}/${readinessReqs.length}</span><span class="tag">blocker ${escapeHtml(readiness.completion_blocker||'-')}</span><p class="muted">blocked requirements: ${escapeHtml(readinessBlocked.length?readinessBlocked.join(', '):'-')}</p><p class="muted">next: <span class="mono">${escapeHtml(readinessNext.command||readinessNext.label||'-')}</span></p></div><div class="card span12"><h3>Raw Status</h3><div class="result">${escapeHtml(JSON.stringify({model_source_status:status,consumer_bundle_status:consumer,config_v2_promotion_plan:promotion,config_v2_release_readiness:readiness},null,2))}</div></div>`
}
function providerEntries(){return (state.providers||[]).map((p,i)=>({p,i})).sort((a,b)=>{if(!!a.p.enabled!==!!b.p.enabled)return a.p.enabled?-1:1;return a.i-b.i})}
function renderProviderList(){const list=$('providerList');list.innerHTML=providerEntries().map(({p,i})=>{const keyTag=p.api_key?'<span class="tag">pending key</span>':(p.has_api_key?'<span class="tag">key set</span>':'<span class="tag off">no key</span>');return `<div class="provider-item ${i===activeProvider?'active':''}" data-i="${i}"><strong>${escapeHtml(p.name||p.id)}</strong><span class="muted mono">${escapeHtml(p.id)}</span><br>${p.enabled?'<span class="tag">enabled</span>':'<span class="tag off">disabled</span>'}${keyTag}<span class="tag">${p.models?.length||0} models</span></div>`}).join('');document.querySelectorAll('.provider-item').forEach(el=>el.onclick=()=>{activeProvider=Number(el.dataset.i);renderAll()})}
function renderProviders(){renderProviderList();renderProviderForm();renderTestSelectors();renderModelTable();}
function checks(name,values,allowed){values=values||[];return `<div class="checks">${allowed.map(v=>`<label class="check"><input type="checkbox" name="${name}" value="${v}" ${values.includes(v)?'checked':''}><span>${v}</span></label>`).join('')}</div>`}
function checkedValues(name){return [...document.querySelectorAll(`input[name="${name}"]:checked`)].map(x=>x.value)}
function renderProviderForm(){const p=current(); if(!p){$('providerForm').innerHTML='<p>暂无通道</p>';return} const pendingKey=!!p.api_key;const keyPlaceholder=pendingKey?'已输入新 key，保存前会保留（不回显）':(p.has_api_key?'已保存；输入新 key 才会覆盖':'sk-...');$('providerForm').innerHTML=`<div class="grid"><div class="span6"><label>内部 ID</label><input id="pId" value="${escapeHtml(p.id)}"></div><div class="span6"><label>显示名</label><input id="pName" value="${escapeHtml(p.name)}"></div><div class="span4"><label>状态</label><select id="pEnabled"><option value="true" ${p.enabled?'selected':''}>启用</option><option value="false" ${!p.enabled?'selected':''}>禁用</option></select></div><div class="span4"><label>role</label><select id="pRole">${['primary','auto','fallback'].map(v=>`<option ${p.role===v?'selected':''}>${v}</option>`).join('')}</select></div><div class="span4"><label>priority</label><input id="pPriority" type="number" value="${escapeHtml(p.priority||100)}"></div><div class="span6"><label>OpenAI base URL</label><input id="pOpenAI" value="${escapeHtml(p.openai_base_url||'')}" placeholder="https://.../v1"></div><div class="span6"><label>Anthropic base URL</label><input id="pAnthropic" value="${escapeHtml(p.anthropic_base_url||'')}" placeholder="https://.../v1 或 /anthropic"></div><div class="span6"><label>API Key（留空不更新）</label><input id="pKey" type="password" placeholder="${escapeHtml(keyPlaceholder)}"></div><div class="span6"><label>models_endpoint</label><input id="pModelsEndpoint" value="${escapeHtml(p.models_endpoint||'/models')}" placeholder="/models 或 manual"></div><div class="span12"><label>protocols</label>${checks('pProtocols',p.protocols,['anthropic_messages','openai_chat_completions'])}</div><div class="span12"><label>supported CLIs</label>${checks('pClis',p.supported_clis,['claude','codex','opencode','agy'])}</div><div class="span12 check"><input id="pUpdateCreds" type="checkbox" ${p.update_credentials?'checked':''}><span>保存时更新凭据（stable 写 credentials.sh；preview 写 secret backend；需要填写 API Key）</span></div><div class="span12 check"><input id="pDefault" type="checkbox" ${state.provider_default===p.id?'checked':''}><span>设为默认 provider</span></div></div><div class="btns"><button id="saveProviderForm">保存通道修改</button></div>`;bindProviderForm()}
function bindProviderForm(){['pId','pName','pEnabled','pRole','pPriority','pOpenAI','pAnthropic','pModelsEndpoint'].forEach(id=>$(id).oninput=syncProvider);const keyEl=$('pKey');keyEl.oninput=()=>{keyEl.dataset.touched='1';syncProvider()};$('pUpdateCreds').onchange=syncProvider;$('pDefault').onchange=()=>{syncProvider(); if($('pDefault').checked) state.provider_default=current().id; renderProviders();};document.querySelectorAll('input[name="pProtocols"],input[name="pClis"]').forEach(x=>x.onchange=syncProvider);const save=$('saveProviderForm');if(save)save.onclick=()=>{syncProvider();setSection('save');toast('通道修改已暂存，生成保存预览后再写入')}}
function syncProvider(){const p=current(); if(!p)return; const old=p.id;touchProvider(old);const keyEl=$('pKey');const updateEl=$('pUpdateCreds');p.id=$('pId').value.trim()||p.id;if(p.id!==old){touchedProviders.delete(old);touchProvider(p.id)}p.name=$('pName').value.trim()||p.id;p.enabled=$('pEnabled').value==='true';p.role=$('pRole').value;p.priority=Number($('pPriority').value||100);p.openai_base_url=$('pOpenAI').value.trim();p.anthropic_base_url=$('pAnthropic').value.trim();p.models_endpoint=$('pModelsEndpoint').value.trim()||'/models';p.protocols=checkedValues('pProtocols');p.supported_clis=checkedValues('pClis');const keyText=keyEl?keyEl.value.trim():'';const keyTouched=keyEl?.dataset?.touched==='1';if(keyText){p.api_key=keyText;p.pending_api_key=true;p.has_api_key=true;if(updateEl)updateEl.checked=true}else if(keyTouched){p.api_key='';p.pending_api_key=false}p.update_credentials=!!(updateEl&&updateEl.checked);if(state.provider_default===old)state.provider_default=p.id;renderProviderList();renderTestSelectors();}
function derivedAliases(base,p){const ids=(base||[]).map(x=>String(x||''));const tails=ids.map(id=>id.toLowerCase().split('/').pop());const aliases=[];if(tails.some(id=>id.startsWith('claude-sonnet-4-')||id.startsWith('claude-sonnet-4.')))aliases.push('claude-sonnet-4-6');if(tails.some(id=>id.startsWith('claude-opus-4-')||id.startsWith('claude-opus-4.')))aliases.push('claude-opus-4-6');const ident=String([p?.id,p?.name,p?.label,p?.provider_profile].filter(Boolean).join(' ')).toLowerCase();const anthropic=String(p?.anthropic_base_url||p?.default_anthropic_base_url||'').toLowerCase();if((anthropic.includes('xiaomimimo.com')||ident.includes('mimo')||ident.includes('xiaomi'))&&!ident.includes('openrouter')){['mimo-v2.5-pro','mimo-v2.5'].forEach(id=>{if(ids.includes(id)&&!ids.includes(`${id}[1m]`))aliases.push(`${id}[1m]`)})}return aliases}
function providerModels(p){p=p||{};const map=new Map();const hiddenLower=new Set((p.hidden_models||[]).map(x=>String(x||'').toLowerCase()));const baseRows=(p.models||[]).filter(r=>r&&r.id&&r.source!=='hidden');baseRows.forEach(r=>map.set(r.id,{...r,visible:r.visible!==false&&!hiddenLower.has(String(r.id).toLowerCase()),capabilities:{...(r.capabilities||{})}}));if(!baseRows.length){(p.fallback_models||[]).forEach(id=>{if(!map.has(id))map.set(id,{id,source:'fallback',visible:!hiddenLower.has(String(id).toLowerCase()),favorite:false,capabilities:defaultCaps(id)})})}const baseIds=[...map.keys()];derivedAliases(baseIds.filter(id=>!hiddenLower.has(String(id).toLowerCase())),p).forEach(id=>{if(!map.has(id))map.set(id,{id,source:'derived_alias',visible:!hiddenLower.has(String(id).toLowerCase()),favorite:false,capabilities:defaultCaps(id)})});(p.extra_models||[]).forEach(id=>{if(!map.has(id))map.set(id,{id,source:'extra',visible:!hiddenLower.has(String(id).toLowerCase()),favorite:false,capabilities:defaultCaps(id)})});(p.hidden_models||[]).forEach(id=>{[...map.keys()].forEach(key=>{if(String(key).toLowerCase()===String(id).toLowerCase())map.get(key).visible=false})});return [...map.values()].sort((a,b)=>a.id.localeCompare(b.id))}
function defaultCaps(id){const l=String(id||'').toLowerCase();return {text:true,vision:['mimo-v2.5','mimo-v2-omni','k2.6','k2.6-code-preview','kimi-k2.5','qwen3.6-plus','qwen3.6-flash','qwen3.5-plus'].includes(l)||l.startsWith('claude-')||l.startsWith('gemini-'),tool_use:/^(claude|gpt|o|qwen|kimi|glm|minimax|gemini)/.test(l),reasoning:/gpt-5|qwen3|kimi-k2|glm-5|deepseek|claude/.test(l),long_context:/1m|long|qwen3|kimi-k2|gpt-5|claude/.test(l),cache_sensitive:/^(qwen|kimi|k2\.|glm|deepseek|minimax|mimo)/.test(l)}}
function providerCurrentIds(p){return new Set(providerModels(p).map(r=>r.id))}
function staleHiddenModels(p){const ids=providerCurrentIds(p);return [...new Set([...(p.stale_hidden_models||[]),...(p.hidden_models||[]).filter(id=>!ids.has(id))])]}
function cleanupStaleHidden(p){const stale=staleHiddenModels(p);const doomed=new Set(stale);p.hidden_models=(p.hidden_models||[]).filter(x=>!doomed.has(x));p.stale_hidden_models=[];return stale.length}
function cleanupAllStaleHidden(){let total=0;(state.providers||[]).forEach(p=>{total+=cleanupStaleHidden(p)});renderProviders();toast(total?`已移除 ${total} 条未匹配隐藏规则`:'没有需要移除的未匹配隐藏规则')}
function staleRouteModels(p){const approved=(p.approved_route_models&&p.approved_route_models.length?p.approved_route_models:(p.fallback_models||[]));const remote=new Set((p.models||[]).filter(r=>r&&r.id).map(r=>String(r.id)));const extras=new Set((p.extra_models||[]).map(x=>String(x)));return [...new Set(approved.filter(id=>id&&!remote.has(String(id))&&!extras.has(String(id))))]}
function renderStaleRouteBox(p){const box=$('staleRouteBox');if(!box)return;const stale=staleRouteModels(p);if(!stale.length){box.innerHTML='<strong>缺失旧 route</strong><p class="muted">当前没有“本地已批准但本次拉取未返回”的旧 route。</p>';return}const armed=staleCleanupProviders.has(p.id);box.innerHTML=`<strong>缺失旧 route（默认保留）</strong><p class="muted">这些模型在本地已批准 routes 里，但不在当前拉取到的模型列表里。默认不会删除；如果勾选“拉取后自动标记”，本页后续拉取会自动标记清理。避免上游 /models 抖动或 New API 临时关闭导致下游模型被清空。</p><div class="chips">${stale.slice(0,24).map(m=>`<span class="chip">${escapeHtml(m)}</span>`).join('')}${stale.length>24?`<span class="chip">+${stale.length-24}</span>`:''}</div><div class="btns"><button id="armStaleRouteCleanup" class="ghost">${armed?'已标记：保存时清理这些旧 route':'显式标记保存时清理这些旧 route'}</button></div>`;$('armStaleRouteCleanup').onclick=()=>{staleCleanupProviders.add(p.id);touchProvider(p.id);renderStaleRouteBox(p);toast(`已标记 ${p.id}：下次写入预览 DB 会清理 ${stale.length} 条缺失旧 route`)}}
function visibleModelsForProvider(providerId,{visionFirst=false,includeHidden=false,enabledOnly=false}={}){let rows=[];(state.providers||[]).forEach(p=>{if(providerId&&p.id!==providerId)return;if(enabledOnly&&p.enabled===false)return;providerModels(p).forEach(r=>{if(!includeHidden&&r.visible===false)return;rows.push({...r,provider_id:p.id,provider_name:p.name||p.id,capabilities:{...(r.capabilities||defaultCaps(r.id))}})})});const seen=new Set();rows=rows.filter(r=>{const key=(providerId?'':r.provider_id+'::')+r.id;if(seen.has(key))return false;seen.add(key);return true});rows.sort((a,b)=>{const av=!!(a.capabilities||{}).vision,bv=!!(b.capabilities||{}).vision;if(visionFirst&&av!==bv)return av?-1:1;return (a.provider_id+' '+a.id).localeCompare(b.provider_id+' '+b.id)});return rows}
function providerOptions(selected,{blankLabel='请选择通道',auto=false,enabledOnly=false}={}){const opts=[];const providers=providerEntries().filter(({p})=>!enabledOnly||p.enabled||p.id===selected);if(auto)opts.push(`<option value="" ${!selected?'selected':''}>自动选择 provider</option>`);else opts.push(`<option value="" ${!selected?'selected':''}>${escapeHtml(blankLabel)}</option>`);opts.push(...providers.map(({p})=>{const disabled=p.enabled?'':' [disabled 当前配置值]';return `<option value="${escapeHtml(p.id)}" ${p.id===selected?'selected':''}>${escapeHtml(p.name||p.id)} / ${escapeHtml(p.id)}${disabled}</option>`}));if(selected&&!state.providers.some(p=>p.id===selected))opts.push(`<option value="${escapeHtml(selected)}" selected>当前配置值：${escapeHtml(selected)}</option>`);return opts.join('')}
function modelOptionValue(providerId,row){return providerId?row.id:`${row.provider_id}::${row.id}`}
function decodeModelSelection(value,currentProvider){const text=String(value||'');if(!text)return{provider_id:currentProvider||'',model:''};const marker='::';if(text.includes(marker)){const [provider_id,...rest]=text.split(marker);return{provider_id,model:rest.join(marker)}}return{provider_id:currentProvider||'',model:text}}
function modelOptions(providerId,selected,{visionFirst=false,auto=false,defaultModels=[],enabledOnly=false,selectedProvider=''}={}){const rows=visibleModelsForProvider(providerId,{visionFirst,enabledOnly});let opts=[];if(auto)opts.push(`<option value="" ${!selected?'selected':''}>自动路线${defaultModels.length?'：'+escapeHtml(defaultModels.join(' / ')):''}</option>`);else opts.push(`<option value="" ${!selected?'selected':''}>请选择模型</option>`);let matched=false;opts.push(...rows.map(r=>{const value=modelOptionValue(providerId,r);const label=providerId?r.id:`${r.provider_id} / ${r.id}`;const tag=(r.capabilities||{}).vision?' [vision]':'';const isSelected=providerId?r.id===selected:((selectedProvider&&r.provider_id===selectedProvider&&r.id===selected)||(!selectedProvider&&r.id===selected));if(isSelected)matched=true;return `<option value="${escapeHtml(value)}" ${isSelected?'selected':''}>${escapeHtml(label)}${tag}</option>`}));if(selected&&!matched)opts.push(`<option value="${escapeHtml(selected)}" selected>当前配置值：${escapeHtml(selected)}</option>`);return opts.join('')}
function renderStaleHiddenBox(p){const stale=staleHiddenModels(p);const box=$('staleHiddenBox');if(!box)return;if(!stale.length){box.innerHTML='<strong>未匹配隐藏规则（hidden_models）</strong><p class="muted">当前没有“暂时匹配不到模型行”的隐藏规则。</p>';return}box.innerHTML=`<strong>未匹配隐藏规则（hidden_models）</strong><p class="muted">这些只是当前通道 hidden_models 里的隐藏规则，暂时没有匹配到当前模型行；不等于远端不存在，也不等于 route 待删除。移除后如果模型仍在远端或 approved routes 里，会重新显示出来。</p><div class="chips">${stale.map(m=>`<span class="chip">${escapeHtml(m)} <button data-stale-rm="${escapeHtml(m)}">移除记录</button></span>`).join('')}</div><div class="btns"><button id="clearStaleHidden" class="ghost">移除当前通道未匹配隐藏规则</button></div>`;document.querySelectorAll('[data-stale-rm]').forEach(b=>b.onclick=()=>{p.hidden_models=(p.hidden_models||[]).filter(x=>x!==b.dataset.staleRm);p.stale_hidden_models=(p.stale_hidden_models||[]).filter(x=>x!==b.dataset.staleRm);renderModelTable()});$('clearStaleHidden').onclick=()=>{const count=cleanupStaleHidden(p);renderModelTable();toast(count?`已移除 ${count} 条当前通道未匹配隐藏规则`:'没有需要移除的未匹配隐藏规则')}}
function renderModelTable(){const p=current(); if(!p)return;const q=($('modelSearch')?.value||'').toLowerCase();const rows=providerModels(p).filter(r=>r.id.toLowerCase().includes(q));const extras=p.extra_models||[];$('modelChips').innerHTML=`<strong>当前通道补充模型库（extra_models）</strong><p class="muted">这些模型是手动补充到当前 provider 的可用模型，会参与当前通道路由；不是待删除列表，也不是全局模型池。</p><div class="chips">${extras.length?extras.map(m=>`<span class="chip">${escapeHtml(m)}${editingExtraModels?` <button data-rm-extra="${escapeHtml(m)}">从补充库移除</button>`:''}</span>`).join(''):'<span class="muted">当前通道暂无手动补充模型。</span>'}</div><div class="btns"><button id="toggleExtraEdit" class="ghost">${editingExtraModels?'完成编辑':'编辑补充模型库'}</button></div><div id="staleRouteBox"></div>`;$('toggleExtraEdit').onclick=()=>{editingExtraModels=!editingExtraModels;renderModelTable()};document.querySelectorAll('[data-rm-extra]').forEach(b=>b.onclick=()=>{p.extra_models=extras.filter(x=>x!==b.dataset.rmExtra);toast(`已从当前通道补充模型库移除 ${b.dataset.rmExtra}`);renderModelTable()});renderStaleRouteBox(p);renderStaleHiddenBox(p);$('modelTable').innerHTML=`<thead><tr><th>显示</th><th>模型</th><th>来源</th><th>收藏</th><th>text</th><th>vision</th><th>tool</th><th>reason</th><th>long</th><th>cache</th></tr></thead><tbody>${rows.map(r=>{const c=r.capabilities||{};return `<tr><td><input type="checkbox" data-model="${escapeHtml(r.id)}" data-field="visible" ${r.visible?'checked':''}></td><td class="mono">${escapeHtml(r.id)}</td><td><span class="tag ${r.visible?'':'off'}">${escapeHtml(r.source||'manual')}</span></td><td><input type="checkbox" data-model="${escapeHtml(r.id)}" data-field="favorite" ${r.favorite?'checked':''}></td>${['text','vision','tool_use','reasoning','long_context','cache_sensitive'].map(k=>`<td><input type="checkbox" data-model="${escapeHtml(r.id)}" data-cap="${k}" ${c[k]?'checked':''}></td>`).join('')}</tr>`}).join('')}</tbody>`;document.querySelectorAll('#modelTable input').forEach(x=>x.onchange=onModelToggle);renderTestSelectors();renderFallback();renderRuntime()}
function onModelToggle(e){const p=current();const model=e.target.dataset.model;let row=providerModels(p).find(r=>r.id===model)||{id:model,source:'hidden',visible:!(p.hidden_models||[]).includes(model),favorite:false,capabilities:defaultCaps(model)};row.policy_touched=true;if(e.target.dataset.field==='visible'){row.visible=e.target.checked;p.hidden_models=e.target.checked?(p.hidden_models||[]).filter(x=>x!==model):[...(p.hidden_models||[]).filter(x=>x!==model),model]}else if(e.target.dataset.field==='favorite'){row.favorite=e.target.checked}else if(e.target.dataset.cap){row.capabilities=row.capabilities||{};row.capabilities[e.target.dataset.cap]=e.target.checked}p.model_capabilities=p.model_capabilities||{};p.model_capabilities[model]=row.capabilities;p.models=(p.models||[]).filter(r=>r.id!==model).concat(row);renderTestSelectors();renderFallback();renderRuntime()}
function renderTestSelectors(){const tp=$('testProvider');if(!tp)return;tp.innerHTML=providerEntries().map(({p,i})=>`<option value="${i}">${escapeHtml(p.name||p.id)}${p.enabled?'':' [disabled]'}</option>`).join('');tp.value=String(activeProvider);tp.onchange=()=>{activeProvider=Number(tp.value);renderAll()};const models=providerModels(current()||{});$('testModel').innerHTML=models.map(r=>`<option>${escapeHtml(r.id)}</option>`).join('')}
function syncFallback(){state.rescue=state.rescue||{};state.rescue.fallback_model=$('rescueModel').value.trim();state.rescue.fallback_cli=$('rescueCli').value;state.rescue.hot_fallback_enabled=$('rescueHot').checked;state.vision_sidecar=state.vision_sidecar||{};state.vision_sidecar.enabled=$('visionEnabled').checked;state.vision_sidecar.provider_id=$('visionProvider').value.trim();state.vision_sidecar.model=$('visionModel').value.trim();state.vision_sidecar.candidates=[...document.querySelectorAll('[data-vision-candidate]')].map(row=>({provider_id:row.querySelector('[data-vc-provider]').value.trim(),model:row.querySelector('[data-vc-model]').value.trim()})).filter(x=>x.provider_id&&x.model)}
function bindVisionCandidateRow(row){const provider=row.querySelector('[data-vc-provider]');const model=row.querySelector('[data-vc-model]');provider.onchange=()=>{model.innerHTML=modelOptions(provider.value,'',{visionFirst:true});syncFallback()};model.onchange=syncFallback;row.querySelector('[data-vc-remove]').onclick=()=>{row.remove();syncFallback()}}
function renderVisionCandidates(candidates){const wrap=$('visionCandidates');wrap.innerHTML=(candidates||[]).map((item,i)=>{const provider=item.provider_id||item.provider||'';const model=item.model||item.vision_model||'';return `<div class="grid span12" data-vision-candidate="1"><div class="span5"><label>候选 ${i+1} provider</label><select data-vc-provider>${providerOptions(provider,{blankLabel:'请选择通道'})}</select></div><div class="span5"><label>候选 ${i+1} model</label><select data-vc-model>${modelOptions(provider,model,{visionFirst:true})}</select></div><div class="span2"><label>&nbsp;</label><button class="ghost" data-vc-remove>移除</button></div></div>`}).join('');document.querySelectorAll('[data-vision-candidate]').forEach(bindVisionCandidateRow)}
function renderFallback(){const r=state.rescue||{},v=state.vision_sidecar||{};$('rescueModel').value=r.fallback_model||'';$('rescueCli').value=r.fallback_cli||'';$('rescueHot').checked=!!r.hot_fallback_enabled;$('visionEnabled').checked=v.enabled!==false;const provider=v.provider_id||v.provider||'';const model=v.model||v.vision_model||'';$('visionProvider').innerHTML=providerOptions(provider,{blankLabel:'请选择 vision 通道'});$('visionProvider').value=provider;$('visionModel').innerHTML=modelOptions(provider,model,{visionFirst:true});$('visionModel').value=model;renderVisionCandidates(v.candidates||[]);['rescueModel','rescueCli','rescueHot','visionEnabled','visionModel'].forEach(id=>$(id).oninput=syncFallback);$('visionProvider').onchange=()=>{$('visionModel').innerHTML=modelOptions($('visionProvider').value,'',{visionFirst:true});syncFallback()};$('rescueHot').onchange=syncFallback;$('visionEnabled').onchange=syncFallback;$('addVisionCandidate').onclick=()=>{const provider=(state.providers[0]||{}).id||'';const model=(visibleModelsForProvider(provider,{visionFirst:true})[0]||{}).id||'';const list=[...(state.vision_sidecar?.candidates||[]),{provider_id:provider,model:model}];state.vision_sidecar=state.vision_sidecar||{};state.vision_sidecar.candidates=list;renderVisionCandidates(list);syncFallback()}}
function opencodeOverrides(){state.opencode=state.opencode||{};state.opencode.agent_models=state.opencode.agent_models||{};return state.opencode.agent_models}
function opencodeRoster(){state.opencode=state.opencode||{};state.opencode.agent_roster=state.opencode.agent_roster||{};return state.opencode.agent_roster}
function opencodeOverrideEntries(){const overrides=opencodeOverrides();return Object.entries(overrides).filter(([,v])=>v&&v.model)}
function opencodeDefaults(){const map={};(state.opencode.agent_catalog||[]).forEach((row,i)=>{map[row.agent]={enabled:true,preset:row.preset||categoryPreset(row.category),priority:row.priority||((i+1)*10),custom:false}});return map}
function categoryPreset(category){const c=String(category||'');if(c==='Vision')return 'vision';if(c==='探索')return 'explore';if(c==='找茬')return 'bughunt';if(c==='审查')return 'reviewer';if(c==='执行')return 'executor';return 'builder'}
function rosterEntry(agent,row={}){const defaults=opencodeDefaults();return {...(defaults[agent]||{enabled:true,preset:row.preset||categoryPreset(row.category),priority:999,custom:!!row.custom}),...(opencodeRoster()[agent]||{})}}
function setOpencodeOverride(agent,provider,model){const overrides=opencodeOverrides();if(model){overrides[agent]={model};if(provider)overrides[agent].provider_id=provider}else{delete overrides[agent]}}
function persistRosterEntry(agent,row,patch={}){const roster=opencodeRoster();const defaults=opencodeDefaults();const base=rosterEntry(agent,row);const next={...base,...patch};const def=defaults[agent]||{};const providerMeaningful=!!next.provider_id&&(!!next.model||!!next.custom);const keep=!!next.custom||next.enabled===false||next.preset!==def.preset||Number(next.priority||0)!==Number(def.priority||0)||providerMeaningful||!!next.model||!!next.description||!!next.prompt;if(!keep){delete roster[agent];return}const payload={preset:next.preset||row.preset||categoryPreset(row.category),enabled:next.enabled!==false,priority:Number(next.priority||def.priority||999)};if(next.custom)payload.custom=true;if(providerMeaningful)payload.provider_id=next.provider_id;if(next.model)payload.model=next.model;if(next.description)payload.description=next.description;if(next.prompt)payload.prompt=next.prompt;roster[agent]=payload}
function setRosterEnabled(agent,row,enabled){persistRosterEntry(agent,row,{enabled})}
function opencodeAllRows(){const base=(state.opencode.agent_catalog||[]).map(row=>({...row,custom:false}));const seen=new Set(base.map(row=>row.agent));Object.entries(opencodeRoster()).forEach(([agent,entry])=>{if(seen.has(agent))return;base.push({agent,route_key:agent,category:presetLabel(entry.preset),preset:entry.preset||'explore',priority:entry.priority||999,default_models:[],custom:true})});return base.sort((a,b)=>Number(rosterEntry(a.agent,a).priority||999)-Number(rosterEntry(b.agent,b).priority||999)||a.agent.localeCompare(b.agent))}
function presetLabel(preset){return {builder:'执行/协调',executor:'执行',explore:'探索',bughunt:'找茬',vision:'Vision',reviewer:'审查',spec:'Spec',fixer:'执行'}[preset]||preset||'custom'}
function customAgentId(preset){const existing=new Set(opencodeAllRows().map(row=>row.agent));let i=1;let id='';do{id=`mobius-${preset}-custom-${i++}`}while(existing.has(id));return id}
function addCustomAgent(preset){const agent=customAgentId(preset);opencodeRoster()[agent]={enabled:true,custom:true,preset,priority:900+Object.keys(opencodeRoster()).length};renderOpencodeAgents();toast(`已添加 ${agent}`)}
function syncRuntime(){state.runtime=state.runtime||{};state.opencode=state.opencode||{};state.runtime.preferred_cli=$('preferredCli').value;state.runtime.coding_preset_model=$('codingModel').value.trim();state.opencode.default_profile=$('opencodeProfile').value;state.opencode.agent_models=Object.fromEntries(opencodeOverrideEntries());state.opencode.agent_roster={...opencodeRoster()}}
function renderOpencodeSummary(){const box=$('opencodeOverrideSummary');if(!box)return;const rows=opencodeAllRows();const enabled=rows.filter(row=>rosterEntry(row.agent,row).enabled!==false).length;const count=opencodeOverrideEntries().length;const custom=rows.filter(row=>rosterEntry(row.agent,row).custom).length;const profile=state.opencode.default_profile||'agent';box.innerHTML=`<div class="oc-metric"><span class="muted">Profile</span><strong>${escapeHtml(profile)}</strong><span class="mono">Lite Pro Roster</span></div><div class="oc-metric"><span class="muted">Enabled agents</span><strong>${enabled}/${rows.length}</strong><span class="mono">进入 session-local opencode.json</span></div><div class="oc-metric"><span class="muted">Agent overrides</span><strong>${count}/${rows.length}</strong><span class="mono">Auto 不写 agent_models</span></div><div class="oc-metric"><span class="muted">Custom agents</span><strong>${custom}</strong><span class="mono">按 preset 继承 prompt/permission</span></div>`}
function opencodeFilterMatches(row,overridden){const entry=rosterEntry(row.agent,row);if(opencodeOnlyOverridden&&!overridden&&entry.enabled!==false&&!entry.custom)return false;if(opencodeAgentFilter==='all')return true;if(opencodeAgentFilter==='enabled')return entry.enabled!==false;if(opencodeAgentFilter==='custom')return !!entry.custom;if(opencodeAgentFilter==='execute')return ['builder','executor','fixer','spec'].includes(entry.preset)||String(row.category||'').startsWith('执行');if(opencodeAgentFilter==='explore')return entry.preset==='explore'||row.category==='探索';if(opencodeAgentFilter==='bughunt')return entry.preset==='bughunt'||row.category==='找茬';if(opencodeAgentFilter==='vision')return entry.preset==='vision'||row.category==='Vision';if(opencodeAgentFilter==='review')return entry.preset==='reviewer'||row.category==='审查';return true}
function renderOpencodeFilters(){const wrap=$('opencodeAgentFilters');if(!wrap)return;const filters=[['all','全部'],['enabled','已启用'],['custom','自定义'],['execute','执行/协调'],['explore','探索'],['bughunt','找茬'],['vision','Vision'],['review','审查']];wrap.innerHTML=`${filters.map(([id,label])=>`<button class="ghost ${opencodeAgentFilter===id?'active':''}" data-oc-filter="${id}">${label}</button>`).join('')}<label class="check"><input id="ocOnlyOverridden" type="checkbox" ${opencodeOnlyOverridden?'checked':''}><span>只看改动项</span></label><button class="ghost" data-oc-add="vision">+ Add Vision Agent</button><button class="ghost" data-oc-add="executor">+ Add Executor Agent</button><button class="ghost" data-oc-add="explore">+ Add Explore Agent</button><button class="ghost" id="ocClearAll">全部自动</button>`;document.querySelectorAll('[data-oc-filter]').forEach(btn=>btn.onclick=()=>{opencodeAgentFilter=btn.dataset.ocFilter;renderOpencodeAgents()});document.querySelectorAll('[data-oc-add]').forEach(btn=>btn.onclick=()=>addCustomAgent(btn.dataset.ocAdd));$('ocOnlyOverridden').onchange=()=>{opencodeOnlyOverridden=$('ocOnlyOverridden').checked;renderOpencodeAgents()};$('ocClearAll').onclick=()=>{state.opencode.agent_models={};state.opencode.agent_roster={};syncRuntime();renderOpencodeAgents();toast('OpenCode roster 已恢复默认自动路线')}}
function renderOpencodeAgents(){const table=$('opencodeAgents');if(!table)return;const overrides=opencodeOverrides();renderOpencodeSummary();renderOpencodeFilters();const rows=opencodeAllRows();const visible=rows.filter(row=>{const entry=rosterEntry(row.agent,row);const overridden=!!(overrides[row.agent]&&overrides[row.agent].model)||entry.enabled===false||entry.custom;return opencodeFilterMatches(row,overridden)});const presetOptions=(selected)=>['builder','executor','explore','bughunt','vision','reviewer','spec','fixer'].map(p=>`<option value="${p}" ${p===selected?'selected':''}>${p}</option>`).join('');const body=visible.length?visible.map(row=>{const entry=rosterEntry(row.agent,row);const ov=overrides[row.agent]||{};const provider=ov.provider_id||entry.provider_id||'';const model=ov.model||entry.model||'';const enabled=entry.enabled!==false;const changed=!!model||!enabled||!!entry.custom;return `<tr data-oc-agent="${escapeHtml(row.agent)}"><td><input class="oc-enabled" type="checkbox" data-oc-enabled ${enabled?'checked':''} ${row.agent==='mobius-builder-pro'?'disabled':''}></td><td class="mono">${escapeHtml(row.agent)}<br><span class="muted">${escapeHtml(row.route_key)}</span>${entry.custom?'<br><span class="tag">custom</span>':''}${changed?'<span class="tag">changed</span>':''}</td><td><select data-oc-preset ${entry.custom?'':'disabled'}>${presetOptions(entry.preset)}</select></td><td><input data-oc-priority type="number" value="${escapeHtml(entry.priority||999)}" style="max-width:86px"></td><td><select data-oc-provider>${providerOptions(provider,{auto:true,enabledOnly:true})}</select></td><td><select data-oc-model>${modelOptions(provider,model,{auto:true,defaultModels:row.default_models||[],visionFirst:(entry.preset==='vision'||row.category==='Vision'),enabledOnly:true,selectedProvider:provider})}</select></td><td class="mono default-route">${escapeHtml((row.default_models||[]).join(' / ')||'preset auto')}</td><td><button class="ghost" data-oc-reset>自动</button></td></tr>`}).join(''):'<tr><td colspan="8" class="empty-row">没有匹配的 agent</td></tr>';table.innerHTML=`<thead><tr><th>启用</th><th>Agent</th><th>Preset</th><th>Priority</th><th>Provider</th><th>Model</th><th>Default</th><th></th></tr></thead><tbody>${body}</tbody>`;document.querySelectorAll('[data-oc-agent]').forEach(tr=>{const agent=tr.dataset.ocAgent;const row=visible.find(r=>r.agent===agent);const entry=rosterEntry(agent,row);tr.querySelector('[data-oc-enabled]').onchange=(e)=>{setRosterEnabled(agent,row,e.target.checked);renderOpencodeSummary()};tr.querySelector('[data-oc-preset]').onchange=(e)=>{persistRosterEntry(agent,row,{preset:e.target.value});renderOpencodeAgents()};tr.querySelector('[data-oc-priority]').oninput=(e)=>{persistRosterEntry(agent,row,{priority:Number(e.target.value)});renderOpencodeSummary()};tr.querySelector('[data-oc-provider]').onchange=(e)=>{const sel=e.target;const modelSel=tr.querySelector('[data-oc-model]');modelSel.innerHTML=modelOptions(sel.value,modelSel.value,{auto:true,defaultModels:row.default_models||[],visionFirst:(entry.preset==='vision'||row.category==='Vision'),enabledOnly:true,selectedProvider:sel.value});setOpencodeOverride(agent,sel.value,tr.querySelector('[data-oc-model]').value);syncRuntime();renderOpencodeSummary()};tr.querySelector('[data-oc-model]').onchange=(e)=>{setOpencodeOverride(agent,tr.querySelector('[data-oc-provider]').value,e.target.value);syncRuntime();renderOpencodeSummary()};tr.querySelector('[data-oc-reset]').onclick=()=>{const roster=opencodeRoster();delete roster[agent];const overrides=opencodeOverrides();delete overrides[agent];syncRuntime();renderOpencodeAgents();toast(`${agent} 已恢复默认`)}})}
function renderRuntime(){state.runtime=state.runtime||{};state.opencode=state.opencode||{};$('preferredCli').value=state.runtime.preferred_cli||'opencode';$('codingModel').value=state.runtime.coding_preset_model||'';$('opencodeProfile').value=state.opencode.default_profile||'agent';$('preferredCli').oninput=syncRuntime;$('codingModel').oninput=syncRuntime;$('opencodeProfile').oninput=()=>{syncRuntime();renderOpencodeSummary()};renderOpencodeAgents()}
function assetRows(){const assets=state.session_assets||{};return Array.isArray(assets.rows)?assets.rows:[]}
function assetDetail(row,label){const wanted=String(label||'').toLowerCase();for(const item of (row.details||[])){if(String(item.label||'').toLowerCase()===wanted)return item.display||item.value||''}return ''}
function assetDetailsHtml(row){const details=Array.isArray(row.details)?row.details:[];const lines=details.map(item=>`<p><strong>${escapeHtml(item.label||'详情')}</strong>：<span class="mono">${escapeHtml(item.display||item.value||'-')}</span></p>`);const raw=row.technical_summary&&row.technical_summary!==row.summary?`<p><strong>原始说明</strong>：${escapeHtml(row.technical_summary)}</p>`:'';const key=`<p><strong>关闭 key</strong>：<span class="mono">${escapeHtml(row.disable_key||row.title||'-')}</span></p>`;return [...lines,raw,key].filter(Boolean).join('')}
function assetSearchHaystack(row){return [row.title,row.summary,row.technical_summary,row.cli_label,row.kind_label,row.group_label,row.origin_label,row.scope_label,row.disable_key,...((row.details||[]).map(d=>`${d.label} ${d.display||d.value}`))].join(' ').toLowerCase()}
function assetFilterButton(id,label,current,attr){const active=current===id;return `<button class="ghost ${active?'active':''}" aria-pressed="${active?'true':'false'}" ${attr}="${escapeHtml(id)}">${escapeHtml(label)}</button>`}
function uniqueTexts(values){return [...new Set((values||[]).map(v=>String(v||'').trim()).filter(Boolean))]}
function cloneAssetDisabledDefaults(){const source=(state.session_assets||{}).disabled_defaults||{};const result={skills:[],mcp:[],hooks:[]};for(const key of ['skills','mcp','hooks']){const values=Array.isArray(source[key])?source[key]:[];result[key]=[...new Set(values.map(x=>String(x||'').trim()).filter(Boolean))]}return result}
function ensureAssetDisabledDraft(){if(!assetDisabledDraft)assetDisabledDraft=cloneAssetDisabledDefaults();for(const key of ['skills','mcp','hooks']){if(!Array.isArray(assetDisabledDraft[key]))assetDisabledDraft[key]=[]}return assetDisabledDraft}
function assetDisabledKind(kind){return kind==='mcp'?'mcp':(kind==='hooks'?'hooks':'skills')}
function assetKindLabel(kind){return kind==='mcp'?'MCP 服务':(kind==='hooks'?'自动钩子':'技能')}
function assetIsDefaultDisabled(row){const kind=assetDisabledKind(row.kind);const key=String(row.disable_key||row.title||'').trim();return !!key&&ensureAssetDisabledDraft()[kind].includes(key)}
function setAssetDefaultDisabled(row,checked){const kind=assetDisabledKind(row.kind);const key=String(row.disable_key||row.title||'').trim();if(!key)return;const draft=ensureAssetDisabledDraft();draft[kind]=draft[kind].filter(x=>x!==key);if(checked)draft[kind].push(key);draft[kind]=[...new Set(draft[kind])].sort()}
function assetTomlString(value){return String(value||'').replaceAll('\\','\\\\').replaceAll('"','\\"')}
function assetArrayToml(values){return `[${[...new Set((values||[]).map(x=>String(x||'').trim()).filter(Boolean))].sort().map(v=>`"${assetTomlString(v)}"`).join(', ')}]`}
function renderAssetPreferenceSnippet(){const assets=state.session_assets||{};const defaults=assets.launch_defaults||{};const draft=ensureAssetDisabledDraft();const snippet=[`[launch.defaults]`,`caveman_mode = "${assetTomlString(defaults.caveman_mode||'enable')}"`,`nsr_mode = "${assetTomlString(defaults.nsr_mode||'enable')}"`,`agent_pack = "${assetTomlString(defaults.agent_pack||'none')}"`,`bypass = ${defaults.bypass===false?'false':'true'}`,'',`[session_surfaces.disabled]`,`skills = ${assetArrayToml(draft.skills)}`,`mcp = ${assetArrayToml(draft.mcp)}`,`hooks = ${assetArrayToml(draft.hooks)}`].join('\n');$('assetPreferenceSnippet').textContent=snippet;return snippet}
function bindAssetPreferenceButtons(){const copy=$('copyAssetPrefs');const reset=$('resetAssetPrefs');if(copy)copy.onclick=async()=>{const snippet=renderAssetPreferenceSnippet();try{await navigator.clipboard.writeText(snippet);toast('偏好片段已复制')}catch(_err){toast('无法访问剪贴板，片段已显示在页面')}};if(reset)reset.onclick=()=>{assetDisabledDraft=cloneAssetDisabledDefaults();renderSessionAssets();toast('已恢复为当前 preferences.toml 状态')}}
function renderAssetManagedRoots(){const box=$('assetManagedRoots');if(!box)return;const roots=(state.session_assets||{}).managed_roots||[];const visible=Array.isArray(roots)?roots.filter(Boolean):[];if(!visible.length){box.innerHTML='<div class="asset-source-mini asset-source-intro"><strong>MMS 动态来源</strong><p class="muted">当前没有解析到动态 skill/MCP 根；请查看单卡高级信息。</p></div>';return}const rootCard=(root)=>{const exists=!!root.exists;const count=Number(root.skill_count||0);const real=root.real_path&&root.real_path!==root.path?`<details class="asset-source-real"><summary>真实路径</summary><p class="mono">${escapeHtml(root.real_path)}</p></details>`:'';return `<div class="asset-source-mini ${exists?'':'is-missing'}"><div class="asset-source-head"><strong class="asset-source-title">${escapeHtml(root.name||'-')}</strong><span class="tag ${exists?'':'off'}">${escapeHtml(root.surface||'Skill')}</span></div><p class="mono asset-source-path">${escapeHtml(root.path||'-')}</p><div class="asset-source-foot"><span class="tag ${exists?'':'off'}">${exists?'已解析':'未找到'}</span><span class="muted">${escapeHtml(root.root_kind||'来源未知')}${count?` · ${count} 个 skill`:''}</span></div>${real}</div>`};box.innerHTML=`<div class="asset-source-mini asset-source-intro"><div class="asset-source-head"><strong>MMS 动态来源</strong><span class="tag">${visible.length} 个根</span></div><p class="muted">安装版和开发版都看这里：这里展示当前 resolver 实际选中的 vendor / agent-pack / MCP 根；启动 session 时再软链到隔离 HOME。</p></div>${visible.map(rootCard).join('')}`}
function assetCliViews(){const assets=state.session_assets||{};return Array.isArray(assets.cli_views)?assets.cli_views:[]}
function assetCliChip(label,value,cls=''){return `<span class="tag ${cls}">${escapeHtml(label)} ${escapeHtml(value)}</span>`}
function assetPanelTag(panel){const counts=panel.scope_counts||{};const detail=panel.id==='summary'?'启动摘要':`默认 ${counts.always||0} / 开关 ${Number(counts.caveman||0)+Number(counts.nsr||0)+Number(counts.ecc||0)+Number(counts.omc||0)}`;return `<span class="tag">${escapeHtml(panel.label||panel.id)}：${escapeHtml(detail)}</span>`}
function renderAssetConfirmMap(){const box=$('assetConfirmMap');if(!box)return;const ref=(state.session_assets||{}).confirm_reference||{};const panels=Array.isArray(ref.panels)?ref.panels:[];const actions=Array.isArray(ref.actions)?ref.actions:[];const constraints=Array.isArray(ref.constraints)?ref.constraints:[];if(!panels.length&&!actions.length){box.innerHTML='';box.classList.add('hide');return}box.classList.remove('hide');box.innerHTML=`<div class="asset-confirm-head"><div><h3>${escapeHtml(ref.title||'TUI 确认页对照')}</h3><p class="muted">WebUI 和 TUI 使用同一个 preview catalog：这里先解释面板、快捷键和约束，再按 CLI 展开实际 skills / MCP / hooks。常用键：Enter / ←/→ / D / Space / Tab / C / N / T / E / X。</p></div><span class="tag">read-only mirror</span></div><div class="asset-confirm-grid"><div class="asset-confirm-block"><h4>面板</h4><div class="asset-confirm-panels">${panels.map(p=>`<span class="tag">${escapeHtml(p.label||p.id)}</span>`).join('')}</div><p class="muted">${escapeHtml((panels[0]||{}).description||'摘要显示启动参数，其它面板显示能力 surface。')}</p></div><div class="asset-confirm-block"><h4>快捷键</h4><div class="asset-confirm-actions">${actions.map(a=>`<span class="tag" title="${escapeHtml(a.description||'')}">${escapeHtml(a.key||'-')} · ${escapeHtml(a.label||'')}</span>`).join('')}</div></div></div><div class="asset-confirm-block"><h4>约束</h4><div class="asset-confirm-constraints">${constraints.map(item=>`<p>${escapeHtml(item)}</p>`).join('')}</div></div>`}
function renderAssetCliSources(view){const sources=Array.isArray(view.global_sources)?view.global_sources:[];const visible=sources.filter(src=>src&&((src.count||0)>0||src.exists));if(!visible.length)return '<p class="asset-cli-sample">没有检测到可展示的全局来源；本 CLI 主要看 MMS 动态注入。</p>';const sourceHtml=(src)=>{const items=Array.isArray(src.items)&&src.items.length?`<p class="asset-cli-sample">示例：${escapeHtml(src.items.slice(0,6).join(' / '))}${src.count>6?' ...':''}</p>`:'';return `<div class="asset-cli-source"><strong>${escapeHtml(src.label||src.surface_label||'全局来源')}</strong><span class="tag ${src.exists?'':'off'}">${src.count||0}</span><p class="mono">${escapeHtml(src.path||'-')}</p>${items}</div>`};const first=visible.slice(0,3).map(sourceHtml).join('');const rest=visible.slice(3);return first+(rest.length?`<details class="asset-details"><summary>展开全部全局来源（${visible.length}）</summary><div class="asset-detail-grid">${visible.map(sourceHtml).join('')}</div></details>`:'')}
function renderAssetCliControls(view){const controls=Array.isArray(view.controls)?view.controls:[];if(!controls.length)return '<span class="tag off">TUI 确认页无额外控制项</span>';return controls.slice(0,8).map(item=>`<span class="tag" title="${escapeHtml(item.hint||'')}">${escapeHtml(item.key?item.key+' · ':'')}${escapeHtml(item.label||item.id)}：${escapeHtml(item.state||'-')}</span>`).join('')}
function renderAssetCliOverview(){const box=$('assetCliOverview');if(!box)return;const views=assetCliViews();if(!views.length){box.innerHTML='';return}box.innerHTML=views.map(view=>{const counts=view.counts||{};const selected=assetCli===view.id;const optional=(view.optional_scopes||view.available_packs||[]).length?(view.optional_scopes||view.available_packs).map(x=>String(x).toUpperCase()).join(' / '):'无';const agentPacks=(view.agent_pack_options||[]).length?view.agent_pack_options.map(x=>String(x).toUpperCase()).join(' / '):'无';const constraints=Array.isArray(view.constraints)?view.constraints:[];const panels=Array.isArray(view.panels)?view.panels:[];return `<article class="card asset-cli-card ${selected?'is-active':''}"><h3><span class="asset-cli-title">${escapeHtml(view.label||view.id)}</span><span class="tag ${view.allow_execution_surfaces?'':'off'}">${view.allow_execution_surfaces?'可注入':'只读/受限'}</span></h3><p class="muted">TUI 确认页同源预览：${escapeHtml(view.label||view.id)} 启动前会看到这些技能、MCP 和钩子。</p><div class="asset-cli-section"><span class="asset-cli-label">数量总览</span><div class="asset-cli-metrics">${assetCliChip('全部',view.row_count||0)}${assetCliChip('MMS 动态',counts.mms_dynamic||0)}${assetCliChip('全局继承',counts.global||0,'off')}${assetCliChip('其它',counts.other||0,'off')}${assetCliChip('技能',counts.skills||0)}${assetCliChip('MCP',counts.mcp||0)}${assetCliChip('钩子',counts.hooks||0)}${assetCliChip('按开关启用',view.inactive_by_default||0,'off')}${assetCliChip('偏好关闭',view.disabled_by_preference||0,'off')}</div></div><div class="asset-cli-section"><span class="asset-cli-label">TUI 面板</span><div class="asset-cli-panels">${panels.map(assetPanelTag).join('')}</div></div><div class="asset-cli-section"><span class="asset-cli-label">TUI 确认页控制</span><div class="asset-cli-controls">${renderAssetCliControls(view)}</div><p class="asset-cli-sample">可选开关：${escapeHtml(optional)}；Claude Agent Pack：${escapeHtml(agentPacks)}。Tab/C/N/T/E/X/D 等仍以启动确认页为准。</p></div><div class="asset-cli-section"><span class="asset-cli-label">全局来源（只读）</span><div class="asset-cli-sources">${renderAssetCliSources(view)}</div></div>${constraints.length?`<p class="asset-cli-note">${escapeHtml(constraints[0])}</p>`:''}<div class="asset-action asset-cli-action"><button class="${selected?'secondary':'ghost'}" data-asset-cli-focus="${escapeHtml(view.id)}">${selected?'正在查看这个 CLI':'只看这个 CLI'}</button></div></article>`}).join('');document.querySelectorAll('[data-asset-cli-focus]').forEach(btn=>btn.onclick=()=>{assetCli=btn.dataset.assetCliFocus;renderSessionAssets();toast(`已切换到 ${btn.dataset.assetCliFocus} 的能力清单`)})}
function renderAssetFilters(){const assets=state.session_assets||{};const tabs=[['all','全部来源',assetRows().length],...(assets.tabs||[]).map(t=>[t.id,t.title,t.row_count])];$('assetTabs').innerHTML=tabs.map(([id,label,count])=>assetFilterButton(id,`${label} (${count||0})`,assetTab,'data-asset-tab')).join('');document.querySelectorAll('[data-asset-tab]').forEach(btn=>btn.onclick=()=>{assetTab=btn.dataset.assetTab;renderSessionAssets()});const cliRows=[['all','全部 CLI'],...(assets.clis||[]).map(c=>[c.id,`${c.label} (${c.row_count||0})`])];$('assetCliFilters').innerHTML=cliRows.map(([id,label])=>assetFilterButton(id,label,assetCli,'data-asset-cli')).join('');document.querySelectorAll('[data-asset-cli]').forEach(btn=>btn.onclick=()=>{assetCli=btn.dataset.assetCli;renderSessionAssets()});const kinds=[['all','全部类型'],['skills','技能'],['mcp','MCP 服务'],['hooks','自动钩子']];$('assetKindFilters').innerHTML=kinds.map(([id,label])=>assetFilterButton(id,label,assetKind,'data-asset-kind')).join('');document.querySelectorAll('[data-asset-kind]').forEach(btn=>btn.onclick=()=>{assetKind=btn.dataset.assetKind;renderSessionAssets()});const search=$('assetSearch');if(search){search.value=assetQuery;search.oninput=()=>{assetQuery=search.value.trim().toLowerCase();renderSessionAssets()}}}
function baseFilteredAssetRows(){return assetRows().filter(row=>(assetTab==='all'||row.group===assetTab)&&(assetCli==='all'||row.cli===assetCli)&&(assetKind==='all'||row.kind===assetKind))}
function mergeAssetRows(rows){if(assetCli!=='all')return rows;const groups=new Map();for(const row of rows){const key=[row.group,row.kind,row.disable_key||row.title,row.title].join('::');if(!groups.has(key)){groups.set(key,{...row,details:[],_cliLabels:[],_scopeLabels:[],_origins:[],_detailsSeen:new Set()})}const item=groups.get(key);item._cliLabels.push(row.cli_label||row.cli);item._scopeLabels.push(row.scope_label||row.scope);item._origins.push(row.origin_label||row.origin);for(const detail of (row.details||[])){const detailKey=`${detail.label}::${detail.display||detail.value}`;if(!item._detailsSeen.has(detailKey)){item._detailsSeen.add(detailKey);item.details.push(detail)}}}return [...groups.values()].map(row=>{const cliLabels=uniqueTexts(row._cliLabels);const scopeLabels=uniqueTexts(row._scopeLabels);const origins=uniqueTexts(row._origins);delete row._cliLabels;delete row._scopeLabels;delete row._origins;delete row._detailsSeen;row.cli_label=cliLabels.join(' / ');row.scope_label=scopeLabels.length>1?'多种启用条件':(scopeLabels[0]||row.scope_label);row.origin_label=origins.length>1?'多来源检测':(origins[0]||row.origin_label);row.merged_count=cliLabels.length;row.details=[{label:'适用 CLI',value:cliLabels.join(' / '),display:cliLabels.join(' / ')},...row.details];return row})}
function filteredAssetRows(){const query=assetQuery.trim().toLowerCase();return mergeAssetRows(baseFilteredAssetRows()).filter(row=>!query||assetSearchHaystack(row).includes(query))}
function assetStatusText(row,disabled){if(disabled)return '默认关闭';if(row.scope==='always')return '默认带上';return '按开关启用'}
function assetGroupTagClass(row){return row.group==='global'?'off':(row.group==='other'?'off':'')}
function renderAssetCard(row,idx){const disabled=assetIsDefaultDisabled(row);const source=row.group_label||row.group||'未归类';const kind=row.kind_label||assetKindLabel(row.kind);const path=assetDetail(row,'路径')||assetDetail(row,'Path')||assetDetail(row,'URL')||assetDetail(row,'触发')||assetDetail(row,'Trigger');const status=assetStatusText(row,disabled);const globalClass=row.group==='global'?' is-global':'';const disabledClass=disabled?' is-disabled':'';const mergeTag=row.merged_count>1?`<span class="tag off">适用 ${row.merged_count} 个 CLI</span>`:'';return `<article class="card asset-card${globalClass}${disabledClass}" data-asset-row="${idx}"><div class="asset-card-head"><div><div class="asset-title">${escapeHtml(row.title||'未命名能力')}</div><div class="asset-subline">${escapeHtml(row.cli_label||row.cli||'CLI')} · ${escapeHtml(kind)} · ${escapeHtml(row.scope_label||row.scope||'默认')}</div></div><span class="tag ${assetGroupTagClass(row)}">${escapeHtml(source)}</span></div><p class="asset-desc">${escapeHtml(row.summary||'暂无说明。')}</p><div class="asset-meta"><span class="tag">${escapeHtml(row.origin_label||row.origin||'来源未知')}</span><span class="tag ${disabled?'off':''}">${escapeHtml(status)}</span>${mergeTag}${path?`<span class="tag off">有技术详情</span>`:''}</div><div class="asset-action"><span>${disabled?'已加入关闭草稿；启动确认页仍可临时打开。':'需要时可加入默认关闭草稿，当前不会写真实配置。'}</span><label class="asset-switch"><input type="checkbox" data-asset-disable="${idx}" ${disabled?'checked':''}>默认关闭</label></div><details class="asset-details"><summary>高级信息：路径、触发和 key</summary><div class="asset-detail-grid">${assetDetailsHtml(row)}</div></details></article>`}
function renderSessionAssets(){if(!$('assetCards'))return;const assets=state.session_assets||{};const summary=assets.summary||{};const contract=assets.configuration_contract||{};const draft=ensureAssetDisabledDraft();const displayCount=filteredAssetRows().length;$('assetSummary').innerHTML=`<div class="card"><span class="asset-count">${summary.mms_dynamic||0}</span><h3>MMS 动态注入</h3><p class="muted">启动 session 时临时带上，不污染全局 CLI。当前筛选显示 ${displayCount} 张卡片；未选具体 CLI 时会合并同名能力，减少重复。</p><div class="asset-meta"><span class="tag">技能 ${summary.skills||0}</span><span class="tag">MCP 服务 ${summary.mcp||0}</span><span class="tag">自动钩子 ${summary.hooks||0}</span><span class="tag off">全局继承 ${summary.global||0}</span></div></div><div class="card"><span class="asset-count">${draft.skills.length+draft.mcp.length+draft.hooks.length}</span><h3>默认关闭草稿</h3><p class="muted">勾选卡片里的“默认关闭”只生成 preferences.toml 片段；WebUI 不会直接改真实配置；启动确认页仍可临时打开。</p><div class="asset-meta"><span class="tag">技能 ${draft.skills.length}</span><span class="tag">MCP ${draft.mcp.length}</span><span class="tag">钩子 ${draft.hooks.length}</span></div></div>`;renderAssetManagedRoots();renderAssetFilters();const rows=filteredAssetRows();$('assetCards').innerHTML=rows.length?rows.map((row,idx)=>renderAssetCard(row,idx)).join(''):`<div class="asset-empty">没有匹配的能力。可以清空搜索，或切换来源 / CLI / 类型筛选。</div>`;renderAssetConfirmMap();renderAssetCliOverview();document.querySelectorAll('[data-asset-disable]').forEach(input=>{input.onchange=()=>{const row=rows[Number(input.dataset.assetDisable)];setAssetDefaultDisabled(row,input.checked);renderAssetPreferenceSnippet();renderSessionAssets()}});$('assetConfigContract').textContent=`持久偏好位置：${contract.persistent_path||'~/.config/mms/preferences.toml'}。${contract.webui_write_scope||'当前 WebUI 只生成片段，不直接写入。'} ${contract.launch_override||''}`;renderAssetPreferenceSnippet();bindAssetPreferenceButtons();$('assetGlobalRoots').innerHTML=(assets.global_roots||[]).map(root=>`<div class="asset-root"><p><span class="tag ${root.exists?'':'off'}">${root.exists?'存在':'未找到'}</span> <strong>${escapeHtml(root.label)}</strong></p><p class="mono">${escapeHtml(root.path)}</p><p class="muted">${root.skill_count?`发现 ${root.skill_count} 个技能；`:''}${escapeHtml(root.note||'只读展示，不自动修改。')}</p></div>`).join('')||'<p class="muted">没有全局位置记录。</p>'}
function renderRefs(){ $('refsGrid').innerHTML=(state.references||[]).map(r=>`<div class="card span6"><h3>${escapeHtml(r.title)}</h3><p>${escapeHtml(r.summary)}</p><p class="mono">${escapeHtml(r.path)}</p></div>`).join('') }
function levelLabel(level){return level==='danger'?'高风险':(level==='warn'?'注意':'信息')}
function planJsonHint(plan){const v2=plan?.registry_v2_save_plan||{};const planJson=v2.plan_json||{};const apply=v2.apply_plan||{};if(!planJson.name&&!apply.cli_apply_command)return '';return `<h4>Plan JSON / apply-plan</h4><p class="muted">${escapeHtml(planJson.note||'Plan JSON 是保存预览的 review artifact。')}</p><p><span class="tag">${escapeHtml(planJson.name||'webui-plan.json')}</span> <span class="tag ${planJson.redacted?'off':''}">secrets ${planJson.redacted?'redacted':'included'}</span></p><p class="mono">${escapeHtml(apply.cli_apply_command||'')}</p>`}
function renderApplyResult(data){const blockers=data.runtime_blockers||{};const next=data.next_action||{};const publish=data.publish||{};const verify=data.verify||{};const ready=data.runtime_ready===true;const notReady=data.runtime_ready===false;const errs=Array.isArray(data.errors)?data.errors:[data.error||'unknown error'];const title=!data.ok?'写入被阻止':(ready?'已发布，可直接给 mmf 使用':'已发布，但 runtime 未就绪');const detail=!data.ok?errs.join('；'):(ready?'latest-approved bundle 已验证，mmf 会读到这次保存后的最新 bundle。':'latest-approved bundle 已发布且已验证；mmf 会读到最新 bundle，但缺 key/base URL/模型 route 的条目不能正常启动。');$('saveResult').innerHTML=`<div><p><span class="tag ${data.ok&&!notReady?'':'off'}">${escapeHtml(title)}</span> <span class="tag">${escapeHtml(data.status||'-')}</span></p><p class="muted">${escapeHtml(detail)}</p><p><span class="tag">manifest ${verify.verified?'verified':'not verified'}</span><span class="tag ${ready?'':'off'}">runtime ${ready?'ready':notReady?'not ready':'unknown'}</span><span class="tag">missing keys ${blockers.missing_api_key_count||0}</span><span class="tag">missing base URL ${blockers.missing_base_url_count||0}</span><span class="tag">provider routes ${blockers.provider_route_count||publish.provider_route_count||0}</span></p>${next.label?`<p><strong>下一步</strong>：${escapeHtml(next.label)}</p>`:''}<details><summary>Raw JSON</summary><pre class="mono">${escapeHtml(JSON.stringify(data,null,2))}</pre></details></div>`}
function renderReviewSummary(plan){const review=plan?.review_summary||{};const counts=review.counts||{};const risks=review.risks||[];const items=review.items||[];const riskHtml=risks.length?`<h4>风险提示</h4><div>${risks.map(r=>`<p><span class="tag ${r.level==='danger'?'off':''}">${escapeHtml(levelLabel(r.level))}</span> <strong>${escapeHtml(r.title)}</strong> ${escapeHtml(r.detail)}</p>`).join('')}</div>`:'<p><span class="tag">无高风险提示</span></p>';const itemHtml=items.length?items.map(item=>`<p><span class="tag ${item.level==='danger'?'off':''}">${escapeHtml(levelLabel(item.level))}</span> <strong>${escapeHtml(item.title)}</strong> ${escapeHtml(item.detail)}</p>`).join(''):'<p class="muted">没有检测到配置变化。</p>';$('reviewSummary').innerHTML=`<div class="chips"><span class="chip">变化 ${counts.items||0}</span><span class="chip">风险 ${counts.risks||0}</span><span class="chip">移除隐藏记录 ${counts.hidden_removed||0}</span><span class="chip">凭据更新 ${counts.credential_updates||0}</span></div>${riskHtml}<h4>将要写入的变化</h4>${itemHtml}${planJsonHint(plan)}`}
function currentBundleRevision(){return state?.consumer_bundle_status?.component_revisions?.bundle||state?.consumer_bundle_status?.manifest?.bundle_revision||state?.model_source_status?.generated_bundle?.component_revisions?.bundle||state?.model_source_status?.generated_bundle?.manifest?.bundle_revision||''}
function draft(){syncProvider();syncFallback();syncRuntime();return JSON.parse(JSON.stringify({providers:state.providers,provider_default:state.provider_default,rescue:state.rescue,vision_sidecar:state.vision_sidecar,runtime:state.runtime,opencode:state.opencode,expected_bundle_revision:currentBundleRevision(),route_scope_provider_ids:[...touchedProviders],route_refresh_provider_ids:[...staleCleanupProviders]}))}
function renderAll(){renderStatus();renderSaveControls();renderSourceStatus();renderProviders();renderFallback();renderRuntime();renderSessionAssets();renderRefs()}
async function load(){const res=await fetch('/api/state');state=await res.json();state.providers=state.providers||[];renderNav();renderAll();}
$('addProvider').onclick=()=>{state.providers.push({id:`provider-${state.providers.length+1}`,original_id:'',name:'新通道',enabled:true,role:'auto',priority:100,models_endpoint:'/models',protocols:['anthropic_messages','openai_chat_completions'],supported_clis:['claude','codex','opencode'],openai_base_url:'',anthropic_base_url:'',api_key:'',update_credentials:false,fallback_models:[],extra_models:[],hidden_models:[],models:[]});activeProvider=state.providers.length-1;renderAll()}
$('duplicateProvider').onclick=()=>{const p=JSON.parse(JSON.stringify(current()));p.id=p.id+'-copy';p.original_id='';p.name=p.name+' Copy';p.api_key='';p.pending_api_key=false;p.update_credentials=false;p.has_api_key=false;state.providers.push(p);activeProvider=state.providers.length-1;renderAll()}
$('modelSearch').oninput=renderModelTable;$('addManualModels').onclick=()=>{const p=current();const vals=$('manualModels').value.split(/[\n,]/).map(x=>x.trim()).filter(Boolean);p.extra_models=[...new Set([...(p.extra_models||[]),...vals])];p.hidden_models=(p.hidden_models||[]).filter(x=>!vals.includes(x));$('manualModels').value='';renderModelTable();toast(`已添加 ${vals.length} 个模型`)};$('clearHidden').onclick=()=>{current().hidden_models=[];renderModelTable()};$('clearAllStaleHidden').onclick=cleanupAllStaleHidden
$('fetchModels').onclick=async()=>{syncProvider();const data=await api('/api/provider/models',{provider:current(),force_refresh:true});if(data.ok&&Array.isArray(data.models)){const p=current();if(!p.approved_route_models||!p.approved_route_models.length){p.approved_route_models=(p.models||[]).filter(r=>r&&r.id&&r.source!=='derived_alias').map(r=>r.id)}p.models=data.models.map(id=>({id,source:data.base_source||'remote',visible:!(p.hidden_models||[]).includes(id),favorite:false,capabilities:defaultCaps(id)}));touchProvider(p.id);if($('autoStaleCleanupOnFetch')?.checked&&staleRouteModels(p).length){staleCleanupProviders.add(p.id)}renderModelTable();$('testResult').textContent=JSON.stringify(data,null,2);toast(staleCleanupProviders.has(p.id)?`拉取到 ${data.models.length} 个模型；已自动标记缺失旧 route 清理`:`拉取到 ${data.models.length} 个模型；不会自动写入 fallback_models；缺失旧 route 默认保留`)}else{$('testResult').textContent=JSON.stringify(data,null,2);toast(data.error||'模型拉取失败，请看测试结果')}}
$('testList').onclick=async()=>{$('testResult').textContent=JSON.stringify(await api('/api/provider/test',{provider:current(),force_refresh:true}),null,2);setSection('test')}
$('testModelBtn').onclick=async()=>{$('testResult').textContent='测试中...';const data=await api('/api/model/test',{provider:state.providers[Number($('testProvider').value)],model:$('testModel').value,protocol:$('testProtocol').value,prompt:$('testPrompt').value});$('testResult').textContent=JSON.stringify(data,null,2)}
$('chatTestBtn').onclick=async()=>{$('testResult').textContent='测试中...';const data=await api('/api/chat/test',{provider:state.providers[Number($('testProvider').value)],model:$('testModel').value,protocol:$('testProtocol').value,prompt:$('testPrompt').value});$('testResult').textContent=JSON.stringify(data,null,2)}
$('previewPlan').onclick=async()=>{const data=await api('/api/plan',{draft:draft()});lastPlan=data;renderSaveControls();renderReviewSummary(data);$('saveResult').textContent=JSON.stringify({ok:data.ok,summary:data.summary,registry_v2_save_plan:data.registry_v2_save_plan,warnings:data.warnings,errors:data.errors,risks:data.review_summary?.risks},null,2);$('diffBox').textContent=[data.diffs?.config_toml,data.diffs?.model_policy_json,data.diffs?.credentials].filter(Boolean).join('\n')||'没有配置变化';toast(data.ok?'预览已生成':'预览有错误')}
function currentApplyCommand(){return lastPlan?.registry_v2_save_plan?.apply_plan?.cli_apply_command||'./mmf config apply-plan --plan-json <webui-plan.json> --apply --confirm-preview-apply --json'}
$('downloadPlanJson').onclick=()=>{if(!lastPlan){toast('请先生成保存预览');return}const blob=new Blob([JSON.stringify(lastPlan,null,2)+'\n'],{type:'application/json'});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=lastPlan?.registry_v2_save_plan?.plan_json?.name||'webui-plan.json';document.body.appendChild(a);a.click();a.remove();URL.revokeObjectURL(url);toast('已下载 redacted plan JSON')}
$('copyApplyCommand').onclick=async()=>{const cmd=currentApplyCommand();try{await navigator.clipboard.writeText(cmd);toast('已复制 CLI apply 命令')}catch(_err){$('saveResult').textContent=cmd;toast('无法访问剪贴板，命令已显示在结果框')}}
$('applyV2Preview').onclick=async()=>{const data=await api('/api/registry-v2/apply',{draft:draft(),confirm_v2_preview:$('confirmSave').checked,confirm_phrase:$('confirmPhrase').value,reason:$('saveReason').value});renderApplyResult(data);toast(data.ok?(data.runtime_ready===false?'已发布但 runtime 未就绪：请看 missing key/base URL':'预览 DB 已写入并发布，mmf 会读最新 bundle'):'预览 DB 写入被阻止'); if(data.ok){const res=await fetch('/api/state');state=await res.json();touchedProviders=new Set();staleCleanupProviders=new Set();renderAll();}}
$('saveBtn').onclick=async()=>{const data=await api('/api/save',{draft:draft(),confirm_save:$('confirmSave').checked,confirm_phrase:$('confirmPhrase').value,reason:$('saveReason').value});$('saveResult').textContent=JSON.stringify(data,null,2);toast(data.ok?'保存完成，已写入 audit':'保存被阻止'); if(data.ok){const res=await fetch('/api/state');state=await res.json();touchedProviders=new Set();staleCleanupProviders=new Set();renderAll();}}
load().catch(err=>{document.body.innerHTML='<pre style="padding:30px;color:var(--danger);font-family:var(--font-mono)">'+escapeHtml(err.stack||err.message)+'</pre>'})
</script>
</body>
</html>"""
