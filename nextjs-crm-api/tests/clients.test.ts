import { afterAll, beforeAll, beforeEach, describe, expect, it } from "vitest";
import * as list from "@/app/api/clients/route";
import * as one from "@/app/api/clients/[id]/route";
import { setDb, type Db } from "@/lib/db";
import { call, resetDb, startTestDb } from "./helpers";

let db: Db;
beforeAll(async () => {
  db = await startTestDb();
});
afterAll(() => setDb(undefined));
beforeEach(() => resetDb(db));

const mk = async (over: Record<string, unknown> = {}) => {
  const res = await call(list.POST, "POST", "/api/clients", {
    json: { name: "Иван Петров", email: "ivan@example.ru", ...over },
  });
  return { res, body: await res.json() };
};

describe("clients CRUD", () => {
  it("creates, reads, deletes", async () => {
    const { res, body } = await mk({ phone: "+7 (900) 123-45-67", company: "ООО «Ромашка»" });
    expect(res.status).toBe(201);
    expect(res.headers.get("location")).toBe(`/api/clients/${body.id}`);
    expect(body.company).toBe("ООО «Ромашка»");

    const got = await call(one.GET, "GET", "/x", { id: body.id });
    expect(got.status).toBe(200);
    expect((await got.json()).email).toBe("ivan@example.ru");

    expect((await call(one.DELETE, "DELETE", "/x", { id: body.id })).status).toBe(204);
    const gone = await call(one.GET, "GET", "/x", { id: body.id });
    expect(gone.status).toBe(404);
    expect((await gone.json()).error.code).toBe("not_found");
  });

  it("patches only the given fields and normalises the e-mail", async () => {
    const { body } = await mk({ company: "Старая" });
    const res = await call(one.PATCH, "PATCH", "/x", {
      id: body.id,
      json: { updatedAt: body.updatedAt, email: "  NEW@Example.RU ", phone: "" },
    });
    expect(res.status).toBe(200);
    const upd = await res.json();
    expect(upd.email).toBe("new@example.ru");
    expect(upd.phone).toBeNull();
    expect(upd.company).toBe("Старая"); // untouched
    expect(upd.name).toBe("Иван Петров");
  });

  it("paginates and searches (case-insensitive, Cyrillic, wildcards are literal)", async () => {
    for (let i = 1; i <= 25; i++) await mk({ name: `Клиент ${i}`, email: `c${i}@example.ru` });
    await mk({ name: "Скидка 50% VIP", email: "vip@example.ru", company: "Альфа_Бета" });

    const p1 = await (await call(list.GET, "GET", "/api/clients?pageSize=10&page=1")).json();
    expect(p1).toMatchObject({ page: 1, pageSize: 10, total: 26, totalPages: 3 });
    expect(p1.items).toHaveLength(10);
    const p3 = await (await call(list.GET, "GET", "/api/clients?pageSize=10&page=3")).json();
    expect(p3.items).toHaveLength(6);
    const ids = new Set([...p1.items, ...p3.items].map((c: any) => c.id));
    expect(ids.size).toBe(16); // no overlaps between pages

    const s1 = await (await call(list.GET, "GET", "/api/clients?q=" + encodeURIComponent("КЛИЕНТ 2"))).json();
    expect(s1.total).toBe(7); // 2, 20..25
    const s2 = await (await call(list.GET, "GET", "/api/clients?q=" + encodeURIComponent("50%"))).json();
    expect(s2.total).toBe(1);
    const s3 = await (await call(list.GET, "GET", "/api/clients?q=%25")).json(); // a bare "%" must not match everything
    expect(s3.total).toBe(1);
    const s4 = await (await call(list.GET, "GET", "/api/clients?q=" + encodeURIComponent("альфа_бета"))).json();
    expect(s4.total).toBe(1);
  });
});

