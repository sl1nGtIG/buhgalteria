import { useState } from "react";
import { api, fmtDate, money, Payment } from "../api";

const SOURCE = { photo: "фото", text: "текст", manual: "вручную" };

export function PaymentCard({ payment, children }: { payment: Payment; children?: React.ReactNode }) {
  const [showImage, setShowImage] = useState(false);
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
          {SOURCE[payment.source]}
          {payment.has_image && (
            <button className="link" onClick={() => setShowImage(!showImage)}>
              {showImage ? "скрыть чек" : "показать чек"}
            </button>
          )}
        </dd>
      </dl>
      {showImage && <img className="receipt" src={api.imageUrl(payment.id)} alt="Чек" />}
      {children}
    </div>
  );
}
