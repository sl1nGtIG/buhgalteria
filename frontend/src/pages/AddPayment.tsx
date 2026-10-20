import { useRef, useState } from "react";
import { api, Payment, RecognizeItem, shrinkImage } from "../api";
import { readReceipt } from "../ocr";

/** Vercel не принимает запросы больше 4,5 МБ: большие PDF отправляем только текстом. */
const MAX_UPLOAD = 4 * 1024 * 1024;
import { Assign } from "../components/Assign";
import { PaymentCard } from "../components/PaymentCard";

interface Picked {
  file: File;
  preview: string;
}

interface Outcome {
  title: string;
  message: string;
  items: RecognizeItem[];
  error?: string;
}

export function AddPayment({ onChanged }: { onChanged: () => void }) {
  const [picked, setPicked] = useState<Picked[]>([]);
  const [text, setText] = useState("");
  const [progress, setProgress] = useState("");
  const [error, setError] = useState("");
  const [outcomes, setOutcomes] = useState<Outcome[]>([]);
  const cameraRef = useRef<HTMLInputElement>(null);
  const galleryRef = useRef<HTMLInputElement>(null);

  function pick(files: FileList | null) {
    if (!files?.length) return;
    const next = Array.from(files).map((file) => ({
      file,
      preview: file.type.startsWith("image/") ? URL.createObjectURL(file) : "",
    }));
    setPicked((p) => [...p, ...next]);
    setError("");
    if (cameraRef.current) cameraRef.current.value = "";
    if (galleryRef.current) galleryRef.current.value = "";
  }

  function unpick(i: number) {
    setPicked((p) => p.filter((_, j) => j !== i));
  }

  async function submit() {
    setError("");
    setOutcomes([]);
    const results: Outcome[] = [];
    try {
      if (picked.length === 0) {
        setProgress("Распознаю…");
        const r = await api.recognize(null, text);
        results.push({ title: "Текст", message: r.message, items: r.items });
      }
      for (const [i, p] of picked.entries()) {
        const prefix = picked.length > 1 ? `${i + 1} из ${picked.length}: ` : "";
        try {
          const upload = await shrinkImage(p.file);
          // Чек читается прямо на устройстве; сервер получает готовый текст и сам файл.
          let ocrText = "";
          try {
            ocrText = await readReceipt(upload, (m) => setProgress(prefix + m));
          } catch {
            // Не получилось прочитать здесь — сервер попробует сам (если умеет).
          }
          setProgress(prefix + "Ищу ученика…");
          const r = await api.recognize(upload.size <= MAX_UPLOAD ? upload : null, text, ocrText);
          results.push({ title: p.file.name, message: r.message, items: r.items });
        } catch (e) {
          results.push({ title: p.file.name, message: "", items: [], error: (e as Error).message });
        }
        setOutcomes([...results]);
      }
      setOutcomes(results);
      setPicked([]);
      setText("");
      onChanged();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setProgress("");
    }
  }

  function replace(p: Payment) {
    setOutcomes((list) =>
      list.map((o) => ({
        ...o,
        items: o.items.map((it) => (it.payment.id === p.id ? { ...it, payment: p, auto_confirmed: p.status === "confirmed" } : it)),
      })),
    );
    onChanged();
  }

  const busy = progress !== "";
  const many = picked.length > 1;

  return (
    <div className="page">
      <div className="card">
        <h2>Новая оплата</h2>
        <p className="muted small">
          Сфотографируйте чек, загрузите скриншот перевода, PDF-квитанцию или выписку с несколькими
          переводами. Система сама найдёт сумму, дату и плательщика и привяжет оплату к ученику или
          родителю. Можно просто написать текстом, по одной оплате в строке: «Сидоров Саша 5000».
        </p>

        <div className="row">
          <button onClick={() => cameraRef.current?.click()} disabled={busy}>📷 Сфотографировать</button>
          <button onClick={() => galleryRef.current?.click()} disabled={busy}>🖼 Фото или PDF</button>
        </div>
        <input ref={cameraRef} type="file" accept="image/*" capture="environment" hidden onChange={(e) => pick(e.target.files)} />
        <input ref={galleryRef} type="file" accept="image/*,application/pdf" multiple hidden onChange={(e) => pick(e.target.files)} />

        {picked.length > 0 && (
          <div className="thumbs">
            {picked.map((p, i) => (
              <div key={i} className="thumb">
                {p.preview ? <img src={p.preview} alt="" /> : <div className="pdf">PDF</div>}
                <button className="remove" aria-label="Убрать" onClick={() => unpick(i)} disabled={busy}>×</button>
              </div>
            ))}
          </div>
        )}

        <textarea
          rows={3}
          placeholder={
            picked.length
              ? `Комментарий к ${many ? "файлам" : "фото"} (необязательно), например «за Машу»`
              : "Например: Иванова Маша 4500 15.10"
          }
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
        <button className="primary wide" disabled={busy || (!picked.length && !text.trim())} onClick={submit}>
          {progress || (many ? `Распознать ${picked.length} файла(ов)` : "Зафиксировать оплату")}
        </button>
        {error && <div className="error">{error}</div>}
      </div>

      {outcomes.map((o, i) => (
        <div key={i} className="page">
          {outcomes.length > 1 && <div className="muted small">{o.title}</div>}
          {o.error ? (
            <div className="error">{o.error}</div>
          ) : (
            <div className={`notice ${noticeKind(o.items)}`}>{o.message}</div>
          )}
          {o.items.map((it) => (
            <PaymentCard key={it.payment.id} payment={it.payment} onChange={replace}>
              {it.payment.status === "needs_review" && !it.duplicate_of && (
                <Assign payment={it.payment} candidates={it.candidates} onDone={replace} />
              )}
            </PaymentCard>
          ))}
        </div>
      ))}
    </div>
  );
}

function noticeKind(items: RecognizeItem[]) {
  if (items.every((i) => i.duplicate_of)) return "warn";
  if (items.every((i) => i.auto_confirmed || i.duplicate_of)) return "ok";
  return "info";
}
