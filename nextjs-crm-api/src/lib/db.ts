import { mkdirSync } from "node:fs";
import type { PgDatabase } from "drizzle-orm/pg-core";
import * as schema from "./schema";
import { migrate } from "./migrate";

export type Db = PgDatabase<any, typeof schema>;

const g = globalThis as unknown as { __crmDb?: Promise<Db> };

/** Tests (and scripts) inject their own database. */
export function setDb(db: Db | undefined) {
  g.__crmDb = db ? Promise.resolve(db) : undefined;
}

export function getDb(): Promise<Db> {
  g.__crmDb ??= connect().catch((e) => {
    g.__crmDb = undefined; // do not cache a failed connection: the next request retries
    throw e;
  });
  return g.__crmDb;
}

async function connect(): Promise<Db> {
  const url = process.env.DATABASE_URL;
  let db: Db;
  if (url) {
    // production: real PostgreSQL through a connection pool
    const { Pool } = await import("pg");
    const { drizzle } = await import("drizzle-orm/node-postgres");
    db = drizzle(new Pool({ connectionString: url, max: 10 }), { schema }) as unknown as Db;
  } else {
    // demo fallback without a PostgreSQL server: embedded PostgreSQL (WASM), data in ./.data/pglite
    const { PGlite } = await import("@electric-sql/pglite");
    const { drizzle } = await import("drizzle-orm/pglite");
    const dir = process.env.PGLITE_DIR ?? ".data/pglite";
    mkdirSync(dir, { recursive: true });
    db = drizzle(new PGlite(dir), { schema }) as unknown as Db;
  }
  await migrate(db);
  return db;
}
