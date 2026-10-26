DEFAULT_POSTHOG_HOST = "https://a.mzworthington.co.uk"
POSTHOG_SDK_DEFAULTS = "2026-05-30"
POSTHOG_UI_HOST = "https://eu.posthog.com"

PublicPostHogConfig = dict[str, object]


def resolve_public_posthog_config(token: str | None, host: str | None = None) -> PublicPostHogConfig:
    api_key = (token or "").strip()
    if api_key == "":
        return {"enabled": False}
    api_host = (host or "").strip() or DEFAULT_POSTHOG_HOST
    return {"enabled": True, "apiKey": api_key, "apiHost": api_host}
