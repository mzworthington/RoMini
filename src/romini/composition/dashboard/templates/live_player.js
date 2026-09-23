(function () {
  var deck = document.querySelector(".studio");
  if (!deck) return;
  if (!window.__rominiDeck) window.__rominiDeck = { scrubbing: false };
  var state = window.__rominiDeck;
  state.deck = deck;
  if (state.timer) {
    window.clearInterval(state.timer);
    state.timer = 0;
  }
  if (!state.bound) {
    state.bound = true;
    document.addEventListener("pointerdown", function (event) {
      var target = event.target;
      if (target && target.closest && target.closest(".waveform input")) state.scrubbing = true;
    });
    document.addEventListener("pointerup", function () {
      state.scrubbing = false;
    });
    document.addEventListener("pointercancel", function () {
      state.scrubbing = false;
    });
    document.addEventListener(
      "submit",
      function (event) {
        var form = event.target;
        if (!form || !form.classList || !form.classList.contains("scrub-form")) return;
        event.preventDefault();
        event.stopPropagation();
      },
      true
    );
    document.addEventListener("change", function (event) {
      var input = event.target;
      if (!input || !input.closest || !input.closest(".scrub-form")) return;
      var form = input.form;
      if (!form) return;
      fetch("/play/seek", { method: "POST", body: new FormData(form) });
    });
  }
  state.timer = window.setInterval(function () {
    if (state.scrubbing || !state.deck || !state.deck.parentNode) return;
    fetch("/now-playing")
      .then(function (response) {
        return response.text();
      })
      .then(function (html) {
        var holder = document.createElement("template");
        holder.innerHTML = html.trim();
        var next = holder.content.querySelector(".studio");
        if (!next || !state.deck || !state.deck.parentNode) return;
        state.deck.parentNode.replaceChild(next, state.deck);
        state.deck = next;
      });
  }, 2000);
})();
