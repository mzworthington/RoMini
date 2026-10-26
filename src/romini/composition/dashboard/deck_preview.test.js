import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { JSDOM } from "jsdom";

const script = readFileSync(
  join(dirname(fileURLToPath(import.meta.url)), "templates", "deck_preview.js"),
  "utf8",
);

function boot() {
  const dom = new JSDOM(
    `<!DOCTYPE html><body>
      <div class="waveform" data-deck-wave style="--play: 0%">
        <input type="range" min="0" max="1000" value="0" data-deck-scrub>
      </div>
      <p data-deck-times><span data-deck-place>0:00</span><span data-deck-length>0:00</span></p>
      <button type="button" class="seek restart" data-deck-restart>Restart</button>
      <button type="button" class="play-main" data-deck-toggle>
        <svg class="play-glyph"></svg><span>Play</span>
      </button>
      <audio class="deck-preview"></audio>
    </body>`,
    { url: "http://romini.local/", runScripts: "dangerously" },
  );
  const { window } = dom;
  const audio = window.document.querySelector("audio");
  let paused = true;
  Object.defineProperty(audio, "duration", { configurable: true, get: () => 125 });
  Object.defineProperty(audio, "paused", { configurable: true, get: () => paused });
  audio.play = () => {
    paused = false;
    audio.dispatchEvent(new window.Event("play"));
    return Promise.resolve();
  };
  audio.pause = () => {
    paused = true;
    audio.dispatchEvent(new window.Event("pause"));
  };
  const tag = window.document.createElement("script");
  tag.textContent = script;
  window.document.body.appendChild(tag);
  return { window, audio };
}

test("the play button drives the preview without replacing it", () => {
  const page = boot();
  const button = page.window.document.querySelector("[data-deck-toggle]");

  button.click();

  assert.equal(button.querySelector("span").textContent, "Pause");
  assert.equal(button.classList.contains("is-pause"), true);

  button.click();

  assert.equal(button.querySelector("span").textContent, "Play");
  assert.equal(button.classList.contains("is-pause"), false);
});

test("the waveform follows playback and a scrub moves the preview", () => {
  const page = boot();
  const { audio, window } = page;
  const wave = window.document.querySelector("[data-deck-wave]");
  const scrub = window.document.querySelector("[data-deck-scrub]");

  audio.currentTime = 62.5;
  audio.dispatchEvent(new window.Event("timeupdate"));

  assert.equal(wave.style.getPropertyValue("--play"), "50%");
  assert.equal(scrub.value, "500");
  assert.equal(window.document.querySelector("[data-deck-place]").textContent, "1:02");
  assert.equal(window.document.querySelector("[data-deck-length]").textContent, "2:05");

  scrub.value = "250";
  scrub.dispatchEvent(new window.Event("input", { bubbles: true }));

  assert.equal(audio.currentTime, 31.25);
  assert.equal(wave.style.getPropertyValue("--play"), "25%");
});

test("restart returns the preview to the beginning and plays it", () => {
  const page = boot();
  page.audio.currentTime = 40;
  page.window.document.querySelector("[data-deck-restart]").click();

  assert.equal(page.audio.currentTime, 0);
  assert.equal(page.window.document.querySelector("[data-deck-toggle] span").textContent, "Pause");
});
