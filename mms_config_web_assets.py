# -*- coding: utf-8 -*-
"""Static assets for the MMS config WebUI."""

_HTML_PAGE = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>MMS 配置中心</title>
  <style>
    :root {
      --bg:      oklch(97% 0.004 250);
      --surface: oklch(100% 0 0);
      --fg:      oklch(16% 0.015 250);
      --muted:   oklch(50% 0.015 250);
      --border:  oklch(88% 0.008 250);
      --accent:  oklch(54% 0.16 155);

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

      --font-body: 'Aptos', 'Geist', 'Satoshi', 'Avenir Next', -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
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
      background: var(--surface);
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
      background: var(--surface);
      padding: 28px;
      box-shadow: var(--shadow-sm);
      transition: box-shadow .2s ease;
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
      background: var(--bg);
      padding: 18px;
      transition: border-color .15s ease, box-shadow .15s ease;
    }
    .card:hover {
      border-color: color-mix(in oklch, var(--accent) 20%, var(--border));
    }
    .module-actions {
      display: flex;
      flex-wrap: wrap;
      gap: 9px;
      margin: -6px 0 18px;
    }
    .module-report {
      margin-top: 14px;
    }
    .model-inventory-summary {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 10px;
    }
    .inventory-tile {
      border: 1.5px solid var(--border);
      background:
        radial-gradient(circle at 100% 0, color-mix(in oklch, var(--accent) 9%, transparent), transparent 42%),
        var(--bg);
      border-radius: var(--radius);
      padding: 12px;
      min-height: 82px;
    }
    .inventory-tile span {
      display: block;
      font-family: var(--font-mono);
      font-size: 10px;
      letter-spacing: .08em;
      text-transform: uppercase;
      color: var(--muted);
    }
    .inventory-tile strong {
      display: block;
      margin-top: 8px;
      font-family: var(--font-mono);
      font-size: 28px;
      line-height: 1;
      font-variant-numeric: tabular-nums;
    }

    /* ===== Settings mission control ===== */
    .settings-command {
      border: 1.5px solid color-mix(in oklch, var(--fg) 22%, var(--border));
      background:
        linear-gradient(90deg, color-mix(in oklch, var(--fg) 4%, transparent) 1px, transparent 1px),
        linear-gradient(0deg, color-mix(in oklch, var(--fg) 4%, transparent) 1px, transparent 1px),
        color-mix(in oklch, var(--surface) 86%, var(--bg));
      background-size: 26px 26px;
      border-radius: 0;
      padding: 18px;
      margin-bottom: 16px;
      box-shadow: 0 16px 36px color-mix(in oklch, var(--fg) 10%, transparent);
    }
    .settings-command-head {
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 16px;
      align-items: start;
      border-bottom: 1.5px solid var(--fg);
      padding-bottom: 14px;
      margin-bottom: 14px;
    }
    .settings-kicker {
      font-family: var(--font-mono);
      font-size: 11px;
      letter-spacing: .14em;
      text-transform: uppercase;
      color: var(--danger);
      margin-bottom: 6px;
    }
    .settings-command h3 {
      font-size: clamp(28px, 4.5vw, 56px);
      line-height: .92;
      letter-spacing: -.06em;
      text-transform: uppercase;
      max-width: 820px;
      margin: 0;
    }
    .settings-command p {
      max-width: 760px;
      color: color-mix(in oklch, var(--fg) 72%, var(--muted));
    }
    .settings-stamp {
      align-self: start;
      border: 1.5px solid var(--danger);
      color: var(--danger);
      font-family: var(--font-mono);
      font-size: 11px;
      letter-spacing: .08em;
      padding: 8px 10px;
      text-transform: uppercase;
      white-space: nowrap;
    }
    .settings-metrics {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 1px;
      background: var(--fg);
      margin-bottom: 14px;
    }
    .settings-metric {
      background: var(--surface);
      padding: 14px;
      min-height: 92px;
    }
    .settings-metric span {
      display: block;
      font-family: var(--font-mono);
      font-size: 10px;
      color: var(--muted);
      letter-spacing: .08em;
      text-transform: uppercase;
    }
    .settings-metric strong {
      display: block;
      font-family: var(--font-mono);
      font-size: clamp(24px, 4vw, 44px);
      line-height: 1;
      margin: 10px 0 4px;
      font-variant-numeric: tabular-nums;
    }
    .settings-metric em {
      display: block;
      color: var(--muted);
      font-size: 12px;
      font-style: normal;
    }
    .settings-route {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 10px;
    }
    .settings-route-card {
      border-left: 3px solid var(--fg);
      background: color-mix(in oklch, var(--fg) 5%, transparent);
      padding: 12px;
    }
    .settings-route-card.locked { border-left-color: var(--danger); }
    .settings-route-card.ready { border-left-color: var(--accent); }
    .settings-route-card.report { border-left-color: var(--warn); }
    .settings-route-card b {
      display: block;
      font-family: var(--font-mono);
      font-size: 11px;
      letter-spacing: .07em;
      text-transform: uppercase;
      margin-bottom: 6px;
    }
    .settings-route-card small {
      display: block;
      color: var(--muted);
      line-height: 1.45;
    }
    .settings-empty-note {
      border: 1px dashed color-mix(in oklch, var(--fg) 26%, var(--border));
      background: color-mix(in oklch, var(--warn) 9%, transparent);
      padding: 12px;
      margin: 12px 0 0;
      color: color-mix(in oklch, var(--fg) 76%, var(--muted));
    }
    .entry-audit {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 1px;
      background: color-mix(in oklch, var(--fg) 22%, var(--border));
      border: 1px solid color-mix(in oklch, var(--fg) 22%, var(--border));
    }
    .entry-audit-item {
      background: var(--surface);
      padding: 12px;
      min-height: 98px;
    }
    .entry-audit-item b {
      display: block;
      font-family: var(--font-mono);
      font-size: 12px;
      margin-bottom: 8px;
    }
    .entry-audit-item small {
      display: block;
      color: var(--muted);
      line-height: 1.45;
    }
    .mapping-card {
      background:
        radial-gradient(circle at top right, color-mix(in oklch, var(--accent) 10%, transparent), transparent 32%),
        var(--bg);
    }
    .mapping-head {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 14px;
      align-items: end;
      margin-bottom: 12px;
    }
    .filterbar.compact {
      margin: 0;
      justify-content: flex-end;
    }
    .mapping-action {
      border-radius: 0;
      padding: 6px 10px;
      font-family: var(--font-mono);
      font-size: 11px;
      letter-spacing: .04em;
      text-transform: uppercase;
    }
    .acceptance-panel {
      border: 1.5px solid color-mix(in oklch, var(--accent) 35%, var(--border));
      background:
        linear-gradient(135deg, color-mix(in oklch, var(--accent) 9%, transparent), transparent 38%),
        color-mix(in oklch, var(--surface) 92%, var(--accent-soft));
      border-radius: var(--radius);
      padding: 14px;
      margin-bottom: 14px;
    }
    .acceptance-head {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 12px;
      align-items: start;
      margin-bottom: 10px;
    }
    .acceptance-head h4 {
      font-size: 18px;
      line-height: 1.05;
      letter-spacing: -.03em;
      text-transform: uppercase;
    }
    .acceptance-progress {
      font-family: var(--font-mono);
      font-size: 24px;
      line-height: 1;
      font-variant-numeric: tabular-nums;
      color: var(--accent);
      white-space: nowrap;
    }
    .mapping-check {
      display: inline-flex;
      gap: 6px;
      align-items: center;
      font-family: var(--font-mono);
      font-size: 11px;
      color: var(--muted);
      white-space: nowrap;
    }
    .mapping-check input {
      width: auto;
      accent-color: var(--accent);
      cursor: pointer;
    }
    .check-evidence {
      font-family: var(--font-mono);
      font-size: 11px;
      color: color-mix(in oklch, var(--fg) 72%, var(--muted));
    }
    .status-native { background: var(--ok-soft); color: var(--ok); }
    .status-report { background: var(--warn-soft); color: color-mix(in oklch, var(--warn) 72%, black); }
    .status-draft_review { background: var(--accent-soft); color: var(--accent); }
    .status-human_gate { background: var(--danger-soft); color: var(--danger); }
    .status-missing {
      background: var(--fg-soft);
      color: var(--muted);
      border: 1px dashed color-mix(in oklch, var(--fg) 18%, var(--border));
    }
    .gate-report {
      white-space: normal;
      font-family: var(--font-body);
      display: grid;
      gap: 14px;
    }
    .gate-plate {
      border: 1.5px solid color-mix(in oklch, var(--danger) 38%, var(--border));
      background:
        radial-gradient(circle at 0 0, color-mix(in oklch, var(--danger) 14%, transparent), transparent 34%),
        color-mix(in oklch, var(--surface) 92%, var(--danger-soft));
      border-radius: var(--radius);
      padding: 14px;
    }
    .gate-head {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 12px;
      align-items: start;
      border-bottom: 1px solid color-mix(in oklch, var(--danger) 28%, var(--border));
      padding-bottom: 10px;
      margin-bottom: 10px;
    }
    .gate-head h4 {
      font-size: clamp(18px, 3vw, 28px);
      line-height: 1;
      letter-spacing: -.04em;
      text-transform: uppercase;
    }
    .gate-head p {
      margin-top: 6px;
      max-width: 740px;
      color: var(--muted);
    }
    .gate-risk {
      font-family: var(--font-mono);
      font-size: 10px;
      letter-spacing: .1em;
      text-transform: uppercase;
      color: var(--danger);
      border: 1px solid var(--danger);
      padding: 6px 8px;
      white-space: nowrap;
    }
    .gate-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
    }
    .gate-box {
      border: 1px solid var(--border);
      background: color-mix(in oklch, var(--bg) 72%, var(--surface));
      border-radius: var(--radius);
      padding: 12px;
      min-width: 0;
    }
    .gate-box h5 {
      margin: 0 0 8px;
      font-family: var(--font-mono);
      font-size: 11px;
      letter-spacing: .08em;
      text-transform: uppercase;
    }
    .gate-list {
      margin: 0;
      padding-left: 18px;
      color: color-mix(in oklch, var(--fg) 78%, var(--muted));
    }
    .gate-list li { margin: 5px 0; }
    .gate-command-row {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 8px;
      align-items: center;
      margin: 7px 0;
      padding: 8px;
      border: 1px solid color-mix(in oklch, var(--fg) 16%, var(--border));
      background: var(--surface);
      border-radius: 8px;
    }
    .gate-command-row code {
      font-family: var(--font-mono);
      font-size: 12px;
      line-height: 1.45;
      word-break: break-word;
    }
    .copy-gate-command {
      border-radius: 0;
      padding: 6px 9px;
      font-family: var(--font-mono);
      font-size: 10px;
      text-transform: uppercase;
      white-space: nowrap;
    }
    .gate-raw summary {
      cursor: pointer;
      color: var(--muted);
      font-family: var(--font-mono);
      font-size: 11px;
      margin-top: 8px;
    }
    .delete-zone {
      border: 1.5px dashed color-mix(in oklch, var(--danger) 42%, var(--border));
      background: color-mix(in oklch, var(--danger) 7%, transparent);
      border-radius: var(--radius);
      padding: 12px;
    }

    /* ===== Grid system ===== */
    .grid {
      display: grid;
      grid-template-columns: repeat(12, 1fr);
      gap: 14px;
    }
    .span3 { grid-column: span 3; }
    .span4 { grid-column: span 4; }
    .span5 { grid-column: span 5; }
    .span6 { grid-column: span 6; }
    .span7 { grid-column: span 7; }
    .span8 { grid-column: span 8; }
    .span9 { grid-column: span 9; }
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

    .provider-editor-shell {
      display: flex;
      flex-direction: column;
      gap: 14px;
    }
    .provider-form-tabs {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 5px;
      padding: 5px;
      border: 1.5px solid var(--border);
      border-radius: 18px;
      background:
        radial-gradient(circle at 8% 0%, color-mix(in oklch, var(--accent) 10%, transparent) 0, transparent 30%),
        color-mix(in oklch, var(--bg) 82%, var(--surface));
    }
    .provider-form-tab {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 4px;
      min-height: 38px;
      background: transparent;
      color: var(--muted);
      border: 1px solid transparent;
      box-shadow: none;
      padding: 7px 10px;
      border-radius: 13px;
      font-size: 12.5px;
      font-weight: 700;
      line-height: 1.2;
    }
    .provider-form-tab .muted { display: none; }
    .provider-form-tab:hover {
      color: var(--fg);
      background: var(--surface);
      border-color: var(--border);
    }
    .provider-form-tab.active {
      color: var(--surface);
      background: var(--fg);
      border-color: var(--fg);
      box-shadow: 0 8px 20px rgba(15, 23, 42, .12);
    }
    .provider-form-tab.active .muted { color: rgba(255,255,255,.72); }
    .provider-form-panel { display: none; }
    .provider-form-panel.active {
      display: block;
      animation: fadeIn .18s ease both;
    }
    .provider-advanced {
      border: 1.5px dashed var(--border);
      border-radius: var(--radius);
      padding: 14px 16px;
      background: var(--bg);
    }
    .provider-advanced summary {
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      font-weight: 700;
      color: var(--fg);
      list-style-position: outside;
    }
    .provider-advanced summary::marker { color: var(--muted); }
    .provider-advanced[open] { border-color: color-mix(in oklch, var(--accent) 35%, var(--border)); }
    .provider-action-grid {
      display: grid;
      grid-template-columns: repeat(12, minmax(0, 1fr));
      gap: 10px;
    }
    .explain-card {
      display: flex;
      flex-direction: column;
      border: 1.5px solid var(--border);
      border-radius: var(--radius);
      background: var(--surface);
      padding: 13px;
      box-shadow: var(--shadow-sm);
      min-height: 170px;
    }
    .explain-card h4 {
      margin-bottom: 6px;
      font-size: 14px;
      line-height: 1.35;
    }
    .explain-card p {
      color: var(--muted);
      font-size: 12.5px;
      line-height: 1.55;
      white-space: normal;
      margin-bottom: 10px;
    }
    .explain-card button {
      align-self: flex-start;
      margin-top: auto;
      padding: 7px 12px;
      font-size: 12.5px;
      border-radius: 13px;
    }
    .provider-editor-actions {
      border-top: 1px solid var(--border);
      padding-top: 14px;
      margin-top: 0;
    }
    .result .usage-report,
    .result .account-report {
      font-family: var(--font-body);
      white-space: normal;
      font-size: 13px;
      line-height: 1.55;
    }
    .result .usage-report h4,
    .result .account-report h4 {
      font-size: 16px;
      margin-bottom: 6px;
    }
    .result .usage-report p,
    .result .account-report p { color: var(--muted); }
    .result .usage-report table,
    .result .account-report table {
      font-family: var(--font-body);
      min-width: 760px;
    }
    .result .usage-report .table-wrap,
    .result .account-report .table-wrap { margin-top: 10px; }
    .usage-report .chips {
      gap: 5px;
      margin: 8px 0 12px;
    }
    .usage-report .chip {
      padding: 4px 9px;
      font-size: 11.5px;
    }
    .result .usage-report table.usage-model-table {
      min-width: 0;
      table-layout: fixed;
      font-size: 12.5px;
    }
    .usage-model-table th,
    .usage-model-table td {
      padding: 8px 10px;
      vertical-align: middle;
    }
    .usage-model-table th:nth-child(1) { width: 36%; }
    .usage-model-table th:nth-child(2) { width: 16%; }
    .usage-model-table th:nth-child(3) { width: 12%; }
    .usage-model-table th:nth-child(4) { width: 11%; }
    .usage-model-table th:nth-child(5) { width: 11%; }
    .usage-model-table th:nth-child(6) { width: 14%; }
    .usage-model-table td:first-child {
      font-family: var(--font-mono);
      word-break: break-word;
    }
    .usage-detail {
      margin-top: 12px;
      border: 1.5px dashed var(--border);
      border-radius: var(--radius);
      background: var(--bg);
      padding: 11px 12px;
    }
    .usage-detail summary {
      cursor: pointer;
      font-weight: 700;
      color: var(--fg);
      user-select: none;
    }
    .usage-detail summary::marker { color: var(--muted); }
    .usage-detail .table-wrap { margin-top: 10px; }

    .settings-console {
      display: grid;
      gap: 14px;
    }
    .settings-hero {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 18px;
      align-items: end;
      border: 1.5px solid color-mix(in oklch, var(--fg) 18%, var(--border));
      border-radius: var(--radius-xl);
      padding: 18px;
      background:
        radial-gradient(circle at 0 0, color-mix(in oklch, var(--accent) 14%, transparent), transparent 34%),
        linear-gradient(135deg, color-mix(in oklch, var(--surface) 84%, var(--bg)), var(--surface));
      box-shadow: var(--shadow-sm);
    }
    .settings-hero h3 {
      font-size: clamp(22px, 3.2vw, 36px);
      letter-spacing: -.035em;
      line-height: 1.05;
      margin-bottom: 8px;
    }
    .settings-hero p {
      color: color-mix(in oklch, var(--fg) 70%, var(--muted));
      max-width: 760px;
    }
    .settings-hero-actions {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      justify-content: flex-end;
    }
    .settings-tabs {
      display: flex;
      gap: 6px;
      padding: 6px;
      border: 1px solid var(--border);
      border-radius: var(--radius-lg);
      background: color-mix(in oklch, var(--bg) 70%, var(--surface));
      overflow-x: auto;
      scrollbar-width: thin;
    }
    .settings-tab {
      flex: 1 0 150px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      border: 1px solid transparent;
      border-radius: var(--radius);
      background: transparent;
      color: var(--muted);
      text-align: left;
      box-shadow: none;
      padding: 8px 10px;
      min-height: 42px;
      white-space: nowrap;
    }
    .settings-tab strong,
    .settings-tab span {
      display: inline;
      white-space: nowrap;
    }
    .settings-tab strong {
      color: inherit;
      font-size: 13px;
      line-height: 1;
    }
    .settings-tab span {
      color: color-mix(in oklch, var(--muted) 84%, var(--fg));
      font-size: 11px;
      line-height: 1;
    }
    .settings-tab:hover {
      background: var(--surface);
      border-color: var(--border);
      color: var(--fg);
    }
    .settings-tab.active {
      background: var(--fg);
      border-color: var(--fg);
      color: var(--surface);
    }
    .settings-tab.active span { color: rgba(255,255,255,.74); }
    .settings-tab-panel { display: none; }
    .settings-tab-panel.active {
      display: block;
      animation: fadeIn .18s ease both;
    }
    .settings-panel-grid {
      display: grid;
      grid-template-columns: repeat(12, minmax(0, 1fr));
      gap: 14px;
    }
    .setting-edit-card {
      border: 1.5px solid var(--border);
      border-radius: var(--radius-lg);
      background: var(--surface);
      padding: 15px;
      box-shadow: var(--shadow-sm);
    }
    .setting-edit-card h3 {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      margin-bottom: 7px;
    }
    .settings-next-step {
      border: 1.5px dashed color-mix(in oklch, var(--accent) 40%, var(--border));
      background: color-mix(in oklch, var(--accent) 8%, transparent);
      border-radius: var(--radius-lg);
      padding: 14px;
    }
    .account-config-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
    }
    .account-config-card {
      border: 1.5px solid var(--border);
      border-radius: var(--radius-lg);
      background:
        linear-gradient(180deg, color-mix(in oklch, var(--surface) 92%, var(--bg)), var(--surface));
      padding: 14px;
      box-shadow: var(--shadow-sm);
    }
    .account-config-card.locked {
      border-style: dashed;
      background: color-mix(in oklch, var(--bg) 74%, var(--surface));
    }
    .account-card-head {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 10px;
      align-items: start;
      margin-bottom: 12px;
    }
    .account-card-head h4 {
      font-size: 16px;
      margin-bottom: 4px;
    }
    .account-fields {
      display: grid;
      grid-template-columns: repeat(6, minmax(0, 1fr));
      gap: 10px;
    }
    .account-fields label { margin-top: 0; }
    .account-advanced {
      margin-top: 12px;
      border: 1px dashed var(--border);
      border-radius: var(--radius);
      background: color-mix(in oklch, var(--bg) 70%, transparent);
      padding: 10px 12px;
    }
    .account-advanced summary {
      cursor: pointer;
      font-weight: 700;
      color: var(--fg);
    }
    .account-advanced summary::marker { color: var(--muted); }
    .settings-compat-note {
      border-left: 3px solid var(--warn);
      background: color-mix(in oklch, var(--warn) 10%, transparent);
      padding: 10px 12px;
      border-radius: var(--radius);
      color: color-mix(in oklch, var(--fg) 76%, var(--muted));
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
    .chip.off {
      color: var(--muted);
      background: color-mix(in oklch, var(--bg) 72%, var(--surface));
      border-color: color-mix(in oklch, var(--border) 82%, var(--muted));
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
    }
    .hide { display: none !important; }

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
      .span3, .span4, .span5, .span6, .span7, .span8, .span9, .span12 { grid-column: span 12; }
      .provider-form-tabs { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .provider-form-tab { justify-content: flex-start; }
      .oc-summary, .model-inventory-summary, .settings-tabs, .account-config-grid { grid-template-columns: 1fr 1fr; }
      .settings-hero, .settings-command-head, .settings-metrics, .settings-route, .entry-audit, .mapping-head, .gate-head, .gate-grid, .acceptance-head { grid-template-columns: 1fr; }
      .settings-hero-actions { justify-content: flex-start; }
      .filterbar.compact { justify-content: flex-start; }
      .settings-command h3 { font-size: clamp(26px, 11vw, 44px); }
      .settings-stamp { white-space: normal; }
      .panel { padding: 20px; }
    }
    @media (max-width: 680px) {
      .settings-tabs, .account-config-grid, .account-fields { grid-template-columns: 1fr; }
    }
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
    .asset-control-help {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
      gap: 10px;
      margin-bottom: 16px;
      min-width: 0;
    }
    .asset-control-card {
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 13px;
      background: oklch(100% 0 0 / 0.72);
      min-width: 0;
    }
    .asset-control-card h3 {
      margin: 0 0 6px;
      font-size: 14px;
    }
    .asset-control-card p {
      margin: 4px 0;
    }
    .asset-control-card .btns {
      margin-top: 10px;
    }
    .asset-pending-bar {
      position: fixed;
      left: max(14px, env(safe-area-inset-left));
      right: max(14px, env(safe-area-inset-right));
      bottom: max(14px, env(safe-area-inset-bottom));
      z-index: 80;
      display: none;
      pointer-events: none;
    }
    .asset-pending-bar.is-visible {
      display: block;
      animation: assetBarIn .18s ease both;
    }
    @keyframes assetBarIn {
      from { opacity: 0; transform: translateY(12px); }
      to { opacity: 1; transform: translateY(0); }
    }
    .asset-pending-inner {
      max-width: 1180px;
      margin: 0 auto;
      pointer-events: auto;
      display: grid;
      grid-template-columns: minmax(220px, 1fr) minmax(360px, auto);
      gap: 12px;
      align-items: center;
      border: 1px solid color-mix(in oklch, var(--accent) 42%, var(--border));
      border-radius: 22px;
      padding: 12px 14px;
      background:
        linear-gradient(135deg, oklch(100% 0 0 / .96), oklch(97.5% 0.018 155 / .96));
      box-shadow: 0 20px 60px oklch(20% 0.02 220 / .18);
      backdrop-filter: blur(14px);
    }
    .asset-pending-title {
      display: flex;
      align-items: center;
      flex-wrap: wrap;
      gap: 8px;
      font-weight: 760;
    }
    .asset-pending-actions {
      display: grid;
      grid-template-columns: minmax(180px, 1fr) minmax(140px, .8fr) auto auto;
      align-items: end;
      gap: 8px;
    }
    .asset-pending-actions label:not(.check) {
      font-size: 12px;
      font-weight: 720;
      color: var(--muted);
    }
    .asset-pending-actions input[type="text"] {
      width: 100%;
      min-width: 0;
    }
    .asset-confirm-field {
      min-width: 0;
    }
    .asset-pending-result {
      grid-column: 1 / -1;
      min-height: 20px;
      margin: 0;
    }
    .asset-source-strip {
      display: block;
      margin: 4px 0 16px;
      min-width: 0;
    }
    #assetCliDetails {
      margin: 16px 0;
    }
    .asset-ops-grid {
      align-items: start;
      margin-top: 16px;
    }
    .asset-ops-card {
      align-self: start;
    }
    .asset-ops-card .btns {
      margin-top: 14px;
    }
    .asset-source-diagnostic {
      border: 1px solid color-mix(in oklch, var(--accent) 24%, var(--border));
      border-radius: var(--radius-lg);
      padding: 12px 14px;
      background:
        linear-gradient(135deg, oklch(99% 0.01 188), oklch(100% 0 0));
      min-width: 0;
    }
    .asset-source-diagnostic summary {
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      flex-wrap: wrap;
      font-weight: 760;
      min-width: 0;
    }
    .asset-source-summary {
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
      min-width: 0;
    }
    .asset-source-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 10px;
      margin-top: 12px;
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
    .asset-group {
      grid-column: 1 / -1;
      border: 1px solid var(--border);
      border-radius: var(--radius-lg);
      background: oklch(100% 0 0 / 0.56);
      padding: 10px;
      min-width: 0;
    }
    .asset-group summary {
      cursor: pointer;
      font-weight: 760;
      letter-spacing: -0.015em;
      padding: 3px 2px 10px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      flex-wrap: wrap;
    }
    .asset-group-note {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      padding: 0 2px 10px;
      min-width: 0;
    }
    .asset-group-note p {
      margin: 0;
      min-width: 0;
    }
    .asset-group-actions {
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
      flex: 0 0 auto;
    }
    .asset-group-cards {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
      gap: 10px;
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
      .asset-pending-inner { grid-template-columns: 1fr; }
      .asset-pending-actions { grid-template-columns: 1fr; align-items: stretch; }
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
    <p class="lead">这里按模块直接配置和测试：通道里改 provider 与模型清单，模型测试里跑 smoke，设置里管账号、语言和 Guard。保存前先预览；stable legacy 走 backup + audit，preview root 走 DB candidate + latest-approved publish。</p>
  </div>
  <div class="statusbar" id="statusbar"><span class="pill warn">加载中</span></div>
</header>
<div class="shell">
  <aside class="side" id="nav"></aside>
  <main class="content">
    <section class="panel" data-section="source">
      <h2>真源状态</h2>
      <p>只读汇总当前 config root、registry DB、legacy import 冲突和 latest-approved bundle 校验状态；registry 的 报告 / 人工确认操作也在这里，不再藏到 设置总表。</p>
      <div class="module-actions">
        <button class="ghost" data-settings-action="model_source_status" data-report-target="sourceReport">模型真源状态</button>
        <button class="ghost" data-settings-action="consumer_bundle_status" data-report-target="sourceReport">消费端 Bundle</button>
        <button class="ghost" data-settings-action="verify_approved" data-report-target="sourceReport">验证已批准 Bundle</button>
        <button class="ghost" data-settings-action="preview_doctor" data-report-target="sourceReport">预览诊断</button>
        <button class="ghost" data-settings-action="check_staleness" data-report-target="sourceReport">检查过期源</button>
        <button class="ghost" data-settings-action="refresh_due_sources_gate" data-report-target="sourceReport">刷新到期源确认</button>
        <button class="ghost" data-settings-action="publish_approved_gate" data-report-target="sourceReport">发布确认</button>
      </div>
      <div class="grid" id="sourceStatus"></div>
      <div class="result module-report" id="sourceReport">选择真源动作查看只读报告或人工确认。</div>
    </section>


    <!-- 通道配置 -->
    <section class="panel" data-section="channel">
      <h2>通道配置</h2>
      <p>先建通道：基础信息、连接凭据、策略高级项和报告确认分在编辑器 Tab 中；Key 只会通过 POST 发送，不会回显。</p>
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
              <div class="model-inventory-summary" id="modelInventorySummary"></div>
              <div class="card">
                <div class="btns">
                  <button id="fetchModels">拉取当前通道模型</button>
                  <button id="testList" class="secondary">测试 /models</button>
                  <button id="openModelTest" class="ghost">打开模型测试</button>
                  <label class="check"><input id="autoStaleCleanupOnFetch" type="checkbox"><span>拉取后自动标记缺失旧 route 为待清理（本页临时）</span></label>
                  <input id="modelSearch" placeholder="搜索模型" style="max-width:260px">
                </div>
                <label style="margin-top:14px">手动补充当前通道模型（extra_models，逗号或换行分隔）</label>
                <textarea id="manualModels" placeholder="例如：gpt-5.5, qwen3.6-plus, K2.6"></textarea>
                <div class="btns">
                  <button id="addManualModels" class="secondary">添加到补充模型库</button>
                  <button id="clearHidden" class="ghost">取消当前通道全部隐藏</button>
                  <button id="restoreModelPatch" class="ghost">恢复默认模型补丁</button>
                  <button id="clearAllStaleHidden" class="ghost">移除全部通道未匹配隐藏规则</button>
                </div>
              </div>
              <div id="modelChips" class="card"></div>
              <div class="card" id="staleHiddenBox"></div>
              <div class="table-wrap"><table id="modelTable"></table></div>
              <div class="result module-report" id="modelConfigResult">模型配置动作结果会显示在这里。</div>
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
          <label>提示词 Prompt</label>
          <textarea id="testPrompt">只回复 pong</textarea>
          <div class="chips" id="testState"></div>
          <div class="btns">
            <button id="testListBtn" class="ghost">测试 /models</button>
            <button id="testModelBtn">Ping 模型</button>
            <button id="chatTestBtn" class="secondary">简单对话</button>
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
      <p>stable legacy 保存写入 config.toml 的 [rescue] / [vision_sidecar]；preview root 保存为 DB candidate 并随 latest-approved bundle 发布。已下线的负载均衡不在本轮 WebUI 迭代范围。</p>
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
          <div class="btns">
            <button class="ghost" data-settings-action="rescue_events" data-report-target="fallbackReport">查看 rescue 事件</button>
            <button class="ghost" data-settings-action="rescue_handover_gate" data-report-target="fallbackReport">交接确认</button>
            <button class="ghost" data-settings-action="rescue_create_demo_gate" data-report-target="fallbackReport">Demo packet 确认</button>
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
        <div class="card span12">
          <h3>Fallback 报告 / 人工确认</h3>
          <div class="result" id="fallbackReport">选择 fallback 动作查看结果。</div>
        </div>
      </div>
    </section>

    <!-- 运行默认值 -->
    <section class="panel" data-section="runtime">
      <h2>运行默认值</h2>
      <p>首选 CLI 会写入 presets.coding.cli；OpenCode profile 和 agent roster 会写入 [opencode]，launcher 会生成 session-local opencode.json；不会写全局 OpenCode 配置。</p>
      <div class="grid">
        <div class="card span5">
          <label>首选 CLI</label>
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
          <label>OpenCode 默认 profile</label>
          <select id="opencodeProfile">
            <option>agent</option>
            <option>omo</option>
            <option>raw</option>
          </select>
          <p class="muted">推荐：5.5 总控/终审，5.4 长跑 executor，国产模型用于 explore / bug-hunt / vision。逐 agent 固定模型放在 Advanced，不作为默认必填项。</p>
        </div>
        <div class="card span12">
          <h3>OpenCode Agent 名单</h3>
          <p class="muted">默认使用 Lite Pro 自动路线；这里管理哪些 agent 进入 session-local opencode.json。顺序表示 priority/fallback 顺序，不是 round-robin。</p>
          <div class="oc-summary" id="opencodeOverrideSummary"></div>
          <div class="oc-order-note">
            Lean 默认只开关键链路；Balanced 适合日常；Deep 再启用第二意见。国产模型适合 explore / bughunt / vision，不默认做最终裁决。
          </div>
          <details class="oc-advanced" id="opencodeAdvanced">
            <summary>高级：OpenCode 逐 Agent 名单</summary>
            <div class="filterbar" id="opencodeAgentFilters"></div>
            <div class="table-wrap"><table id="opencodeAgents"></table></div>
          </details>
        </div>
      </div>
    </section>

    <!-- Settings -->
    <section class="panel" data-section="settings">
      <h2>设置</h2>
      <p>这里是 WebUI 配置台：日常配置在当前页面改草稿，统一去保存页生成 diff / 审计摘要；TUI 后续只保留启动、应急和人工确认兜底。</p>
      <div class="settings-console">
        <div class="settings-hero">
          <div>
            <h3>把设置从 TUI 迁到可保存的 WebUI 表单</h3>
            <p>用户只需要记住启动命令；通道、模型、Fallback、Runtime 和账号默认值都在 WebUI 里完成配置，再通过保存预览写入。</p>
            <div id="settingsGapSummary" class="chips"></div>
          </div>
          <div class="settings-hero-actions">
            <button class="secondary" data-section-jump="save">生成保存预览</button>
            <button class="ghost" data-settings-action="accounts" data-report-target="settingsReport">刷新账号状态</button>
          </div>
        </div>

        <div class="settings-tabs" id="settingsTabs">
          <button class="settings-tab" data-settings-tab="basics"><strong>常用设置</strong><span>语言 / 保存入口</span></button>
          <button class="settings-tab" data-settings-tab="accounts"><strong>账号默认值</strong><span>default / priority / note</span></button>
          <button class="settings-tab" data-settings-tab="guard"><strong>安全确认</strong><span>Snapshot / 迁移</span></button>
          <button class="settings-tab" data-settings-tab="about"><strong>维护关于</strong><span>版本 / 升级 gate</span></button>
          <button class="settings-tab" data-settings-tab="audit"><strong>验收辅助</strong><span>折叠的 TUI 对照</span></button>
        </div>

        <div class="settings-tab-panel" data-settings-panel="basics">
          <div class="settings-panel-grid">
            <div class="setting-edit-card span5">
              <h3>界面语言 <span class="tag">可配置</span></h3>
              <p class="muted">进入 WebUI 草稿，写入仍走保存 / 审计。</p>
              <label>ui.language</label>
              <select id="uiLanguage">
                <option value="zh">中文</option>
                <option value="en">English</option>
              </select>
              <div class="btns">
                <button id="saveUiLanguage" class="ghost">暂存语言修改</button>
                <button class="ghost" data-settings-action="language_status" data-report-target="settingsReport">语言状态</button>
              </div>
            </div>
            <div class="setting-edit-card span4">
              <h3>配置入口 <span class="tag">主路径</span></h3>
              <p class="muted">通道 URL/API Key、模型补丁、Fallback、Runtime 默认值都在各自模块配置，不再回到 TUI 里点散落菜单。</p>
              <div class="btns">
                <button class="ghost" data-section-jump="channel">通道配置</button>
                <button class="ghost" data-section-jump="fallback">Fallback 设置</button>
                <button class="ghost" data-section-jump="runtime">运行默认值</button>
              </div>
            </div>
            <div class="settings-next-step span3">
              <h3>保存规则</h3>
              <p class="muted">修改后先生成保存预览；preview root 写 DB candidate + latest-approved bundle，stable root 走 backup + audit。</p>
              <button class="secondary" data-section-jump="save">去保存审计</button>
            </div>
          </div>
        </div>

        <div class="settings-tab-panel" data-settings-panel="accounts">
          <div class="setting-edit-card">
            <h3>CLI 账号默认值 <span class="tag">草稿预览</span></h3>
            <p class="muted">这里配置已有 account 的默认选择、启用状态、priority、timezone 和 note；Claude account 仍是 human-only。OAuth / AGY 官方登录不再作为 WebUI 主流程。</p>
            <div class="btns" id="accountModuleActions">
              <button class="ghost" data-settings-action="accounts" data-report-target="settingsReport">刷新账号状态</button>
              <button class="ghost" data-section-jump="save">保存账号草稿</button>
            </div>
            <div id="accountTable" class="account-config-grid"></div>
          </div>
        </div>

        <div class="settings-tab-panel" data-settings-panel="guard">
          <div class="settings-panel-grid">
            <div class="setting-edit-card span6">
              <h3>启动快照守卫（Snapshot Guard）</h3>
              <p class="muted">状态是只读报告；接受 baseline 需要人工确认，不在 WebUI 自动执行。</p>
              <div class="btns">
                <button class="ghost" data-settings-action="guard_status" data-report-target="settingsReport">快照状态</button>
                <button class="ghost" data-settings-action="guard_accept_gate" data-report-target="settingsReport">接受基线确认</button>
              </div>
            </div>
            <div class="setting-edit-card span6">
              <h3>迁移 / 网络边界</h3>
              <p class="muted">会触发真实配置、账号目录、proxy/no_proxy 或迁移写入的动作保持人工确认；WebUI 只显示影响面。</p>
              <div class="btns">
                <button class="ghost" data-settings-action="migrate_config_gate" data-report-target="settingsReport">迁移确认</button>
                <button class="ghost" data-settings-action="account_network_gate" data-report-target="settingsReport">账号网络确认</button>
              </div>
            </div>
          </div>
        </div>

        <div class="settings-tab-panel" data-settings-panel="about">
          <div class="settings-panel-grid">
            <div class="setting-edit-card span6">
              <h3>关于 / 版本</h3>
              <p class="muted">默认读取缓存状态；刷新版本检查和升级命令都需要人工确认。</p>
              <div class="btns">
                <button class="ghost" data-settings-action="about" data-report-target="settingsReport">关于状态</button>
                <button class="ghost" data-settings-action="about_refresh_gate" data-report-target="settingsReport">刷新版本确认</button>
                <button class="ghost" data-settings-action="about_upgrade_gate" data-report-target="settingsReport">升级确认</button>
              </div>
            </div>
            <div class="settings-compat-note span6">
              <strong>OAuth 主流程已下线</strong>
              <p>AGY / OAuth 仅作为旧 account 兼容状态查看；新增可用通道请走 API Key provider。</p>
              <details class="account-advanced">
                <summary>查看已下线兼容说明</summary>
                <div class="btns">
                  <button class="ghost" data-settings-action="connect_official_gate" data-report-target="settingsReport">查看下线说明</button>
                </div>
              </details>
            </div>
          </div>
        </div>

        <div class="settings-tab-panel" data-settings-panel="audit">
          <details class="setting-edit-card" open>
            <summary>开发验收辅助，不作为用户设置入口</summary>
            <p class="muted">这些表只用于核对 TUI 功能迁移，不再占据设置主页面。</p>
            <div class="table-wrap"><table id="settingsCoverage"></table></div>
          </details>
          <details class="setting-edit-card mapping-card" id="mappingAuditDetails">
            <summary>验收辅助：TUI ↔ WebUI 对照表</summary>
            <div class="mapping-head">
              <div>
                <h3>TUI ↔ WebUI 对照表</h3>
                <p class="muted">功能入口应在通道、模型测试、真源、Fallback、Runtime 或设置对应 tab 里；这里仅做验收证据。</p>
              </div>
              <div id="mappingFilters" class="filterbar compact"></div>
            </div>
            <div id="acceptancePanel" class="acceptance-panel"></div>
            <div class="table-wrap"><table id="tuiMappingTable"></table></div>
          </details>
        </div>

        <div class="setting-edit-card">
          <h3>报告 / 人工确认</h3>
          <div class="result" id="settingsReport">选择一个设置动作查看结果</div>
        </div>
      </div>
    </section>

    <!-- 保存 / 审计 -->
    <!-- Session 能力面板 -->
    <section class="panel" data-section="sessionAssets">
      <h2>Skill / MCP 管理</h2>
      <p>这里就是会话能力的配置入口：筛选 Skill / MCP / Hook，勾选默认关闭；只有产生未保存变化时，底部才会出现保存栏。</p>
      <div class="asset-hero" id="assetSummary"></div>
      <div class="asset-control-help" id="assetControlHelp"></div>
      <div class="asset-manager">
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
        <div class="asset-source-strip" id="assetManagedRoots"></div>
      </div>
      <details class="oc-advanced" id="assetCliDetails">
        <summary>展开查看各 CLI 的 TUI 确认页能力和来源</summary>
        <div class="card asset-confirm-map" id="assetConfirmMap"></div>
        <div class="asset-cli-grid" id="assetCliOverview"></div>
      </details>
      <div class="grid asset-ops-grid">
        <div class="card span6 asset-config-card asset-ops-card">
          <h3>备份：复制 TOML 片段</h3>
          <p class="muted" id="assetConfigContract">这里保留可复制片段；正常保存请使用底部出现的未保存变化栏。</p>
          <div class="btns">
            <button id="copyAssetPrefs" class="ghost">复制偏好片段</button>
            <button id="resetAssetPrefs" class="ghost">恢复当前偏好</button>
          </div>
          <details>
            <summary>查看要写入 preferences.toml 的片段</summary>
            <pre class="result" id="assetPreferenceSnippet"></pre>
          </details>
        </div>
        <div class="card span6 asset-ops-card">
          <h3>Global 添加位置</h3>
          <p class="muted">要让原生 CLI 也能加载，就把 Skill 放到对应目录；MMS 本页只管理 MMS 启动时是否默认关闭。</p>
          <p class="mono">Claude: ~/.claude/skills/&lt;skill-name&gt;</p>
          <p class="mono">Codex: ~/.codex/skills/&lt;skill-name&gt;</p>
          <details>
            <summary>查看已检测到的 Global / plugin 位置</summary>
            <div class="asset-roots" id="assetGlobalRoots"></div>
          </details>
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
            <summary>高级 / 恢复：plan JSON 与 CLI fallback</summary>
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
          <h3 style="margin-bottom:8px">原始 diff / 审计详情</h3>
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
<div class="asset-pending-bar" id="assetPendingBar"></div>
<div class="toast" id="toast"></div>
<script>
const sections=[
  ['source','真源状态','DB / legacy / bundle'],
  ['channel','通道配置','URL / Key / 协议 / 模型'],
  ['test','模型测试','ping / chat smoke'],
  ['fallback','Fallback','rescue / vision'],
  ['runtime','运行默认值','首选 CLI / OpenCode'],
  ['sessionAssets','能力面板','技能 / MCP / 钩子'],
  ['settings','设置','配置台 / 账号 / 安全'],
  ['save','保存审计','diff / backup / audit'],
  ['refs','本地参考','配置契约 / 文档']
];
let state=null; let activeProvider=0; let activeProviderTab='config'; let activeProviderFormTab='basic'; let lastPlan=null; let opencodeAgentFilter="all"; let opencodeOnlyOverridden=false; let editingExtraModels=false; let settingsActiveTab='accounts'; let settingsMappingFilter='all'; let touchedProviders=new Set(); let staleCleanupProviders=new Set(); let lastGateCommands=[]; let checkedMappingRows=new Set(); let assetTab='mms_dynamic'; let assetCli='all'; let assetKind='all'; let assetQuery=''; let assetDisabledDraft=null; let assetGroupOpenState={}; let assetConfirmPrefsChecked=false; let assetConfirmPhraseValue=''; let assetPrefsResultText='不会走模型配置审计；这里只保存 Skill/MCP/Hook 偏好。';
const $=id=>document.getElementById(id);
function toast(msg){const el=$('toast');el.textContent=msg;el.classList.add('show');setTimeout(()=>el.classList.remove('show'),3600)}
async function api(path,body){const res=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body||{})});const data=await res.json();if(!res.ok){data.ok=false;data.http_status=res.status;data.error=data.error||res.statusText}return data}
function current(){return state.providers[activeProvider]}
function touchProvider(id){if(id)touchedProviders.add(id)}
function setSection(id){document.querySelectorAll('[data-section]').forEach(el=>el.classList.toggle('hide',el.dataset.section!==id));document.querySelectorAll('.navbtn').forEach(el=>el.classList.toggle('active',el.dataset.id===id))}
function switchProviderTab(tab){activeProviderTab=tab;document.querySelectorAll('.provider-tabs .tab-btn').forEach(b=>b.classList.toggle('active',b.dataset.tab===tab));document.querySelectorAll('.tab-panel').forEach(p=>p.classList.toggle('active',p.dataset.tabPanel===tab))}
function switchProviderFormTab(tab){activeProviderFormTab=tab||'basic';document.querySelectorAll('[data-provider-form-tab]').forEach(b=>b.classList.toggle('active',b.dataset.providerFormTab===activeProviderFormTab));document.querySelectorAll('[data-provider-form-panel]').forEach(p=>p.classList.toggle('active',p.dataset.providerFormPanel===activeProviderFormTab))}
function renderNav(){ $('nav').innerHTML=sections.map(([id,title,sub])=>`<button class="navbtn" data-id="${id}">${title}<small>${sub}</small></button>`).join(''); document.querySelectorAll('.navbtn').forEach(b=>b.onclick=()=>setSection(b.dataset.id)); setSection('source') }
function renderStatus(){const providers=state.providers||[];const root=(state.model_source_status||{}).root||{};$('statusbar').innerHTML=`<span class="pill ok">${state.mode}</span><span class="pill">${escapeHtml(root.mode||'stable')}</span><span class="pill">通道 ${providers.length}</span><span class="pill">配置：${escapeHtml(state.paths.config||'-')}</span><span class="pill">策略模型：${state.policy_summary.model_count}</span>`}
function escapeHtml(s){return String(s??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]))}
function yn(value){return value?'是':'否'}
function enumLabel(value){const key=String(value??'');const map={ok:'正常',missing:'缺失',unknown:'未知',ready:'就绪','not ready':'未就绪',not_ready:'未就绪',auto:'自动',enable:'启用',disable:'禁用',enabled:'已启用',disabled:'已禁用',configured:'已配置',none:'未配置',imported:'已导入',not_imported:'未导入',blocked:'已拦截',high:'高风险',medium:'中风险',low:'低风险',critical:'严重',required:'必需',redacted:'已脱敏',included:'包含明文'};return map[key]||key||'-'}
function writePolicyLabel(policy){const key=String(policy||'');const map={native:'原生',report:'报告',draft_review:'草稿预览',human_gate:'人工确认',missing:'缺失',report_only:'只读报告',native_test_panel:'原生测试面板',planned:'待补齐',existing_save_flow:'现有保存流程',manual_cli_only:'仅人工 CLI',draft_review_confirmed_save:'草稿预览后确认保存',manual_login_only:'仅人工登录',mixed_draft_review_human_gate:'草稿预览 + 人工确认',manual_cli_human_gate:'人工 CLI 确认',read_only_report:'只读报告',draft_review_human_gate:'草稿预览 + 人工确认',save_flow_or_preview_publish:'保存流程 / preview 发布',audited_secret_write:'审计凭据写入',network_policy_human_gate:'网络策略人工确认',account_home_human_gate:'账号 home 人工确认',account_network_human_gate:'账号网络人工确认',manual_remove_only:'仅人工删除',read_only:'只读',mixed:'混合',save_preview:'保存预览',network_write_human_gate:'联网写入人工确认',network_human_gate:'联网人工确认',write_human_gate:'写入人工确认',local_artifact_human_gate:'本地产物人工确认',speed_stats_write_human_gate:'速度统计写入人工确认',deprecated_read_only_compat:'已下线，只读兼容',deprecated_no_webui_iteration:'已下线，不再迭代',claude_human_only_locked:'Claude 人工锁定',can_degrade_after_save_flow_verified:'保存链路验证后可弱化',can_degrade_after_route_guard_verified:'route guard 验证后可弱化',can_degrade_after_report_smoke:'报告 smoke 后可弱化',keep_emergency_only_for_login_remove_and_claude_human_gate:'仅保留登录/删除/Claude 人工确认应急',keep_emergency_only_for_remove_and_claude_human_gate:'仅保留删除/Claude 人工确认应急',read_only_reports_plus_existing_apply:'只读报告 + 现有 apply',can_degrade_report_display_after_webui_smoke:'WebUI smoke 后可弱化报告展示',keep_until_webui_double_confirm_flow_exists:'保留到 WebUI 双确认流程补齐',can_degrade_config_display_after_save_flow_verified:'保存链路验证后可弱化配置展示',keep_emergency_only_until_handover_write_flow_exists:'保留应急直到 handover 写入流程补齐',report_or_planned:'报告或待补齐',keep_small:'保留最小入口',module_native_controls_plus_reports:'模块原生控件 + 报告',keep_as_keyboard_launcher_until_webui_launch_surface_exists:'保留键盘 launcher，直到 WebUI 启动面补齐'};return map[key]||key||'-'}
function clickTargetsLabel(text){const map={open_section:'打开模块',settings_report:'查看报告',save_preview:'保存预览',human_gate_card:'人工确认卡片',missing_gap:'缺口'};return String(text||'-').split(' + ').map(x=>map[x]||x).join(' + ')}
function riskLabel(level){return enumLabel(level||'high')}
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
  const ready=bundle.runtime_ready===true?'就绪':bundle.runtime_ready===false?'未就绪':'未知';
  const bundleCommand=(root.command||state.command||'mms')==='mmf'?'mmf config bundle --json':'mms config bundle --json';
  box.innerHTML=`<div class="card span6"><h3>配置 Root</h3><p class="mono">${escapeHtml(root.config_root||status.config_root||consumer.config_root||'-')}</p><p class="muted">${escapeHtml(status.headline||'-')}</p><span class="tag ${status.ready?'':'off'}">${enumLabel(status.status||'unknown')}</span><span class="tag">${escapeHtml(root.command||state.command||'-')}</span><span class="tag">${escapeHtml(root.mode||'-')}</span><span class="tag">${escapeHtml(root.root_source||'-')}</span></div><div class="card span6"><h3>Registry DB</h3><p class="mono">${escapeHtml(db.path||'-')}</p><span class="tag ${db.status==='ok'?'':'off'}">${escapeHtml(db.status||'missing')}</span><span class="tag">source ${counts.source_snapshot||0}</span><span class="tag">fact ${counts.model_fact||0}</span><span class="tag">routes ${counts.provider_route||0}</span></div><div class="card span6"><h3>Legacy 导入</h3><p class="muted">${escapeHtml(legacy.next_action||'-')}</p><span class="tag">通道 ${legacy.provider_count||0}</span><span class="tag ${legacy.conflict_count?'off':''}">冲突 ${legacy.conflict_count||0}</span><span class="tag ${candidates.status==='imported'?'':'off'}">候选 ${enumLabel(candidates.status||'not_imported')}</span><span class="tag">候选 route ${candidates.provider_route_count||0}</span></div><div class="card span6"><h3>已批准 Bundle</h3><p class="mono">${escapeHtml(bundle.manifest_path||'-')}</p><span class="tag ${okBundle==='ok'?'':'off'}">${enumLabel(bundle.status||'missing')}</span><span class="tag">已验证 ${yn(bundle.verified)}</span><span class="tag ${bundle.runtime_ready===true?'':'off'}">runtime ${ready}</span><span class="tag">缺 API Key ${bundle.router_missing_api_key_count||0}</span><span class="tag">文件 ${bundle.file_count||0}</span></div><div class="card span12"><h3>消费端 Bundle</h3><p class="mono">${escapeHtml(consumer.consumer_entrypoint||bundle.manifest_path||'-')}</p><p class="muted">${escapeHtml((rules.length?rules.join(' · '):'下游只读 latest-approved manifest；不读 SQLite；不混合不同 revision。'))}</p><span class="tag ${okConsumer==='ok'?'':'off'}">${enumLabel(consumer.status||'missing')}</span><span class="tag">已验证 ${yn(consumer.verified)}</span><span class="tag">bundle ${escapeHtml(revisions.bundle||'-')}</span><span class="tag">route ${escapeHtml(revisions.route||'-')}</span><span class="tag">policy ${escapeHtml(revisions.policy||'-')}</span><span class="tag">profile ${escapeHtml(revisions.profile||'-')}</span><span class="tag">文件 ${Object.keys(consumerFiles).length}</span><p class="muted">CLI: <span class="mono">${escapeHtml(bundleCommand)}</span></p></div><div class="card span12"><h3>晋级计划 / 人工确认</h3><p class="muted">stable backup + bundle comparison 是只读审查；apply 仍停在 人工确认。</p><span class="tag ${okPromotion==='ok'?'':'off'}">${escapeHtml(promotion.status||'not_ready')}</span><span class="tag">人工审查 ${promotion.ready_for_human_review?'就绪':'未就绪'}</span><span class="tag">apply ${promotion.apply_enabled?'已启用':'已禁用'}</span><span class="tag">stable ${escapeHtml(safety.stable_write_policy||'human_only')}</span><span class="tag">backup ${backup.requires_backup_before_apply?'必需':'未知'}</span><span class="tag">将创建 backup ${yn(backup.would_create_backup)}</span><span class="tag">Bundle 对比 ${escapeHtml(compare.comparison_status||'-')}</span><p class="muted">preview ${escapeHtml(comparePreview.bundle_revision||comparePreview.status||'-')} → stable ${escapeHtml(compareStable.bundle_revision||compareStable.status||'-')}</p></div><div class="card span12"><h3>4.0 发布就绪度</h3><p class="muted">只读 audit：证明自动检查已到 stable promotion 人工确认；release_complete 仍为 false。</p><span class="tag ${readinessOk==='ok'?'':'off'}">${escapeHtml(readiness.result||'NOT_READY')}</span><span class="tag">状态 ${enumLabel(readiness.status||'not_ready')}</span><span class="tag">发布完成 ${yn(readiness.release_complete)}</span><span class="tag">人工确认 ${readiness.ready_for_human_gate?'就绪':'未就绪'}</span><span class="tag">阻塞 ${readinessBlocked.length}</span><span class="tag">检查项 ${readinessReqs.filter(r=>r&&r.ok).length}/${readinessReqs.length}</span><span class="tag">阻塞原因 ${escapeHtml(readiness.completion_blocker||'-')}</span><p class="muted">阻塞检查项：${escapeHtml(readinessBlocked.length?readinessBlocked.join(', '):'-')}</p><p class="muted">下一步：<span class="mono">${escapeHtml(readinessNext.command||readinessNext.label||'-')}</span></p></div><div class="card span12"><details><summary>原始状态 JSON</summary><div class="result">${escapeHtml(JSON.stringify({model_source_status:status,consumer_bundle_status:consumer,config_v2_promotion_plan:promotion,config_v2_release_readiness:readiness},null,2))}</div></details></div>`
}
function providerEntries(){return (state.providers||[]).map((p,i)=>({p,i})).sort((a,b)=>{if(!!a.p.enabled!==!!b.p.enabled)return a.p.enabled?-1:1;return a.i-b.i})}
function renderProviderList(){const list=$('providerList');list.innerHTML=providerEntries().map(({p,i})=>{const keyTag=p.api_key?'<span class="tag">待保存 Key</span>':(p.has_api_key?'<span class="tag">已保存 Key</span>':'<span class="tag off">缺少 Key</span>');const usage=p.usage||{};return `<div class="provider-item ${i===activeProvider?'active':''}" data-i="${i}"><strong>${escapeHtml(p.name||p.id)}</strong><span class="muted mono">${escapeHtml(p.id)}</span><br>${p.enabled?'<span class="tag">已启用</span>':'<span class="tag off">已禁用</span>'}${keyTag}<span class="tag">模型 ${p.models?.length||0}</span><span class="tag">启动 ${usage.launches||0}</span></div>`}).join('');document.querySelectorAll('.provider-item').forEach(el=>el.onclick=()=>{activeProvider=Number(el.dataset.i);renderAll()})}
function renderProviders(){renderProviderList();renderProviderForm();renderTestSelectors();renderModelTable();}
function checks(name,values,allowed){values=values||[];return `<div class="checks">${allowed.map(v=>`<label class="check"><input type="checkbox" name="${name}" value="${v}" ${values.includes(v)?'checked':''}><span>${v}</span></label>`).join('')}</div>`}
function checkedValues(name){return [...document.querySelectorAll(`input[name="${name}"]:checked`)].map(x=>x.value)}

