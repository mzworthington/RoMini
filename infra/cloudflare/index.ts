import * as cloudflare from "@pulumi/cloudflare";
import * as pulumi from "@pulumi/pulumi";

import { DEMO_BUCKET_NAME, DEMO_HOSTNAME, DEMO_WORKER_NAME } from "./importIds";

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

new cloudflare.WorkersCustomDomain("demo", {
  accountId,
  zoneId,
  zoneName: zone.name,
  hostname: DEMO_HOSTNAME,
  service: worker.name,
});

export const databaseName = database.name;
export const bucketName = library.name;
export const hostname = DEMO_HOSTNAME;