describe("validation and errors", () => {
  it("rejects invalid input with 422 and per-field details", async () => {
    const { res, body } = await mk({ name: "  ", email: "not-an-email", phone: "abc" });
    expect(res.status).toBe(422);
    expect(body.error.code).toBe("validation_error");
    const fields = body.error.details.map((d: any) => d.field).sort();
    expect(fields).toEqual(["email", "name", "phone"]);
  });

  it("rejects bad JSON, bad ids, bad paging", async () => {
    const bad = await call(list.POST, "POST", "/api/clients", { rawBody: "{oops" });
    expect(bad.status).toBe(400);
    expect((await bad.json()).error.code).toBe("bad_json");

    const id = await call(one.GET, "GET", "/x", { id: "123" });
    expect(id.status).toBe(400);
    expect((await id.json()).error.code).toBe("bad_id");

    expect((await call(list.GET, "GET", "/api/clients?pageSize=1000")).status).toBe(422);
    expect((await call(list.GET, "GET", "/api/clients?page=0")).status).toBe(422);
  });

  it("answers 409 on duplicate e-mail, case-insensitively, on create and on update", async () => {
    await mk();
    const dup = await mk({ name: "Другой", email: "IVAN@example.ru" });
    expect(dup.res.status).toBe(409);
    expect(dup.body.error.code).toBe("email_taken");

    const other = (await mk({ name: "Пётр", email: "petr@example.ru" })).body;
    const res = await call(one.PATCH, "PATCH", "/x", {
      id: other.id,
      json: { updatedAt: other.updatedAt, email: "ivan@example.ru" },
    });
    expect(res.status).toBe(409);
    expect((await res.json()).error.code).toBe("email_taken");
  });

  it("PATCH requires updatedAt and rejects unknown fields; unknown id is 404", async () => {
    const { body } = await mk();
    const noVer = await call(one.PATCH, "PATCH", "/x", { id: body.id, json: { name: "Х" } });
    expect(noVer.status).toBe(422);
    const extra = await call(one.PATCH, "PATCH", "/x", { id: body.id, json: { updatedAt: body.updatedAt, id: "hack" } });
    expect(extra.status).toBe(422);
    const missing = await call(one.PATCH, "PATCH", "/x", {
      id: "00000000-0000-4000-8000-000000000000",
      json: { updatedAt: body.updatedAt, name: "Х" },
    });
    expect(missing.status).toBe(404);
  });
});

describe("optimistic locking (no lost updates)", () => {
  it("second save from the same base version gets 409 with the current record", async () => {
    const { body } = await mk();
    const a = await call(one.PATCH, "PATCH", "/x", { id: body.id, json: { updatedAt: body.updatedAt, name: "Правка A" } });
    expect(a.status).toBe(200);
    const aBody = await a.json();
    expect(new Date(aBody.updatedAt).getTime()).toBeGreaterThan(new Date(body.updatedAt).getTime());

    const b = await call(one.PATCH, "PATCH", "/x", { id: body.id, json: { updatedAt: body.updatedAt, name: "Правка B" } });
    expect(b.status).toBe(409);
    const bBody = await b.json();
    expect(bBody.error.code).toBe("version_conflict");
    expect(bBody.error.details.current.name).toBe("Правка A");

    // the loser re-reads, re-applies on the fresh version and succeeds
    const retry = await call(one.PATCH, "PATCH", "/x", {
      id: body.id,
      json: { updatedAt: bBody.error.details.current.updatedAt, name: "Правка B" },
    });
    expect(retry.status).toBe(200);
  });

  it("parallel saves with the same base version: exactly one wins", async () => {
    const { body } = await mk();
    const results = await Promise.all(
      Array.from({ length: 6 }, (_, i) =>
        call(one.PATCH, "PATCH", "/x", { id: body.id, json: { updatedAt: body.updatedAt, notes: `writer ${i}` } }),
      ),
    );
    const codes = results.map((r) => r.status).sort();
    expect(codes).toEqual([200, 409, 409, 409, 409, 409]);
    const winner = results.findIndex((r) => r.status === 200);
    const final = await (await call(one.GET, "GET", "/x", { id: body.id })).json();
    expect(final.notes).toBe(`writer ${winner}`);
  });

  it("back-to-back saves always get distinct versions", async () => {
    let cur = (await mk()).body;
    const seen = new Set([cur.updatedAt]);
    for (let i = 0; i < 10; i++) {
      const r = await call(one.PATCH, "PATCH", "/x", { id: cur.id, json: { updatedAt: cur.updatedAt, notes: String(i) } });
      expect(r.status).toBe(200);
      cur = await r.json();
      expect(seen.has(cur.updatedAt)).toBe(false);
      seen.add(cur.updatedAt);
    }
  });
});
