import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { JSDOM } from "jsdom";

const script = readFileSync(
  join(dirname(fileURLToPath(import.meta.url)), "templates", "live_player.js"),
  "utf8",
);

function clock(window) {
  let t = 0;
  let seq = 1;
  const items = new Map();
  window.setTimeout = (fn, ms = 0) => {
    const id = seq++;
    items.set(id, { fn, at: t + ms, every: 0 });
    return id;
  };
  window.setInterval = (fn, ms = 0) => {
    const id = seq++;
    items.set(id, { fn, at: t + ms, every: ms });
    return id;
  };
  window.clearTimeout = (id) => items.delete(id);
  window.clearInterval = (id) => items.delete(id);
  return {
    async tick(ms) {
      t += ms;
      let progressed = true;
      while (progressed) {
        progressed = false;
        const due = [...items.entries()]
          .filter(([, item]) => item.at <= t)
          .sort((a, b) => a[1].at - b[1].at);
        for (const [id, item] of due) {
          if (!items.has(id) || item.at > t) continue;
          progressed = true;
          if (item.every) item.at += item.every;
          else items.delete(id);
          await item.fn();
          await new Promise((resolve) => setImmediate(resolve));
        }
      }
    },
  };
}

function boot(html) {
  const dom = new JSDOM(`<!DOCTYPE html><html><body>${html}</body></html>`, {
    url: "http://romini.local/",
    runScripts: "dangerously",
  });
  const { window } = dom;
  const fetches = [];
  let handler = async () => ({ text: async () => "", url: "http://romini.local/now-playing" });
  window.fetch = (input, init = {}) => {
    fetches.push({ url: String(input), init });
    return Promise.resolve(handler(input, init));
  };
  const time = clock(window);
  const tag = window.document.createElement("script");
  tag.textContent = script;
  window.document.body.appendChild(tag);
  return {
    window,
    fetches,
    time,
    respond(fn) {
      handler = fn;
    },
  };
}

test("the deck refreshes from now-playing without reloading the page", async () => {
  const page = boot(`<div class="studio" id="old">Playing</div>`);
  page.respond(async () => ({
    text: async () => `<div class="studio" id="next">Next</div>`,
    url: "http://romini.local/now-playing",
  }));

  await page.time.tick(2000);

  assert.deepEqual(
    page.fetches.map((call) => call.url),
    ["/now-playing"],
  );
  assert.equal(page.window.document.querySelector(".studio").id, "next");
  assert.equal(page.window.document.getElementById("old"), null);
});
