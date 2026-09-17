import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const srcDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../src");
const app = fs.readFileSync(path.join(srcDir, "App.tsx"), "utf-8");
const settings = fs.readFileSync(path.join(srcDir, "SettingsPage.tsx"), "utf-8");
const css = fs.readFileSync(path.join(srcDir, "studio.css"), "utf-8");

test("sidebar version sits beside the home button, not inside it", () => {
  const row = app.indexOf('className="brand-row"');
  const home = app.indexOf('className="brand"');
  const version = app.indexOf("<AppVersion");
  const homeEnd = app.indexOf("</button>", home);
  assert.ok(row >= 0 && home > row && version > home);
  assert.ok(version > homeEnd, "AppVersion must not be nested in the home button");
});

test("sidebar version opens the same update dialog as settings", () => {
  const sidebar = app.slice(app.indexOf("<AppVersion"), app.indexOf("<AppVersion") + 280);
  assert.match(sidebar, /onClick=\{\(\) => setUpdateOpen\(true\)\}/);
  assert.match(sidebar, /updateAvailable=\{!!updateStatus\?\.available\}/);
  assert.match(settings, /onClick=\{openUpdates\}/);
  assert.match(settings, /updateAvailable=\{updateAvailable\}/);
});

test("brand-row styles keep the version on the same header line", () => {
  assert.match(css, /\.brand-row\s*\{[^}]*display:\s*flex/);
  assert.match(css, /\.brand-row > \.app-version/);
  assert.doesNotMatch(css, /\.brand > \.app-version/);
});
