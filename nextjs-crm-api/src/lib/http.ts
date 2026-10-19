import { HttpError } from "./errors";
import { uuidParam } from "./validation";

export type IdCtx = { params: Promise<{ id: string }> };

export async function idFrom(ctx: IdCtx): Promise<string> {
  const { id } = await ctx.params;
  const r = uuidParam.safeParse(id);
  if (!r.success) throw new HttpError(400, "bad_id", "Некорректный идентификатор");
  return r.data;
}

export async function jsonBody(req: Request): Promise<unknown> {
  try {
    return await req.json();
  } catch {
    throw new HttpError(400, "bad_json", "Тело запроса должно быть корректным JSON");
  }
}
