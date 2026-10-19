import { getDb } from "@/lib/db";
import { deleteDocument, getDocument } from "@/lib/documents";
import { route } from "@/lib/errors";
import { contentDisposition } from "@/lib/files";
import { idFrom, type IdCtx } from "@/lib/http";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export const GET = route(async (req: Request, ctx: IdCtx) => {
  const doc = await getDocument(await getDb(), await idFrom(ctx));
  const etag = `"${doc.sha256}"`;
  const headers = {
    ETag: etag,
    "Cache-Control": "private, no-cache",
    "X-Content-Type-Options": "nosniff",
  };
  if (req.headers.get("if-none-match") === etag) return new Response(null, { status: 304, headers });
  return new Response(new Uint8Array(doc.data), {
    headers: {
      ...headers,
      "Content-Type": doc.contentType,
      "Content-Length": String(doc.data.length),
      "Content-Disposition": contentDisposition(doc.filename),
    },
  });
});

export const DELETE = route(async (_req: Request, ctx: IdCtx) => {
  await deleteDocument(await getDb(), await idFrom(ctx));
  return new Response(null, { status: 204 });
});
