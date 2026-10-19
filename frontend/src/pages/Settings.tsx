import { useState } from "react";
import { api, getSettings, Health, isNative, saveSettings } from "../api";

export function Settings({ onSaved }: { onSaved: () => void }) {
  const initial = getSettings();
  const [serverUrl, setServerUrl] = useState(initial.serverUrl);
  const [token, setToken] = useState(initial.token);
  const [status, setStatus] = useState<{ ok: boolean; text: string } | null>(null);

  async function check() {
    saveSettings({ serverUrl, token });
    setStatus(null);
    try {
      const h: Health = await api.health();
      await api.students(); // проверяет код доступа
      setStatus({
        ok: true,
        text: h.photo_recognition
          ? "Подключено. Распознавание фото включено."
          : "Подключено. Распознавание фото выключено на сервере — работает только ввод текстом.",
      });
      onSaved();
    } catch (e) {
      setStatus({ ok: false, text: (e as Error).message });
    }
  }

  return (
    <div className="page">
      <div className="card">
        <h2>Настройки</h2>
        <label>
          Адрес сервера
          <input
            placeholder={isNative ? "https://buh.example.ru" : "пусто — этот же сайт"}
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
      </div>
    </div>
  );
}
