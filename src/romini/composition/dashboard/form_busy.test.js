import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { JSDOM } from "jsdom";

const script = readFileSync(
  join(dirname(fileURLToPath(import.meta.url)), "templates", "form_busy.js"),
  "utf8",
);

function boot(html) {
  const dom = new JSDOM(`<!DOCTYPE html><html><body>${html}</body></html>`, {
    url: "http://romini.local/",
    runScripts: "dangerously",
  });
  const tag = dom.window.document.createElement("script");
  tag.textContent = script;
  dom.window.document.body.appendChild(tag);
  return dom.window;
}

test("a form submit shows its busy message and disables every button", () => {
  const window = boot(`
    <form data-busy="Saving the story">
      <p role="status" hidden></p>
      <button type="submit">Save</button>
    </form>
    <button type="button">Elsewhere</button>
  `);
  const form = window.document.querySelector("form");
  const status = form.querySelector("[role='status']");

  form.dispatchEvent(new window.Event("submit", { bubbles: true, cancelable: true }));

  assert.equal(status.hidden, false);
  assert.equal(status.textContent, "Saving the story");
  assert.equal(form.getAttribute("aria-busy"), "true");
  for (const button of window.document.querySelectorAll("button")) {
    assert.equal(button.disabled, true);
  }
});

test("a second submit is ignored while the first is still busy", () => {
  const window = boot(`
    <form>
      <p role="status" hidden></p>
      <button type="submit">Save</button>
    </form>
  `);
  const form = window.document.querySelector("form");
  form.dispatchEvent(new window.Event("submit", { bubbles: true, cancelable: true }));
  const again = new window.Event("submit", { bubbles: true, cancelable: true });

  form.dispatchEvent(again);

  assert.equal(again.defaultPrevented, true);
});
