export const STORY_ARTICLE =
  "https://mzworthington.co.uk/open-source/building-a-story-box-for-romy";

const APEX_HOSTS = new Set(["romini.party", "www.romini.party"]);

/**
 * @param {URL} url
 * @returns {{ kind: "redirect", location: string } | { kind: "demo" } | { kind: "missing" }}
 */
export function routeParty(url) {
  const host = url.hostname.toLowerCase();
  if (APEX_HOSTS.has(host)) {
    if (url.pathname === "/" || url.pathname === "") {
      return { kind: "redirect", location: STORY_ARTICLE };
    }
    const demo = new URL(url.pathname + url.search, "https://demo.romini.party/");
    return { kind: "redirect", location: demo.toString() };
  }
  if (
    host === "demo.romini.party" ||
    host === "localhost" ||
    host === "127.0.0.1" ||
    host.endsWith(".workers.dev")
  ) {
    return { kind: "demo" };
  }
  return { kind: "missing" };
}

/**
 * @param {Request} request
 * @param {(request: Request) => Response | Promise<Response>} fetchDemo
 */
export function respondParty(request, fetchDemo) {
  const decision = routeParty(new URL(request.url));
  if (decision.kind === "redirect") {
    return Response.redirect(decision.location, 302);
  }
  if (decision.kind === "demo") {
    return fetchDemo(request);
  }
  return new Response("Not found", { status: 404 });
}
