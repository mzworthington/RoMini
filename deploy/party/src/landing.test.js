import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const wrangler = JSON.parse(
  readFileSync(new URL("../wrangler.jsonc", import.meta.url), "utf8").replace(/^\s*\/\/.*$/gm, ""),
);

const html = readFileSync(new URL("../public/index.html", import.meta.url), "utf8");

const BLOG = "https://mzworthington.co.uk/open-source/building-a-story-box-for-romy";
const DEMO = "https://demo.romini.party";

test("the public page names RoMini, shows the box, and keeps the demo closed", () => {
  assert.match(html, /<h1>\s*RoMini\s*<\/h1>/);
  assert.match(html, /screen-free story box/);
  assert.match(html, /<img[^>]*src="\/romini\.jpg"[^>]*alt="Wooden RoMini story box"/);
  assert.match(html, /border-radius:\s*50%/);
  assert.match(html, new RegExp(`href="${BLOG}"[^>]*>\\s*find out more\\s*<`));
  assert.match(html, /<button[^>]*disabled[^>]*>\s*demo dashboard\s*<\/button>/);
  assert.doesNotMatch(html, new RegExp(`href="${DEMO}"`));
  assert.match(html, /class="flag"[^>]*>\s*coming soon\s*</);
  assert.match(html, /rel="icon"[^>]*href="\/favicon\.svg"/);
  assert.match(html, /property="og:title"[^>]*content="RoMini"/);
  assert.match(html, /property="og:description"[^>]*content="[^"]*screen-free story box[^"]*"/);
  assert.match(html, /property="og:image"[^>]*content="https:\/\/romini\.party\/romini\.jpg"/);
  assert.match(html, /name="description"[^>]*content="[^"]*screen-free story box[^"]*"/);
});

test("the landing page fits the visible mobile screen", () => {
  assert.match(html, /min-height:\s*100svh/);
  assert.match(html, /width:\s*min\(22rem,\s*78vw,\s*calc\(100svh\s*-\s*9rem\)\)/);
  assert.match(html, /height:\s*min\(22rem,\s*78vw,\s*calc\(100svh\s*-\s*9rem\)\)/);
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
