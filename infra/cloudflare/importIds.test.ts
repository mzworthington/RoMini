import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const ACCOUNT = "fe0bb0a89551958509fe4d65883026cc";

test("the demo stack imports the database and bucket Wrangler already created", async () => {
  const ids = await import("./importIds.ts");

  assert.equal(ids.DEMO_DATABASE_ID, "5948544a-74ae-4e4e-922c-908af99e4b9a");
  assert.equal(ids.DEMO_BUCKET_NAME, "romini-demo");
  assert.equal(ids.DEMO_WORKER_NAME, "romini-demo");
  assert.equal(ids.DEMO_HOSTNAME, "demo.romini.party");
  assert.equal(ids.d1ImportId(ACCOUNT), `${ACCOUNT}/${ids.DEMO_DATABASE_ID}`);
  assert.equal(ids.r2ImportId(ACCOUNT), `${ACCOUNT}/${ids.DEMO_BUCKET_NAME}/default`);
});

test("the Pulumi program adopts that database and bucket and attaches the demo hostname", () => {
  const source = readFileSync(new URL("./index.ts", import.meta.url), "utf8");

  assert.match(source, /new cloudflare\.D1Database\(/);
  assert.match(source, /new cloudflare\.R2Bucket\(/);
  assert.match(source, /protect: true/);
  assert.doesNotMatch(source, /import:/);
  assert.match(source, /new cloudflare\.Worker\(/);
  assert.match(source, /new cloudflare\.WorkersCustomDomain\(/);
  assert.match(source, /new cloudflare\.ObservatoryScheduledTest\(/);
  assert.match(source, /DEMO_HOSTNAME/);
  assert.match(source, /pywrangler deploy/);
});

test("the library bucket is readable at the media hostname", async () => {
  const ids = await import("./importIds.ts");
  const source = readFileSync(new URL("./index.ts", import.meta.url), "utf8");

  assert.equal(ids.DEMO_MEDIA_HOST, "media.romini.party");
  assert.match(source, /new cloudflare\.R2CustomDomain\(/);
  assert.match(source, /DEMO_MEDIA_HOST/);
  assert.match(source, /enabled: true/);
});
