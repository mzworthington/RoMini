(function () {
  var audio = document.querySelector("audio.deck-preview");
  var button = document.querySelector("[data-deck-toggle]");
  if (!audio || !button) return;
  var wave = document.querySelector("[data-deck-wave]");
  var scrub = document.querySelector("[data-deck-scrub]");
  var restart = document.querySelector("[data-deck-restart]");
  var place = document.querySelector("[data-deck-place]");
  var length = document.querySelector("[data-deck-length]");
  var play = '<path d="M8 5v14l11-7z"/>';
  var pause = '<path d="M6 5h4v14H6z"/><path d="M14 5h4v14h-4z"/>';
  var dragging = false;

  function clock(seconds) {
    if (!isFinite(seconds) || seconds < 0) return "0:00";
    var whole = Math.floor(seconds);
    var minutes = Math.floor(whole / 60);
    var rest = whole % 60;
    return minutes + ":" + (rest < 10 ? "0" : "") + rest;
  }

  function label(playing) {
    var glyph = button.querySelector(".play-glyph");
    var text = button.querySelector("span");
    if (glyph) glyph.innerHTML = playing ? pause : play;
    if (text) text.textContent = playing ? "Pause" : "Play";
    button.classList.toggle("is-pause", playing);
  }

  function paint() {
    var duration = audio.duration;
    if (!duration) return;
    var pct = (audio.currentTime / duration) * 100;
    if (wave) wave.style.setProperty("--play", pct + "%");
    if (scrub && !dragging) scrub.value = String(Math.round(pct * 10));
    if (place) place.textContent = clock(audio.currentTime);
    if (length) length.textContent = clock(duration);
  }

  function start() {
    var pending = audio.play();
    if (pending && pending.catch) pending.catch(function () {});
  }

  button.addEventListener("click", function () {
    if (audio.paused) start();
    else audio.pause();
  });
  audio.addEventListener("play", function () { label(true); });
  audio.addEventListener("pause", function () { label(false); });
  audio.addEventListener("ended", function () {
    label(false);
    if (wave) wave.style.setProperty("--play", "0%");
    if (scrub) scrub.value = "0";
    if (place) place.textContent = "0:00";
  });
  audio.addEventListener("timeupdate", paint);
  audio.addEventListener("loadedmetadata", paint);
  if (scrub) {
    scrub.addEventListener("input", function () {
      dragging = true;
      var pct = Number(scrub.value) / 10;
      if (wave) wave.style.setProperty("--play", pct + "%");
      if (audio.duration) audio.currentTime = (pct / 100) * audio.duration;
      if (place) place.textContent = clock(audio.currentTime);
    });
    scrub.addEventListener("change", function () { dragging = false; });
  }
  if (restart) {
    restart.addEventListener("click", function () {
      audio.currentTime = 0;
      paint();
      start();
    });
  }
})();
