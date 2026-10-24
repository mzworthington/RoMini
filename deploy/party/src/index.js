import { Container } from "@cloudflare/containers";

import { respondParty } from "./route.js";

export class RominiDemo extends Container {
  defaultPort = 8080;
  sleepAfter = "10m";
  enableInternet = false;
  envVars = {
    ROMINI_PROFILE: "demo",
    ROMINI_DATA: "/var/lib/romini",
    ROMINI_DASHBOARD_PORT: "8080",
  };
}

export default {
  /**
   * @param {Request} request
   * @param {{ DEMO: { getByName: (name: string) => { fetch: (request: Request) => Promise<Response> | Response } } }} env
   */
  async fetch(request, env) {
    return respondParty(request, (incoming) => env.DEMO.getByName("public").fetch(incoming));
  },
};
