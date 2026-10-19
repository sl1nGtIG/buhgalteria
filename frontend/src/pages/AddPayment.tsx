import { useRef, useState } from "react";
import { api, Payment, RecognizeResult, shrinkImage } from "../api";
import { Assign } from "../components/Assign";
import { PaymentCard } from "../components/PaymentCard";

export function AddPayment({ onChanged }: { onChanged: () => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState("");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<RecognizeResult | null>(null);
  const cameraRef = useRef<HTMLInputElement>(null);
  const galleryRef = useRef<HTMLInputElement>(null);

  function pick(f: File | undefined) {
    if (!f) return;
    setFile(f);
    setPreview(URL.createObjectURL(f));
    setResult(null);
    setError("");
  }

  function reset() {
    setFile(null);
    setPreview("");
    setText("");
    if (cameraRef.current) cameraRef.current.value = "";
    if (galleryRef.current) galleryRef.current.value = "";
  }

  async function submit() {
    setBusy(true);
    setError("");
    setResult(null);
    try {
      const blob = file ? await shrinkImage(file) : null;
      const r = await api.recognize(blob, text);
      setResult(r);
      reset();
      onChanged();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  function assigned(p: Payment) {
    setResult((r) => r && { ...r, payment: p, auto_confirmed: true, message: "Оплата зафиксирована" });
    onChanged();
  }

  return (
    <div className="page">
      <div className="card">
        <h2>Новая оплата</h2>
        <p className="muted small">
          Сфотографируйте чек или загрузите скриншот перевода — система сама найдёт сумму, дату и
          плательщика и привяжет оплату к ученику или родителю. Можно просто написать текстом:
          «Сидоров Саша 5000 за октябрь».
        </p>

        <div className="row">
          <button onClick={() => cameraRef.current?.click()}>📷 Сфотографировать</button>
          <button onClick={() => galleryRef.current?.click()}>🖼 Выбрать фото</button>
        </div>
        <input ref={cameraRef} type="file" accept="image/*" capture="environment" hidden onChange={(e) => pick(e.target.files?.[0])} />
        <input ref={galleryRef} type="file" accept="image/*" hidden onChange={(e) => pick(e.target.files?.[0])} />

        {preview && (
          <div className="preview">
            <img src={preview} alt="Чек" />
            <button className="link" onClick={() => { setFile(null); setPreview(""); }}>убрать фото</button>
          </div>
        )}

        <textarea
          rows={3}
          placeholder={file ? "Комментарий к фото (необязательно), например «за Машу»" : "Например: Иванова Маша 4500 15.10"}
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
        <button className="primary wide" disabled={busy || (!file && !text.trim())} onClick={submit}>
          {busy ? "Распознаю…" : "Зафиксировать оплату"}
        </button>
        {error && <div className="error">{error}</div>}
      </div>

      {result && (
        <>
          <div className={`notice ${result.auto_confirmed ? "ok" : result.duplicate_of ? "warn" : "info"}`}>
            {result.message}
          </div>
          <PaymentCard payment={result.payment}>
            {result.payment.status === "needs_review" && !result.duplicate_of && (
              <Assign payment={result.payment} candidates={result.candidates} onDone={assigned} />
            )}
          </PaymentCard>
        </>
      )}
    </div>
  );
}
