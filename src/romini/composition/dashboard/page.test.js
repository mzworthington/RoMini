import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { JSDOM, VirtualConsole } from "jsdom";

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
  const virtualConsole = new VirtualConsole();
  const dom = new JSDOM(`<!DOCTYPE html><html><head><title>RoMini</title></head><body>${html}${chrome}</body></html>`, {
    url,
    runScripts: "dangerously",
    pretendToBeVisual: true,
    virtualConsole,
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
  window.scrollTo = () => {};
  window.HTMLElement.prototype.scrollIntoView = () => {};
  const time = clock(window);
  const tag = window.document.createElement("script");
  // jsdom's location.assign cannot be replaced, so record the URL beside the real call.
  tag.textContent = script.replaceAll(
    /location\.assign\(([^)]+)\)/g,
    "(window.__assigned.push(String($1)), location.assign($1))",
  );
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

test("modified, external, download, and same-page clicks stay with the browser", () => {
  const page = boot(`
    <div class="shell">
      <a id="same" href="/">Here</a>
      <a id="away" href="https://example.com/docs">Away</a>
      <a id="file" href="/library/track.wav" download>Download</a>
      <a id="tab" href="/settings" target="_blank">Settings</a>
      <a id="meta" href="/figures">Figures</a>
    </div>
  `);
  const { window } = page;
  const click = (id, extra = {}) => {
    const event = new window.MouseEvent("click", { bubbles: true, cancelable: true, button: 0, ...extra });
    window.document.getElementById(id).dispatchEvent(event);
    return event.defaultPrevented;
  };

  assert.equal(click("same"), false);
  assert.equal(click("away"), false);
  assert.equal(click("file"), false);
  assert.equal(click("tab"), false);
  assert.equal(click("meta", { metaKey: true }), false);
  assert.deepEqual(page.fetches, []);
});

test("a notice on the next page becomes a toast that can be dismissed", async () => {
  const page = boot(`<div class="shell"><a href="/library">Library</a></div>`);
  page.respond(async () => ({
    text: async () =>
      `<!DOCTYPE html><html><body><div class="shell"><p>Done</p></div><div data-toast><p class="toast-text">Saved the story</p></div></body></html>`,
    url: "http://romini.local/library?notice=Saved",
  }));
  page.window.document.querySelector("a").dispatchEvent(
    new page.window.MouseEvent("click", { bubbles: true, cancelable: true, button: 0 }),
  );
  await new Promise((resolve) => setImmediate(resolve));

  const toast = page.window.document.querySelector("[data-toast-stack] [data-toast]");
  assert.equal(toast.querySelector(".toast-text").textContent, "Saved the story");

  toast.querySelector("[data-toast-close]").dispatchEvent(
    new page.window.MouseEvent("click", { bubbles: true, cancelable: true, button: 0 }),
  );
  assert.equal(toast.classList.contains("is-leaving"), true);
  await page.time.tick(200);
  assert.equal(page.window.document.querySelector("[data-toast-stack] [data-toast]"), null);
});

test("a polling page refreshes until the form is dirty or polling stops", async () => {
  const page = boot(`<div class="shell" data-poll><input name="title" value="Frog"><p id="now">1</p></div>`);
  page.respond(async () => ({
    text: async () =>
      `<!DOCTYPE html><html><body><div class="shell" data-poll><input name="title" value="Frog"><p id="now">2</p></div></body></html>`,
    url: "http://romini.local/",
  }));

  await page.time.tick(2000);

  assert.equal(page.fetches.length, 1);
  assert.equal(page.window.document.getElementById("now").textContent, "2");
  const input = page.window.document.querySelector("input");
  input.value = "Changed";
  await page.time.tick(2000);
  assert.equal(page.fetches.length, 1);

  input.value = input.defaultValue;
  page.respond(async () => ({
    text: async () => `<!DOCTYPE html><html><body><div class="shell"><p id="now">3</p></div></body></html>`,
    url: "http://romini.local/library",
  }));
  await page.time.tick(2000);
  assert.equal(page.window.document.getElementById("now").textContent, "3");
  assert.equal(page.fetches.length, 2);
  await page.time.tick(2000);
  assert.equal(page.fetches.length, 2);
});

test("a post form sends its fields and swaps in the response", async () => {
  const page = boot(`
    <div class="shell">
      <form method="post" action="/library" data-busy="Saving">
        <input name="title" value="Frog">
        <button type="submit">Save</button>
        <p role="status" hidden></p>
      </form>
    </div>
  `);
  page.respond(async () => ({
    text: async () => pageHtml("<p>Stored</p>", "Library"),
    url: "http://romini.local/library",
  }));
  const form = page.window.document.querySelector("form");
  const button = form.querySelector("button");
  const submit = new page.window.SubmitEvent("submit", { bubbles: true, cancelable: true, submitter: button });

  form.dispatchEvent(submit);
  await new Promise((resolve) => setImmediate(resolve));

  assert.equal(submit.defaultPrevented, true);
  assert.equal(page.fetches[0].url, "http://romini.local/library");
  assert.equal(page.fetches[0].init.method, "POST");
  assert.equal(page.fetches[0].init.body.get("title"), "Frog");
  assert.equal(page.window.document.querySelector(".shell p").textContent, "Stored");
});

test("a failed visit falls back to a full page load", async () => {
  const page = boot(`<div class="shell"><a href="/library">Library</a></div>`);
  page.respond(() => Promise.reject(new Error("offline")));
  page.window.document.querySelector("a").dispatchEvent(
    new page.window.MouseEvent("click", { bubbles: true, cancelable: true, button: 0 }),
  );
  await new Promise((resolve) => setImmediate(resolve));

  assert.deepEqual(page.assigned, ["http://romini.local/library"]);
});

test("an open assign menu closes only when the click lands outside it", () => {
  const page = boot(`
    <div class="shell">
      <details class="row-assign" open>
        <summary>Edit</summary>
        <form><input name="title" value="Frog"></form>
      </details>
      <button type="button" id="away">Away</button>
    </div>
  `);
  const { window } = page;
  const details = window.document.querySelector("details");
  const click = (el) => {
    el.dispatchEvent(new window.MouseEvent("click", { bubbles: true, cancelable: true, button: 0 }));
  };

  click(details.querySelector("input"));
  assert.equal(details.open, true);

  click(window.document.getElementById("away"));
  assert.equal(details.open, false);
});

test("a dirty form asks before a link leaves the page", async () => {
  const page = boot(`<div class="shell"><input name="title" value="Frog"><a href="/library">Library</a></div>`);
  const asked = [];
  page.window.confirm = (message) => {
    asked.push(message);
    return false;
  };
  page.window.document.querySelector("input").value = "Toad";
  page.window.document.querySelector("a").dispatchEvent(
    new page.window.MouseEvent("click", { bubbles: true, cancelable: true, button: 0 }),
  );
  await new Promise((resolve) => setImmediate(resolve));

  assert.equal(asked.length, 1);
  assert.deepEqual(page.fetches, []);
  assert.equal(page.window.location.pathname, "/");
});

test("a select asks only after its saved choice changes", async () => {
  const saved = `
    <div class="shell">
      <select name="play_mode">
        <option value="presence" selected>Presence</option>
        <option value="tap">Tap</option>
      </select>
      <a href="/library">Library</a>
    </div>`;

  async function leave(change, html = saved) {
    const page = boot(html);
    const asked = [];
    page.window.confirm = (message) => {
      asked.push(message);
      return false;
    };
    if (change) change(page.window);
    page.window.document.querySelector("a").dispatchEvent(
      new page.window.MouseEvent("click", { bubbles: true, cancelable: true, button: 0 }),
    );
    await new Promise((resolve) => setImmediate(resolve));
    return { asked: asked.length, fetches: page.fetches.length };
  }

  const clean = await leave();
  assert.equal(clean.asked, 0);
  assert.equal(clean.fetches, 1);

  const edited = await leave((window) => {
    window.document.querySelector("select").value = "tap";
  });
  assert.equal(edited.asked, 1);
  assert.equal(edited.fetches, 0);

  const preview = `
    <div class="shell">
      <select id="preview">
        <option value="/a">A</option>
        <option value="/b">B</option>
      </select>
      <a href="/library">Library</a>
    </div>`;
  const untouched = await leave(null, preview);
  assert.equal(untouched.asked, 0);
  assert.equal(untouched.fetches, 1);
  const picked = await leave((window) => {
    window.document.querySelector("select").value = "/b";
  }, preview);
  assert.equal(picked.asked, 1);
  assert.equal(picked.fetches, 0);
});

test("a focused field that still matches its saved value does not ask before leaving", async () => {
  const page = boot(`<div class="shell"><input name="title" value="Frog"><a href="/library">Library</a></div>`);
  const asked = [];
  page.window.confirm = (message) => {
    asked.push(message);
    return false;
  };
  page.window.document.querySelector("input").focus();
  page.window.document.querySelector("a").dispatchEvent(
    new page.window.MouseEvent("click", { bubbles: true, cancelable: true, button: 0 }),
  );
  await new Promise((resolve) => setImmediate(resolve));

  assert.equal(asked.length, 0);
  assert.equal(page.fetches.length, 1);
});
