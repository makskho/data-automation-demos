import { and, count, desc, eq, ilike, or, sql } from "drizzle-orm";
import type { z } from "zod";
import type { Db } from "./db";
import { HttpError, notFound, pgCode } from "./errors";
import { clients, type ClientRow } from "./schema";
import type { clientCreate, clientPatch, listQuery } from "./validation";

export const toClientDto = (c: ClientRow) => ({
  id: c.id,
  name: c.name,
  email: c.email,
  phone: c.phone,
  company: c.company,
  notes: c.notes,
  createdAt: c.createdAt.toISOString(),
  updatedAt: c.updatedAt.toISOString(),
});

const emailTaken = () => new HttpError(409, "email_taken", "Клиент с таким e-mail уже существует");

/** Escape LIKE wildcards so searching for "50%" or "a_b" matches literally. */
const likeEscape = (s: string) => s.replace(/[\\%_]/g, (m) => "\\" + m);

export async function createClient(db: Db, input: z.infer<typeof clientCreate>) {
  try {
    const [row] = await db.insert(clients).values(input).returning();
    return toClientDto(row);
  } catch (err) {
    if (pgCode(err) === "23505") throw emailTaken();
    throw err;
  }
}

export async function listClients(db: Db, q: z.infer<typeof listQuery>) {
  const pattern = q.q ? `%${likeEscape(q.q)}%` : undefined;
  const where = pattern
    ? or(ilike(clients.name, pattern), ilike(clients.email, pattern), ilike(clients.company, pattern))
    : undefined;
  const [{ total }] = await db.select({ total: count() }).from(clients).where(where);
  const rows = await db
    .select()
    .from(clients)
    .where(where)
    .orderBy(desc(clients.createdAt), clients.id)
    .limit(q.pageSize)
    .offset((q.page - 1) * q.pageSize);
  return {
    items: rows.map(toClientDto),
    page: q.page,
    pageSize: q.pageSize,
    total,
    totalPages: Math.max(1, Math.ceil(total / q.pageSize)),
  };
}

export async function getClient(db: Db, id: string) {
  const [row] = await db.select().from(clients).where(eq(clients.id, id));
  if (!row) throw notFound("Клиент");
  return toClientDto(row);
}

/**
 * Optimistic lock: the UPDATE only matches when updated_at is still the value the caller saw.
 * Two editors with the same base version: one wins (200), the other gets 409 and the current record,
 * instead of silently overwriting (the classic "lost save").
 * updated_at always moves forward by at least 1 ms, so two quick saves cannot share a version.
 */
export async function updateClient(db: Db, id: string, input: z.infer<typeof clientPatch>) {
  const { updatedAt, ...patch } = input;
  const fields = Object.fromEntries(Object.entries(patch).filter(([, v]) => v !== undefined));
  try {
    const [row] = await db
      .update(clients)
      .set({
        ...fields,
        updatedAt: sql`GREATEST(date_trunc('milliseconds', clock_timestamp()), ${clients.updatedAt} + interval '1 millisecond')`,
      })
      .where(and(eq(clients.id, id), eq(clients.updatedAt, new Date(updatedAt))))
      .returning();
    if (row) return toClientDto(row);
  } catch (err) {
    if (pgCode(err) === "23505") throw emailTaken();
    throw err;
  }
  const [current] = await db.select().from(clients).where(eq(clients.id, id));
  if (!current) throw notFound("Клиент");
  throw new HttpError(409, "version_conflict", "Запись изменена другим пользователем. Обновите данные и повторите.", {
    current: toClientDto(current),
  });
}

/** Documents are removed by ON DELETE CASCADE in the same statement: no orphans, nothing half-deleted. */
export async function deleteClient(db: Db, id: string) {
  const rows = await db.delete(clients).where(eq(clients.id, id)).returning({ id: clients.id });
  if (!rows.length) throw notFound("Клиент");
}
