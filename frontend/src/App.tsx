import { useCallback, useEffect, useState } from "react";
import { api, ApiError, needsSetup, UNAUTHORIZED_EVENT, User } from "./api";
import { AppDownloadBanner } from "./components/AppDownload";
import { AddPayment } from "./pages/AddPayment";
import { Login } from "./pages/Login";
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
  const [volatile, setVolatile] = useState(false);
  const [needLogin, setNeedLogin] = useState(false);
  const [user, setUser] = useState<User | null>(null);

  // Сервер ответил 401: при входе через Telegram показываем экран входа, иначе — настройки с кодом.
  useEffect(() => {
    const onUnauthorized = () =>
      api
        .health()
        .then((h) => (h.auth_mode === "telegram" ? setNeedLogin(true) : setTab("settings")))
        .catch(() => setTab("settings"));
    window.addEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
    if (!needsSetup()) api.me().then((r) => setUser(r.user)).catch(() => {});
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
  }, []);

  const refreshPending = useCallback(() => {
    if (needsSetup()) return;
    api
      .payments({ status: "needs_review" })
      .then((list) => setPending(list.length))
      .catch((e) => {
        if (e instanceof ApiError && e.status === 401) return; // экран входа покажет обработчик 401
      });
  }, []);

  useEffect(refreshPending, [refreshPending]);
  useEffect(() => {
    if (!needsSetup()) api.health().then((h) => setVolatile(!h.persistent_storage)).catch(() => {});
  }, [tab]);

  if (needLogin) {
    return (
      <div className="app">
        <header>
          <span className="logo">₽</span> Бухгалтерия
        </header>
        <main>
          <Login
            onLoggedIn={(u) => {
              setUser(u);
              setNeedLogin(false);
              setTab("add");
              refreshPending();
            }}
            onServerSettings={() => {
              setNeedLogin(false);
              setTab("settings");
            }}
          />
        </main>
      </div>
    );
  }

  return (
    <div className="app">
      <header>
        <span className="logo">₽</span> Бухгалтерия
        {user && <span className="user">{user.name}</span>}
      </header>
      <main>
        {volatile && (
          <div className="error">
            Сервер работает без базы данных — всё введённое пропадёт при его перезапуске. Подключите Postgres
            (на Vercel: Storage → Neon) и сделайте Redeploy.
          </div>
        )}
        {tab === "add" && <AppDownloadBanner />}
        {tab === "add" && <AddPayment onChanged={refreshPending} />}
        {tab === "payments" && <Payments onChanged={refreshPending} />}
        {tab === "students" && <Students />}
        {tab === "report" && <Report />}
        {tab === "settings" && <Settings onSaved={refreshPending} user={user} />}
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
