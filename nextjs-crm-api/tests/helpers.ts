import { PGlite } from "@electric-sql/pglite";
import { sql } from "drizzle-orm";
import { drizzle } from "drizzle-orm/pglite";
import { setDb, type Db } from "@/lib/db";
import { migrate } from "@/lib/migrate";
import * as schema from "@/lib/schema";

/** Real PostgreSQL engine (PGlite = Postgres compiled to WASM), in memory, same migrations/*.sql as production. */
export async function startTestDb(): Promise<Db> {
  const db = drizzle(new PGlite(), { schema }) as unknown as Db;
  await migrate(db);
  setDb(db);
  return db;
}

export const resetDb = (db: Db) => db.execute(sql`TRUNCATE clients CASCADE`);

const BASE = "http://localhost";
type Handler = (req: Request, ctx: any) => Promise<Response>;

export function call(
  handler: Handler,
  method: string,
  path: string,
  opts: { json?: unknown; form?: FormData; id?: string; rawBody?: string; headers?: Record<string, string> } = {},
) {
  const headers: Record<string, string> = { ...opts.headers };
  let body: BodyInit | undefined;
  if (opts.json !== undefined) {
    body = JSON.stringify(opts.json);
    headers["content-type"] = "application/json";
  } else if (opts.rawBody !== undefined) {
    body = opts.rawBody;
    headers["content-type"] = "application/json";
  } else if (opts.form) {
    body = opts.form;
  }
  return handler(new Request(BASE + path, { method, body, headers }), {
    params: Promise.resolve({ id: opts.id ?? "" }),
  });
}

export function fileForm(name: string, bytes: Uint8Array, type = "application/octet-stream") {
  const form = new FormData();
  form.append("file", new File([bytes as BlobPart], name, { type }));
  return form;
}

export const pdfBytes = (size = 2048) => {
  const b = Buffer.alloc(size);
  for (let i = 0; i < size; i++) b[i] = (i * 31 + 7) & 0xff; // all byte values, incl. 0x00 and 0xFF
  Buffer.from("%PDF-1.7\n").copy(b);
  return b;
};
