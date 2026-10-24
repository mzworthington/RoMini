import assert from "node:assert/strict";
import test from "node:test";

import { STORY_ARTICLE, routeParty } from "./route.js";

test("apex homepage redirects to the story-box article", () => {
  const decision = routeParty(new URL("https://romini.party/"));
  assert.deepEqual(decision, { kind: "redirect", location: STORY_ARTICLE });
});

test("the demo host is the companion", () => {
  assert.equal(routeParty(new URL("https://demo.romini.party/settings")).kind, "demo");
});

test("other apex paths go to the demo host", () => {
  const decision = routeParty(new URL("https://www.romini.party/library?q=frog"));
  assert.equal(decision.kind, "redirect");
  assert.equal(decision.location, "https://demo.romini.party/library?q=frog");
});
