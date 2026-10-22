import { useEffect, useState } from "react";
import { api, currentMonth, money, Payment } from "../api";
import { Assign } from "../components/Assign";
import { PaymentCard } from "../components/PaymentCard";

export function Payments({ onChanged }: { onChanged: () => void }) {
  const [status, setStatus] = useState("needs_review");
  const [month, setMonth] = useState(currentMonth());
  const [items, setItems] = useState<Payment[]>([]);
  const [error, setError] = useState("");
  const [editing, setEditing] = useState<number | null>(null);

  async function load() {
    setError("");
    try {
      setItems(await api.payments({ status, month: status === "needs_review" ? "" : month }));
    } catch (e) {
      setError((e as Error).message);
    }
  }

  useEffect(() => {
    load();
  }, [status, month]);

  function updated(p: Payment) {
    setEditing(null);
    setItems((list) => (status === "needs_review" ? list.filter((x) => x.id !== p.id) : list.map((x) => (x.id === p.id ? p : x))));
    onChanged();
  }

  function replace(p: Payment) {
    setItems((list) => list.map((x) => (x.id === p.id ? p : x)));
    onChanged();
  }

  async function remove(p: Payment) {
    if (!confirm(`Удалить оплату ${money(p.amount)}?`)) return;
    try {
      await api.deletePayment(p.id);
      setItems((list) => list.filter((x) => x.id !== p.id));
      onChanged();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  const total = items.reduce((s, p) => s + (p.amount ?? 0), 0);

  return (
    <div className="page">
      <div className="card filters">
        <div className="segmented">
          <button className={status === "needs_review" ? "active" : ""} onClick={() => setStatus("needs_review")}>
            На проверке
          </button>
          <button className={status === "confirmed" ? "active" : ""} onClick={() => setStatus("confirmed")}>
            Зафиксированные
          </button>
          <button className={status === "" ? "active" : ""} onClick={() => setStatus("")}>
            Все
          </button>
        </div>
        {status !== "needs_review" && (
          <div className="row">
            <input type="month" value={month} onChange={(e) => setMonth(e.target.value)} />
            <a className="button" href={api.exportUrl(month)} target="_blank" rel="noreferrer">
              ⬇ Excel (CSV)
            </a>
          </div>
        )}
        <div className="muted small">
          {items.length} шт. на сумму {money(total)}
        </div>
      </div>
      {error && <div className="error">{error}</div>}
      {items.length === 0 && !error && (
        <div className="empty">{status === "needs_review" ? "Все оплаты разобраны 🎉" : "Оплат нет"}</div>
      )}
      {items.map((p) => (
        <PaymentCard key={p.id} payment={p} onChange={replace}>
          {p.status === "needs_review" || editing === p.id ? (
            <Assign payment={p} onDone={updated} />
          ) : (
            <div className="row">
              <button className="link" onClick={() => setEditing(p.id)}>изменить привязку</button>
            </div>
          )}
          <div className="row end">
            <button className="link danger" onClick={() => remove(p)}>удалить</button>
          </div>
        </PaymentCard>
      ))}
    </div>
  );
}
