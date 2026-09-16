import { strict as assert } from "node:assert";
import test from "node:test";
import { decideWhatsNew } from "../src/whats-new.ts";

const notes = "# v4.17.0\nsomething changed";

test("an upgrade into a version not yet read shows the notes once", () => {
  assert.equal(decideWhatsNew({ version: "4.17.0", notes, seenVersion: "4.16.0" }), "show");
  assert.equal(decideWhatsNew({ version: "4.17.0", notes, seenVersion: "4.17.0" }), "skip");
});

test("no recorded version means an existing install, not a new one", () => {
  // A never-used install is stamped by the server before the browser ever
  // sees it, so an empty value here can only be a real upgrade.
  assert.equal(decideWhatsNew({ version: "4.17.0", notes }), "show");
  assert.equal(decideWhatsNew({ version: "4.17.0", notes, seenVersion: "   " }), "show");
});

test("nothing to say means nothing is shown", () => {
  assert.equal(decideWhatsNew({ version: "4.17.0", notes: "" }), "skip");
  assert.equal(decideWhatsNew({ version: "", notes }), "skip");
  assert.equal(decideWhatsNew({ version: "  ", notes }), "skip");
  assert.equal(decideWhatsNew({}), "skip");
});
