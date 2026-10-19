import { useEffect, useState } from "react";
import { api, Candidate, Parent, Payment, Student } from "../api";

interface Props {
  payment: Payment;
  candidates?: Candidate[];
  onDone: (p: Payment) => void;
}

/** Выбор, к кому относится оплата: подсказки системы или любой ученик/родитель из списка. */
export function Assign({ payment, candidates: initial, onDone }: Props) {
  const [candidates, setCandidates] = useState<Candidate[]>(initial ?? []);
  const [students, setStudents] = useState<Student[]>([]);
  const [parents, setParents] = useState<Parent[]>([]);
  const [choice, setChoice] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!initial) api.candidates(payment.id).then(setCandidates).catch(() => {});
    api.students().then(setStudents).catch(() => {});
    api.parents().then(setParents).catch(() => {});
  }, [payment.id, initial]);

  async function assign(student_id: number | null, parent_id: number | null) {
    setBusy(true);
    setError("");
    try {
      onDone(await api.updatePayment(payment.id, { student_id, parent_id }));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  function assignChoice() {
    const [kind, id] = choice.split(":");
    if (kind === "s") {
      const s = students.find((x) => x.id === Number(id));
      // Если у ученика один родитель — привязываем и его, чтобы запомнить плательщика.
      assign(Number(id), s && s.parents.length === 1 ? s.parents[0].id : null);
    } else if (kind === "p") assign(null, Number(id));
  }

  return (
    <div className="assign">
      {candidates.length > 0 && (
        <>
          <div className="muted small">Возможно, это:</div>
          <div className="chips">
            {candidates.map((c, i) => (
              <button
                key={i}
                className="chip"
                disabled={busy}
                title={c.reasons.join("; ")}
                onClick={() => assign(c.student?.id ?? null, c.parent?.id ?? null)}
              >
                {c.student ? c.student.full_name : `${c.parent?.full_name} (родитель)`}
                {c.student && c.parent && <span className="muted"> · {c.parent.full_name}</span>}
                <span className="score">{Math.round(c.score * 100)}%</span>
              </button>
            ))}
          </div>
        </>
      )}
      <div className="row">
        <select value={choice} onChange={(e) => setChoice(e.target.value)}>
          <option value="">Выбрать вручную…</option>
          <optgroup label="Ученики">
            {students.map((s) => (
              <option key={s.id} value={`s:${s.id}`}>
                {s.full_name}
                {s.group_name ? ` (${s.group_name})` : ""}
              </option>
            ))}
          </optgroup>
          <optgroup label="Родители">
            {parents.map((p) => (
              <option key={p.id} value={`p:${p.id}`}>
                {p.full_name}
              </option>
            ))}
          </optgroup>
        </select>
        <button className="primary" disabled={!choice || busy} onClick={assignChoice}>
          Привязать
        </button>
      </div>
      {error && <div className="error">{error}</div>}
    </div>
  );
}