function modelFamilies(){return (state.model_families&&state.model_families.length?state.model_families:['Claude','GPT','Gemini','DeepSeek','Qwen','Kimi','Mimo','MiniMax','GLM'])}
function familyPriorityInputs(values={},name='familyPriority'){return `<div class="grid">${modelFamilies().map(f=>`<div class="span4"><label>${escapeHtml(f)}</label><input data-family-priority="${escapeHtml(name)}" data-family="${escapeHtml(f)}" type="number" min="1" value="${escapeHtml(values[f]||'')}" placeholder="继承"></div>`).join('')}</div>`}
function readFamilyPriorityInputs(name='familyPriority'){const result={};document.querySelectorAll(`[data-family-priority="${name}"]`).forEach(input=>{const family=input.dataset.family;const raw=String(input.value||'').trim();if(family&&raw){result[family]=Math.max(1,Number(raw)||100)}});return result}
function formatFamilyOverrides(values={}){return Object.entries(values||{}).map(([k,v])=>`${k}=${v}`).join(', ')}
function parseFamilyOverrides(text){const allowed=new Set(modelFamilies());const result={};String(text||'').split(/[\n,]/).map(x=>x.trim()).filter(Boolean).forEach(part=>{const [rawFamily,rawValue]=part.split(/[=:]/);const family=modelFamilies().find(f=>f.toLowerCase()===String(rawFamily||'').trim().toLowerCase());const value=Math.max(1,Number(String(rawValue||'').trim())||0);if(family&&allowed.has(family)&&value>0)result[family]=value});return result}
function modelSourceLabel(source){return {remote:'远端',fallback:'fallback',extra:'手动补充',hidden:'隐藏',derived_alias:'派生 alias',manual:'手动'}[source]||escapeHtml(source||'-')}
function renderProviderForm(){
  const p=current();
  if(!p){$('providerForm').innerHTML='<p>暂无通道</p>';return}
  const pendingKey=!!p.api_key;
  const keyPlaceholder=pendingKey?'已输入新 key，保存前会保留（不回显）':(p.has_api_key?'已保存；输入新 key 才会覆盖':'sk-...');
  const activeTabs=new Set(['basic','connect','advanced','reports']);
  if(!activeTabs.has(activeProviderFormTab))activeProviderFormTab='basic';
  const familyOverrides=p.family_priority_overrides||{};
  const familyOverrideCount=Object.keys(familyOverrides).filter(k=>familyOverrides[k]).length;
  const familySummary=familyOverrideCount?`已配置 ${familyOverrideCount} 个 family`:'默认继承 priority';
  const tabButton=(id,label,desc)=>`<button type="button" class="provider-form-tab ${activeProviderFormTab===id?'active':''}" data-provider-form-tab="${id}">${label}<span class="muted"> · ${desc}</span></button>`;
  const panelClass=id=>`provider-form-panel ${activeProviderFormTab===id?'active':''}`;
  $('providerForm').innerHTML=`<div class="provider-editor-shell">
    <div class="provider-form-tabs" role="tablist" aria-label="通道配置分组">
      ${tabButton('basic','基础信息','ID / 默认 / priority')}
      ${tabButton('connect','连接与协议','Base URL / Key')}
      ${tabButton('advanced','策略与高级','Claude / Family / 删除')}
      ${tabButton('reports','报告与确认','统计 / 人工确认')}
    </div>
    <div class="${panelClass('basic')}" data-provider-form-panel="basic">
      <div class="grid">
        <div class="span6"><label>内部 ID</label><input id="pId" value="${escapeHtml(p.id)}"></div>
        <div class="span6"><label>显示名</label><input id="pName" value="${escapeHtml(p.name)}"></div>
        <div class="span4"><label>状态</label><select id="pEnabled"><option value="true" ${p.enabled?'selected':''}>启用</option><option value="false" ${!p.enabled?'selected':''}>禁用</option></select></div>
        <div class="span4"><label>role（角色）</label><select id="pRole">${['primary','auto','fallback'].map(v=>`<option ${p.role===v?'selected':''}>${v}</option>`).join('')}</select></div>
        <div class="span4"><label>priority（优先级）</label><input id="pPriority" type="number" value="${escapeHtml(p.priority||100)}"></div>
        <div class="span12 check"><input id="pDefault" type="checkbox" ${state.provider_default===p.id?'checked':''}><span>设为默认通道</span></div>
        <div class="span12"><p class="muted">role 决定 primary / auto / fallback 层级；同一层级里 priority 数值越大越优先。这里只暂存草稿，真正写入仍走保存预览。</p></div>
      </div>
    </div>
    <div class="${panelClass('connect')}" data-provider-form-panel="connect">
      <div class="grid">
        <div class="span6"><label>OpenAI Base URL</label><input id="pOpenAI" value="${escapeHtml(p.openai_base_url||'')}" placeholder="https://.../v1"></div>
        <div class="span6"><label>Anthropic Base URL</label><input id="pAnthropic" value="${escapeHtml(p.anthropic_base_url||'')}" placeholder="https://.../v1 或 /anthropic"></div>
        <div class="span6"><label>API Key（留空不更新）</label><input id="pKey" type="password" placeholder="${escapeHtml(keyPlaceholder)}"></div>
        <div class="span6"><label>models_endpoint</label><input id="pModelsEndpoint" value="${escapeHtml(p.models_endpoint||'/models')}" placeholder="/models 或 manual"></div>
        <div class="span12"><label>protocols（协议）</label>${checks('pProtocols',p.protocols,['anthropic_messages','openai_chat_completions'])}</div>
        <div class="span12"><label>supported CLIs（支持的 CLI）</label>${checks('pClis',p.supported_clis,['claude','codex','opencode','pi','agy'])}</div>
        <div class="span12 check"><input id="pUpdateCreds" type="checkbox" ${p.update_credentials?'checked':''}><span>保存时更新凭据（stable 写 credentials.sh；preview 写 secret backend；需要填写 API Key）</span></div>
      </div>
    </div>
    <div class="${panelClass('advanced')}" data-provider-form-panel="advanced">
      <div class="grid">
        <div class="span4"><label>Claude 1M 策略</label><select id="pClaude1m">${['auto','enable','disable'].map(v=>`<option value="${v}" ${(p.claude_1m_mode||'auto')===v?'selected':''}>${enumLabel(v)}</option>`).join('')}</select></div>
        <div class="span4"><label>timezone（时区）</label><input id="pTimezone" value="${escapeHtml(p.timezone||'')}" placeholder="Asia/Singapore"></div>
        <div class="span4"><label>网络策略</label><p class="muted">proxy ${p.proxy_configured?'已配置':'未配置'} · no_proxy ${p.no_proxy_configured?'已配置':'未配置'} · 明文走人工确认</p><button type="button" class="ghost" data-settings-action="provider_network_gate" data-report-target="channelReport">查看网络配置人工确认</button></div>
        <div class="span12"><label>备注 note</label><input id="pNote" value="${escapeHtml(p.note||'')}" placeholder="用途、限制或路由说明"></div>
        <div class="span12">
          <details class="provider-advanced">
            <summary><span>Family 权重覆盖（不常用）</span><span class="tag off">${escapeHtml(familySummary)}</span></summary>
            <p class="muted">对应 TUI 模型页 +/- 对单个 family 写入的权重覆盖；平时保持折叠，留空表示继承全局 priority。</p>
            ${familyPriorityInputs(familyOverrides,'providerFamilyPriority')}
          </details>
        </div>
        <div class="span12 delete-zone"><label>删除通道确认</label><input id="pDeleteConfirm" placeholder="输入 ${escapeHtml(p.id)} 后从草稿移除"><p class="muted">只从 WebUI 草稿移除；真正写入仍需要保存预览和确认。</p><div class="btns"><button type="button" id="deleteProvider" class="danger">从草稿移除通道</button></div></div>
      </div>
    </div>
    <div class="${panelClass('reports')}" data-provider-form-panel="reports">
      <div class="provider-action-grid">
        <div class="explain-card span4"><h4>使用统计</h4><p>读取当前通道的 usage 明细，并按这个通道内的模型展开启动次数；不会把其他通道混进来。</p><button type="button" class="ghost" data-settings-action="provider_usage_summary" data-report-target="channelReport">查看当前通道使用统计</button></div>
        <div class="explain-card span4"><h4>保存审计入口</h4><p>这里改的是持久通道配置。填完 Base URL、API Key、protocol、模型补丁后，统一到保存页生成 diff 和审计摘要。</p><button type="button" class="ghost" data-section-jump="save">去生成保存预览</button></div>
        <div class="explain-card span4"><h4>高级人工确认</h4><p>网络策略、自动排序这类会影响路由或本机边界的动作，不再放主路径；需要时只看说明，不自动执行。</p><button type="button" class="ghost" data-settings-action="provider_network_gate" data-report-target="channelReport">查看网络配置人工确认</button></div>
        <div class="span12"><div class="result module-report" id="channelReport">选择上方动作查看表格报告或人工确认说明。</div></div>
      </div>
    </div>
    <div class="btns provider-editor-actions"><button type="button" id="saveProviderForm">保存通道修改</button></div>
  </div>`;
  bindProviderForm();
  bindSettingsActionButtons();
}
function bindProviderForm(){
  document.querySelectorAll('[data-provider-form-tab]').forEach(btn=>{btn.onclick=()=>switchProviderFormTab(btn.dataset.providerFormTab)});
  ['pId','pName','pEnabled','pRole','pPriority','pClaude1m','pTimezone','pNote','pOpenAI','pAnthropic','pModelsEndpoint'].forEach(id=>{const el=$(id);if(!el)return;el.oninput=syncProvider;el.onchange=syncProvider});
  const keyEl=$('pKey');
  if(keyEl)keyEl.oninput=()=>{keyEl.dataset.touched='1';syncProvider()};
  const updateCreds=$('pUpdateCreds');if(updateCreds)updateCreds.onchange=syncProvider;
  const defaultEl=$('pDefault');if(defaultEl)defaultEl.onchange=()=>{syncProvider(); if($('pDefault').checked) state.provider_default=current().id; renderProviders();};
  const del=$('deleteProvider');if(del)del.onclick=deleteCurrentProviderDraft;
  document.querySelectorAll('input[name="pProtocols"],input[name="pClis"],[data-family-priority="providerFamilyPriority"]').forEach(x=>x.onchange=syncProvider);
  const save=$('saveProviderForm');if(save)save.onclick=()=>{syncProvider();setSection('save');toast('通道修改已暂存，生成保存预览后再写入')}
}
function deleteCurrentProviderDraft(){const p=current();if(!p)return;const typed=($('pDeleteConfirm')?.value||'').trim();if(typed!==p.id){toast('输入当前通道 ID 后才能从草稿移除');return}if((state.providers||[]).length<=1){toast('至少保留一个通道；删除最后一个通道请走 CLI/人工确认');return}const removed=p.id;state.providers.splice(activeProvider,1);touchedProviders.add(removed);if(state.provider_default===removed)state.provider_default=(state.providers[0]||{}).id||'';activeProvider=Math.max(0,Math.min(activeProvider,state.providers.length-1));lastPlan=null;renderAll();setSection('save');toast(`${removed} 已从 WebUI 草稿移除，生成保存预览后再写入`)}
function syncProvider(){const p=current(); if(!p)return; const old=p.id;touchProvider(old);const keyEl=$('pKey');const updateEl=$('pUpdateCreds');p.id=$('pId').value.trim()||p.id;if(p.id!==old){touchedProviders.delete(old);touchProvider(p.id)}p.name=$('pName').value.trim()||p.id;p.enabled=$('pEnabled').value==='true';p.role=$('pRole').value;p.priority=Number($('pPriority').value||100);p.family_priority_overrides=readFamilyPriorityInputs('providerFamilyPriority');p.claude_1m_mode=$('pClaude1m').value;p.timezone=$('pTimezone').value.trim();p.note=$('pNote').value.trim();p.openai_base_url=$('pOpenAI').value.trim();p.anthropic_base_url=$('pAnthropic').value.trim();p.models_endpoint=$('pModelsEndpoint').value.trim()||'/models';p.protocols=checkedValues('pProtocols');p.supported_clis=checkedValues('pClis');const keyText=keyEl?keyEl.value.trim():'';const keyTouched=keyEl?.dataset?.touched==='1';if(keyText){p.api_key=keyText;p.pending_api_key=true;p.has_api_key=true;if(updateEl)updateEl.checked=true}else if(keyTouched){p.api_key='';p.pending_api_key=false}p.update_credentials=!!(updateEl&&updateEl.checked);if(state.provider_default===old)state.provider_default=p.id;renderProviderList();renderTestSelectors();}

