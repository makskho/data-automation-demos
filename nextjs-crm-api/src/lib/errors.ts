import { ZodError } from "zod";

export class HttpError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details?: unknown,
  ) {
    super(message);
  }
}

export const notFound = (what: string) => new HttpError(404, "not_found", `${what} не найден`);

/** Consistent error body: { error: { code, message, details? } } */
export function errorResponse(err: unknown): Response {
  if (err instanceof HttpError) {
    return Response.json(
      { error: { code: err.code, message: err.message, ...(err.details !== undefined && { details: err.details }) } },
      { status: err.status },
    );
  }
  if (err instanceof ZodError) {
    return Response.json(
      {
        error: {
          code: "validation_error",
          message: "Проверьте введённые данные",
          details: err.issues.map((i) => ({ field: i.path.join("."), message: i.message })),
        },
      },
      { status: 422 },
    );
  }
  if (pgCode(err) === "22P02") {
    // invalid_text_representation, e.g. a malformed uuid slipped through
    return Response.json({ error: { code: "bad_request", message: "Некорректный идентификатор" } }, { status: 400 });
  }
  console.error("[unhandled]", err);
  return Response.json({ error: { code: "internal_error", message: "Внутренняя ошибка сервера" } }, { status: 500 });
}

/** SQLSTATE of a driver error (Drizzle wraps the original error in `cause`). */
export function pgCode(err: unknown): string | undefined {
  let e: any = err;
  for (let i = 0; i < 4 && e; i++) {
    if (typeof e.code === "string" && /^[0-9A-Z]{5}$/.test(e.code)) return e.code;
    e = e.cause;
  }
  return undefined;
}

type Handler<C> = (req: Request, ctx: C) => Promise<Response>;

/** Wraps a route handler so every failure becomes the same JSON error. */
export function route<C>(fn: Handler<C>): Handler<C> {
  return async (req, ctx) => {
    try {
      return await fn(req, ctx);
    } catch (err) {
      return errorResponse(err);
    }
  };
}
