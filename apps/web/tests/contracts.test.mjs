import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("shared demo flow exposes stable project and task fields", async () => {
  const path = new URL("../../../contracts/examples/demo-flow.json", import.meta.url);
  const payload = JSON.parse(await readFile(path, "utf8"));

  assert.equal(payload.project.id, "demo-project-001");
  assert.equal(payload.task.status, "WAITING_USER");
  assert.ok(Array.isArray(payload.result.items));
});
