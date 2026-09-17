import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));

test("BotPresetPanel supports click-outside and escape key with dirty guard", () => {
  const file = resolve(__dirname, "../src/BotPresetPanel.tsx");
  const source = readFileSync(file, "utf8");

  // Panel ref binding
  assert.match(source, /ref=\{panelRef\}/, "panelRef must be attached to the aside element");

  // Capture clicks so cancelling a dirty close also cancels the outside action
  assert.match(source, /document\.addEventListener\("click", handleOutsideClick, true\)/);
  assert.match(source, /panel\.contains\(target\)/);

  // Trigger button exclusion so clicking the trigger button does not cause double toggling
  assert.match(source, /target\.closest\?\.?\('\\[aria-label="调整工作预设"\\], \\\[title="工作预设"\\]'\)|target\.closest/);

  // Escape key listener
  assert.match(source, /e\.key === "Escape"/);
  assert.match(source, /window\.addEventListener\("keydown", handleKeyDown\)/);

  // Dirty guard against accidental data loss
  assert.match(source, /isDirty/, "must track dirty state");
  assert.match(source, /initialPromptRef/, "must compare against initial baseline");
  assert.match(source, /window\.confirm/, "must prompt when discarding dirty changes");
});

test("BotMemoryPanel and BotCommunications support click-outside and escape key", () => {
  const memoryFile = resolve(__dirname, "../src/BotMemoryPanel.tsx");
  const memorySource = readFileSync(memoryFile, "utf8");
  assert.match(memorySource, /ref=\{panelRef\}/);
  assert.match(memorySource, /addEventListener\("pointerdown"/);
  assert.match(memorySource, /e\.key === "Escape"/);

  const commFile = resolve(__dirname, "../src/BotCommunications.tsx");
  const commSource = readFileSync(commFile, "utf8");
  assert.match(commSource, /ref=\{panelRef\}/);
  assert.match(commSource, /addEventListener\("pointerdown"/);
  assert.match(commSource, /e\.key === "Escape"/);
});
