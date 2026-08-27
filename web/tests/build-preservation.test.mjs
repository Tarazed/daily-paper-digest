import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

test("build script preserves source documentation", () => {
  const source = fs.readFileSync(
    new URL("../scripts/build.mjs", import.meta.url),
    "utf8"
  );

  assert.equal(source.includes("fs.rmSync(docsDir, { recursive: true"), false);
  assert.equal(source.includes("generatedPaths"), true);
});
