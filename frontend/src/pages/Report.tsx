import { Fragment, useEffect, useState } from "react";
import { api, currentMonth, fmtDate, money, MonthReport, Payment } from "../api";

export function Report() {
  const [month, setMonth] = useState(currentMonth());
  const [report, setReport] = useState<MonthReport | null>(null);
  const [onlyDebtors, setOnlyDebtors] = useState(false);
  const [error, setError] = useState("");
  const [open, setOpen] = useState<number | null>(null);
  const [history, setHistory] = useState<Payment[] | null>(null);

  function toggle(studentId: number) {
    if (open === studentId) {
      setOpen(null);
      return;
    }
    setOpen(studentId);
    setHistory(null);
    api.payments({ student_id: String(studentId) }).then(setHistory).catch((e) => setError(e.message));
  }

  useEffect(() => {
    setError("");
    api.report(month).then(setReport).catch((e) => setError(e.message));
  }, [month]);

  const rows = report?.rows.filter((r) => !onlyDebtors || r.debt > 0) ?? [];
  const debt = report?.rows.reduce((s, r) => s + r.debt, 0) ?? 0;

  return (
    <div className="page">
      <div className="card filters">
        <div className="row">
          <input type="month" value={month} onChange={(e) => setMonth(e.target.value)} />
          <label className="check">
            <input type="checkbox" checked={onlyDebtors} onChange={(e) => setOnlyDebtors(e.target.checked)} />
            только должники
          </label>
        </div>
        {report && (
          <div className="stats">
            <div>
              <div className="muted small">Получено</div>
              <div className="stat">{money(report.total)}</div>
            </div>
            <div>
              <div className="muted small">Долг</div>
              <div className="stat debt">{money(debt)}</div>
            </div>
            <div>
              <div className="muted small">На проверке</div>
              <div className="stat">{report.needs_review}</div>
            </div>
          </div>
        )}
      </div>
      {error && <div className="error">{error}</div>}
      {report && (
        <div className="card">
          <table>
            <thead>
              <tr>
                <th>Ученик</th>
                <th className="num">Оплачено</th>
                <th className="num">Долг</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <Fragment key={r.student.id}>
                  <tr className="clickable" onClick={() => toggle(r.student.id)}>
                    <td>
                      {r.student.full_name}
                      {r.student.group_name && <div className="muted small">{r.student.group_name}</div>}
                    </td>
                    <td className="num">{money(r.paid)}</td>
                    <td className={`num ${r.debt > 0 ? "debt" : "paid"}`}>{r.debt > 0 ? money(r.debt) : "✓"}</td>
                  </tr>
                  {open === r.student.id && (
                    <tr className="history">
                      <td colSpan={3}>
                        {history === null ? (
                          <span className="muted small">Загрузка…</span>
                        ) : history.length === 0 ? (
                          <span className="muted small">Оплат ещё не было</span>
                        ) : (
                          <ul className="plain small">
                            {history.map((p) => (
                              <li key={p.id}>
                                {fmtDate(p.paid_at)} — <b>{money(p.amount)}</b>
                                {p.status === "needs_review" && <span className="muted"> (на проверке)</span>}
                              </li>
                            ))}
                          </ul>
                        )}
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
          {report.parent_only.length > 0 && (
            <>
              <h3>Оплаты от родителей без указания ребёнка</h3>
              <ul className="plain">
                {report.parent_only.map((p) => (
                  <li key={p.parent.id}>
                    {p.parent.full_name}: <b>{money(p.paid)}</b>
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      )}
    </div>
  );
}
