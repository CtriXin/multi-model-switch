import test from "node:test";
import assert from "node:assert/strict";
import { withoutUpgradeSection } from "../src/release-notes.ts";

test("the upgrade section is removed from the body and later sections survive", () => {
  const body = "# v4.20.0 · X\n\n## 升级须知\n\n先运行安装器。\n\n更多。\n\n## 其他\n\n- 一条\n";
  assert.equal(withoutUpgradeSection(body), "# v4.20.0 · X\n\n## 其他\n\n- 一条");
});

test("a body without the section is returned unchanged apart from trimming", () => {
  assert.equal(withoutUpgradeSection("# v1\n\n- a\n"), "# v1\n\n- a");
});

test("a deeper heading inside the section is skipped too", () => {
  assert.equal(withoutUpgradeSection("## 升级须知\n\n### 细节\n\nx\n\n## 后面\n\ny"), "## 后面\n\ny");
});
