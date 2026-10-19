# Мини-CRM: API клиентов и документов (Next.js + TypeScript + PostgreSQL)

Демо-проект: серверная часть небольшой CRM на **Next.js (App Router, route handlers) + TypeScript + PostgreSQL (Drizzle ORM)**.
Клиенты (CRUD, поиск, пагинация), документы клиента (загрузка, список, скачивание, удаление), единый формат ошибок,
защита от потери данных при одновременном редактировании. Автор: Максим.

## Какие типичные проблемы это решает

| Симптом в «живой» CRM | Причина | Что сделано здесь |
|---|---|---|
| «Я сохранил, а потом данные откатились» (потерянные сохранения) | два сотрудника открыли карточку, последний `UPDATE` молча затирает первый | оптимистическая блокировка: `PATCH` обязан прислать `updatedAt`, `UPDATE ... WHERE id=? AND updated_at=?`; при расхождении — `409` и актуальная запись в ответе. Версия растёт минимум на 1 мс, две быстрые правки не получат одинаковую версию |
| Файл «загрузился», но не открывается / пропал | запись файла на диск и строки в БД не атомарны, при удалении клиента остаются «хвосты» | файл хранится в `bytea` в той же БД: одна транзакция, `ON DELETE CASCADE`, один бэкап |
| Лимит файлов обходится параллельными загрузками | проверка «count < N» и вставка не защищены | транзакция + `SELECT ... FOR UPDATE` по строке клиента |
| Скачанный файл называется `%D0%94...` или `????.pdf` | неверный `Content-Disposition` для кириллицы | `filename="ascii-запасной"; filename*=UTF-8''%D0%94...` (RFC 5987/8187), `Content-Type` берётся из белого списка, а не от клиента |
| Подмена расширения (`virus.pdf` с HTML внутри), `../../etc/passwd` в имени | имя и тип файла берутся «как есть» | белый список расширений + проверка сигнатур (PDF/PNG/JPEG/ZIP-форматы), очистка имени от путей, управляющих и bidi-символов, NFC-нормализация, `nosniff` |
| Поиск «по 50%» находит всё подряд | `%` и `_` в `LIKE` не экранируются | экранирование шаблона |
| Дубли клиентов `Ivan@x.ru` / `ivan@x.ru` | уникальность без учёта регистра | уникальный индекс по `lower(email)` → `409 email_taken` |
| На ошибку фронт получает то HTML, то строку, то стек | ошибки обрабатываются в каждом обработчике по-своему | один формат `{ "error": { "code", "message", "details?" } }` для всех путей |

## Архитектура

```
src/app/api/…           тонкие route handlers (парсинг → сервис → JSON)
src/lib/clients.ts      сервис клиентов (поиск, пагинация, optimistic lock)
src/lib/documents.ts    сервис документов (транзакция + блокировка строки клиента)
src/lib/files.ts        белый список типов, сигнатуры, имя файла, Content-Disposition
src/lib/validation.ts   zod-схемы
src/lib/errors.ts       HttpError + единый JSON ошибок + обёртка route()
src/lib/db.ts           подключение: pg Pool (DATABASE_URL) или встроенный PGlite
src/lib/migrate.ts      простой прогон migrations/*.sql (с advisory lock)
migrations/0001_init.sql  схема PostgreSQL
src/app/page.tsx        минимальная страница: список клиентов, поиск, загрузка/скачивание
tests/                  vitest, 18 тестов
```

**Где хранить файлы — решение и обоснование.** Выбран `bytea` в PostgreSQL, лимит 10 МБ на файл и 50 файлов на клиента:
атомарность с метаданными, каскадное удаление, единый бэкап, никаких «осиротевших» файлов и прав доступа к диску.
Минус — рост БД и память на файл при загрузке. Для файлов больше ~10–20 МБ или большого объёма схема переносится на S3-совместимое
хранилище: в таблице `documents` остаются метаданные и ключ объекта, сервис `documents.ts` — единственное место, которое меняется.

## Запуск

Проверено на Node.js 24 и npm 11.

```bash
npm install
cp .env.example .env            # DATABASE_URL=postgres://crm:crm@localhost:5432/crm
docker compose up -d db         # PostgreSQL 16 (или свой сервер)
npm run migrate                 # применить migrations/*.sql (также выполняется при первом запросе)
npm run dev                     # http://localhost:3000
```

