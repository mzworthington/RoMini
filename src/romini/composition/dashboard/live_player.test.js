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

test("a paused deck waits before refreshing now-playing", async () => {
  const page = boot(`<div class="studio" id="old">Paused</div>`);
  page.respond(async () => ({
    text: async () => `<div class="studio" id="next">Next</div>`,
    url: "http://romini.local/now-playing",
  }));

  await page.time.tick(2000);
  assert.deepEqual(page.fetches, []);

  await page.time.tick(8000);
  assert.deepEqual(
    page.fetches.map((call) => call.url),
    ["/now-playing"],
  );
});

test("the deck refreshes from now-playing without reloading the page", async () => {
  const page = boot(`<div class="studio" id="old" data-playing="on">Playing</div>`);
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

test("dragging the scrubber holds the deck still", async () => {
  const page = boot(`
    <div class="studio">
      <form class="scrub-form"><div class="waveform"><input type="range" name="at" value="1"></div></form>
    </div>
  `);
  const input = page.window.document.querySelector(".waveform input");
  input.dispatchEvent(new page.window.Event("pointerdown", { bubbles: true }));

  await page.time.tick(2000);

  assert.deepEqual(page.fetches, []);
  assert.equal(page.window.document.querySelector(".studio").isConnected, true);
});

test("moving the scrubber seeks in place", () => {
  const page = boot(`
    <div class="studio">
      <form class="scrub-form" action="/play/seek" method="post">
        <div class="waveform"><input type="range" name="at" value="4"></div>
      </form>
    </div>
  `);
  const form = page.window.document.querySelector(".scrub-form");
  const submit = new page.window.Event("submit", { bubbles: true, cancelable: true });
  form.dispatchEvent(submit);
  const input = form.querySelector("input");
  input.value = "9";
  input.dispatchEvent(new page.window.Event("change", { bubbles: true }));

  assert.equal(submit.defaultPrevented, true);
  assert.equal(page.fetches.length, 1);
  assert.equal(page.fetches[0].url, "/play/seek");
  assert.equal(page.fetches[0].init.method, "POST");
  assert.equal(page.fetches[0].init.body.get("at"), "9");
});

test("dragging the volume cap holds the deck still", async () => {
  const page = boot(`
    <div class="studio">
      <form class="guard-volume"><input type="range" name="level" value="4"></form>
    </div>
  `);
  page.window.document
    .querySelector(".guard-volume input")
    .dispatchEvent(new page.window.Event("pointerdown", { bubbles: true }));

  await page.time.tick(2000);

  assert.deepEqual(page.fetches, []);
  assert.equal(page.window.document.querySelector(".studio").isConnected, true);
});
