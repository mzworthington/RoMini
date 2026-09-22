(function () {
  var deck = document.querySelector(".deck");
  if (!deck) return;
  setInterval(function () {
    fetch("/now-playing")
      .then(function (response) {
        return response.text();
      })
      .then(function (html) {
        var holder = document.createElement("template");
        holder.innerHTML = html.trim();
        var next = holder.content.querySelector(".deck");
        if (!next || !deck.parentNode) return;
        deck.parentNode.replaceChild(next, deck);
        deck = next;
      });
  }, 2000);
})();
