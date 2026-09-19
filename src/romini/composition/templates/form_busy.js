(function () {
  var forms = document.querySelectorAll("form.form-busy");
  for (var i = 0; i < forms.length; i++) {
    forms[i].addEventListener("submit", function (event) {
      var form = event.currentTarget;
      var status = form.querySelector("[role='status']");
      var message = form.getAttribute("data-busy") || "Working…";
      if (status) {
        status.hidden = false;
        status.textContent = message;
      }
      form.setAttribute("aria-busy", "true");
      var buttons = form.querySelectorAll("button");
      for (var j = 0; j < buttons.length; j++) {
        buttons[j].disabled = true;
      }
    });
  }
})();
