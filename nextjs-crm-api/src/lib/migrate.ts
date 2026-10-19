import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { sql } from "drizzle-orm";
import type { Db } from "./db";

/** Minimal forward-only migration runner: applies migrations/*.sql once each, inside a transaction. */
export async function migrate(db: Db, dir = path.join(process.cwd(), "migrations")) {
  await db.execute(sql`CREATE TABLE IF NOT EXISTS schema_migrations (name text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())`);
  const files = readdirSync(dir).filter((f) => f.endsWith(".sql")).sort();
  for (const file of files) {
    await db.transaction(async (tx) => {
      // lock so two app instances starting at once do not apply the same migration twice
      await tx.execute(sql`SELECT pg_advisory_xact_lock(727001)`);
      const done = await tx.execute(sql`SELECT 1 FROM schema_migrations WHERE name = ${file}`);
      if (rowsOf(done).length) return;
      const text = readFileSync(path.join(dir, file), "utf8");
      for (const stmt of text.split(/;\s*$/m).map((s) => s.trim()).filter(Boolean)) {
        await tx.execute(sql.raw(stmt));
      }
      await tx.execute(sql`INSERT INTO schema_migrations (name) VALUES (${file})`);
    });
  }
}

/** node-postgres returns {rows}, PGlite too; keep both shapes working. */
export function rowsOf(result: unknown): any[] {
  const r = result as any;
  return Array.isArray(r) ? r : (r?.rows ?? []);
}
