(function () {
  var submitting = false;
  document.addEventListener("submit", function (event) {
    if (submitting) {
      event.preventDefault();
      return;
    }
    submitting = true;
    var form = event.target;
    var status = form.querySelector("[role='status']");
    var message = form.getAttribute("data-busy") || "Working…";
    if (status) {
      status.hidden = false;
      status.textContent = message;
    }
    form.setAttribute("aria-busy", "true");
    var buttons = document.querySelectorAll("button");
    for (var j = 0; j < buttons.length; j++) {
      buttons[j].disabled = true;
    }
  });
})();
