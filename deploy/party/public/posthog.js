(function () {
  var arrayUrl = "https://eu-assets.i.posthog.com/static/array.js";

  function init(config) {
    if (!window.posthog || typeof window.posthog.init !== "function") return;
    window.posthog.init(config.apiKey, {
      api_host: config.apiHost,
      ui_host: "https://eu.posthog.com",
      defaults: "2026-05-30",
      capture_pageview: "history_change",
      cookieless_mode: "always",
      person_profiles: "never",
      disable_session_recording: true,
    });
  }

  function boot(config) {
    if (!config || config.enabled !== true || typeof config.apiKey !== "string" || config.apiKey === "") return;
    var existing = document.querySelector('script[src="' + arrayUrl + '"]');
    if (existing) {
      init(config);
      return;
    }
    var script = document.createElement("script");
    script.async = true;
    script.crossOrigin = "anonymous";
    script.src = arrayUrl;
    script.onload = function () {
      init(config);
    };
    document.head.appendChild(script);
  }

  fetch("/posthog-config.json")
    .then(function (response) {
      if (!response.ok) return null;
      return response.json();
    })
    .then(boot)
    .catch(function () {});
})();
