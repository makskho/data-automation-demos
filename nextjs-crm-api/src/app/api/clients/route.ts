import { createClient, listClients } from "@/lib/clients";
import { getDb } from "@/lib/db";
import { route } from "@/lib/errors";
import { jsonBody } from "@/lib/http";
import { clientCreate, listQuery } from "@/lib/validation";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export const GET = route(async (req: Request) => {
  const q = listQuery.parse(Object.fromEntries(new URL(req.url).searchParams));
  return Response.json(await listClients(await getDb(), q));
});

export const POST = route(async (req: Request) => {
  const input = clientCreate.parse(await jsonBody(req));
  const created = await createClient(await getDb(), input);
  return Response.json(created, { status: 201, headers: { Location: `/api/clients/${created.id}` } });
});
