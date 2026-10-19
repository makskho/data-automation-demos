import { desc, eq, sql } from "drizzle-orm";
import type { Db } from "./db";
import { HttpError, notFound } from "./errors";
import { checkFile, MAX_DOCS_PER_CLIENT, sanitizeFilename, sha256 } from "./files";
import { clients, documents, type DocumentRow } from "./schema";

const meta = {
  id: documents.id,
  clientId: documents.clientId,
  filename: documents.filename,
  contentType: documents.contentType,
  size: documents.size,
  sha256: documents.sha256,
  createdAt: documents.createdAt,
};

type Meta = Omit<DocumentRow, "data">;
const toDto = (d: Meta) => ({ ...d, createdAt: d.createdAt.toISOString() });

/**
 * Stored as bytea in the same database (see README: one transaction, one backup, ON DELETE CASCADE,
 * no orphan files on disk). Fine up to ~10 MB per file; for large files switch to S3 + metadata here.
 * The client row is locked FOR UPDATE so the per-client limit cannot be exceeded by parallel uploads.
 */
export async function uploadDocument(db: Db, clientId: string, rawName: string, bytes: Buffer) {
  const filename = sanitizeFilename(rawName);
  const { mime } = checkFile(filename, bytes);
  return db.transaction(async (tx) => {
    const locked = await tx.select({ id: clients.id }).from(clients).where(eq(clients.id, clientId)).for("update");
    if (!locked.length) throw notFound("Клиент");
    const [{ n }] = await tx
      .select({ n: sql<number>`count(*)::int` })
      .from(documents)
      .where(eq(documents.clientId, clientId));
    if (n >= MAX_DOCS_PER_CLIENT) {
      throw new HttpError(422, "document_limit", `Не больше ${MAX_DOCS_PER_CLIENT} документов на клиента`);
    }
    const [row] = await tx
      .insert(documents)
      .values({ clientId, filename, contentType: mime, size: bytes.length, sha256: sha256(bytes), data: bytes })
      .returning(meta);
    return toDto(row);
  });
}

export async function listDocuments(db: Db, clientId: string) {
  const [c] = await db.select({ id: clients.id }).from(clients).where(eq(clients.id, clientId));
  if (!c) throw notFound("Клиент");
  const rows = await db
    .select(meta)
    .from(documents)
    .where(eq(documents.clientId, clientId))
    .orderBy(desc(documents.createdAt), documents.id);
  return rows.map(toDto);
}

export async function getDocument(db: Db, id: string) {
  const [row] = await db.select().from(documents).where(eq(documents.id, id));
  if (!row) throw notFound("Документ");
  return row;
}

export async function deleteDocument(db: Db, id: string) {
  const rows = await db.delete(documents).where(eq(documents.id, id)).returning({ id: documents.id });
  if (!rows.length) throw notFound("Документ");
}
