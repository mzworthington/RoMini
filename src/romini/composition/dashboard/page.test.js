import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { JSDOM } from "jsdom";

const script = readFileSync(join(dirname(fileURLToPath(import.meta.url)), "templates", "page.js"), "utf8");

const chrome = `
  <div data-toast-stack></div>
  <template data-toast-template>
    <div class="toast" data-toast>
      <p class="toast-text"></p>
      <button type="button" data-toast-close>Dismiss</button>
    </div>
  </template>
`;

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

function boot(html, url = "http://romini.local/") {
  const dom = new JSDOM(`<!DOCTYPE html><html><head><title>RoMini</title></head><body>${html}${chrome}</body></html>`, {
    url,
    runScripts: "dangerously",
    pretendToBeVisual: true,
  });
  const { window } = dom;
  const fetches = [];
  const assigned = [];
  let handler = async () => ({ text: async () => "", url });
  window.fetch = (input, init = {}) => {
    fetches.push({ url: String(input), init });
    return Promise.resolve(handler(input, init));
  };
  window.__assigned = assigned;
  window.eval(
    "Location.prototype.assign = function (next) { window.__assigned.push(String(next)); };",
  );
  const time = clock(window);
  const tag = window.document.createElement("script");
  tag.textContent = script;
  window.document.body.appendChild(tag);
  return {
    window,
    fetches,
    assigned,
    time,
    respond(fn) {
      handler = fn;
    },
  };
}

function pageHtml(body, title = "Library") {
  return `<!DOCTYPE html><html><head><title>${title}</title></head><body><div class="shell">${body}</div>${chrome}</body></html>`;
}

test("a same-origin link swaps the shell and leaves the notice off the address", async () => {
  const page = boot(`<div class="shell"><a href="/library?notice=Saved&detail=ok">Library</a></div>`);
  page.respond(async () => ({
    text: async () => pageHtml("<h2>Library</h2>", "Library · RoMini"),
    url: "http://romini.local/library?notice=Saved&detail=ok",
  }));
  const link = page.window.document.querySelector("a");
  const click = new page.window.MouseEvent("click", { bubbles: true, cancelable: true, button: 0 });

  link.dispatchEvent(click);
  await new Promise((resolve) => setImmediate(resolve));

  assert.equal(click.defaultPrevented, true);
  assert.equal(page.fetches[0].url, "http://romini.local/library?notice=Saved&detail=ok");
  assert.equal(page.window.document.title, "Library · RoMini");
  assert.equal(page.window.document.querySelector(".shell h2").textContent, "Library");
  assert.equal(page.window.location.pathname, "/library");
  assert.equal(page.window.location.search, "");
  assert.deepEqual(page.assigned, []);
});
