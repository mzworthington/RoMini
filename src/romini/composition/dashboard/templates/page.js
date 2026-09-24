(function () {
  var pollTimer = 0;
  var navigating = false;

  function dismiss(toast) {
    if (!toast || toast.classList.contains("is-leaving")) return;
    window.clearTimeout(toast._hide);
    toast.classList.add("is-leaving");
    window.setTimeout(function () {
      toast.remove();
    }, 200);
  }

  function arm(toast) {
    toast._hide = window.setTimeout(function () {
      dismiss(toast);
    }, 4200);
  }

  function show(message) {
    var template = document.querySelector("[data-toast-template]");
    var stack = document.querySelector("[data-toast-stack]");
    if (!message || !template || !stack || !template.content.firstElementChild) return;
    var toast = template.content.firstElementChild.cloneNode(true);
    var text = toast.querySelector(".toast-text");
    if (text) text.textContent = message;
    arm(toast);
    stack.appendChild(toast);
  }

  function cleanUrl(url) {
    var next = new URL(url, location.origin);
    next.searchParams.delete("notice");
    next.searchParams.delete("detail");
    return next.pathname + next.search + next.hash;
  }

  function runScripts(root) {
    var scripts = Array.prototype.slice.call(root.querySelectorAll("script"));
    scripts.forEach(function (old) {
      var script = document.createElement("script");
      script.textContent = old.textContent;
      old.replaceWith(script);
    });
  }

  function landedUrl(requested, responseUrl) {
    var asked = new URL(requested, location.origin);
    var landed = new URL(responseUrl || requested, location.origin);
    if (!landed.hash) landed.hash = asked.hash;
    return landed.href;
  }

  function apply(html, finalUrl, push) {
    var doc = new DOMParser().parseFromString(html, "text/html");
    var next = doc.querySelector(".shell");
    var shell = document.querySelector(".shell");
    if (!next || !shell) {
      location.assign(finalUrl);
      return;
    }
    var incoming = doc.querySelector("[data-toast] .toast-text");
    var message = incoming ? incoming.textContent.trim() : "";
    var landed = new URL(finalUrl, location.origin);
    var previous = new URL(location.href);
    var samePath = landed.pathname === previous.pathname;
    var y = window.scrollY;
    shell.replaceWith(next);
    runScripts(next);
    document.title = doc.title;
    var clean = cleanUrl(landed.href);
    if (push && !samePath) history.pushState({ spa: 1 }, "", clean);
    else history.replaceState({ spa: 1 }, "", clean);
    if (message) show(message);
    var moved = push || landed.pathname !== previous.pathname || landed.hash !== previous.hash;
    var target = null;
    if (moved && landed.hash.length > 1) {
      target = document.getElementById(decodeURIComponent(landed.hash.slice(1)));
    }
    if (target && target.scrollIntoView) target.scrollIntoView();
    else if (push && !samePath) window.scrollTo(0, 0);
    else window.scrollTo(0, y);
    syncPoll();
  }

  function visit(url, push) {
    if (navigating) return Promise.resolve();
    navigating = true;
    return fetch(url, { credentials: "same-origin" })
      .then(function (response) {
        return response.text().then(function (html) {
          apply(html, landedUrl(url, response.url), push);
        });
      })
      .catch(function () {
        location.assign(url);
      })
      .then(function () {
        navigating = false;
      });
  }

  function editing() {
    var el = document.activeElement;
    if (el && /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName)) return true;
    var fields = document.querySelectorAll("input, textarea, select");
    for (var i = 0; i < fields.length; i++) {
      var field = fields[i];
      if (field.type === "file") {
        if (field.files && field.files.length) return true;
        continue;
      }
      if (field.type === "checkbox" || field.type === "radio") {
        if (field.checked !== field.defaultChecked) return true;
        continue;
      }
      if (field.value !== field.defaultValue) return true;
    }
    return false;
  }

  function syncPoll() {
    var polling = document.querySelector("[data-poll]");
    if (polling && !pollTimer) {
      pollTimer = window.setInterval(function () {
        if (!document.querySelector("[data-poll]") || editing() || navigating) return;
        visit(location.href, false);
      }, 2000);
    }
    if (!polling && pollTimer) {
      window.clearInterval(pollTimer);
      pollTimer = 0;
    }
  }

  document.addEventListener("click", function (event) {
    var toast = event.target.closest("[data-toast]");
    if (toast && event.target.closest("[data-toast-close]")) {
      event.preventDefault();
      dismiss(toast);
      return;
    }
    if (
      event.defaultPrevented ||
      event.button !== 0 ||
      event.metaKey ||
      event.ctrlKey ||
      event.shiftKey ||
      event.altKey
    ) {
      return;
    }
    var link = event.target.closest("a[href]");
    if (!link || link.hasAttribute("download")) return;
    if (link.target && link.target !== "_self") return;
    var url = new URL(link.href, location.href);
    if (url.origin !== location.origin) return;
    if (url.pathname === location.pathname && url.search === location.search) return;
    event.preventDefault();
    visit(link.href, true);
  });

  document.addEventListener(
    "submit",
    function (event) {
      var form = event.target;
      if (!form || form.tagName !== "FORM") return;
      if (form.classList.contains("scrub-form") || form.hasAttribute("data-inject")) return;
      if (!form.getAttribute("action")) return;
      event.preventDefault();
      event.stopPropagation();
      var submitter = event.submitter || null;
      var method = (form.getAttribute("method") || "get").toUpperCase();
      var target = new URL(form.action, location.href);
      var status = form.querySelector("[role='status']");
      if (method === "GET") {
        var params = new URLSearchParams(submitter ? new FormData(form, submitter) : new FormData(form));
        target.search = params.toString();
        visit(target.pathname + target.search, true);
        return;
      }
      if (status) {
        status.hidden = false;
        status.textContent = form.getAttribute("data-busy") || "Working…";
      }
      if (submitter) submitter.disabled = true;
      var body = submitter ? new FormData(form, submitter) : new FormData(form);
      navigating = true;
      fetch(target.href, { method: "POST", body: body, credentials: "same-origin" })
        .then(function (response) {
          return response.text().then(function (html) {
            apply(html, response.url || target.href, true);
          });
        })
        .catch(function () {
          if (submitter) submitter.disabled = false;
          if (status) status.textContent = "Could not reach the box";
        })
        .then(function () {
          navigating = false;
        });
    },
    true
  );

  window.addEventListener("popstate", function () {
    visit(location.href, false);
  });

  var open = document.querySelectorAll("[data-toast-stack] > [data-toast]");
  for (var i = 0; i < open.length; i++) arm(open[i]);
  history.replaceState({ spa: 1 }, "", cleanUrl(location.href));
  syncPoll();
  window.rominiToast = show;
})();
