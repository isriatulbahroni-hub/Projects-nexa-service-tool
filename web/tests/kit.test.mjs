import { test } from "node:test";
import assert from "node:assert/strict";
import { sq } from "../src/kit.js";

test("sq membungkus dengan kutip tunggal dan meng-escape kutip di dalamnya", () => {
  assert.equal(sq("abc"), "'abc'");
  assert.equal(sq("a'b"), "'a'\\''b'");
});

test("sq menetralkan karakter shell berbahaya", () => {
  const out = sq("x; rm -rf /sdcard $(id) `id`");
  assert.ok(out.startsWith("'") && out.endsWith("'"));
  assert.ok(!out.slice(1, -1).includes("'"));
});
