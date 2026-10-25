// Demo dashboard resources for romini.party.
// The Worker script is uploaded by the deploy-demo job
// (`uv run pywrangler deploy` in deploy/demo). This stack owns the D1
// database, the R2 bucket, the Worker shell, and the demo.romini.party
// hostname. romini.party and www stay on the romini-party Worker config
// (deploy/party) so this stack does not attach those names a second time.
// The zone itself stays in edge-dns.
import * as cloudflare from "@pulumi/cloudflare";
import * as pulumi from "@pulumi/pulumi";

import { DEMO_BUCKET_NAME, DEMO_HOSTNAME, DEMO_MEDIA_HOST, DEMO_WORKER_NAME } from "./importIds";

const config = new pulumi.Config();
const accountId = config.require("accountId");
const zoneId = config.require("zoneId");

const database = new cloudflare.D1Database(
  "romini-demo",
  {
    accountId,
    name: "romini-demo",
    readReplication: { mode: "disabled" },
  },
  { protect: true },
);

const library = new cloudflare.R2Bucket(
  "romini-demo-library",
  {
    accountId,
    name: DEMO_BUCKET_NAME,
    jurisdiction: "default",
    location: "weur",
    storageClass: "Standard",
  },
  { protect: true },
);

const worker = new cloudflare.Worker(
  "romini-demo",
  {
    accountId,
    name: DEMO_WORKER_NAME,
  },
  { ignoreChanges: ["subdomain", "observability"] },
);

const zone = cloudflare.getZoneOutput({ zoneId });

new cloudflare.R2CustomDomain("media", {
  accountId,
  bucketName: library.name,
  domain: DEMO_MEDIA_HOST,
  enabled: true,
  jurisdiction: "default",
  minTls: "1.2",
  zoneId,
});

new cloudflare.WorkersCustomDomain("demo", {
  accountId,
  zoneId,
  zoneName: zone.name,
  hostname: DEMO_HOSTNAME,
  service: worker.name,
});

new cloudflare.ObservatoryScheduledTest("observatory-demo", {
  zoneId,
  url: DEMO_HOSTNAME,
});

export const databaseName = database.name;
export const bucketName = library.name;
export const hostname = DEMO_HOSTNAME;
