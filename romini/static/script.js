(function () {
  "use strict";

  const heroInput = document.getElementById("hero");
  const themesEl = document.getElementById("themes");
  const generateBtn = document.getElementById("generate");
  const againBtn = document.getElementById("again");
  const storyEl = document.getElementById("story");
  const storyTitle = document.getElementById("story-title");
  const storyBody = document.getElementById("story-body");
  const storyEmoji = document.getElementById("story-emoji");

  let selectedTheme =
    themesEl.querySelector(".theme-chip.selected")?.dataset.theme || "forest";

  themesEl.addEventListener("click", function (event) {
    const chip = event.target.closest(".theme-chip");
    if (!chip) return;
    themesEl.querySelectorAll(".theme-chip").forEach(function (c) {
      c.classList.remove("selected");
      c.setAttribute("aria-checked", "false");
    });
    chip.classList.add("selected");
    chip.setAttribute("aria-checked", "true");
    selectedTheme = chip.dataset.theme;
  });

  async function tellStory() {
    generateBtn.classList.add("loading");
    generateBtn.disabled = true;

    try {
      const response = await fetch("/api/story", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          hero: heroInput.value.trim() || "Romy",
          theme: selectedTheme,
        }),
      });

      if (!response.ok) {
        throw new Error("Request failed: " + response.status);
      }

      const story = await response.json();
      renderStory(story);
    } catch (err) {
      storyTitle.textContent = "Oops! The magic fizzled.";
      storyBody.innerHTML =
        "<p>Something went wrong. Please try again in a moment. ✨</p>";
      storyEmoji.textContent = "😅";
      storyEl.hidden = false;
      againBtn.hidden = true;
      console.error(err);
    } finally {
      generateBtn.classList.remove("loading");
      generateBtn.disabled = false;
    }
  }

  function renderStory(story) {
    storyEmoji.textContent = story.emoji || "📖";
    storyTitle.textContent = story.title;
    storyBody.innerHTML = "";
    (story.paragraphs || []).forEach(function (para) {
      const p = document.createElement("p");
      p.textContent = para;
      storyBody.appendChild(p);
    });
    againBtn.hidden = false;
    storyEl.hidden = false;
    storyEl.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  generateBtn.addEventListener("click", tellStory);
  againBtn.addEventListener("click", tellStory);
  heroInput.addEventListener("keydown", function (event) {
    if (event.key === "Enter") tellStory();
  });
})();
