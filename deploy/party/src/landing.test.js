import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const wrangler = JSON.parse(
  readFileSync(new URL("../wrangler.jsonc", import.meta.url), "utf8").replace(/^\s*\/\/.*$/gm, ""),
);

const html = readFileSync(new URL("../public/index.html", import.meta.url), "utf8");

const BLOG = "https://mzworthington.co.uk/open-source/building-a-story-box-for-romy";
const DEMO = "https://demo.romini.party";

test("the public page names RoMini, shows the box, and links the demo dashboard", () => {
  assert.match(html, /<h1>\s*RoMini\s*<\/h1>/);
  assert.match(html, /screen-free story box/);
  assert.match(html, /<img[^>]*src="\/romini\.jpg"[^>]*alt="Wooden RoMini story box"/);
  assert.match(html, /border-radius:\s*50%/);
  assert.match(html, new RegExp(`href="${BLOG}"[^>]*>\\s*find out more\\s*<`));
  assert.match(html, new RegExp(`href="${DEMO}"[^>]*>\\s*demo dashboard\\s*<`));
  assert.doesNotMatch(html, /<button[^>]*disabled[^>]*>\s*demo dashboard\s*<\/button>/);
  assert.doesNotMatch(html, /coming soon/);
  assert.match(html, /rel="icon"[^>]*href="\/favicon\.svg"/);
  assert.match(html, /property="og:title"[^>]*content="RoMini"/);
  assert.match(html, /property="og:description"[^>]*content="[^"]*screen-free story box[^"]*"/);
  assert.match(html, /property="og:image"[^>]*content="https:\/\/romini\.party\/romini\.jpg"/);
  assert.match(html, /name="description"[^>]*content="[^"]*screen-free story box[^"]*"/);
});

test("the landing page carries the dashboard footer", () => {
  assert.match(html, /<footer class="site-foot">/);
  assert.match(html, /Made for Romy, with ❤️ by\s*<a href="https:\/\/mzworthington\.co\.uk\/" target="_blank"[^>]*>Matthew Z Worthington<\/a>/);
  assert.match(html, /Screen-free domestic audio for growing minds\. Local network hosted\./);
  assert.match(html, /\.site-foot\s*\{[^}]*display:\s*flex/);
  assert.match(html, /\.site-foot\s*\{[^}]*justify-content:\s*space-between/);
  assert.match(html, /\.site-foot a\s*\{[^}]*text-decoration:\s*underline/);
  assert.match(html, /\.site-foot a\s*\{[^}]*border:\s*0/);
});

test("the landing page fits the visible mobile screen", () => {
  assert.match(html, /min-height:\s*100svh/);
  assert.match(html, /width:\s*min\(22rem,\s*78vw,\s*calc\(100svh\s*-\s*13rem\)\)/);
  assert.match(html, /height:\s*min\(22rem,\s*78vw,\s*calc\(100svh\s*-\s*13rem\)\)/);
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
