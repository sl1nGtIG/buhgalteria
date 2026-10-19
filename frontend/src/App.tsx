import { useCallback, useEffect, useState } from "react";
import { api, ApiError, needsSetup } from "./api";
import { AddPayment } from "./pages/AddPayment";
import { Payments } from "./pages/Payments";
import { Report } from "./pages/Report";
import { Settings } from "./pages/Settings";
import { Students } from "./pages/Students";

type Tab = "add" | "payments" | "students" | "report" | "settings";

const TABS: { id: Tab; icon: string; label: string }[] = [
  { id: "add", icon: "➕", label: "Оплата" },
  { id: "payments", icon: "🧾", label: "Оплаты" },
  { id: "students", icon: "👥", label: "Ученики" },
  { id: "report", icon: "📊", label: "Отчёт" },
  { id: "settings", icon: "⚙️", label: "Настройки" },
];

export function App() {
  const [tab, setTab] = useState<Tab>(needsSetup() ? "settings" : "add");
  const [pending, setPending] = useState(0);

  const refreshPending = useCallback(() => {
    if (needsSetup()) return;
    api
      .payments({ status: "needs_review" })
      .then((list) => setPending(list.length))
      .catch((e) => {
        if (e instanceof ApiError && e.status === 401) setTab("settings");
      });
  }, []);

  useEffect(refreshPending, [refreshPending]);

  return (
    <div className="app">
      <header>
        <span className="logo">₽</span> Бухгалтерия
      </header>
      <main>
        {tab === "add" && <AddPayment onChanged={refreshPending} />}
        {tab === "payments" && <Payments onChanged={refreshPending} />}
        {tab === "students" && <Students />}
        {tab === "report" && <Report />}
        {tab === "settings" && <Settings onSaved={refreshPending} />}
      </main>
      <nav>
        {TABS.map((t) => (
          <button key={t.id} className={tab === t.id ? "active" : ""} onClick={() => setTab(t.id)}>
            <span className="icon">{t.icon}</span>
            {t.label}
            {t.id === "payments" && pending > 0 && <span className="dot">{pending}</span>}
          </button>
        ))}
      </nav>
    </div>
  );
}
