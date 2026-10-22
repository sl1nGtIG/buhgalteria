import { useEffect, useState } from "react";
import { isNative } from "../api";

const APK_URL = "download/buhgalteria.apk";
const HIDE_KEY = "buh.hideAppBanner";

interface ApkInfo {
  sizeMb: string;
  updated: string;
}

/** Есть ли на сайте свежий APK (его выкладывает сборка GitHub Actions). */
function useApk(): ApkInfo | null {
  const [info, setInfo] = useState<ApkInfo | null>(null);
  useEffect(() => {
    if (isNative) return;
    fetch(APK_URL, { method: "HEAD" })
      .then((r) => {
        const type = r.headers.get("content-type") ?? "";
        if (!r.ok || type.includes("text/html")) return;
        const size = Number(r.headers.get("content-length") ?? 0);
        const modified = r.headers.get("last-modified");
        setInfo({
          sizeMb: size ? `${(size / 1024 / 1024).toFixed(0)} МБ` : "",
          updated: modified ? new Date(modified).toLocaleDateString("ru-RU") : "",
        });
      })
      .catch(() => {});
  }, []);
  return info;
}

function readHidden() {
  try {
    return localStorage.getItem(HIDE_KEY) === "1";
  } catch {
    return false;
  }
}

/** Карточка в «Настройках»: скачать приложение для Android. */
export function AppDownloadCard() {
  const apk = useApk();
  if (!apk) return null;
  return (
    <div className="card">
      <h2>Приложение для Android</h2>
      <p className="muted small">
        Те же возможности, что на сайте, плюс съёмка чеков камерой. Адрес сервера уже настроен.
        {apk.updated && ` Версия от ${apk.updated}.`}
      </p>
      <a className="button primary wide" href={APK_URL} download="buhgalteria.apk">
        ⬇ Скачать APK{apk.sizeMb && ` (${apk.sizeMb})`}
      </a>
      <p className="muted small">
        Откройте скачанный файл на телефоне. Если Android спросит, разрешите установку из этого источника
        (браузера или «Файлов»).
      </p>
    </div>
  );
}

/** Подсказка вверху сайта, если его открыли в браузере на Android. */
export function AppDownloadBanner() {
  const apk = useApk();
  const [hidden, setHidden] = useState(readHidden);
  if (!apk || hidden || !/Android/i.test(navigator.userAgent)) return null;

  function hide() {
    setHidden(true);
    try {
      localStorage.setItem(HIDE_KEY, "1");
    } catch {
      /* без хранилища баннер просто вернётся при следующем открытии */
    }
  }

  return (
    <div className="notice info banner">
      <span>Есть приложение для Android</span>
      <a className="button primary" href={APK_URL} download="buhgalteria.apk">
        Скачать
      </a>
      <button className="link" onClick={hide} aria-label="Скрыть">
        ✕
      </button>
    </div>
  );
}
