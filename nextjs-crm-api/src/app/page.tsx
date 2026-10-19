"use client";
import { useCallback, useEffect, useState } from "react";

type Client = { id: string; name: string; email: string; company: string | null; updatedAt: string };
type Doc = { id: string; filename: string; size: number };

const api = async (url: string, init?: RequestInit) => {
  const res = await fetch(url, init);
  const body = res.status === 204 ? null : await res.json();
  if (!res.ok) throw new Error(body?.error?.message ?? res.statusText);
  return body;
};

export default function Page() {
  const [q, setQ] = useState("");
  const [clients, setClients] = useState<Client[]>([]);
  const [total, setTotal] = useState(0);
  const [active, setActive] = useState<Client | null>(null);
  const [docs, setDocs] = useState<Doc[]>([]);
  const [msg, setMsg] = useState("");

  const load = useCallback(async () => {
    const r = await api(`/api/clients?pageSize=20&q=${encodeURIComponent(q)}`);
    setClients(r.items);
    setTotal(r.total);
  }, [q]);
  useEffect(() => { load().catch((e) => setMsg(e.message)); }, [load]);

  const open = async (c: Client) => {
    setActive(c);
    setDocs((await api(`/api/clients/${c.id}/documents`)).items);
  };

  const addClient = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    try {
      await api("/api/clients", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ name: f.get("name"), email: f.get("email"), company: f.get("company") }),
      });
      e.currentTarget.reset();
      setMsg("Клиент добавлен");
      await load();
    } catch (err) { setMsg((err as Error).message); }
  };

  const upload = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!active) return;
    try {
      await api(`/api/clients/${active.id}/documents`, { method: "POST", body: new FormData(e.currentTarget) });
      e.currentTarget.reset();
      setMsg("Файл загружен");
      await open(active);
    } catch (err) { setMsg((err as Error).message); }
  };

  const remove = async (d: Doc) => {
    await api(`/api/documents/${d.id}`, { method: "DELETE" });
    if (active) await open(active);
  };

  return (
    <main>
      <h1>Мини-CRM</h1>
      {msg && <p role="status"><b>{msg}</b></p>}
      <input placeholder="Поиск: имя, e-mail, компания" value={q} onChange={(e) => setQ(e.target.value)} style={{ width: "100%" }} />
      <p>Найдено: {total}</p>
      <ul>
        {clients.map((c) => (
          <li key={c.id}>
            <button onClick={() => open(c)}>{c.name}</button> {c.email} {c.company && `· ${c.company}`}
          </li>
        ))}
      </ul>
      <form onSubmit={addClient}>
        <h3>Новый клиент</h3>
        <input name="name" placeholder="Имя" required /> <input name="email" type="email" placeholder="E-mail" required />{" "}
        <input name="company" placeholder="Компания" /> <button>Добавить</button>
      </form>
      {active && (
        <section>
          <h3>Документы: {active.name}</h3>
          <ul>
            {docs.map((d) => (
              <li key={d.id}>
                <a href={`/api/documents/${d.id}`}>{d.filename}</a> ({Math.ceil(d.size / 1024)} КБ){" "}
                <button onClick={() => remove(d)}>Удалить</button>
              </li>
            ))}
          </ul>
          <form onSubmit={upload}>
            <input type="file" name="file" required /> <button>Загрузить</button>
          </form>
        </section>
      )}
    </main>
  );
}
