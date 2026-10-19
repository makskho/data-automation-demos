import type { ReactNode } from "react";

export const metadata = { title: "Мини-CRM: клиенты и документы" };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="ru">
      <body style={{ fontFamily: "system-ui, sans-serif", maxWidth: 860, margin: "2rem auto", padding: "0 1rem" }}>
        {children}
      </body>
    </html>
  );
}
