import { useState } from "react";
import { api, getSettings, Health, isNative, saveSettings } from "../api";

export function Settings({ onSaved }: { onSaved: () => void }) {
  const initial = getSettings();
  const [serverUrl, setServerUrl] = useState(initial.serverUrl);
  const [token, setToken] = useState(initial.token);
  const [health, setHealth] = useState<Health | null>(null);
  const [status, setStatus] = useState<{ ok: boolean; text: string } | null>(null);
  const [bot, setBot] = useState<{ ok: boolean; text: string } | null>(null);

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

  async function connectBot() {
    setBot(null);
    try {
      const r = await api.telegramSetup();
      setBot({ ok: true, text: `Бот @${r.bot} подключён. Напишите ему /start.` });
    } catch (e) {
      setBot({ ok: false, text: (e as Error).message });
    }
  }

  return (
    <div className="page">
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
        <label>
          Код доступа
          <input type="password" value={token} onChange={(e) => setToken(e.target.value)} />
        </label>
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
        {health?.telegram_bot && health.telegram_mode === "webhook" && (
          <>
            <button onClick={connectBot}>Подключить Telegram-бота к этому сайту</button>
            {bot && <div className={bot.ok ? "notice ok" : "error"}>{bot.text}</div>}
          </>
        )}
      </div>
    </div>
  );
}
