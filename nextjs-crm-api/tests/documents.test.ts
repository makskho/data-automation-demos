import { afterAll, beforeAll, beforeEach, describe, expect, it } from "vitest";
import { eq } from "drizzle-orm";
import * as clientsRoute from "@/app/api/clients/route";
import * as docsRoute from "@/app/api/clients/[id]/documents/route";
import * as clientRoute from "@/app/api/clients/[id]/route";
import * as docRoute from "@/app/api/documents/[id]/route";
import { setDb, type Db } from "@/lib/db";
import { contentDisposition, MAX_DOCS_PER_CLIENT, MAX_FILE_BYTES, sanitizeFilename } from "@/lib/files";
import { documents } from "@/lib/schema";
import { call, fileForm, pdfBytes, resetDb, startTestDb } from "./helpers";

let db: Db;
let clientId: string;
beforeAll(async () => {
  db = await startTestDb();
});
afterAll(() => setDb(undefined));
beforeEach(async () => {
  await resetDb(db);
  const res = await call(clientsRoute.POST, "POST", "/api/clients", { json: { name: "Анна", email: "anna@example.ru" } });
  clientId = (await res.json()).id;
});

const upload = (name: string, bytes: Uint8Array, id = clientId) =>
  call(docsRoute.POST, "POST", "/x", { id, form: fileForm(name, bytes) });

describe("upload / download round-trip", () => {
  it("keeps bytes and the Cyrillic file name intact", async () => {
    const name = "Договор №5 (скан) — финал.pdf";
    const bytes = pdfBytes(300_000);
    const up = await upload(name, bytes);
    expect(up.status).toBe(201);
    const meta = await up.json();
    expect(meta).toMatchObject({ filename: name, contentType: "application/pdf", size: bytes.length, clientId });
    expect(meta.data).toBeUndefined();

    const down = await call(docRoute.GET, "GET", "/x", { id: meta.id });
    expect(down.status).toBe(200);
    expect(down.headers.get("content-type")).toBe("application/pdf");
    expect(down.headers.get("content-length")).toBe(String(bytes.length));
    expect(down.headers.get("x-content-type-options")).toBe("nosniff");
    expect(Buffer.from(await down.arrayBuffer()).equals(bytes)).toBe(true);

    const cd = down.headers.get("content-disposition")!;
    expect(cd).toMatch(/^attachment; filename="[\x20-\x7e]+"; filename\*=UTF-8''[A-Za-z0-9%._~!-]+$/);
    const star = /filename\*=UTF-8''(.+)$/.exec(cd)![1];
    expect(decodeURIComponent(star)).toBe(name);
    expect(star).toContain("%D0%94%D0%BE%D0%B3%D0%BE%D0%B2%D0%BE%D1%80"); // «Договор» as UTF-8
  });

  it("lists metadata without file bodies and supports ETag / 304", async () => {
    const meta = await (await upload("отчёт.csv", Buffer.from("а;б\n1;2\n"))).json();
    await upload("scan.png", Buffer.from([0x89, 0x50, 0x4e, 0x47, 1, 2, 3]));
    const listed = await (await call(docsRoute.GET, "GET", "/x", { id: clientId })).json();
    expect(listed.items).toHaveLength(2);
    expect(listed.items.every((d: any) => d.data === undefined && d.sha256.length === 64)).toBe(true);

    const first = await call(docRoute.GET, "GET", "/x", { id: meta.id });
    expect(first.headers.get("content-type")).toBe("text/csv; charset=utf-8");
    const etag = first.headers.get("etag")!;
    const again = await call(docRoute.GET, "GET", "/x", { id: meta.id, headers: { "if-none-match": etag } });
    expect(again.status).toBe(304);
  });

  it("deletes a document; deleting the client removes its documents (no orphans)", async () => {
    const a = await (await upload("a.txt", Buffer.from("привет"))).json();
    await upload("b.txt", Buffer.from("мир"));
    expect((await call(docRoute.DELETE, "DELETE", "/x", { id: a.id })).status).toBe(204);
    expect((await call(docRoute.GET, "GET", "/x", { id: a.id })).status).toBe(404);
    expect((await call(docRoute.DELETE, "DELETE", "/x", { id: a.id })).status).toBe(404);

    expect((await call(clientRoute.DELETE, "DELETE", "/x", { id: clientId })).status).toBe(204);
    expect(await db.select().from(documents)).toHaveLength(0);
  });
});

