import assert from "node:assert/strict";
import test from "node:test";

import { STORY_ARTICLE, respondParty } from "./route.js";

test("apex fetch redirects without starting the demo", async () => {
  let started = false;
  const response = await respondParty(new Request("https://romini.party/"), () => {
    started = true;
    return new Response("demo");
  });
  assert.equal(response.status, 302);
  assert.equal(response.headers.get("location"), STORY_ARTICLE);
  assert.equal(started, false);
});
