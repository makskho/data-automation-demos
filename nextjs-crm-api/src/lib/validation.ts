import { z } from "zod";

const optionalText = (max: number) =>
  z
    .string()
    .trim()
    .max(max)
    .transform((v) => (v === "" ? null : v))
    .nullable()
    .optional();

const phone = z
  .string()
  .trim()
  .regex(/^\+?[0-9 ()\-]{5,25}$/, "Телефон: цифры, пробелы, скобки, дефис, допустим + в начале")
  .or(z.literal(""))
  .transform((v) => (v === "" ? null : v))
  .nullable()
  .optional();

export const clientCreate = z.object({
  name: z.string().trim().min(1, "Укажите имя").max(200),
  email: z.string().trim().max(254).toLowerCase().pipe(z.email("Некорректный e-mail")),
  phone,
  company: optionalText(200),
  notes: optionalText(5000),
});

/** PATCH: any subset of fields + updatedAt the client last saw (optimistic lock). */
export const clientPatch = clientCreate
  .partial()
  .extend({ updatedAt: z.iso.datetime({ message: "updatedAt обязателен (ISO-дата из последнего ответа)" }) })
  .strict();

export const listQuery = z.object({
  q: z.string().trim().max(100).optional(),
  page: z.coerce.number().int().min(1).default(1),
  pageSize: z.coerce.number().int().min(1).max(100).default(20),
});

export const uuidParam = z.uuid("Некорректный идентификатор");