describe("upload limits and safety", () => {
  const errOf = async (res: Response) => (await res.json()).error.code as string;

  it("rejects disallowed types, content/extension mismatch, empty and oversize files", async () => {
    const exe = await upload("virus.exe", Buffer.from("MZ...."));
    expect(exe.status).toBe(415);
    expect(await errOf(exe)).toBe("unsupported_type");

    const fake = await upload("fake.pdf", Buffer.from("<html>not a pdf</html>"));
    expect(fake.status).toBe(415);
    expect(await errOf(fake)).toBe("content_mismatch");

    const empty = await upload("empty.txt", Buffer.alloc(0));
    expect(empty.status).toBe(400);

    const big = await upload("big.pdf", pdfBytes(MAX_FILE_BYTES + 1));
    expect(big.status).toBe(413);
    expect(await errOf(big)).toBe("file_too_large");

    expect(await db.select().from(documents)).toHaveLength(0); // nothing half-saved
  });

  it("rejects non-multipart, missing file field, unknown client", async () => {
    const json = await call(docsRoute.POST, "POST", "/x", { id: clientId, json: { a: 1 } });
    expect(json.status).toBe(415);

    const form = new FormData();
    form.append("note", "no file here");
    const noFile = await call(docsRoute.POST, "POST", "/x", { id: clientId, form });
    expect(noFile.status).toBe(400);
    expect(await errOf(noFile)).toBe("file_missing");

    const ghost = await upload("a.txt", Buffer.from("x"), "00000000-0000-4000-8000-000000000000");
    expect(ghost.status).toBe(404);
    expect((await call(docsRoute.GET, "GET", "/x", { id: "00000000-0000-4000-8000-000000000000" })).status).toBe(404);
  });

  it("strips path parts from the name (no traversal) and enforces the per-client limit under parallel uploads", async () => {
    const sneaky = await (await upload("..\\..\\etc/passwd.txt", Buffer.from("x"))).json();
    expect(sneaky.filename).toBe("passwd.txt");

    const results = await Promise.all(
      Array.from({ length: MAX_DOCS_PER_CLIENT + 5 }, (_, i) => upload(`f${i}.txt`, Buffer.from("data " + i))),
    );
    const ok = results.filter((r) => r.status === 201).length;
    expect(ok).toBe(MAX_DOCS_PER_CLIENT - 1); // one slot was already taken by passwd.txt
    expect(results.filter((r) => r.status === 422)).toHaveLength(6);
    const rows = await db.select({ id: documents.id }).from(documents).where(eq(documents.clientId, clientId));
    expect(rows).toHaveLength(MAX_DOCS_PER_CLIENT);
  });
});

describe("helpers", () => {
  it("contentDisposition is pure ASCII and RFC 5987 correct for tricky names", () => {
    for (const n of ['Отчёт "Q3" (финал).xlsx', "it's 100%.pdf", "日本語.txt", "a;b,c*.csv"]) {
      const cd = contentDisposition(n);
      expect(cd).toMatch(/^[\x20-\x7e]+$/);
      const star = /filename\*=UTF-8''(.+)$/.exec(cd)![1];
      expect(decodeURIComponent(star)).toBe(n);
      expect(star).not.toMatch(/['()*;,"]/);
      const fb = /filename="([^"]*)"/.exec(cd)![1];
      expect(fb).toMatch(/\.[a-z]+$/);
    }
  });

  it("sanitizeFilename normalises Unicode and drops bidi tricks", () => {
    expect(sanitizeFilename("C:\\Users\\x\\Отчёт.pdf")).toBe("Отчёт.pdf");
    expect(sanitizeFilename("И\u0306.txt")).toBe("Й.txt"); // NFD -> NFC
    expect(sanitizeFilename("photo\u202egnp.exe")).toBe("photognp.exe");
    expect(() => sanitizeFilename("..")).toThrow();
  });
});
