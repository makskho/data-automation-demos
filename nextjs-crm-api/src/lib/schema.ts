import { customType, integer, pgTable, text, timestamp, uuid } from "drizzle-orm/pg-core";

/** bytea <-> Buffer. node-postgres returns Buffer, PGlite returns Uint8Array; normalise to Buffer. */
const bytea = customType<{ data: Buffer; driverData: Uint8Array | Buffer }>({
  dataType: () => "bytea",
  toDriver: (value) => value,
  fromDriver: (value) => Buffer.from(value),
});

const ts = (name: string) =>
  timestamp(name, { withTimezone: true, mode: "date" }).notNull().defaultNow();

export const clients = pgTable("clients", {
  id: uuid("id").primaryKey().defaultRandom(),
  name: text("name").notNull(),
  email: text("email").notNull(),
  phone: text("phone"),
  company: text("company"),
  notes: text("notes"),
  createdAt: ts("created_at"),
  updatedAt: ts("updated_at"),
});

export const documents = pgTable("documents", {
  id: uuid("id").primaryKey().defaultRandom(),
  clientId: uuid("client_id")
    .notNull()
    .references(() => clients.id, { onDelete: "cascade" }),
  filename: text("filename").notNull(),
  contentType: text("content_type").notNull(),
  size: integer("size").notNull(),
  sha256: text("sha256").notNull(),
  data: bytea("data").notNull(),
  createdAt: ts("created_at"),
});

export type ClientRow = typeof clients.$inferSelect;
export type DocumentRow = typeof documents.$inferSelect;
