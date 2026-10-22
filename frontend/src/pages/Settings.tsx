import { useEffect, useState } from "react";
import { api, getSettings, Health, isNative, saveSettings, saveToken, User } from "../api";
import { AppDownloadCard } from "../components/AppDownload";

export function Settings({ onSaved, user }: { onSaved: () => void; user: User | null }) {
  const initial = getSettings();
  const [serverUrl, setServerUrl] = useState(initial.serverUrl);
  const [token, setToken] = useState(initial.token);
  const [health, setHealth] = useState<Health | null>(null);
  const [status, setStatus] = useState<{ ok: boolean; text: string } | null>(null);
  const [mode, setMode] = useState<Health["auth_mode"] | null>(null);

  useEffect(() => {
    api.health().then((h) => setMode(h.auth_mode)).catch(() => {});
  }, []);

  async function check() {
    saveSettings({ serverUrl, token });
    setStatus(null);
    setHealth(null);
    try {
      const h = await api.health();
      await api.students(); // проверяет код доступа
      setHealth(h);
      setStatus({ ok: true, text: "Подключено." });
      onSaved();
    } catch (e) {
      setStatus({ ok: false, text: (e as Error).message });
    }
  }

  // На сайте адрес сервера — это сам сайт; настраивать нечего, если нет кода доступа.
  const showServer = isNative || mode === "token";

  return (
    <div className="page">
      {showServer && (
        <div className="card">
          <h2>Настройки</h2>
          <label>
            Адрес сервера
            <input
              placeholder={isNative ? "https://buhgalteria.vercel.app" : "пусто — этот же сайт"}
              value={serverUrl}
              inputMode="url"
              autoCapitalize="off"
              onChange={(e) => setServerUrl(e.target.value)}
            />
          </label>
          {mode === "token" && (
            <label>
              Код доступа
              <input type="password" value={token} onChange={(e) => setToken(e.target.value)} />
            </label>
          )}
          <button className="primary wide" onClick={check}>
            Сохранить и проверить
          </button>
          {status && <div className={status.ok ? "notice ok" : "error"}>{status.text}</div>}
          {health && (
            <ul className="plain small">
              <li>Фото и PDF читаются прямо на этом устройстве, без внешних сервисов.</li>
              {health.ai_recognition && <li>На сервере включено распознавание нейросетью (точнее на плохих фото).</li>}
              {!health.persistent_storage && (
                <li className="debt">
                  База данных не подключена: данные пропадут при перезапуске сервера. Подключите Postgres
                  (на Vercel: Storage → Neon).
                </li>
              )}
            </ul>
          )}
        </div>
      )}
      {user && <Account user={user} />}
      {!showServer && !user && <div className="card muted small">Вход не настроен: сайт открыт без пароля.</div>}
      <AppDownloadCard />
    </div>
  );
}

function Account({ user }: { user: User }) {
  const [users, setUsers] = useState<User[]>([]);
  const [error, setError] = useState("");

  async function load() {
    if (!user.is_owner) return;
    try {
      setUsers(await api.users());
    } catch (e) {
      setError((e as Error).message);
    }
  }

  useEffect(() => {
    load();
  }, [user.id]);

  function logout() {
    saveToken("");
    window.location.reload();
  }

  async function act(fn: () => Promise<unknown>) {
    setError("");
    try {
      await fn();
      await load();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <div className="card">
      <h2>Аккаунт</h2>
      <div>
        Вы вошли через Telegram как <b>{user.name}</b>
        {user.username && <span className="muted"> @{user.username}</span>}
        {user.is_owner && <span className="badge confirmed"> владелец</span>}
      </div>
      {user.is_owner && users.length > 1 && (
        <>
          <div className="muted small">Доступ к бухгалтерии:</div>
          <ul className="plain">
            {users
              .filter((u) => u.id !== user.id)
              .map((u) => (
                <li key={u.id} className="row">
                  <span className="grow">
                    {u.name}
                    {u.username && <span className="muted"> @{u.username}</span>}
                    {!u.approved && <span className="badge needs_review"> ждёт разрешения</span>}
                  </span>
                  {!u.approved && (
                    <button className="link" onClick={() => act(() => api.approveUser(u.id))}>
                      разрешить
                    </button>
                  )}
                  <button className="link danger" onClick={() => confirm(`Убрать доступ у ${u.name}?`) && act(() => api.removeUser(u.id))}>
                    убрать
                  </button>
                </li>
              ))}
          </ul>
        </>
      )}
      {error && <div className="error">{error}</div>}
      <button onClick={logout}>Выйти</button>
    </div>
  );
}