Без `DATABASE_URL` приложение стартует на встроенном PostgreSQL (PGlite, данные в `.data/pglite`) — только для демонстрации.

```bash
npm test            # 18 тестов, работают офлайн
npm run typecheck   # tsc --noEmit
```

## API

| Метод и путь | Назначение | Успех | Ошибки |
|---|---|---|---|
| `GET /api/clients?q=&page=&pageSize=` | список, поиск по имени/e-mail/компании, `pageSize` ≤ 100 | 200 `{items,page,pageSize,total,totalPages}` | 422 |
| `POST /api/clients` | создать `{name,email,phone?,company?,notes?}` | 201 + `Location` | 400, 409 `email_taken`, 422 |
| `GET /api/clients/:id` | карточка | 200 | 400, 404 |
| `PATCH /api/clients/:id` | изменить; **обязателен `updatedAt`** из последнего ответа | 200 | 404, 409 `version_conflict` (в `details.current` актуальная запись) / `email_taken`, 422 |
| `DELETE /api/clients/:id` | удалить вместе с документами | 204 | 404 |
| `GET /api/clients/:id/documents` | список документов (без содержимого) | 200 `{items}` | 404 |
| `POST /api/clients/:id/documents` | `multipart/form-data`, поле `file` | 201 + `Location` | 400, 404, 413 `file_too_large`, 415 `unsupported_type`/`content_mismatch`/`multipart_required`, 422 `document_limit` |
| `GET /api/documents/:id` | скачать; `ETag`, `If-None-Match` → 304 | 200 | 404 |
| `DELETE /api/documents/:id` | удалить | 204 | 404 |

Разрешённые типы: pdf, png, jpg/jpeg, docx, xlsx, txt, csv.

## Что покрыто тестами

CRUD, пагинация и поиск (кириллица, регистр, `%`/`_` как обычные символы), ошибки валидации (422 с полями), битый JSON, неверный id,
дубликат e-mail без учёта регистра, конфликт версий (`409`), 6 параллельных сохранений с одной версии — выигрывает ровно одно,
загрузка и скачивание бинарного файла 300 КБ с именем «Договор №5 (скан) — финал.pdf» (совпадение байт и имени), отказ для
`.exe`, подделанного `.pdf`, пустого и >10 МБ файлов, обход пути в имени, лимит 50 документов при параллельных загрузках, каскадное удаление.
Дополнительно вручную прогнан реальный HTTP-стек: `next build` → `next start` → загрузка и скачивание файла с кириллическим именем через `fetch`.

## Честные ограничения

- В среде разработки не было сервера PostgreSQL и Docker. Тесты выполняются на **PGlite** (настоящий PostgreSQL, собранный в WASM, в памяти)
  с теми же файлами `migrations/*.sql`, что и в продакшене. Работа через `pg` Pool и `docker-compose.yml` в этой среде **не запускалась**:
  код подключения написан по документации, перед сдачей на реальном сервере нужен прогон `npm run migrate` и тестов.
- Аутентификации и ролей нет — это демо API; в рабочем проекте добавляются сессии/JWT и проверка прав на клиента.
- `request.formData()` буферизует тело в памяти: ранний отказ идёт по `Content-Length`, но для файлов крупнее лимита нужен потоковый разбор или прямая загрузка в S3.
- Нет антивирусной проверки и ограничения частоты запросов.

---

## English (short)

Demo back end for a small CRM: **Next.js App Router route handlers + TypeScript + PostgreSQL (Drizzle ORM)**.
Clients: CRUD, search, pagination, zod validation, optimistic locking via `updatedAt` (`409` + current record instead of a silently lost save).
Documents: multipart upload with size/type limits (extension allow-list + magic bytes, 10 MB, 50 per client), stored as `bytea`
in the same database (atomic with metadata, cascade delete, one backup), download with correct `Content-Type` and
RFC 5987 `Content-Disposition` for Cyrillic/UTF-8 file names. Consistent error JSON everywhere.

Run: `npm install`, set `DATABASE_URL` (a PostgreSQL 16 service is in `docker-compose.yml`), `npm run migrate`, `npm run dev`.
Tests (`npm test`, 18 tests, offline) run on PGlite, a real PostgreSQL engine compiled to WASM, using the production migrations.
A live PostgreSQL server was not available in the build environment, so the `pg` Pool path is untested here.

Author: Максим.
