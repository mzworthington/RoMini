(function () {
  var deck = document.querySelector(".studio");
  if (!deck) return;
  var scrubbing = false;
  document.addEventListener("pointerdown", function (event) {
    var target = event.target;
    if (target && target.closest && target.closest(".waveform input")) scrubbing = true;
  });
  document.addEventListener("pointerup", function () {
    scrubbing = false;
  });
  document.addEventListener("pointercancel", function () {
    scrubbing = false;
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
  setInterval(function () {
    if (scrubbing) return;
    fetch("/now-playing")
      .then(function (response) {
        return response.text();
      })
      .then(function (html) {
        var holder = document.createElement("template");
        holder.innerHTML = html.trim();
        var next = holder.content.querySelector(".studio");
        if (!next || !deck.parentNode) return;
        deck.parentNode.replaceChild(next, deck);
        deck = next;
      });
  }, 2000);
})();
