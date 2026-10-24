import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const wrangler = JSON.parse(
  readFileSync(new URL("../wrangler.jsonc", import.meta.url), "utf8").replace(/^\s*\/\/.*$/gm, ""),
);

const html = readFileSync(new URL("../public/index.html", import.meta.url), "utf8");

const BLOG = "https://mzworthington.co.uk/open-source/building-a-story-box-for-romy";
const DEMO = "https://demo.romini.party";

test("the public page shows a circular romini, find out more, and a flagged demo", () => {
  assert.match(html, /<img[^>]*src="\/romini\.jpg"[^>]*alt="RoMini"/);
  assert.match(html, /border-radius:\s*50%/);
  assert.match(html, new RegExp(`href="${BLOG}"[^>]*>\\s*find out more\\s*<`));
  assert.match(html, new RegExp(`href="${DEMO}"[^>]*>\\s*demo dashboard\\s*<`));
  assert.match(html, /class="flag"[^>]*>\s*coming soon\s*</);
});

test("cloudflare publishes the static page and not the demo container", () => {
  assert.equal(wrangler.assets.directory, "./public");
  assert.equal(wrangler.main, undefined);
  assert.equal(wrangler.containers, undefined);
  assert.deepEqual(
    wrangler.routes.map((route) => route.pattern),
    ["romini.party", "www.romini.party"],
  );
});
