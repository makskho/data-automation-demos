-- Production schema (PostgreSQL). The same file is applied in tests to a real PostgreSQL engine (PGlite).
CREATE TABLE IF NOT EXISTS clients (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name        text NOT NULL CHECK (length(btrim(name)) > 0),
  email       text NOT NULL,
  phone       text,
  company     text,
  notes       text,
  created_at  timestamptz NOT NULL DEFAULT date_trunc('milliseconds', clock_timestamp()),
  updated_at  timestamptz NOT NULL DEFAULT date_trunc('milliseconds', clock_timestamp())
);

-- e-mail is unique case-insensitively: "Ivan@x.ru" and "ivan@x.ru" are the same client
CREATE UNIQUE INDEX IF NOT EXISTS clients_email_lower_uq ON clients (lower(email));
CREATE INDEX IF NOT EXISTS clients_created_idx ON clients (created_at DESC, id);

CREATE TABLE IF NOT EXISTS documents (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  client_id     uuid NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
  filename      text NOT NULL,
  content_type  text NOT NULL,
  size          integer NOT NULL CHECK (size > 0),
  sha256        text NOT NULL,
  data          bytea NOT NULL,
  created_at    timestamptz NOT NULL DEFAULT date_trunc('milliseconds', clock_timestamp())
);

CREATE INDEX IF NOT EXISTS documents_client_idx ON documents (client_id, created_at DESC);
