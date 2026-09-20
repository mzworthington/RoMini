(function () {
  function busy() {
    var el = document.activeElement;
    if (el && /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName)) return true;
    var fields = document.querySelectorAll("input, textarea, select");
    for (var i = 0; i < fields.length; i++) {
      var field = fields[i];
      if (field.type === "file") {
        if (field.files && field.files.length) return true;
        continue;
      }
      if (field.value !== field.defaultValue) return true;
    }
    return false;
  }
  setInterval(function () {
    if (busy()) return;
    location.reload();
  }, 2000);
})();
