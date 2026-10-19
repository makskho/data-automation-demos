import { createHash } from "node:crypto";
import { HttpError } from "./errors";

export const MAX_FILE_BYTES = 10 * 1024 * 1024; // 10 MB per document
export const MAX_DOCS_PER_CLIENT = 50;

const ZIP = [0x50, 0x4b, 0x03, 0x04];

/** Whitelist: extension -> MIME we serve (the client-declared type is never trusted) + magic bytes where the format has them. */
export const ALLOWED: Record<string, { mime: string; magic?: number[] }> = {
  pdf: { mime: "application/pdf", magic: [0x25, 0x50, 0x44, 0x46] },
  png: { mime: "image/png", magic: [0x89, 0x50, 0x4e, 0x47] },
  jpg: { mime: "image/jpeg", magic: [0xff, 0xd8, 0xff] },
  jpeg: { mime: "image/jpeg", magic: [0xff, 0xd8, 0xff] },
  docx: { mime: "application/vnd.openxmlformats-officedocument.wordprocessingml.document", magic: ZIP },
  xlsx: { mime: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", magic: ZIP },
  txt: { mime: "text/plain; charset=utf-8" },
  csv: { mime: "text/csv; charset=utf-8" },
};

/** Browsers send paths or odd characters; keep a safe display name, NFC-normalised, Cyrillic preserved. */
export function sanitizeFilename(raw: string): string {
  let name = raw.normalize("NFC");
  name = name.split(/[\\/]/).pop() ?? "";
  name = name
    .replace(/[\u0000-\u001f\u007f]/g, "") // control chars
    .replace(/[\u202a-\u202e\u2066-\u2069\u200e\u200f]/g, "") // bidi overrides (spoofed extensions)
    .trim();
  if (name === "" || name === "." || name === "..") {
    throw new HttpError(400, "bad_filename", "Некорректное имя файла");
  }
  const chars = [...name];
  if (chars.length > 255) {
    const dot = name.lastIndexOf(".");
    const ext = dot > 0 ? [...name.slice(dot)].slice(0, 20).join("") : "";
    name = chars.slice(0, 255 - [...ext].length).join("") + ext;
  }
  return name;
}

export function checkFile(filename: string, bytes: Buffer): { mime: string } {
  if (bytes.length === 0) throw new HttpError(400, "empty_file", "Файл пустой");
  if (bytes.length > MAX_FILE_BYTES) {
    throw new HttpError(413, "file_too_large", `Файл больше ${MAX_FILE_BYTES / 1024 / 1024} МБ`);
  }
  const ext = filename.includes(".") ? filename.slice(filename.lastIndexOf(".") + 1).toLowerCase() : "";
  const rule = ALLOWED[ext];
  if (!rule) {
    throw new HttpError(415, "unsupported_type", `Тип .${ext || "?"} не разрешён`, { allowed: Object.keys(ALLOWED) });
  }
  if (rule.magic && !rule.magic.every((b, i) => bytes[i] === b)) {
    throw new HttpError(415, "content_mismatch", "Содержимое файла не соответствует расширению");
  }
  return { mime: rule.mime };
}

export const sha256 = (b: Buffer) => createHash("sha256").update(b).digest("hex");

/**
 * Content-Disposition with an ASCII fallback and an RFC 5987/8187 `filename*` for UTF-8 names,
 * so «Договор №5 (скан).pdf» is saved as-is by every modern browser.
 */
export function contentDisposition(filename: string, type: "attachment" | "inline" = "attachment"): string {
  const dot = filename.lastIndexOf(".");
  const ext = dot > 0 ? filename.slice(dot).replace(/[^\x20-\x7e]|["\\%]/g, "_") : "";
  const base = dot > 0 ? filename.slice(0, dot) : filename;
  const fallback = base.replace(/[^\x20-\x7e]|["\\%]/g, "_").replace(/_{2,}/g, "_").trim() || "file";
  const encoded = encodeURIComponent(filename).replace(
    /['()*]/g,
    (c) => "%" + c.charCodeAt(0).toString(16).toUpperCase(),
  );
  return `${type}; filename="${fallback}${ext}"; filename*=UTF-8''${encoded}`;
}