function derivedAliases(base,p){const ids=(base||[]).map(x=>String(x||''));const tails=ids.map(id=>id.toLowerCase().split('/').pop());const aliases=[];if(tails.some(id=>id.startsWith('claude-sonnet-4-')||id.startsWith('claude-sonnet-4.')))aliases.push('claude-sonnet-4-6');if(tails.some(id=>id.startsWith('claude-opus-4-')||id.startsWith('claude-opus-4.')))aliases.push('claude-opus-4-6');const ident=String([p?.id,p?.name,p?.label,p?.provider_profile].filter(Boolean).join(' ')).toLowerCase();const anthropic=String(p?.anthropic_base_url||p?.default_anthropic_base_url||'').toLowerCase();if((anthropic.includes('xiaomimimo.com')||ident.includes('mimo')||ident.includes('xiaomi'))&&!ident.includes('openrouter')){['mimo-v2.5-pro','mimo-v2.5'].forEach(id=>{if(ids.includes(id)&&!ids.includes(`${id}[1m]`))aliases.push(`${id}[1m]`)})}return aliases}
function providerModels(p){p=p||{};const map=new Map();const hiddenLower=new Set((p.hidden_models||[]).map(x=>String(x||'').toLowerCase()));const baseRows=(p.models||[]).filter(r=>r&&r.id&&r.source!=='hidden');baseRows.forEach(r=>map.set(r.id,{...r,visible:r.visible!==false&&!hiddenLower.has(String(r.id).toLowerCase()),capabilities:{...(r.capabilities||{})}}));if(!baseRows.length){(p.fallback_models||[]).forEach(id=>{if(!map.has(id))map.set(id,{id,source:'fallback',visible:!hiddenLower.has(String(id).toLowerCase()),favorite:false,capabilities:defaultCaps(id)})})}const baseIds=[...map.keys()];derivedAliases(baseIds.filter(id=>!hiddenLower.has(String(id).toLowerCase())),p).forEach(id=>{if(!map.has(id))map.set(id,{id,source:'derived_alias',visible:!hiddenLower.has(String(id).toLowerCase()),favorite:false,capabilities:defaultCaps(id)})});(p.extra_models||[]).forEach(id=>{if(!map.has(id))map.set(id,{id,source:'extra',visible:!hiddenLower.has(String(id).toLowerCase()),favorite:false,capabilities:defaultCaps(id)})});(p.hidden_models||[]).forEach(id=>{[...map.keys()].forEach(key=>{if(String(key).toLowerCase()===String(id).toLowerCase())map.get(key).visible=false})});return [...map.values()].sort((a,b)=>a.id.localeCompare(b.id))}
function defaultCaps(id){const l=String(id||'').toLowerCase();return {text:true,vision:['mimo-v2.5','mimo-v2-omni','k2.6','k2.6-code-preview','kimi-k2.5','qwen3.6-plus','qwen3.6-flash','qwen3.5-plus'].includes(l)||l.startsWith('claude-')||l.startsWith('gemini-'),tool_use:/^(claude|gpt|o|qwen|kimi|glm|minimax|gemini)/.test(l),reasoning:/gpt-5|qwen3|kimi-k2|glm-5|deepseek|claude/.test(l),long_context:/1m|long|qwen3|kimi-k2|gpt-5|claude/.test(l),cache_sensitive:/^(qwen|kimi|k2\.|glm|deepseek|minimax|mimo)/.test(l)}}
function providerCurrentIds(p){return new Set(providerModels(p).map(r=>r.id))}
function staleHiddenModels(p){const ids=providerCurrentIds(p);return [...new Set([...(p.stale_hidden_models||[]),...(p.hidden_models||[]).filter(id=>!ids.has(id))])]}
function cleanupStaleHidden(p){const stale=staleHiddenModels(p);const doomed=new Set(stale);p.hidden_models=(p.hidden_models||[]).filter(x=>!doomed.has(x));p.stale_hidden_models=[];return stale.length}
function cleanupAllStaleHidden(){let total=0;(state.providers||[]).forEach(p=>{const count=cleanupStaleHidden(p);if(count)touchProvider(p.id);total+=count});renderProviders();toast(total?`已移除 ${total} 条未匹配隐藏规则`:'没有需要移除的未匹配隐藏规则')}
function staleRouteModels(p){const approved=(p.approved_route_models&&p.approved_route_models.length?p.approved_route_models:(p.fallback_models||[]));const remote=new Set((p.models||[]).filter(r=>r&&r.id).map(r=>String(r.id)));const extras=new Set((p.extra_models||[]).map(x=>String(x)));return [...new Set(approved.filter(id=>id&&!remote.has(String(id))&&!extras.has(String(id))))]}
function renderStaleRouteBox(p){const box=$('staleRouteBox');if(!box)return;const stale=staleRouteModels(p);if(!stale.length){box.innerHTML='<strong>缺失旧 route</strong><p class="muted">当前没有“本地已批准但本次拉取未返回”的旧 route。</p>';return}const armed=staleCleanupProviders.has(p.id);box.innerHTML=`<strong>缺失旧 route（默认保留）</strong><p class="muted">这些模型在本地已批准 routes 里，但不在当前拉取到的模型列表里。默认不会删除；如果勾选“拉取后自动标记”，本页后续拉取会自动标记清理。避免上游 /models 抖动或 New API 临时关闭导致下游模型被清空。</p><div class="chips">${stale.slice(0,24).map(m=>`<span class="chip">${escapeHtml(m)}</span>`).join('')}${stale.length>24?`<span class="chip">+${stale.length-24}</span>`:''}</div><div class="btns"><button id="armStaleRouteCleanup" class="ghost">${armed?'已标记：保存时清理这些旧 route':'显式标记保存时清理这些旧 route'}</button></div>`;$('armStaleRouteCleanup').onclick=()=>{staleCleanupProviders.add(p.id);touchProvider(p.id);renderStaleRouteBox(p);toast(`已标记 ${p.id}：下次写入预览 DB 会清理 ${stale.length} 条缺失旧 route`)}}
function visibleModelsForProvider(providerId,{visionFirst=false,includeHidden=false,enabledOnly=false}={}){let rows=[];(state.providers||[]).forEach(p=>{if(providerId&&p.id!==providerId)return;if(enabledOnly&&p.enabled===false)return;providerModels(p).forEach(r=>{if(!includeHidden&&r.visible===false)return;rows.push({...r,provider_id:p.id,provider_name:p.name||p.id,capabilities:{...(r.capabilities||defaultCaps(r.id))}})})});const seen=new Set();rows=rows.filter(r=>{const key=(providerId?'':r.provider_id+'::')+r.id;if(seen.has(key))return false;seen.add(key);return true});rows.sort((a,b)=>{const av=!!(a.capabilities||{}).vision,bv=!!(b.capabilities||{}).vision;if(visionFirst&&av!==bv)return av?-1:1;return (a.provider_id+' '+a.id).localeCompare(b.provider_id+' '+b.id)});return rows}
function providerOptions(selected,{blankLabel='请选择通道',auto=false,enabledOnly=false}={}){const opts=[];const providers=providerEntries().filter(({p})=>!enabledOnly||p.enabled||p.id===selected);if(auto)opts.push(`<option value="" ${!selected?'selected':''}>自动选择通道</option>`);else opts.push(`<option value="" ${!selected?'selected':''}>${escapeHtml(blankLabel)}</option>`);opts.push(...providers.map(({p})=>{const disabled=p.enabled?'':' [已禁用，当前配置值]';return `<option value="${escapeHtml(p.id)}" ${p.id===selected?'selected':''}>${escapeHtml(p.name||p.id)} / ${escapeHtml(p.id)}${disabled}</option>`}));if(selected&&!state.providers.some(p=>p.id===selected))opts.push(`<option value="${escapeHtml(selected)}" selected>当前配置值：${escapeHtml(selected)}</option>`);return opts.join('')}
function modelOptionValue(providerId,row){return providerId?row.id:`${row.provider_id}::${row.id}`}
function decodeModelSelection(value,currentProvider){const text=String(value||'');if(!text)return{provider_id:currentProvider||'',model:''};const marker='::';if(text.includes(marker)){const [provider_id,...rest]=text.split(marker);return{provider_id,model:rest.join(marker)}}return{provider_id:currentProvider||'',model:text}}
function modelOptions(providerId,selected,{visionFirst=false,auto=false,defaultModels=[],enabledOnly=false,selectedProvider=''}={}){const rows=visibleModelsForProvider(providerId,{visionFirst,enabledOnly});let opts=[];if(auto)opts.push(`<option value="" ${!selected?'selected':''}>自动路线${defaultModels.length?'：'+escapeHtml(defaultModels.join(' / ')):''}</option>`);else opts.push(`<option value="" ${!selected?'selected':''}>请选择模型</option>`);let matched=false;opts.push(...rows.map(r=>{const value=modelOptionValue(providerId,r);const label=providerId?r.id:`${r.provider_id} / ${r.id}`;const tag=(r.capabilities||{}).vision?' [vision]':'';const isSelected=providerId?r.id===selected:((selectedProvider&&r.provider_id===selectedProvider&&r.id===selected)||(!selectedProvider&&r.id===selected));if(isSelected)matched=true;return `<option value="${escapeHtml(value)}" ${isSelected?'selected':''}>${escapeHtml(label)}${tag}</option>`}));if(selected&&!matched)opts.push(`<option value="${escapeHtml(selected)}" selected>当前配置值：${escapeHtml(selected)}</option>`);return opts.join('')}
function renderStaleHiddenBox(p){const stale=staleHiddenModels(p);const box=$('staleHiddenBox');if(!box)return;if(!stale.length){box.innerHTML='<strong>未匹配隐藏规则（hidden_models）</strong><p class="muted">当前没有“暂时匹配不到模型行”的隐藏规则。</p>';return}box.innerHTML=`<strong>未匹配隐藏规则（hidden_models）</strong><p class="muted">这些只是当前通道 hidden_models 里的隐藏规则，暂时没有匹配到当前模型行；不等于远端不存在，也不等于 route 待删除。移除后如果模型仍在远端或 approved routes 里，会重新显示出来。</p><div class="chips">${stale.map(m=>`<span class="chip">${escapeHtml(m)} <button data-stale-rm="${escapeHtml(m)}">移除记录</button></span>`).join('')}</div><div class="btns"><button id="clearStaleHidden" class="ghost">移除当前通道未匹配隐藏规则</button></div>`;document.querySelectorAll('[data-stale-rm]').forEach(b=>b.onclick=()=>{p.hidden_models=(p.hidden_models||[]).filter(x=>x!==b.dataset.staleRm);p.stale_hidden_models=(p.stale_hidden_models||[]).filter(x=>x!==b.dataset.staleRm);touchProvider(p.id);renderModelTable()});$('clearStaleHidden').onclick=()=>{const count=cleanupStaleHidden(p);if(count)touchProvider(p.id);renderModelTable();toast(count?`已移除 ${count} 条当前通道未匹配隐藏规则`:'没有需要移除的未匹配隐藏规则')}}
function renderModelInventorySummary(p){const box=$('modelInventorySummary');if(!box||!p)return;const rows=providerModels(p);const visible=rows.filter(r=>r.visible!==false).length;const hidden=(p.hidden_models||[]).length;const extra=(p.extra_models||[]).length;const stale=staleRouteModels(p).length+(p.stale_hidden_models||[]).length;box.innerHTML=[['显示',visible,'当前显示模型'],['补充',extra,'extra_models 补充'],['隐藏',hidden,'hidden_models 隐藏'],['待清理',stale,'待清理 route/hidden']].map(([label,count,desc])=>`<div class="inventory-tile"><span>${escapeHtml(label)}</span><strong>${count}</strong><p class="muted">${escapeHtml(desc)}</p></div>`).join('')}
function renderModelTable(){const p=current(); if(!p)return;renderModelInventorySummary(p);const q=($('modelSearch')?.value||'').toLowerCase();const rows=providerModels(p).filter(r=>r.id.toLowerCase().includes(q));const extras=p.extra_models||[];$('modelChips').innerHTML=`<strong>当前通道补充模型库（extra_models）</strong><p class="muted">这些模型是手动补充到当前 provider 的可用模型，会参与当前通道路由；不是待删除列表，也不是全局模型池。</p><div class="chips">${extras.length?extras.map(m=>`<span class="chip">${escapeHtml(m)}${editingExtraModels?` <button data-rm-extra="${escapeHtml(m)}">从补充库移除</button>`:''}</span>`).join(''):'<span class="muted">当前通道暂无手动补充模型。</span>'}</div><div class="btns"><button id="toggleExtraEdit" class="ghost">${editingExtraModels?'完成编辑':'编辑补充模型库'}</button></div><div id="staleRouteBox"></div>`;$('toggleExtraEdit').onclick=()=>{editingExtraModels=!editingExtraModels;renderModelTable()};document.querySelectorAll('[data-rm-extra]').forEach(b=>b.onclick=()=>{p.extra_models=extras.filter(x=>x!==b.dataset.rmExtra);touchProvider(p.id);toast(`已从当前通道补充模型库移除 ${b.dataset.rmExtra}`);renderModelTable()});renderStaleRouteBox(p);renderStaleHiddenBox(p);$('modelTable').innerHTML=`<thead><tr><th>显示</th><th>模型</th><th>来源</th><th>收藏</th><th>text</th><th>vision</th><th>tool</th><th>reason</th><th>long</th><th>cache</th></tr></thead><tbody>${rows.map(r=>{const c=r.capabilities||{};return `<tr><td><input type="checkbox" data-model="${escapeHtml(r.id)}" data-field="visible" ${r.visible?'checked':''}></td><td class="mono">${escapeHtml(r.id)}</td><td><span class="tag ${r.visible?'':'off'}">${modelSourceLabel(r.source||'manual')}</span></td><td><input type="checkbox" data-model="${escapeHtml(r.id)}" data-field="favorite" ${r.favorite?'checked':''}></td>${['text','vision','tool_use','reasoning','long_context','cache_sensitive'].map(k=>`<td><input type="checkbox" data-model="${escapeHtml(r.id)}" data-cap="${k}" ${c[k]?'checked':''}></td>`).join('')}</tr>`}).join('')}</tbody>`;document.querySelectorAll('#modelTable input').forEach(x=>x.onchange=onModelToggle);renderTestSelectors();renderFallback();renderRuntime()}
function onModelToggle(e){const p=current();const model=e.target.dataset.model;let row=providerModels(p).find(r=>r.id===model)||{id:model,source:'hidden',visible:!(p.hidden_models||[]).includes(model),favorite:false,capabilities:defaultCaps(model)};row.policy_touched=true;if(e.target.dataset.field==='visible'){row.visible=e.target.checked;p.hidden_models=e.target.checked?(p.hidden_models||[]).filter(x=>x!==model):[...(p.hidden_models||[]).filter(x=>x!==model),model]}else if(e.target.dataset.field==='favorite'){row.favorite=e.target.checked}else if(e.target.dataset.cap){row.capabilities=row.capabilities||{};row.capabilities[e.target.dataset.cap]=e.target.checked}p.model_capabilities=p.model_capabilities||{};p.model_capabilities[model]=row.capabilities;p.models=(p.models||[]).filter(r=>r.id!==model).concat(row);touchProvider(p.id);renderTestSelectors();renderFallback();renderRuntime()}
function renderTestSelectors(){const tp=$('testProvider');if(!tp)return;tp.innerHTML=providerEntries().map(({p,i})=>`<option value="${i}">${escapeHtml(p.name||p.id)}${p.enabled?'':' [已禁用]'}</option>`).join('');tp.value=String(activeProvider);tp.onchange=()=>{activeProvider=Number(tp.value);renderAll()};const models=providerModels(current()||{});$('testModel').innerHTML=models.map(r=>`<option>${escapeHtml(r.id)}</option>`).join('')}
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
function presetLabel(preset){return {builder:'执行/协调',executor:'执行',explore:'探索',bughunt:'找茬',vision:'Vision',reviewer:'审查',spec:'Spec',fixer:'执行'}[preset]||preset||'自定义'}
function customAgentId(preset){const existing=new Set(opencodeAllRows().map(row=>row.agent));let i=1;let id='';do{id=`mobius-${preset}-custom-${i++}`}while(existing.has(id));return id}
function addCustomAgent(preset){const agent=customAgentId(preset);opencodeRoster()[agent]={enabled:true,custom:true,preset,priority:900+Object.keys(opencodeRoster()).length};renderOpencodeAgents();toast(`已添加 ${agent}`)}
function syncRuntime(){state.runtime=state.runtime||{};state.opencode=state.opencode||{};state.runtime.preferred_cli=$('preferredCli').value;state.runtime.coding_preset_model=$('codingModel').value.trim();state.opencode.default_profile=$('opencodeProfile').value;state.opencode.agent_models=Object.fromEntries(opencodeOverrideEntries());state.opencode.agent_roster={...opencodeRoster()}}
function renderOpencodeSummary(){const box=$('opencodeOverrideSummary');if(!box)return;const rows=opencodeAllRows();const enabled=rows.filter(row=>rosterEntry(row.agent,row).enabled!==false).length;const count=opencodeOverrideEntries().length;const custom=rows.filter(row=>rosterEntry(row.agent,row).custom).length;const profile=state.opencode.default_profile||'agent';box.innerHTML=`<div class="oc-metric"><span class="muted">Profile</span><strong>${escapeHtml(profile)}</strong><span class="mono">Lite Pro Roster</span></div><div class="oc-metric"><span class="muted">已启用 Agent</span><strong>${enabled}/${rows.length}</strong><span class="mono">进入 session-local opencode.json</span></div><div class="oc-metric"><span class="muted">Agent 覆盖</span><strong>${count}/${rows.length}</strong><span class="mono">自动模式不写 agent_models</span></div><div class="oc-metric"><span class="muted">自定义 Agent</span><strong>${custom}</strong><span class="mono">按 preset 继承 prompt/permission</span></div>`}
function opencodeFilterMatches(row,overridden){const entry=rosterEntry(row.agent,row);if(opencodeOnlyOverridden&&!overridden&&entry.enabled!==false&&!entry.custom)return false;if(opencodeAgentFilter==='all')return true;if(opencodeAgentFilter==='enabled')return entry.enabled!==false;if(opencodeAgentFilter==='custom')return !!entry.custom;if(opencodeAgentFilter==='execute')return ['builder','executor','fixer','spec'].includes(entry.preset)||String(row.category||'').startsWith('执行');if(opencodeAgentFilter==='explore')return entry.preset==='explore'||row.category==='探索';if(opencodeAgentFilter==='bughunt')return entry.preset==='bughunt'||row.category==='找茬';if(opencodeAgentFilter==='vision')return entry.preset==='vision'||row.category==='Vision';if(opencodeAgentFilter==='review')return entry.preset==='reviewer'||row.category==='审查';return true}
function renderOpencodeFilters(){const wrap=$('opencodeAgentFilters');if(!wrap)return;const filters=[['all','全部'],['enabled','已启用'],['custom','自定义'],['execute','执行/协调'],['explore','探索'],['bughunt','找茬'],['vision','Vision'],['review','审查']];wrap.innerHTML=`${filters.map(([id,label])=>`<button class="ghost ${opencodeAgentFilter===id?'active':''}" data-oc-filter="${id}">${label}</button>`).join('')}<label class="check"><input id="ocOnlyOverridden" type="checkbox" ${opencodeOnlyOverridden?'checked':''}><span>只看改动项</span></label><button class="ghost" data-oc-add="vision">+ 添加 Vision Agent</button><button class="ghost" data-oc-add="executor">+ 添加执行 Agent</button><button class="ghost" data-oc-add="explore">+ 添加探索 Agent</button><button class="ghost" id="ocClearAll">全部自动</button>`;document.querySelectorAll('[data-oc-filter]').forEach(btn=>btn.onclick=()=>{opencodeAgentFilter=btn.dataset.ocFilter;renderOpencodeAgents()});document.querySelectorAll('[data-oc-add]').forEach(btn=>btn.onclick=()=>addCustomAgent(btn.dataset.ocAdd));$('ocOnlyOverridden').onchange=()=>{opencodeOnlyOverridden=$('ocOnlyOverridden').checked;renderOpencodeAgents()};$('ocClearAll').onclick=()=>{state.opencode.agent_models={};state.opencode.agent_roster={};syncRuntime();renderOpencodeAgents();toast('OpenCode roster 已恢复默认自动路线')}}
function renderOpencodeAgents(){const table=$('opencodeAgents');if(!table)return;const overrides=opencodeOverrides();renderOpencodeSummary();renderOpencodeFilters();const rows=opencodeAllRows();const visible=rows.filter(row=>{const entry=rosterEntry(row.agent,row);const overridden=!!(overrides[row.agent]&&overrides[row.agent].model)||entry.enabled===false||entry.custom;return opencodeFilterMatches(row,overridden)});const presetOptions=(selected)=>['builder','executor','explore','bughunt','vision','reviewer','spec','fixer'].map(p=>`<option value="${p}" ${p===selected?'selected':''}>${p}</option>`).join('');const body=visible.length?visible.map(row=>{const entry=rosterEntry(row.agent,row);const ov=overrides[row.agent]||{};const provider=ov.provider_id||entry.provider_id||'';const model=ov.model||entry.model||'';const enabled=entry.enabled!==false;const changed=!!model||!enabled||!!entry.custom;return `<tr data-oc-agent="${escapeHtml(row.agent)}"><td><input class="oc-enabled" type="checkbox" data-oc-enabled ${enabled?'checked':''} ${row.agent==='mobius-builder-pro'?'disabled':''}></td><td class="mono">${escapeHtml(row.agent)}<br><span class="muted">${escapeHtml(row.route_key)}</span>${entry.custom?'<br><span class="tag">自定义</span>':''}${changed?'<span class="tag">已改动</span>':''}</td><td><select data-oc-preset ${entry.custom?'':'disabled'}>${presetOptions(entry.preset)}</select></td><td><input data-oc-priority type="number" value="${escapeHtml(entry.priority||999)}" style="max-width:86px"></td><td><select data-oc-provider>${providerOptions(provider,{auto:true,enabledOnly:true})}</select></td><td><select data-oc-model>${modelOptions(provider,model,{auto:true,defaultModels:row.default_models||[],visionFirst:(entry.preset==='vision'||row.category==='Vision'),enabledOnly:true,selectedProvider:provider})}</select></td><td class="mono default-route">${escapeHtml((row.default_models||[]).join(' / ')||'preset auto')}</td><td><button class="ghost" data-oc-reset>自动</button></td></tr>`}).join(''):'<tr><td colspan="8" class="empty-row">没有匹配的 agent</td></tr>';table.innerHTML=`<thead><tr><th>启用</th><th>Agent</th><th>Preset</th><th>优先级</th><th>Provider</th><th>Model</th><th>默认模型</th><th></th></tr></thead><tbody>${body}</tbody>`;document.querySelectorAll('[data-oc-agent]').forEach(tr=>{const agent=tr.dataset.ocAgent;const row=visible.find(r=>r.agent===agent);const entry=rosterEntry(agent,row);tr.querySelector('[data-oc-enabled]').onchange=(e)=>{setRosterEnabled(agent,row,e.target.checked);renderOpencodeSummary()};tr.querySelector('[data-oc-preset]').onchange=(e)=>{persistRosterEntry(agent,row,{preset:e.target.value});renderOpencodeAgents()};tr.querySelector('[data-oc-priority]').oninput=(e)=>{persistRosterEntry(agent,row,{priority:Number(e.target.value)});renderOpencodeSummary()};tr.querySelector('[data-oc-provider]').onchange=(e)=>{const sel=e.target;const modelSel=tr.querySelector('[data-oc-model]');modelSel.innerHTML=modelOptions(sel.value,modelSel.value,{auto:true,defaultModels:row.default_models||[],visionFirst:(entry.preset==='vision'||row.category==='Vision'),enabledOnly:true,selectedProvider:sel.value});setOpencodeOverride(agent,sel.value,tr.querySelector('[data-oc-model]').value);syncRuntime();renderOpencodeSummary()};tr.querySelector('[data-oc-model]').onchange=(e)=>{setOpencodeOverride(agent,tr.querySelector('[data-oc-provider]').value,e.target.value);syncRuntime();renderOpencodeSummary()};tr.querySelector('[data-oc-reset]').onclick=()=>{const roster=opencodeRoster();delete roster[agent];const overrides=opencodeOverrides();delete overrides[agent];syncRuntime();renderOpencodeAgents();toast(`${agent} 已恢复默认`)}})}
function renderRuntime(){state.runtime=state.runtime||{};state.opencode=state.opencode||{};$('preferredCli').value=state.runtime.preferred_cli||'opencode';$('codingModel').value=state.runtime.coding_preset_model||'';$('opencodeProfile').value=state.opencode.default_profile||'agent';$('preferredCli').oninput=syncRuntime;$('codingModel').oninput=syncRuntime;$('opencodeProfile').oninput=()=>{syncRuntime();renderOpencodeSummary()};renderOpencodeAgents()}
function accountLocked(a){return !!a.is_claude_human_only}
function syncAccounts(){if(!state.accounts)return;state.account_defaults=state.account_defaults||{};document.querySelectorAll('[data-account-id]').forEach(tr=>{const id=tr.dataset.accountId;const acc=(state.accounts||[]).find(a=>a.id===id);if(!acc||accountLocked(acc))return;const nameEl=tr.querySelector('[data-account-name]');const enabledEl=tr.querySelector('[data-account-enabled]');const priorityEl=tr.querySelector('[data-account-priority]');const familyEl=tr.querySelector('[data-account-family]');const claude1mEl=tr.querySelector('[data-account-claude-1m]');const timezoneEl=tr.querySelector('[data-account-timezone]');const noteEl=tr.querySelector('[data-account-note]');if(nameEl)acc.name=nameEl.value;if(enabledEl)acc.enabled=enabledEl.checked;if(priorityEl)acc.priority=Number(priorityEl.value||100);if(familyEl)acc.family_priority_overrides=parseFamilyOverrides(familyEl.value);if(claude1mEl)acc.claude_1m_mode=claude1mEl.value;if(timezoneEl)acc.timezone=timezoneEl.value.trim();if(noteEl)acc.note=noteEl.value.trim()});document.querySelectorAll('[data-account-default]:checked').forEach(el=>{if(!el.disabled&&el.dataset.accountCli)state.account_defaults[el.dataset.accountCli]=el.value})}
function mappingStatusLabel(status){return {native:'原生',report:'报告',draft_review:'草稿预览',human_gate:'人工确认',missing:'缺失'}[status]||status||'-'}
function mappingStatusClass(status){return 'status-'+String(status||'missing').replace(/[^a-z0-9_ -]/gi,'').replace(/\s+/g,'_')}
function mappingActionButton(row){const parts=[];if(row.webui_section_id){parts.push(`<button class="ghost mapping-action" data-section-jump="${escapeHtml(row.webui_section_id)}">打开</button>`)}if(row.api_action){const label=row.status==='human_gate'?'人工确认':(row.status==='missing'?'缺口':'报告');parts.push(`<button class="ghost mapping-action" data-settings-action="${escapeHtml(row.api_action)}">${label}</button>`)}return parts.join(' ')}
function renderMappingFilters(mapping){const box=$('mappingFilters');if(!box)return;const count=s=>mapping.filter(row=>s==='all'||row.status===s).length;const filters=[['all','全部'],['native','原生'],['report','报告'],['draft_review','草稿'],['human_gate','人工确认'],['missing','缺失']];box.innerHTML=filters.map(([id,label])=>`<button class="${settingsMappingFilter===id?'active':''}" data-map-filter="${id}">${label} ${count(id)}</button>`).join('');document.querySelectorAll('[data-map-filter]').forEach(btn=>{btn.onclick=()=>{settingsMappingFilter=btn.dataset.mapFilter;renderSettings()}})}
function acceptanceStorageKey(){return `mms-webui-tui-acceptance:${state?.command||'mms'}:${state?.schema||'snapshot'}`}
function loadAcceptanceState(mapping){try{const allowed=new Set((mapping||[]).map(row=>row.id));const raw=JSON.parse(localStorage.getItem(acceptanceStorageKey())||'[]');checkedMappingRows=new Set((Array.isArray(raw)?raw:[]).filter(id=>allowed.has(id)))}catch(_err){checkedMappingRows=new Set()}}
function saveAcceptanceState(){try{localStorage.setItem(acceptanceStorageKey(),JSON.stringify([...checkedMappingRows].sort()))}catch(_err){}}
function currentMappingRows(mapping){return settingsMappingFilter==='all'?mapping:mapping.filter(row=>row.status===settingsMappingFilter)}
function acceptanceReportText(mapping){const rows=mapping||[];const unchecked=rows.filter(row=>!checkedMappingRows.has(row.id));const counts=(state.tui_webui_mapping_summary||{}).counts||{};return [`MMS WebUI 设置/通道验收`,`命令: ${state.command||'mms'}`,`总数: ${rows.length}`,`已检查: ${rows.length-unchecked.length}`,`未检查: ${unchecked.length}`,`状态: 原生 ${counts.native||0} / 报告 ${counts.report||0} / 草稿 ${counts.draft_review||0} / 人工确认 ${counts.human_gate||0} / 缺失 ${counts.missing||0}`,`可点击: ${(state.tui_webui_mapping_summary||{}).clickable_rows||0}/${rows.length}`,`未检查行: ${unchecked.map(row=>row.id).join(', ')||'-'}`].join('\\n')}
async function copyAcceptanceReport(mapping){const text=acceptanceReportText(mapping);try{await navigator.clipboard.writeText(text);toast('已复制验收摘要')}catch(_err){$('settingsReport').textContent=text;toast('无法访问剪贴板，验收摘要已显示在报告区')}}
function renderAcceptancePanel(mapping){const box=$('acceptancePanel');if(!box)return;const rows=mapping||[];const visible=currentMappingRows(rows);const checked=rows.filter(row=>checkedMappingRows.has(row.id)).length;const clickable=(state.tui_webui_mapping_summary||{}).clickable_rows??rows.filter(row=>row.clickable==='yes').length;const missing=(state.tui_webui_mapping_summary||{}).counts?.missing||0;box.innerHTML=`<div class="acceptance-head"><div><h4>逐项验收清单</h4><p class="muted">你可以按行点击打开 / 报告 / 人工确认 / 保存预览验证，再勾选左侧已检查；状态保存在本浏览器 localStorage，不写真实 MMS config。</p></div><div class="acceptance-progress" id="mapCheckProgress">${checked}/${rows.length}</div></div><div class="chips"><span class="chip">可点击 ${clickable}/${rows.length}</span><span class="chip">当前可见 ${visible.length}</span><span class="chip">缺失 ${missing}</span><span class="chip">${checked===rows.length?'全部已检查':'未检查 '+(rows.length-checked)}</span></div><div class="btns"><button class="ghost" id="markVisibleChecked">标记当前筛选已检查</button><button class="ghost" id="copyAcceptanceReport">复制验收摘要</button><button class="ghost" id="clearAcceptanceChecks">清空本地勾选</button></div>`;$('markVisibleChecked').onclick=()=>{visible.forEach(row=>checkedMappingRows.add(row.id));saveAcceptanceState();renderTuiMapping(rows);toast(`已标记 ${visible.length} 行为已检查`)};$('clearAcceptanceChecks').onclick=()=>{checkedMappingRows.clear();saveAcceptanceState();renderTuiMapping(rows);toast('已清空本地验收勾选')};$('copyAcceptanceReport').onclick=()=>copyAcceptanceReport(rows)}
function bindMappingChecks(mapping){document.querySelectorAll('[data-map-check]').forEach(input=>{input.onchange=()=>{const id=input.dataset.mapCheck;if(input.checked)checkedMappingRows.add(id);else checkedMappingRows.delete(id);saveAcceptanceState();renderAcceptancePanel(mapping)}})}
function renderTuiMapping(mapping){renderMappingFilters(mapping);renderAcceptancePanel(mapping);const rows=currentMappingRows(mapping);const body=rows.length?rows.map(row=>`<tr><td><label class="mapping-check"><input data-map-check="${escapeHtml(row.id)}" type="checkbox" ${checkedMappingRows.has(row.id)?'checked':''}>已检查</label></td><td class="mono">${escapeHtml(row.tui_area)}<br><span class="muted">${escapeHtml(row.tui_action_id)}</span></td><td>${escapeHtml(row.tui_label)}</td><td>${escapeHtml(row.webui_section)}<br><span class="muted">${escapeHtml(row.webui_control)}</span></td><td><span class="tag ${mappingStatusClass(row.status)}">${mappingStatusLabel(row.status)}</span><br><span class="muted">${writePolicyLabel(row.write_policy)}</span></td><td class="default-route">${escapeHtml(row.verification||'-')}<br><span class="check-evidence">${clickTargetsLabel(row.click_targets||'-')}</span><br><span class="muted">${escapeHtml(row.acceptance_check||row.manual_check||'')}</span></td><td>${mappingActionButton(row)}</td></tr>`).join(''):'<tr><td colspan="7" class="empty-row">当前筛选没有条目</td></tr>';$('tuiMappingTable').innerHTML=`<thead><tr><th>检查</th><th>TUI 区域/动作</th><th>TUI 文案</th><th>WebUI 落点</th><th>状态</th><th>验证 / 点击证据</th><th>操作</th></tr></thead><tbody>${body}</tbody>`;bindMappingChecks(mapping)}
function gateArray(items){return Array.isArray(items)?items.filter(x=>String(x??'').trim()).map(x=>String(x)) : []}
function gateList(items,empty='-'){const rows=gateArray(items);return rows.length?`<ol class="gate-list">${rows.map(x=>`<li>${escapeHtml(x)}</li>`).join('')}</ol>`:`<p class="muted">${escapeHtml(empty)}</p>`}
function gateCommands(commands){lastGateCommands=gateArray(commands);if(!lastGateCommands.length)return '<p class="muted">没有安全 one-shot CLI；按人工步骤处理。</p>';return lastGateCommands.map((cmd,i)=>`<div class="gate-command-row"><code>${escapeHtml(cmd)}</code><button class="ghost copy-gate-command" data-copy-gate-command="${i}">复制</button></div>`).join('')}
async function copyGateCommand(i){const cmd=lastGateCommands[Number(i)]||'';if(!cmd){toast('没有可复制命令');return}try{await navigator.clipboard.writeText(cmd);toast('已复制 人工确认 命令')}catch(_err){$('settingsReport').insertAdjacentHTML('afterbegin',`<div class="gate-box"><h5>剪贴板备用显示</h5><p class="mono">${escapeHtml(cmd)}</p></div>`);toast('无法访问剪贴板，命令已显示')}}
function bindGateCopyButtons(){document.querySelectorAll('[data-copy-gate-command]').forEach(btn=>{btn.onclick=()=>copyGateCommand(btn.dataset.copyGateCommand)})}
function renderGateReport(data,targetId='settingsReport'){const mapping=data.mapping||[];const mappingHtml=mapping.length?mapping.map(row=>`<span class="chip">${escapeHtml(row.tui_area||'-')} / ${escapeHtml(row.tui_label||row.tui_action_id||'-')}</span>`).join(''):'<span class="chip">无 mapping 行</span>';const writes=gateArray(data.writes);const writeText=writes.length?writes:['无直接写入；仍保留人工确认。'];const target=$(targetId)||$('settingsReport');if(!target)return;target.innerHTML=`<div class="gate-report"><div class="gate-plate"><div class="gate-head"><div><h4>${escapeHtml(data.title||data.action||'人工确认')}</h4><p>${escapeHtml(data.note||'该动作需要人工确认，WebUI 不自动执行。')}</p></div><div class="gate-risk">${riskLabel(data.risk_level||'high')} / 已拦截</div></div><div class="chips"><span class="chip">${writePolicyLabel(data.write_policy||'human_gate')}</span><span class="chip">${data.requires_human_confirmation?'需要人工确认':'只读'}</span><span class="chip">${data.blocked_auto_execute?'禁止自动执行':'允许自动执行'}</span><span class="chip">${data.copyable?'可复制命令':'仅人工'}</span></div></div><div class="gate-grid"><div class="gate-box"><h5>可复制命令</h5>${gateCommands(data.commands)}</div><div class="gate-box"><h5>人工步骤</h5>${gateList(data.manual_steps,'按项目 人工确认 规则人工处理。')}</div><div class="gate-box"><h5>写入范围</h5>${gateList(writeText)}</div><div class="gate-box"><h5>更安全的 WebUI 路径</h5><p>${escapeHtml(data.safe_alternative||'使用只读报告或保存页 diff 预览。')}</p><div class="chips">${mappingHtml}</div></div></div><details class="gate-raw"><summary>原始 JSON</summary><pre class="mono">${escapeHtml(JSON.stringify(data,null,2))}</pre></details></div>`;bindGateCopyButtons()}
function reportTopModels(rows=[]){const top=[];(rows||[]).forEach(row=>{(row.top_models||[]).forEach(item=>{if(item&&item.model)top.push(`${item.model} × ${item.launches||0}`)})});return top.slice(0,6).join(' / ')||'-'}
function usageDetailRows(ownerId,rows=[]){const safeRows=Array.isArray(rows)?rows:[];if(!safeRows.length)return '';return safeRows.map(row=>`<tr><td class="mono">${escapeHtml(ownerId)}</td><td>${escapeHtml(row.cli||'-')}</td><td>${escapeHtml(row.name||row.id||'-')}</td><td>${Number(row.launches||0)}</td><td class="mono">${escapeHtml(row.last_model||'-')}</td><td>${escapeHtml(row.last_used_at||'-')}</td><td>${escapeHtml(reportTopModels([row]))}</td></tr>`).join('')}
function modelUsageKey(id){return String(id||'').trim().toLowerCase()}
function providerModelUsageRows(p){
  const counts=new Map();const lastUsed=new Map();const lastCli=new Map();
  (p.usage_rows||[]).forEach(row=>{
    (row.model_usage||row.top_models||[]).forEach(item=>{const key=modelUsageKey(item.model);if(!key)return;counts.set(key,(counts.get(key)||0)+Number(item.launches||0))});
    const lastKey=modelUsageKey(row.last_model);if(lastKey){lastUsed.set(lastKey,row.last_used_at||'');lastCli.set(lastKey,row.cli||'')}
  });
  const modelRows=Array.isArray(p.models)?p.models:[];const seen=new Set();
  const rows=modelRows.map(row=>{const id=String(row.id||'').trim();const key=modelUsageKey(id);seen.add(key);return {id,source:row.source||'manual',visible:row.visible!==false,favorite:!!row.favorite,launches:counts.get(key)||0,last_used_at:lastUsed.get(key)||'',last_cli:lastCli.get(key)||''}}).filter(row=>row.id);
  counts.forEach((launches,key)=>{if(seen.has(key))return;const display=(p.usage_rows||[]).flatMap(row=>row.model_usage||row.top_models||[]).find(item=>modelUsageKey(item.model)===key)?.model||key;rows.push({id:display,source:'usage-only',visible:true,favorite:false,launches,last_used_at:lastUsed.get(key)||'',last_cli:lastCli.get(key)||''})});
  return rows.sort((a,b)=>Number(b.launches||0)-Number(a.launches||0)||a.id.localeCompare(b.id));
}
function renderProviderUsageReport(data,targetId='settingsReport'){
  const target=$(targetId)||$('settingsReport');if(!target)return;
  let providers=Array.isArray(data.providers)?data.providers:[];
  if(targetId==='channelReport'&&current()){const activeId=current().id;providers=providers.filter(p=>p.id===activeId);if(providers.length===1){providers=[{...providers[0],models:providerModels(current())}]}}
  const channelScoped=targetId==='channelReport';
  const totalLaunches=providers.reduce((sum,p)=>sum+Number((p.usage||{}).launches||0),0);
  if(channelScoped&&!providers.length){target.innerHTML='<div class="usage-report"><h4>当前通道使用统计</h4><p class="muted">当前通道没有可读取的 usage 记录。</p></div>';return}
  const providerRows=!channelScoped&&providers.length?`<div class="table-wrap"><table><thead><tr><th>通道 ID</th><th>名称</th><th>状态</th><th>role</th><th>priority</th><th>模型数</th><th>启动</th><th>最近使用</th><th>常用模型</th></tr></thead><tbody>${providers.map(p=>`<tr><td class="mono">${escapeHtml(p.id||'-')}</td><td>${escapeHtml(p.name||'-')}</td><td>${p.enabled?'<span class="tag">启用</span>':'<span class="tag off">禁用</span>'}</td><td>${escapeHtml(p.role||'-')}</td><td>${Number(p.priority||0)}</td><td>${Number(p.model_count||0)}</td><td>${Number((p.usage||{}).launches||0)}</td><td>${escapeHtml((p.usage||{}).last_used_at||'-')}</td><td>${escapeHtml(reportTopModels(p.usage_rows||[]))}</td></tr>`).join('')}</tbody></table></div>`:'';
  const modelSections=providers.map(p=>{const modelRows=providerModelUsageRows(p);const usedCount=modelRows.filter(row=>Number(row.launches||0)>0).length;const rows=modelRows.length?modelRows.map(row=>`<tr><td>${escapeHtml(row.id)}</td><td><span class="tag ${row.visible?'':'off'}">${modelSourceLabel(row.source)}</span>${row.favorite?'<span class="tag">收藏</span>':''}</td><td>${row.visible?'显示':'隐藏'}</td><td>${Number(row.launches||0)}</td><td>${escapeHtml(row.last_cli||'-')}</td><td>${escapeHtml(row.last_used_at||'-')}</td></tr>`).join(''):'<tr><td colspan="6" class="empty-row">当前通道没有模型清单</td></tr>';return `<div class="chips usage-summary"><span class="chip">当前通道 ${escapeHtml(p.name||p.id||'-')}</span><span class="chip mono">${escapeHtml(p.id||'-')}</span><span class="chip">模型 ${modelRows.length}</span><span class="chip">有使用 ${usedCount}</span><span class="chip">总启动 ${Number((p.usage||{}).launches||0)}</span><span class="chip">最近 ${escapeHtml((p.usage||{}).last_used_at||'-')}</span></div><div class="table-wrap usage-table-wrap"><table class="usage-model-table"><thead><tr><th>模型</th><th>来源</th><th>显示状态</th><th>启动次数</th><th>最近 CLI</th><th>最近使用</th></tr></thead><tbody>${rows}</tbody></table></div>`}).join('')||'<p class="muted">暂无通道使用统计</p>';
  const detailRows=providers.map(p=>usageDetailRows(p.id||p.name||'-',p.usage_rows||[])).join('')||'<tr><td colspan="7" class="empty-row">暂无 CLI 维度使用明细</td></tr>';
  const title=channelScoped?'当前通道使用统计':'通道使用统计汇总';
  const note=channelScoped?'只读报告：只展示当前选中通道，并按这个通道内的模型展开启动次数；不会把其他通道混进来。':'只读报告：展示全部 provider usage 汇总；通道页按钮会自动限定到当前通道。';
  target.innerHTML=`<div class="usage-report"><h4>${title}</h4><p>${note}</p><div class="chips"><span class="chip">统计范围 ${channelScoped?'当前通道':'全部通道'}</span><span class="chip">总启动 ${totalLaunches}</span><span class="chip">写入策略 ${writePolicyLabel(data.write_policy||'read_only')}</span></div>${providerRows}${modelSections}<details class="usage-detail"><summary>CLI 明细（按需展开）</summary><div class="table-wrap"><table><thead><tr><th>通道 ID</th><th>CLI</th><th>明细名</th><th>启动</th><th>最近模型</th><th>最近使用</th><th>Top models</th></tr></thead><tbody>${detailRows}</tbody></table></div></details></div>`;
}
function renderAccountStatusReport(data,targetId='settingsReport'){
  const target=$(targetId)||$('settingsReport');if(!target)return;
  const accounts=Array.isArray(data.accounts)?data.accounts:[];
  const defaults=data.account_defaults||{};
  const rows=accounts.length?accounts.map(a=>{const cli=String(a.cli||'').toLowerCase();const isDefault=defaults[cli]===a.id;return `<tr><td class="mono">${escapeHtml(a.id||'-')}</td><td>${escapeHtml(a.name||'-')}</td><td>${escapeHtml((a.cli||'-').toUpperCase())}</td><td>${isDefault?'是':'否'}</td><td>${a.enabled?'<span class="tag">启用</span>':'<span class="tag off">禁用</span>'}</td><td>${Number(a.priority||0)}</td><td>${escapeHtml(formatFamilyOverrides(a.family_priority_overrides||{})||'-')}</td><td>${escapeHtml(a.auth_mode||'-')}</td><td>${Number((a.usage||{}).launches||0)}</td><td>${escapeHtml((a.usage||{}).last_used_at||'-')}</td><td>${escapeHtml(reportTopModels(a.usage_rows||[]))}</td><td>${a.is_claude_human_only?'<span class="tag off">Claude 人工锁定</span>':`<span class="tag">${writePolicyLabel(a.webui_write_policy||'draft_review')}</span>`}</td></tr>`}).join(''):'<tr><td colspan="12" class="empty-row">暂无账号状态</td></tr>';
  target.innerHTML=`<div class="account-report"><h4>账号状态</h4><p>${escapeHtml(data.note||'只读表格展示；OAuth / AGY 新登录主流程已下线，删除、重命名和 Claude account 仍保持人工确认。')}</p><div class="table-wrap"><table><thead><tr><th>ID</th><th>名称</th><th>CLI</th><th>默认</th><th>状态</th><th>priority</th><th>Family</th><th>auth</th><th>启动</th><th>最近</th><th>常用模型</th><th>写入边界</th></tr></thead><tbody>${rows}</tbody></table></div></div>`;
}
function renderSettingsReport(data,targetId='settingsReport'){
  const target=$(targetId)||$('settingsReport');if(!target)return;
  if(data&&data.action==='provider_usage_summary'){renderProviderUsageReport(data,targetId);return}
  if(data&&(data.action==='accounts'||data.action==='account_status')){renderAccountStatusReport(data,targetId);return}
  if(data&&(data.blocked_auto_execute||data.requires_human_confirmation||data.status==='human_gate')){renderGateReport(data,targetId);return}
  target.textContent=JSON.stringify(data,null,2)
}
function bindSettingsActionButtons(){document.querySelectorAll('[data-settings-action]').forEach(btn=>{btn.onclick=async()=>{const action=btn.dataset.settingsAction;const targetId=btn.dataset.reportTarget||'settingsReport';const target=$(targetId)||$('settingsReport');if(target)target.textContent='读取中...';const payload={action};if(btn.dataset.accountId)payload.account_id=btn.dataset.accountId;if(btn.dataset.providerId)payload.provider_id=btn.dataset.providerId;if(action==='provider_usage_summary'&&targetId==='channelReport'&&current()?.id)payload.provider_id=current().id;const data=await api('/api/settings/report',payload);renderSettingsReport(data,targetId);if(targetId==='channelReport')switchProviderFormTab('reports');toast(data.ok?`${btn.textContent} 已刷新`:`${btn.textContent} 失败`)}});document.querySelectorAll('[data-section-jump]').forEach(btn=>{btn.onclick=()=>{setSection(btn.dataset.sectionJump);toast(`已打开 ${btn.dataset.sectionJump} 对应 WebUI 区域`)}})}
function syncUiSettings(){state.ui=state.ui||{};state.ui.language=$('uiLanguage')?.value||'zh'}
function renderUiSettings(mapping){state.ui=state.ui||{language:'zh'};const lang=state.ui.language||'zh';if($('uiLanguage')){$('uiLanguage').value=['zh','en'].includes(lang)?lang:'zh';$('uiLanguage').onchange=()=>{syncUiSettings();toast('界面语言已暂存，生成保存预览后再写入')}}const save=$('saveUiLanguage');if(save)save.onclick=()=>{syncUiSettings();setSection('save');toast('界面语言修改已暂存，生成保存预览后再写入')};const counts=(state.tui_webui_mapping_summary||{}).counts||{};const missingRows=(mapping||[]).filter(row=>row.status==='missing').map(row=>row.tui_label);if($('settingsGapSummary')){$('settingsGapSummary').innerHTML=`<span class="chip">原生 ${counts.native||0}</span><span class="chip">报告 ${counts.report||0}</span><span class="chip">草稿 ${counts.draft_review||0}</span><span class="chip">人工确认 ${counts.human_gate||0}</span><span class="chip">缺失 ${counts.missing||0}</span>${missingRows.length?`<span class="chip">仍缺：${escapeHtml(missingRows.join(' / '))}</span>`:'<span class="chip">无缺失行</span>'}`}}
function switchSettingsTab(tab){
  settingsActiveTab=tab||'accounts';
  const panels=[...document.querySelectorAll('[data-settings-panel]')];
  if(!panels.some(p=>p.dataset.settingsPanel===settingsActiveTab))settingsActiveTab='accounts';
  document.querySelectorAll('[data-settings-tab]').forEach(btn=>btn.classList.toggle('active',btn.dataset.settingsTab===settingsActiveTab));
  panels.forEach(panel=>panel.classList.toggle('active',panel.dataset.settingsPanel===settingsActiveTab));
}
function bindSettingsTabs(){document.querySelectorAll('[data-settings-tab]').forEach(btn=>{btn.onclick=()=>switchSettingsTab(btn.dataset.settingsTab)})}
function accountActionButtons(a){const id=escapeHtml(a.id||'');return `<details class="account-advanced"><summary>兼容 / 危险动作（已降级）</summary><p class="muted">登录、重命名、网络和删除会碰外部账号状态或本机目录，不作为 WebUI 日常配置主流程。</p><div class="btns"><button class="ghost mapping-action" data-settings-action="account_login_gate" data-report-target="settingsReport" data-account-id="${id}">登录兼容说明</button><button class="ghost mapping-action" data-settings-action="account_rename_gate" data-report-target="settingsReport" data-account-id="${id}">重命名确认</button><button class="ghost mapping-action" data-settings-action="account_network_gate" data-report-target="settingsReport" data-account-id="${id}">网络确认</button><button class="ghost mapping-action" data-settings-action="account_remove_gate" data-report-target="settingsReport" data-account-id="${id}">删除确认</button></div></details>`}
function accountConfigCard(a){
  const locked=accountLocked(a);const cli=String(a.cli||'').toLowerCase();const isDefault=(state.account_defaults||{})[cli]===a.id;const name=escapeHtml(a.name||a.id||'-');const id=escapeHtml(a.id||'');const defaultInput=`<label class="check"><input data-account-default data-account-cli="${escapeHtml(cli)}" name="account-default-${escapeHtml(cli)}" type="radio" value="${id}" ${isDefault?'checked':''} ${locked?'disabled':''}><span>设为 ${escapeHtml((a.cli||'-').toUpperCase())} 默认账号</span></label>`;
  const fieldHtml=locked?`<div class="account-fields"><div class="span6"><label>名称</label><p class="mono">${name}</p></div><div class="span3"><label>priority</label><p class="mono">${Number(a.priority||100)}</p></div><div class="span3"><label>Claude 1M</label><p class="mono">${escapeHtml(a.claude_1m_mode||'auto')}</p></div><div class="span3"><label>timezone</label><p class="mono">${escapeHtml(a.timezone||'-')}</p></div><div class="span3"><label>note</label><p>${escapeHtml(a.note||'-')}</p></div></div>`:`<div class="account-fields"><div class="span6"><label>名称</label><input data-account-name value="${name}"></div><div class="span3"><label>priority</label><input data-account-priority type="number" value="${escapeHtml(a.priority||100)}"></div><div class="span3"><label>Claude 1M</label><select data-account-claude-1m><option value="auto" ${(a.claude_1m_mode||'auto')==='auto'?'selected':''}>自动</option><option value="enable" ${a.claude_1m_mode==='enable'?'selected':''}>启用</option><option value="disable" ${a.claude_1m_mode==='disable'?'selected':''}>禁用</option></select></div><div class="span3"><label>timezone</label><input data-account-timezone value="${escapeHtml(a.timezone||'')}" placeholder="Asia/Singapore"></div><div class="span9"><label>note</label><input data-account-note value="${escapeHtml(a.note||'')}" placeholder="备注会进入保存预览"></div></div>`;
  const family=locked?`<p class="mono">${escapeHtml(formatFamilyOverrides(a.family_priority_overrides||{})||'继承')}</p>`:`<input data-account-family value="${escapeHtml(formatFamilyOverrides(a.family_priority_overrides||{}))}" placeholder="GPT=120, Qwen=90">`;
  return `<div class="account-config-card ${locked?'locked':''}" data-account-id="${id}"><div class="account-card-head"><div><h4>${name}</h4><p class="mono">${id}</p></div><div class="chips"><span class="chip">${escapeHtml((a.cli||'-').toUpperCase())}</span><span class="chip ${a.enabled?'':'off'}">${a.enabled?'启用':'禁用'}</span>${isDefault?'<span class="chip">默认</span>':''}${locked?'<span class="chip off">Claude 人工锁定</span>':''}</div></div>${locked?'<p class="muted">Claude account 只读展示，不允许 WebUI 自动写入。</p>':`<label class="check"><input data-account-enabled type="checkbox" ${a.enabled?'checked':''}><span>启用这个账号</span></label>`}${defaultInput}${fieldHtml}<details class="account-advanced"><summary>Family 权重覆盖（不常用）</summary><p class="muted">平时留空继承账号 priority；只在某个 family 需要单独排序时填写。</p>${family}</details><div class="chips"><span class="chip">auth ${escapeHtml(a.auth_mode||'-')}</span><span class="chip">home ${yn(a.home_dir_configured)}</span><span class="chip">proxy ${yn(a.proxy_configured)}</span><span class="chip">启动 ${Number((a.usage||{}).launches||0)}</span><span class="chip">最近 ${escapeHtml((a.usage||{}).last_used_at||'-')}</span><span class="chip ${locked?'off':''}">${writePolicyLabel(a.webui_write_policy||'read_only')}</span></div>${accountActionButtons(a)}</div>`
}
function renderSettings(){
  state.account_defaults=state.account_defaults||{};
  const accounts=state.accounts||[];const coverage=state.webui_capability_coverage||[];const mapping=state.tui_webui_mapping||[];
  renderUiSettings(mapping);
  const accountEmpty='<div class="settings-compat-note"><strong>暂无 CLI account</strong><p>API Key provider 请在「通道配置」维护。OAuth / AGY 官方登录已不再作为新增主流程。</p></div>';
  if($('accountTable')){$('accountTable').innerHTML=accounts.length?accounts.map(accountConfigCard).join(''):accountEmpty}
  document.querySelectorAll('[data-account-name],[data-account-enabled],[data-account-priority],[data-account-family],[data-account-claude-1m],[data-account-timezone],[data-account-note]').forEach(el=>{const handler=()=>{syncAccounts();toast('账号草稿已暂存，生成保存预览后再写入')};el.oninput=handler;el.onchange=handler});
  document.querySelectorAll('[data-account-default]').forEach(el=>{el.onchange=()=>{syncAccounts();renderSettings();toast('账号默认值已暂存，生成保存预览后再写入')}});
  if($('settingsCoverage')){$('settingsCoverage').innerHTML=`<thead><tr><th>区域</th><th>能力</th><th>WebUI</th><th>TUI 后续</th></tr></thead><tbody>${coverage.map(row=>`<tr><td>${escapeHtml(row.area)}</td><td>${escapeHtml(row.capability)}</td><td><span class="tag ${String(row.webui||'').includes('planned')||String(row.webui||'').includes('human_gate')||String(row.webui||'').includes('待补齐')||String(row.webui||'').includes('人工确认')?'off':''}">${writePolicyLabel(row.webui)}</span></td><td>${writePolicyLabel(row.tui)}</td></tr>`).join('')}</tbody>`}
  renderTuiMapping(mapping);
  bindSettingsTabs();
  bindSettingsActionButtons();
  switchSettingsTab(settingsActiveTab);
}
function renderRefs(){ $('refsGrid').innerHTML=(state.references||[]).map(r=>`<div class="card span6"><h3>${escapeHtml(r.title)}</h3><p>${escapeHtml(r.summary)}</p><p class="mono">${escapeHtml(r.path)}</p></div>`).join('') }
function levelLabel(level){return level==='danger'?'高风险':(level==='warn'?'注意':'信息')}
function planJsonHint(plan){const v2=plan?.registry_v2_save_plan||{};const planJson=v2.plan_json||{};const apply=v2.apply_plan||{};if(!planJson.name&&!apply.cli_apply_command)return '';return `<h4>Plan JSON / apply-plan</h4><p class="muted">${escapeHtml(planJson.note||'Plan JSON 是保存预览的审查产物。')}</p><p><span class="tag">${escapeHtml(planJson.name||'webui-plan.json')}</span> <span class="tag ${planJson.redacted?'off':''}">secrets ${planJson.redacted?'已脱敏':'含明文'}</span></p><p class="mono">${escapeHtml(apply.cli_apply_command||'')}</p>`}
function renderApplyResult(data){const blockers=data.runtime_blockers||{};const next=data.next_action||{};const publish=data.publish||{};const verify=data.verify||{};const ready=data.runtime_ready===true;const notReady=data.runtime_ready===false;const errs=Array.isArray(data.errors)?data.errors:[data.error||'unknown error'];const title=!data.ok?'写入被阻止':(ready?'已发布，可直接给 mmf 使用':'已发布，但 runtime 未就绪');const detail=!data.ok?errs.join('；'):(ready?'latest-approved bundle 已验证，mmf 会读到这次保存后的最新 bundle。':'latest-approved bundle 已发布且已验证；mmf 会读到最新 bundle，但缺 key/base URL/模型 route 的条目不能正常启动。');$('saveResult').innerHTML=`<div><p><span class="tag ${data.ok&&!notReady?'':'off'}">${escapeHtml(title)}</span> <span class="tag">${escapeHtml(data.status||'-')}</span></p><p class="muted">${escapeHtml(detail)}</p><p><span class="tag">manifest ${verify.verified?'已验证':'未验证'}</span><span class="tag ${ready?'':'off'}">runtime ${ready?'就绪':notReady?'未就绪':'未知'}</span><span class="tag">缺 API Key ${blockers.missing_api_key_count||0}</span><span class="tag">缺 Base URL ${blockers.missing_base_url_count||0}</span><span class="tag">通道 route ${blockers.provider_route_count||publish.provider_route_count||0}</span></p>${next.label?`<p><strong>下一步</strong>：${escapeHtml(next.label)}</p>`:''}<details><summary>原始 JSON</summary><pre class="mono">${escapeHtml(JSON.stringify(data,null,2))}</pre></details></div>`}
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
function assetDisableSupported(row){return row&&row.disable_supported!==false}
function assetIsDefaultDisabled(row){if(!assetDisableSupported(row))return false;const kind=assetDisabledKind(row.kind);const key=String(row.disable_key||row.title||'').trim();return !!key&&ensureAssetDisabledDraft()[kind].includes(key)}
function setAssetDefaultDisabled(row,checked){if(!assetDisableSupported(row))return;const kind=assetDisabledKind(row.kind);const key=String(row.disable_key||row.title||'').trim();if(!key)return;const draft=ensureAssetDisabledDraft();draft[kind]=draft[kind].filter(x=>x!==key);if(checked)draft[kind].push(key);draft[kind]=[...new Set(draft[kind])].sort()}
function assetTomlString(value){return String(value||'').replaceAll('\\','\\\\').replaceAll('"','\\"')}
function assetArrayToml(values){return `[${[...new Set((values||[]).map(x=>String(x||'').trim()).filter(Boolean))].sort().map(v=>`"${assetTomlString(v)}"`).join(', ')}]`}
function renderAssetPreferenceSnippet(){const assets=state.session_assets||{};const defaults=assets.launch_defaults||{};const install=assets.managed_install||{};const draft=ensureAssetDisabledDraft();const managedRoot=install.real_root||install.root||'~/.local/share/mms/assets';const snippet=[`[launch.defaults]`,`caveman_mode = "${assetTomlString(defaults.caveman_mode||'enable')}"`,`nsr_mode = "${assetTomlString(defaults.nsr_mode||'enable')}"`,`agent_pack = "${assetTomlString(defaults.agent_pack||'none')}"`,`bypass = ${defaults.bypass===false?'false':'true'}`,'',`[session_surfaces.disabled]`,`skills = ${assetArrayToml(draft.skills)}`,`mcp = ${assetArrayToml(draft.mcp)}`,`hooks = ${assetArrayToml(draft.hooks)}`,'',`[assets]`,`managed_enabled = ${install.enabled===false?'false':'true'}`,`managed_root = "${assetTomlString(managedRoot)}"`].join('\n');$('assetPreferenceSnippet').textContent=snippet;return snippet}
function assetPreferencesPayload(){const assets=state.session_assets||{};const install=assets.managed_install||{};const draft=ensureAssetDisabledDraft();return {disabled:{skills:[...draft.skills],mcp:[...draft.mcp],hooks:[...draft.hooks]},assets:{managed_enabled:install.enabled!==false,managed_root:install.real_root||install.root||'~/.local/share/mms/assets'}}}
function renderAssetPendingBar(){const bar=$('assetPendingBar');if(!bar)return;const diff=assetDraftDiff();if(!diff.total){bar.classList.remove('is-visible');bar.innerHTML='';assetConfirmPrefsChecked=false;assetConfirmPhraseValue='';assetPrefsResultText='有未保存变化时，底部会出现保存栏。';return}const labels={skills:'Skill',mcp:'MCP',hooks:'Hook'};const chips=['skills','mcp','hooks'].map(key=>diff[key].length?`<span class="tag">${labels[key]} ${diff[key].length}</span>`:'').join('');bar.classList.add('is-visible');bar.innerHTML=`<div class="asset-pending-inner"><div><div class="asset-pending-title"><span>有 ${diff.total} 项未保存变化</span>${chips}</div><p class="muted">确认后只写 preferences.toml；如果你把开关改回原状态，这条保存栏会自动消失。</p></div><div class="asset-pending-actions"><label class="check"><input id="assetConfirmPrefs" type="checkbox"><span>确认只保存 Skill/MCP/Hook 偏好</span></label><div class="asset-confirm-field"><label for="assetConfirmPhrase">确认文字</label><input id="assetConfirmPhrase" type="text" placeholder="保存偏好"></div><button id="applyAssetPrefs" class="secondary">保存并应用</button><button id="discardAssetPrefs" class="ghost">放弃变化</button><p class="muted asset-pending-result" id="assetPrefsResult">${escapeHtml(assetPrefsResultText)}</p></div></div>`}
function bindAssetPreferenceButtons(){const copy=$('copyAssetPrefs');const reset=$('resetAssetPrefs');const discard=$('discardAssetPrefs');const apply=$('applyAssetPrefs');const confirm=$('assetConfirmPrefs');const phrase=$('assetConfirmPhrase');const result=$('assetPrefsResult');const resetDraft=()=>{assetDisabledDraft=cloneAssetDisabledDefaults();assetConfirmPrefsChecked=false;assetConfirmPhraseValue='';assetPrefsResultText='已放弃未保存变化。';renderSessionAssets();toast('已恢复为当前 preferences.toml 状态')};if(confirm){confirm.checked=assetConfirmPrefsChecked;confirm.onchange=()=>{assetConfirmPrefsChecked=confirm.checked}}if(phrase){phrase.value=assetConfirmPhraseValue;phrase.oninput=()=>{assetConfirmPhraseValue=phrase.value}}if(result)result.textContent=assetPrefsResultText;if(copy)copy.onclick=async()=>{const snippet=renderAssetPreferenceSnippet();try{await navigator.clipboard.writeText(snippet);toast('偏好片段已复制')}catch(_err){toast('无法访问剪贴板，片段已显示在页面')}};if(reset)reset.onclick=resetDraft;if(discard)discard.onclick=resetDraft;if(apply)apply.onclick=async()=>{if(confirm)assetConfirmPrefsChecked=confirm.checked;if(phrase)assetConfirmPhraseValue=phrase.value;const payload=assetPreferencesPayload();const data=await api('/api/preferences/apply',{...payload,confirm_preferences:assetConfirmPrefsChecked,confirm_phrase:assetConfirmPhraseValue,reason:'setup-web-ui:asset-preferences'});assetPrefsResultText=data.ok?(data.status==='no_change'?'偏好没有变化。':`已写入 ${data.target_path||'preferences.toml'}；backup ${data.backup_path||'-'}`):(data.errors||[data.error||'保存被阻止']).join('；');if(result)result.textContent=assetPrefsResultText;toast(data.ok?(data.status==='no_change'?'偏好没有变化':'Skill/MCP 偏好已保存'):'Skill/MCP 偏好保存被阻止');if(data.ok){assetConfirmPrefsChecked=false;assetConfirmPhraseValue='';const res=await fetch('/api/state');state=await res.json();assetDisabledDraft=null;renderAll()}}}
function renderAssetControlHelp(){
  const box=$('assetControlHelp');
  if(!box)return;
  const assets=state.session_assets||{};
  const contract=assets.configuration_contract||{};
  const install=assets.managed_install||{};
  const rows=assetRows();
  const canClose=rows.filter(row=>assetDisableSupported(row)).length;
  const globalCanClose=rows.filter(row=>row.group==='global'&&assetDisableSupported(row)).length;
  const prefPath=contract.persistent_path||'~/.config/mms/preferences.toml';
  const managedRoot=install.root||contract.managed_assets_root||'~/.local/share/mms/assets';
  box.innerHTML=`<article class="asset-control-card"><h3>在这里开 / 关</h3><p class="muted">在下面卡片右侧勾“默认关闭”。一旦和当前 preferences 不同，页面底部会出现“保存并应用”栏；改回原状后自动消失。</p><p><span class="tag">可关闭 ${canClose}</span><span class="tag">Global 可关闭 ${globalCanClose}</span></p><div class="btns"><button class="ghost" data-asset-jump-tab="mms_dynamic" data-asset-jump-kind="all">管理 MMS 动态</button><button class="ghost" data-asset-jump-tab="global" data-asset-jump-kind="skills">管理 Global Skill</button><button class="ghost" data-asset-jump-tab="all" data-asset-jump-kind="mcp">管理 MCP</button></div></article><article class="asset-control-card"><h3>添加到 MMS 动态</h3><p class="muted">固定放到 MMS managed assets root；推荐放 symlink，不复制大包。launcher 会优先读这里，再回退 vendor / 历史路径。</p><p class="mono">${escapeHtml(managedRoot)}</p><p class="muted">偏好文件：${escapeHtml(prefPath)}</p><div class="btns"><button class="ghost" data-asset-open-sources="1">查看当前加载路径</button></div></article><article class="asset-control-card"><h3>添加到 Global</h3><p class="muted">想让原生 CLI 也能看到，就放到对应全局目录；本页可帮 MMS 启动时默认关闭 Claude/Codex Global Skill。</p><p class="mono">Claude: ~/.claude/skills/&lt;name&gt;</p><p class="mono">Codex: ~/.codex/skills/&lt;name&gt;</p></article>`;
  document.querySelectorAll('[data-asset-jump-tab]').forEach(btn=>{btn.onclick=()=>{assetTab=btn.dataset.assetJumpTab||assetTab;assetKind=btn.dataset.assetJumpKind||assetKind;assetCli='all';renderSessionAssets();toast('已切换管理范围')}});
  document.querySelectorAll('[data-asset-open-sources]').forEach(btn=>{btn.onclick=()=>{const diag=document.querySelector('#assetManagedRoots details.asset-source-diagnostic');if(diag){diag.open=true;diag.scrollIntoView({block:'nearest',behavior:'smooth'});toast('已展开当前加载路径')}}})
}
function renderAssetManagedRoots(){const box=$('assetManagedRoots');if(!box)return;const assets=state.session_assets||{};const install=assets.managed_install||{};const roots=assets.managed_roots||[];const visible=Array.isArray(roots)?roots.filter(Boolean):[];const installBadge=install.enabled===false?'<span class="tag off">固定根已关闭</span>':`<span class="tag ${install.exists?'':'off'}">${install.exists?'固定根存在':'固定根待创建'}</span>`;if(!visible.length){box.innerHTML=`<details class="asset-source-diagnostic"><summary><span>当前加载来源 / 路径诊断</span><span class="tag off">未解析</span></summary><p class="muted">当前没有解析到动态 Skill/MCP 根；固定安装位置仍是 <span class="mono">${escapeHtml(install.root||'~/.local/share/mms/assets')}</span>。</p></details>`;return}const resolved=visible.filter(root=>!!root.exists).length;const skillRoots=visible.filter(root=>String(root.surface||'').toLowerCase().includes('skill')).length;const mcpRoots=visible.filter(root=>String(root.surface||'').toLowerCase().includes('mcp')).length;const rootCard=(root)=>{const exists=!!root.exists;const count=Number(root.skill_count||0);const real=root.real_path&&root.real_path!==root.path?`<p><strong>真实路径</strong>：<span class="mono">${escapeHtml(root.real_path)}</span></p>`:'';const installPath=root.install_path?`<p><strong>固定安装位</strong>：<span class="mono">${escapeHtml(root.install_path)}</span></p>`:'';return `<div class="asset-source-mini ${exists?'':'is-missing'}"><div class="asset-source-head"><strong class="asset-source-title">${escapeHtml(root.name||'-')}</strong><span class="tag ${exists?'':'off'}">${exists?'已解析':'未找到'}</span></div><div class="asset-source-foot"><span class="tag">${escapeHtml(root.surface||'Skill')}</span><span class="muted">${escapeHtml(root.root_kind||'来源未知')}${count?` · ${count} 个 skill`:''}</span></div><details class="asset-source-real"><summary>路径</summary><p><strong>当前加载</strong>：<span class="mono">${escapeHtml(root.path||'-')}</span></p>${real}${installPath}</details></div>`};box.innerHTML=`<details class="asset-source-diagnostic"><summary><span>当前加载来源 / 路径诊断</span><span class="asset-source-summary">${installBadge}<span class="tag">${visible.length} 个来源</span><span class="tag">已解析 ${resolved}</span><span class="tag">Skill ${skillRoots}</span><span class="tag">MCP ${mcpRoots}</span></span></summary><p class="muted">固定安装根：<span class="mono">${escapeHtml(install.root||'~/.local/share/mms/assets')}</span>。建议把包软链到这里；launcher 优先读固定根，再回退 vendor / 历史路径。</p><div class="asset-source-grid">${visible.map(rootCard).join('')}</div></details>`}
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
function assetStatusText(row,disabled){if(!assetDisableSupported(row))return row.inventory_only?'全局只读':'只读展示';if(disabled)return '默认关闭';if(row.scope==='always')return '默认带上';return '按开关启用'}
function assetGroupTagClass(row){return row.group==='global'?'off':(row.group==='other'?'off':'')}
function renderAssetCard(row,idx){const supported=assetDisableSupported(row);const disabled=assetIsDefaultDisabled(row);const source=row.group_label||row.group||'未归类';const kind=row.kind_label||assetKindLabel(row.kind);const path=assetDetail(row,'路径')||assetDetail(row,'Path')||assetDetail(row,'URL')||assetDetail(row,'触发')||assetDetail(row,'Trigger');const status=assetStatusText(row,disabled);const globalClass=row.group==='global'?' is-global':'';const disabledClass=disabled?' is-disabled':'';const mergeTag=row.merged_count>1?`<span class="tag off">适用 ${row.merged_count} 个 CLI</span>`:'';const action=supported?`<span>${disabled?'已加入关闭草稿；启动确认页仍可临时打开。':'需要时可加入默认关闭草稿，当前不会写真实配置。'}</span><label class="asset-switch"><input type="checkbox" data-asset-disable="${idx}" ${disabled?'checked':''}>默认关闭</label>`:`<span>全局 Skill 当前只读展示；默认关闭需要 launcher 继承过滤支持，不会写入草稿。</span><span class="tag off">不可在此关闭</span>`;return `<article class="card asset-card${globalClass}${disabledClass}" data-asset-row="${idx}"><div class="asset-card-head"><div><div class="asset-title">${escapeHtml(row.title||'未命名能力')}</div><div class="asset-subline">${escapeHtml(row.cli_label||row.cli||'CLI')} · ${escapeHtml(kind)} · ${escapeHtml(row.scope_label||row.scope||'默认')}</div></div><span class="tag ${assetGroupTagClass(row)}">${escapeHtml(source)}</span></div><p class="asset-desc">${escapeHtml(row.summary||'暂无说明。')}</p><div class="asset-meta"><span class="tag">${escapeHtml(row.origin_label||row.origin||'来源未知')}</span><span class="tag ${disabled||!supported?'off':''}">${escapeHtml(status)}</span>${mergeTag}${row.inventory_only?'<span class="tag off">完整清单</span>':''}${path?`<span class="tag off">有技术详情</span>`:''}</div><div class="asset-action">${action}</div><details class="asset-details"><summary>高级信息：路径、触发和 key</summary><div class="asset-detail-grid">${assetDetailsHtml(row)}</div></details></article>`}
function assetSkillFamily(row){const title=String(row.title||'').toLowerCase();const origin=String(row.origin_label||'全局技能');if(title.startsWith('lark-'))return 'Lark CLI 技能组';if(title.startsWith('caveman'))return 'Caveman 技能组';if(title.startsWith('scmp-'))return 'SCMP 技能组';if(title.includes('browser'))return 'Browser / Web 技能组';return origin}
function assetSkillFamilyHint(name){if(name==='Lark CLI 技能组')return '这些是 agent 使用 Lark CLI 的任务说明，不是另一套 CLI；不用飞书时可以整组默认关闭。';if(name==='Caveman 技能组')return '压缩表达、提交和 review 风格相关技能，按需要打开即可。';if(name==='Claude 全局技能')return '来自 ~/.claude/skills；只影响 MMS 启动的 Claude session，不会删除全局文件。';if(name==='Codex 全局技能')return '来自 ~/.codex/skills；只影响 MMS 启动的 Codex session，不会删除全局文件。';if(name.includes('plugin'))return '来自 Codex plugin cache，当前只读展示，避免误改插件缓存。';if(name.includes('共享 agent'))return '来自 ~/.agents/skills 的宿主共享候选，当前只读展示。';return '同类全局 Skill 已折叠，展开后可查看路径、来源和关闭 key。'}
function assetGroupedRows(rows){const groups=new Map();rows.forEach((row,idx)=>{const name=assetSkillFamily(row);if(!groups.has(name))groups.set(name,[]);groups.get(name).push({row,idx})});return [...groups.entries()].sort((a,b)=>b[1].length-a[1].length||a[0].localeCompare(b[0]))}
function assetGroupStateKey(name){return [assetTab,assetCli,assetKind,String(name||'')].join('::')}
function assetGroupShouldOpen(name,groupIdx,disabledCount){const key=assetGroupStateKey(name);if(Object.prototype.hasOwnProperty.call(assetGroupOpenState,key))return !!assetGroupOpenState[key];return groupIdx<2||disabledCount>0}
function renderAssetRows(rows){if(!(assetTab==='global'&&assetKind==='skills'))return rows.map((row,idx)=>renderAssetCard(row,idx)).join('');return assetGroupedRows(rows).map(([name,items],groupIdx)=>{const supported=items.filter(item=>assetDisableSupported(item.row));const disabled=supported.filter(item=>assetIsDefaultDisabled(item.row));const allDisabled=supported.length>0&&disabled.length===supported.length;const state=supported.length?`${disabled.length?'已关 '+disabled.length+'/'+supported.length:'可关闭 '+supported.length}`:'只读';const cards=items.map(item=>renderAssetCard(item.row,item.idx)).join('');const open=assetGroupShouldOpen(name,groupIdx,disabled.length)?' open':'';const action=supported.length?`<div class="asset-group-actions"><button class="ghost" data-asset-group-disable="${escapeHtml(name)}">${allDisabled?'保持整组关闭':'整组默认关闭'}</button><button class="ghost" data-asset-group-enable="${escapeHtml(name)}">取消整组关闭</button></div>`:'<span class="tag off">当前只读</span>';return `<details class="asset-group"${open} data-asset-group-details="${escapeHtml(name)}"><summary><span>${escapeHtml(name)}</span><span><span class="tag">${items.length} 个</span> <span class="tag ${supported.length?'':'off'}">${escapeHtml(state)}</span></span></summary><div class="asset-group-note"><p class="muted">${escapeHtml(assetSkillFamilyHint(name))}</p>${action}</div><div class="asset-group-cards">${cards}</div></details>`}).join('')}
function renderSessionAssets(){if(!$('assetCards'))return;const assets=state.session_assets||{};const summary=assets.summary||{};const contract=assets.configuration_contract||{};const draft=ensureAssetDisabledDraft();const pending=assetDraftDiff();const displayCount=filteredAssetRows().length;$('assetSummary').innerHTML=`<div class="card"><span class="asset-count">${displayCount}</span><h3>当前管理范围</h3><p class="muted">下面这些卡片就是当前筛选到的 Skill / MCP / Hook；在卡片上直接勾“默认关闭”。</p><div class="asset-meta"><span class="tag">全部 ${summary.total||0}</span><span class="tag">Skill ${summary.skills||0}</span><span class="tag">MCP ${summary.mcp||0}</span><span class="tag">Hook ${summary.hooks||0}</span></div></div><div class="card"><span class="asset-count">${pending.total}</span><h3>本次未保存变化</h3><p class="muted">只统计相对当前 preferences 的变化；改回原状态后底部保存栏会消失。</p><div class="asset-meta"><span class="tag">Skill ${pending.skills.length}</span><span class="tag">MCP ${pending.mcp.length}</span><span class="tag">Hook ${pending.hooks.length}</span><span class="tag off">当前关闭 ${draft.skills.length+draft.mcp.length+draft.hooks.length}</span></div></div>`;renderAssetControlHelp();renderAssetManagedRoots();renderAssetFilters();const rows=filteredAssetRows();$('assetCards').innerHTML=rows.length?renderAssetRows(rows):`<div class="asset-empty">没有匹配的能力。可以清空搜索，或切换来源 / CLI / 类型筛选。</div>`;renderAssetConfirmMap();renderAssetCliOverview();document.querySelectorAll('[data-asset-disable]').forEach(input=>{input.onchange=()=>{const row=rows[Number(input.dataset.assetDisable)];setAssetDefaultDisabled(row,input.checked);renderAssetPreferenceSnippet();renderSessionAssets()}});document.querySelectorAll('[data-asset-group-details]').forEach(details=>{details.onclick=(event)=>{const target=event.target;if(target&&target.closest&&target.closest('summary'))assetGroupOpenState[assetGroupStateKey(details.dataset.assetGroupDetails||'')]=!details.open};details.ontoggle=()=>{assetGroupOpenState[assetGroupStateKey(details.dataset.assetGroupDetails||'')]=details.open}});document.querySelectorAll('[data-asset-group-disable]').forEach(btn=>{btn.onclick=()=>{const name=btn.dataset.assetGroupDisable;rows.filter(row=>assetSkillFamily(row)===name&&assetDisableSupported(row)).forEach(row=>setAssetDefaultDisabled(row,true));renderAssetPreferenceSnippet();renderSessionAssets();toast(`${name} 已加入默认关闭草稿`)}});document.querySelectorAll('[data-asset-group-enable]').forEach(btn=>{btn.onclick=()=>{const name=btn.dataset.assetGroupEnable;rows.filter(row=>assetSkillFamily(row)===name&&assetDisableSupported(row)).forEach(row=>setAssetDefaultDisabled(row,false));renderAssetPreferenceSnippet();renderSessionAssets();toast(`${name} 已移出默认关闭草稿`)}});$('assetConfigContract').textContent=`持久偏好位置：${contract.persistent_path||'~/.config/mms/preferences.toml'}。固定安装根：${contract.managed_assets_root||'~/.local/share/mms/assets'}。${contract.webui_write_scope||'当前 WebUI 只生成片段，不直接写入。'} ${contract.launch_override||''}`;renderAssetPreferenceSnippet();renderAssetPendingBar();bindAssetPreferenceButtons();$('assetGlobalRoots').innerHTML=(assets.global_roots||[]).map(root=>`<div class="asset-root"><p><span class="tag ${root.exists?'':'off'}">${root.exists?'存在':'未找到'}</span> <strong>${escapeHtml(root.label)}</strong></p><p class="mono">${escapeHtml(root.path)}</p><p class="muted">${root.skill_count?`发现 ${root.skill_count} 个技能；`:''}${escapeHtml(root.note||'只读展示，不自动修改。')}</p></div>`).join('')||'<p class="muted">没有全局位置记录。</p>'}
function renderRefs(){ $('refsGrid').innerHTML=(state.references||[]).map(r=>`<div class="card span6"><h3>${escapeHtml(r.title)}</h3><p>${escapeHtml(r.summary)}</p><p class="mono">${escapeHtml(r.path)}</p></div>`).join('') }
function levelLabel(level){return level==='danger'?'高风险':(level==='warn'?'注意':'信息')}
function planJsonHint(plan){const v2=plan?.registry_v2_save_plan||{};const planJson=v2.plan_json||{};const apply=v2.apply_plan||{};if(!planJson.name&&!apply.cli_apply_command)return '';return `<h4>Plan JSON / apply-plan</h4><p class="muted">${escapeHtml(planJson.note||'Plan JSON 是保存预览的 review artifact。')}</p><p><span class="tag">${escapeHtml(planJson.name||'webui-plan.json')}</span> <span class="tag ${planJson.redacted?'off':''}">secrets ${planJson.redacted?'redacted':'included'}</span></p><p class="mono">${escapeHtml(apply.cli_apply_command||'')}</p>`}
function renderApplyResult(data){const blockers=data.runtime_blockers||{};const next=data.next_action||{};const publish=data.publish||{};const verify=data.verify||{};const ready=data.runtime_ready===true;const notReady=data.runtime_ready===false;const errs=Array.isArray(data.errors)?data.errors:[data.error||'unknown error'];const title=!data.ok?'写入被阻止':(ready?'已发布，可直接给 mmf 使用':'已发布，但 runtime 未就绪');const detail=!data.ok?errs.join('；'):(ready?'latest-approved bundle 已验证，mmf 会读到这次保存后的最新 bundle。':'latest-approved bundle 已发布且已验证；mmf 会读到最新 bundle，但缺 key/base URL/模型 route 的条目不能正常启动。');$('saveResult').innerHTML=`<div><p><span class="tag ${data.ok&&!notReady?'':'off'}">${escapeHtml(title)}</span> <span class="tag">${escapeHtml(data.status||'-')}</span></p><p class="muted">${escapeHtml(detail)}</p><p><span class="tag">manifest ${verify.verified?'verified':'not verified'}</span><span class="tag ${ready?'':'off'}">runtime ${ready?'ready':notReady?'not ready':'unknown'}</span><span class="tag">缺 API Key ${blockers.missing_api_key_count||0}</span><span class="tag">missing base URL ${blockers.missing_base_url_count||0}</span><span class="tag">provider routes ${blockers.provider_route_count||publish.provider_route_count||0}</span></p>${next.label?`<p><strong>下一步</strong>：${escapeHtml(next.label)}</p>`:''}<details><summary>Raw JSON</summary><pre class="mono">${escapeHtml(JSON.stringify(data,null,2))}</pre></details></div>`}
function assetDraftDiff(){const base=cloneAssetDisabledDefaults();const draft=ensureAssetDisabledDraft();const result={skills:[],mcp:[],hooks:[],total:0};for(const key of ['skills','mcp','hooks']){const before=new Set(base[key]||[]);const after=new Set(draft[key]||[]);result[key]=[...new Set([...before,...after])].filter(value=>before.has(value)!==after.has(value)).sort();result.total+=result[key].length}return result}
function renderReviewSummary(plan){const review=plan?.review_summary||{};const counts=review.counts||{};const risks=review.risks||[];const items=review.items||[];const configItems=items.filter(item=>item.kind!=='no_change');const assetDiff=assetDraftDiff();const riskHtml=risks.length?`<h4>风险提示</h4><div>${risks.map(r=>`<p><span class="tag ${r.level==='danger'?'off':''}">${escapeHtml(levelLabel(r.level))}</span> <strong>${escapeHtml(r.title)}</strong> ${escapeHtml(r.detail)}</p>`).join('')}</div>`:'<p><span class="tag">无高风险提示</span></p>';let itemHtml=configItems.length?configItems.map(item=>`<p><span class="tag ${item.level==='danger'?'off':''}">${escapeHtml(levelLabel(item.level))}</span> <strong>${escapeHtml(item.title)}</strong> ${escapeHtml(item.detail)}</p>`).join(''):'<p class="muted">模型/通道配置没有变化。</p>';if(assetDiff.total){itemHtml+=`<p><span class="tag">能力草稿</span> <strong>Skill/MCP 默认关闭草稿有 ${assetDiff.total} 项</strong> 这不会通过“保存审计”写入；请回到 Skill / MCP 管理，使用底部未保存变化栏点击“保存并应用”。</p>`}$('reviewSummary').innerHTML=`<div class="chips"><span class="chip">配置变化 ${configItems.length}</span><span class="chip">能力草稿 ${assetDiff.total}</span><span class="chip">风险 ${counts.risks||0}</span><span class="chip">移除隐藏记录 ${counts.hidden_removed||0}</span><span class="chip">凭据更新 ${counts.credential_updates||0}</span></div>${riskHtml}<h4>将要写入的变化</h4>${itemHtml}${planJsonHint(plan)}`}
function currentBundleRevision(){return state?.consumer_bundle_status?.component_revisions?.bundle||state?.consumer_bundle_status?.manifest?.bundle_revision||state?.model_source_status?.generated_bundle?.component_revisions?.bundle||state?.model_source_status?.generated_bundle?.manifest?.bundle_revision||''}
function draft(){syncProvider();syncFallback();syncRuntime();syncAccounts();syncUiSettings();return JSON.parse(JSON.stringify({providers:state.providers,provider_default:state.provider_default,accounts:state.accounts,account_defaults:state.account_defaults,rescue:state.rescue,vision_sidecar:state.vision_sidecar,ui:state.ui,runtime:state.runtime,opencode:state.opencode,expected_bundle_revision:currentBundleRevision(),route_scope_provider_ids:[...touchedProviders],route_refresh_provider_ids:[...staleCleanupProviders]}))}
function renderAll(){renderStatus();renderSaveControls();renderSourceStatus();renderProviders();renderFallback();renderRuntime();renderSessionAssets();renderSettings();renderRefs()}
async function load(){const res=await fetch('/api/state');state=await res.json();state.providers=state.providers||[];loadAcceptanceState(state.tui_webui_mapping||[]);renderNav();renderAll();}
$('addProvider').onclick=()=>{state.providers.push({id:`provider-${state.providers.length+1}`,original_id:'',name:'新通道',enabled:true,role:'auto',priority:100,family_priority_overrides:{},claude_1m_mode:'auto',timezone:'Asia/Singapore',note:'',models_endpoint:'/models',protocols:['anthropic_messages','openai_chat_completions'],supported_clis:['claude','codex','opencode'],openai_base_url:'',anthropic_base_url:'',api_key:'',update_credentials:false,fallback_models:[],extra_models:[],hidden_models:[],models:[]});activeProvider=state.providers.length-1;renderAll()}
$('duplicateProvider').onclick=()=>{const p=JSON.parse(JSON.stringify(current()));p.id=p.id+'-copy';p.original_id='';p.name=p.name+' Copy';p.api_key='';p.pending_api_key=false;p.update_credentials=false;p.has_api_key=false;state.providers.push(p);activeProvider=state.providers.length-1;renderAll()}
$('modelSearch').oninput=renderModelTable
$('addManualModels').onclick=()=>{const p=current();const vals=$('manualModels').value.split(/[\n,]/).map(x=>x.trim()).filter(Boolean);p.extra_models=[...new Set([...(p.extra_models||[]),...vals])];p.hidden_models=(p.hidden_models||[]).filter(x=>!vals.includes(x));$('manualModels').value='';if(vals.length)touchProvider(p.id);renderModelTable();toast(`已添加 ${vals.length} 个模型`)}
$('clearHidden').onclick=()=>{const p=current();const count=(p.hidden_models||[]).length;p.hidden_models=[];p.stale_hidden_models=[];if(count)touchProvider(p.id);renderModelTable();toast(count?`已取消隐藏 ${count} 个模型`:'当前通道没有隐藏模型')}
$('restoreModelPatch').onclick=()=>{const p=current();const extra=(p.extra_models||[]).length;const hidden=(p.hidden_models||[]).length;p.extra_models=[];p.hidden_models=[];p.stale_hidden_models=[];touchProvider(p.id);renderModelTable();toast(extra||hidden?`已恢复默认模型补丁：清空 ${extra} 个补充 / ${hidden} 个隐藏`:'当前已是默认模型补丁')}
$('clearAllStaleHidden').onclick=cleanupAllStaleHidden
function setTestState(label,ok=null){const box=$('testState');if(!box)return;const cls=ok===false?'off':'';box.innerHTML=`<span class="chip ${cls}">${escapeHtml(label)}</span>`}
function showJson(targetId,data){const target=$(targetId);if(target)target.textContent=JSON.stringify(data,null,2)}
async function runProviderModelsTest({targetId='testResult',switchToTest=false,applyToCurrent=false}={}){syncProvider();const target=$(targetId);if(target)target.textContent='测试 /models 中...';setTestState('models endpoint 测试中');const data=await api('/api/provider/test',{provider:current(),force_refresh:true});showJson(targetId,data);setTestState(data.ok?'models endpoint 正常':'models endpoint 失败',data.ok);if(switchToTest)setSection('test');if(applyToCurrent&&data.ok&&Array.isArray(data.models)){const p=current();if(!p.approved_route_models||!p.approved_route_models.length){p.approved_route_models=(p.models||[]).filter(r=>r&&r.id&&r.source!=='derived_alias').map(r=>r.id)}p.models=data.models.map(id=>({id,source:data.base_source||'remote',visible:!(p.hidden_models||[]).includes(id),favorite:false,capabilities:defaultCaps(id)}));touchProvider(p.id);if($('autoStaleCleanupOnFetch')?.checked&&staleRouteModels(p).length){staleCleanupProviders.add(p.id)}renderModelTable()}return data}
$('fetchModels').onclick=async()=>{const data=await runProviderModelsTest({targetId:'modelConfigResult',applyToCurrent:true});if(data.ok&&Array.isArray(data.models)){toast(staleCleanupProviders.has(current()?.id)?`拉取到 ${data.models.length} 个模型；已自动标记缺失旧 route 清理`:`拉取到 ${data.models.length} 个模型；不会自动写入 fallback_models；缺失旧 route 默认保留`)}else{toast(data.error||'模型拉取失败，请看模型配置结果')}}
$('testList').onclick=async()=>{await runProviderModelsTest({targetId:'modelConfigResult',switchToTest:true})}
$('openModelTest').onclick=()=>{renderTestSelectors();setSection('test')}
$('testListBtn').onclick=async()=>{await runProviderModelsTest({targetId:'testResult'})}
async function runSelectedModelTest(path,label){$('testResult').textContent=`${label} 测试中...`;setTestState(`${label} 测试中`);const data=await api(path,{provider:state.providers[Number($('testProvider').value)],model:$('testModel').value,protocol:$('testProtocol').value,prompt:$('testPrompt').value});$('testResult').textContent=JSON.stringify(data,null,2);setTestState(data.ok?`${label} 成功`:`${label} 失败`,data.ok)}
$('testModelBtn').onclick=async()=>runSelectedModelTest('/api/model/test','ping')
$('chatTestBtn').onclick=async()=>runSelectedModelTest('/api/chat/test','chat')
$('previewPlan').onclick=async()=>{const data=await api('/api/plan',{draft:draft()});lastPlan=data;renderSaveControls();renderReviewSummary(data);$('saveResult').textContent=JSON.stringify({ok:data.ok,summary:data.summary,registry_v2_save_plan:data.registry_v2_save_plan,warnings:data.warnings,errors:data.errors,risks:data.review_summary?.risks},null,2);$('diffBox').textContent=[data.diffs?.config_toml,data.diffs?.model_policy_json,data.diffs?.credentials].filter(Boolean).join('\n')||'没有配置变化';toast(data.ok?'预览已生成':'预览有错误')}
function currentApplyCommand(){return lastPlan?.registry_v2_save_plan?.apply_plan?.cli_apply_command||'./mmf config apply-plan --plan-json <webui-plan.json> --apply --confirm-preview-apply --json'}
$('downloadPlanJson').onclick=()=>{if(!lastPlan){toast('请先生成保存预览');return}const blob=new Blob([JSON.stringify(lastPlan,null,2)+'\n'],{type:'application/json'});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=lastPlan?.registry_v2_save_plan?.plan_json?.name||'webui-plan.json';document.body.appendChild(a);a.click();a.remove();URL.revokeObjectURL(url);toast('已下载脱敏 plan JSON')}
$('copyApplyCommand').onclick=async()=>{const cmd=currentApplyCommand();try{await navigator.clipboard.writeText(cmd);toast('已复制 CLI apply 命令')}catch(_err){$('saveResult').textContent=cmd;toast('无法访问剪贴板，命令已显示在结果框')}}
$('applyV2Preview').onclick=async()=>{const data=await api('/api/registry-v2/apply',{draft:draft(),confirm_v2_preview:$('confirmSave').checked,confirm_phrase:$('confirmPhrase').value,reason:$('saveReason').value});renderApplyResult(data);toast(data.ok?(data.runtime_ready===false?'已发布但 runtime 未就绪：请看 missing key/base URL':'预览 DB 已写入并发布，mmf 会读最新 bundle'):'预览 DB 写入被阻止'); if(data.ok){const res=await fetch('/api/state');state=await res.json();touchedProviders=new Set();staleCleanupProviders=new Set();renderAll();}}
$('saveBtn').onclick=async()=>{const data=await api('/api/save',{draft:draft(),confirm_save:$('confirmSave').checked,confirm_phrase:$('confirmPhrase').value,reason:$('saveReason').value});$('saveResult').textContent=JSON.stringify(data,null,2);toast(data.ok?'保存完成，已写入 audit':'保存被阻止'); if(data.ok){const res=await fetch('/api/state');state=await res.json();touchedProviders=new Set();staleCleanupProviders=new Set();renderAll();}}
load().catch(err=>{document.body.innerHTML='<pre style="padding:30px;color:var(--danger);font-family:var(--font-mono)">'+escapeHtml(err.stack||err.message)+'</pre>'})
</script>
</body>
</html>"""
