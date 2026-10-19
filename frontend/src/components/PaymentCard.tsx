import { useState } from "react";
import { api, fmtDate, money, Payment } from "../api";

const SOURCE = { photo: "фото", text: "текст", manual: "вручную", telegram: "Telegram" };

interface Props {
  payment: Payment;
  /** Если передан — в карточке можно исправить сумму, дату и назначение. */
  onChange?: (p: Payment) => void;
  children?: React.ReactNode;
}

export function PaymentCard({ payment, onChange, children }: Props) {
  const [showImage, setShowImage] = useState(false);
  const [editing, setEditing] = useState(false);
  const who = payment.student?.full_name ?? (payment.parent ? `${payment.parent.full_name} (родитель)` : null);

  return (
    <div className={`card payment ${payment.status}`}>
      <div className="payment-head">
        <div className="amount">{money(payment.amount)}</div>
        <span className={`badge ${payment.status}`}>
          {payment.status === "confirmed" ? "зафиксирована" : "на проверке"}
        </span>
      </div>
      <div className="who">{who ?? <span className="muted">не привязана</span>}</div>
      {payment.student && payment.parent && <div className="muted small">родитель: {payment.parent.full_name}</div>}

      {editing && onChange ? (
        <EditForm payment={payment} onCancel={() => setEditing(false)} onSaved={(p) => { setEditing(false); onChange(p); }} />
      ) : (
        <dl className="details">
          <dt>Дата</dt>
          <dd>{fmtDate(payment.paid_at)}</dd>
          {payment.payer_name && (
            <>
              <dt>Плательщик</dt>
              <dd>{payment.payer_name}</dd>
            </>
          )}
          {payment.purpose && (
            <>
              <dt>Назначение</dt>
              <dd>{payment.purpose}</dd>
            </>
          )}
          {payment.bank && (
            <>
              <dt>Банк</dt>
              <dd>{payment.bank}</dd>
            </>
          )}
          <dt>Источник</dt>
          <dd>
            {SOURCE[payment.source] ?? payment.source}
            {payment.attachment === "image" && (
              <button className="link" onClick={() => setShowImage(!showImage)}>
                {showImage ? "скрыть чек" : "показать чек"}
              </button>
            )}
            {payment.attachment === "pdf" && (
              <a className="link" href={api.imageUrl(payment.id)} target="_blank" rel="noreferrer">
                открыть PDF
              </a>
            )}
          </dd>
        </dl>
      )}
      {showImage && <img className="receipt" src={api.imageUrl(payment.id)} alt="Чек" />}
      {onChange && !editing && (
        <div className="row">
          <button className="link" onClick={() => setEditing(true)}>исправить сумму или дату</button>
        </div>
      )}
      {children}
    </div>
  );
}

function EditForm({ payment, onCancel, onSaved }: { payment: Payment; onCancel: () => void; onSaved: (p: Payment) => void }) {
  const [amount, setAmount] = useState(payment.amount != null ? String(payment.amount) : "");
  const [paidAt, setPaidAt] = useState(payment.paid_at ?? "");
  const [purpose, setPurpose] = useState(payment.purpose ?? "");
  const [error, setError] = useState("");

  async function save() {
    const value = Number(amount.replace(/\s/g, "").replace(",", "."));
    if (!value || value <= 0) {
      setError("Введите сумму");
      return;
    }
    try {
      onSaved(await api.updatePayment(payment.id, { amount: value, paid_at: paidAt || null, purpose: purpose || null }));
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <div className="edit">
      <div className="row">
        <label className="grow">
          Сумма, ₽
          <input inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} />
        </label>
        <label className="grow">
          Дата
          <input type="date" value={paidAt} onChange={(e) => setPaidAt(e.target.value)} />
        </label>
      </div>
      <label>
        Назначение
        <input value={purpose} onChange={(e) => setPurpose(e.target.value)} />
      </label>
      <div className="row">
        <button className="primary" onClick={save}>Сохранить</button>
        <button onClick={onCancel}>Отмена</button>
      </div>
      {error && <div className="error">{error}</div>}
    </div>
  );
}
