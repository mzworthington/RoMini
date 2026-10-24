export const DEMO_DATABASE_ID = "5948544a-74ae-4e4e-922c-908af99e4b9a";

export const DEMO_BUCKET_NAME = "romini-demo";

export const DEMO_WORKER_NAME = "romini-demo";

export const DEMO_HOSTNAME = "demo.romini.party";

export function d1ImportId(accountId: string): string {
  return `${accountId}/${DEMO_DATABASE_ID}`;
}

export function r2ImportId(accountId: string): string {
  return `${accountId}/${DEMO_BUCKET_NAME}/default`;
}
