import test from "node:test";
import assert from "node:assert/strict";
import { localFilePaths } from "../../apps/mms-web/src/local-file-paths.ts";

test("windows drive paths, with spaces/CJK, quoted or pasted in batches", () => {
  assert.deepEqual(localFilePaths("C:\\Users\\me\\file.txt"), ["C:\\Users\\me\\file.txt"]);
  assert.deepEqual(localFilePaths("C:\\我的 文件\\a b.txt"), ["C:\\我的 文件\\a b.txt"]);
  assert.deepEqual(localFilePaths('"C:\\我的 文件\\a b.txt"'), ["C:\\我的 文件\\a b.txt"]);
  assert.deepEqual(localFilePaths("'D:\\data\\x.json'"), ["D:\\data\\x.json"]);
  assert.deepEqual(localFilePaths("c:/lower/slash.md"), ["c:/lower/slash.md"]);
  assert.deepEqual(
    localFilePaths("C:\\a.txt\r\nD:\\b 中文.txt"),
    ["C:\\a.txt", "D:\\b 中文.txt"],
  );
});

test("UNC paths and file:// URLs map to drive or UNC forms", () => {
  assert.deepEqual(localFilePaths("\\\\server\\share\\folder\\file.txt"), ["\\\\server\\share\\folder\\file.txt"]);
  assert.deepEqual(localFilePaths("file:///C:/Users/me/a.txt"), ["C:/Users/me/a.txt"]);
  assert.deepEqual(localFilePaths("file://C:/Users/me/a.txt"), ["C:/Users/me/a.txt"]);
  // file://localhost/C:/... must not degrade to the posix-looking /C:/... form.
  assert.deepEqual(localFilePaths("file://localhost/C:/Users/me/a.txt"), ["C:/Users/me/a.txt"]);
  assert.deepEqual(localFilePaths("file://server/share/folder/file.txt"), ["\\\\server\\share\\folder\\file.txt"]);
  assert.deepEqual(
    localFilePaths("file://server/share/%E6%88%91%E7%9A%84%20%E6%96%87%E4%BB%B6.txt"),
    ["\\\\server\\share\\我的 文件.txt"],
  );
  assert.deepEqual(localFilePaths("file:///Users/me/a%20b.txt"), ["/Users/me/a b.txt"]);
});

test("non-paths, drive-relative paths and mixed batches are rejected whole", () => {
  for (const bad of [
    "docs/a.txt", // relative
    "c:file.txt", // drive-relative is not an absolute path
    "not a path",
    '"not a path"', // quoted non-path
    "file://C:", // drive letter without a path separator
  ]) {
    assert.deepEqual(localFilePaths(bad), [], bad);
  }
  // All-or-nothing: one non-path line rejects the whole paste.
  assert.deepEqual(localFilePaths("C:\\a.txt\nnot a path"), []);
  assert.deepEqual(localFilePaths(""), []);
  assert.deepEqual(localFilePaths("/help"), []);
});
