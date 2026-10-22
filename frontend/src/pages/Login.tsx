import { useEffect, useRef, useState } from "react";
import { api, isNative, saveToken, User } from "../api";

/** Вход через Telegram: ссылка на бота с одноразовым кодом, затем ждём подтверждения. */
export function Login({ onLoggedIn, onServerSettings }: { onLoggedIn: (u: User) => void; onServerSettings: () => void }) {
  const [link, setLink] = useState<{ code: string; url: string } | null>(null);
  const [state, setState] = useState<"idle" | "waiting" | "pending">("idle");
  const [error, setError] = useState("");
  const timer = useRef<number | undefined>(undefined);

  async function newLink() {
    setError("");
    try {
      setLink(await api.authStart());
    } catch (e) {
      setError((e as Error).message);
    }
  }

  // Ссылку готовим заранее: тогда кнопка — обычная ссылка, и браузер не блокирует её как всплывающее окно.
  useEffect(() => {
    newLink();
  }, []);

  useEffect(() => {
    if (!link) return;
    const tick = async () => {
      try {
        const r = await api.authPoll(link.code);
        if (r.status === "ok") {
          saveToken(r.token);
          onLoggedIn(r.user);
          return;
        }
        if (r.status === "expired") {
          setState("idle");
          await newLink();
          return;
        }
        if (r.status === "pending") setState("pending");
      } catch {
        /* нет связи — попробуем на следующем шаге */
      }
      timer.current = window.setTimeout(tick, 2000);
    };
    timer.current = window.setTimeout(tick, 2000);
    return () => window.clearTimeout(timer.current);
  }, [link]);

  return (
    <div className="page login">
      <div className="card">
        <h2>Вход</h2>
        <p className="muted small">
          Войдите через Telegram — на телефоне и на компьютере будет один и тот же аккаунт.
        </p>
        {link ? (
          <a
            className="button primary wide tg"
            href={link.url}
            target="_blank"
            rel="noreferrer"
            onClick={() => setState((s) => (s === "idle" ? "waiting" : s))}
          >
            ✈️ Войти через Telegram
          </a>
        ) : (
          !error && <div className="muted small">Готовлю вход…</div>
        )}
        {state === "waiting" && (
          <div className="notice info">В Telegram откроется бот — нажмите в нём «Запустить» (Start). Вход завершится сам.</div>
        )}
        {state === "pending" && (
          <div className="notice warn">Запрос отправлен владельцу. Как только он нажмёт «Разрешить» в Telegram, вход завершится сам.</div>
        )}
        {error && (
          <>
            <div className="error">{error}</div>
            <button onClick={newLink}>Попробовать снова</button>
          </>
        )}
        {isNative && (
          <button className="link" onClick={onServerSettings}>
            Адрес сервера
          </button>
        )}
      </div>
    </div>
  );
}
