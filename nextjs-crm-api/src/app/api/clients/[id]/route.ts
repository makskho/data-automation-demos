import { deleteClient, getClient, updateClient } from "@/lib/clients";
import { getDb } from "@/lib/db";
import { route } from "@/lib/errors";
import { idFrom, jsonBody, type IdCtx } from "@/lib/http";
import { clientPatch } from "@/lib/validation";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export const GET = route(async (_req: Request, ctx: IdCtx) =>
  Response.json(await getClient(await getDb(), await idFrom(ctx))),
);

export const PATCH = route(async (req: Request, ctx: IdCtx) => {
  const id = await idFrom(ctx);
  const input = clientPatch.parse(await jsonBody(req));
  return Response.json(await updateClient(await getDb(), id, input));
});

export const DELETE = route(async (_req: Request, ctx: IdCtx) => {
  await deleteClient(await getDb(), await idFrom(ctx));
  return new Response(null, { status: 204 });
});
