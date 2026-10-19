import { getDb } from "@/lib/db";
import { listDocuments, uploadDocument } from "@/lib/documents";
import { HttpError, route } from "@/lib/errors";
import { MAX_FILE_BYTES } from "@/lib/files";
import { idFrom, type IdCtx } from "@/lib/http";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export const GET = route(async (_req: Request, ctx: IdCtx) =>
  Response.json({ items: await listDocuments(await getDb(), await idFrom(ctx)) }),
);

export const POST = route(async (req: Request, ctx: IdCtx) => {
  const id = await idFrom(ctx);
  if (!(req.headers.get("content-type") ?? "").toLowerCase().startsWith("multipart/form-data")) {
    throw new HttpError(415, "multipart_required", "Ожидается multipart/form-data с полем file");
  }
  // cheap early rejection before the body is buffered (+64 KB for multipart framing)
  const declared = Number(req.headers.get("content-length"));
  if (Number.isFinite(declared) && declared > MAX_FILE_BYTES + 64 * 1024) {
    throw new HttpError(413, "file_too_large", `Файл больше ${MAX_FILE_BYTES / 1024 / 1024} МБ`);
  }
  let form: FormData;
  try {
    form = await req.formData();
  } catch {
    throw new HttpError(400, "bad_multipart", "Не удалось прочитать multipart-тело");
  }
  const file = form.get("file");
  if (!(file instanceof File)) throw new HttpError(400, "file_missing", "Поле file с файлом обязательно");
  if (file.size > MAX_FILE_BYTES) {
    throw new HttpError(413, "file_too_large", `Файл больше ${MAX_FILE_BYTES / 1024 / 1024} МБ`);
  }
  const bytes = Buffer.from(await file.arrayBuffer());
  const doc = await uploadDocument(await getDb(), id, file.name, bytes);
  return Response.json(doc, { status: 201, headers: { Location: `/api/documents/${doc.id}` } });
});
