import { useEffect, useState } from "react";
import { api, money, Parent, Student } from "../api";

interface Form {
  id: number | null;
  full_name: string;
  group_name: string;
  monthly_fee: string;
  parent_ids: number[];
  new_parent_name: string;
  new_parent_phone: string;
}

const EMPTY: Form = {
  id: null,
  full_name: "",
  group_name: "",
  monthly_fee: "",
  parent_ids: [],
  new_parent_name: "",
  new_parent_phone: "",
};

export function Students() {
  const [students, setStudents] = useState<Student[]>([]);
  const [parents, setParents] = useState<Parent[]>([]);
  const [form, setForm] = useState<Form | null>(null);
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");

  async function load() {
    try {
      const [s, p] = await Promise.all([api.students(), api.parents()]);
      setStudents(s);
      setParents(p);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  useEffect(() => {
    load();
  }, []);

  function edit(s: Student) {
    setForm({
      id: s.id,
      full_name: s.full_name,
      group_name: s.group_name ?? "",
      monthly_fee: String(s.monthly_fee || ""),
      parent_ids: s.parents.map((p) => p.id),
      new_parent_name: "",
      new_parent_phone: "",
    });
  }

  async function save() {
    if (!form) return;
    setError("");
    const body = {
      full_name: form.full_name,
      group_name: form.group_name || null,
      monthly_fee: Number(form.monthly_fee.replace(",", ".")) || 0,
      parent_ids: form.parent_ids,
      new_parents: form.new_parent_name.trim()
        ? [{ full_name: form.new_parent_name, phone: form.new_parent_phone || null }]
        : [],
    };
    try {
      if (form.id) await api.updateStudent(form.id, body);
      else await api.createStudent(body);
      setForm(null);
      load();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function remove(s: Student) {
    if (!confirm(`Удалить ученика ${s.full_name}? Оплаты останутся, но без привязки.`)) return;
    await api.deleteStudent(s.id).catch((e) => setError(e.message));
    load();
  }

  async function editParent(p: Parent) {
    const name = prompt("ФИО родителя", p.full_name);
    if (name === null) return;
    const phone = prompt("Телефон (по нему тоже узнаём плательщика)", p.phone ?? "");
    if (phone === null) return;
    await api
      .updateParent(p.id, { full_name: name, phone: phone || null, student_ids: p.students.map((s) => s.id) })
      .catch((e) => setError(e.message));
    load();
  }

  const q = query.trim().toLowerCase();
  const visible = students.filter(
    (s) => !q || s.full_name.toLowerCase().includes(q) || s.parents.some((p) => p.full_name.toLowerCase().includes(q)),
  );
  const set = (patch: Partial<Form>) => setForm((f) => f && { ...f, ...patch });

  return (
    <div className="page">
      {error && <div className="error">{error}</div>}
      {form ? (
        <div className="card">
          <h2>{form.id ? "Редактировать ученика" : "Новый ученик"}</h2>
          <label>
            ФИО ученика (Фамилия Имя Отчество)
            <input value={form.full_name} onChange={(e) => set({ full_name: e.target.value })} autoFocus />
          </label>
          <label>
            Группа / кружок
            <input value={form.group_name} onChange={(e) => set({ group_name: e.target.value })} />
          </label>
          <label>
            Оплата в месяц, ₽
            <input inputMode="decimal" value={form.monthly_fee} onChange={(e) => set({ monthly_fee: e.target.value })} />
          </label>
          <fieldset>
            <legend>Родители</legend>
            {parents.length > 0 && (
              <div className="checklist">
                {parents.map((p) => (
                  <label key={p.id} className="check">
                    <input
                      type="checkbox"
                      checked={form.parent_ids.includes(p.id)}
                      onChange={(e) =>
                        set({
                          parent_ids: e.target.checked
                            ? [...form.parent_ids, p.id]
                            : form.parent_ids.filter((x) => x !== p.id),
                        })
                      }
                    />
                    {p.full_name}
                  </label>
                ))}
              </div>
            )}
            <div className="muted small">Добавить нового родителя:</div>
            <input
              placeholder="ФИО родителя"
              value={form.new_parent_name}
              onChange={(e) => set({ new_parent_name: e.target.value })}
            />
            <input
              placeholder="Телефон"
              inputMode="tel"
              value={form.new_parent_phone}
              onChange={(e) => set({ new_parent_phone: e.target.value })}
            />
          </fieldset>
          <div className="row">
            <button className="primary" disabled={form.full_name.trim().length < 2} onClick={save}>
              Сохранить
            </button>
            <button onClick={() => setForm(null)}>Отмена</button>
          </div>
        </div>
      ) : (
        <div className="row">
          <input placeholder="Поиск…" value={query} onChange={(e) => setQuery(e.target.value)} />
          <button className="primary" onClick={() => setForm({ ...EMPTY })}>
            + Ученик
          </button>
        </div>
      )}

      {visible.map((s) => (
        <div key={s.id} className="card person">
          <div className="person-head">
            <div>
              <div className="who">{s.full_name}</div>
              <div className="muted small">
                {s.group_name ? `${s.group_name} · ` : ""}
                {money(s.monthly_fee)} в месяц
              </div>
            </div>
            <div className="row">
              <button className="link" onClick={() => edit(s)}>изменить</button>
              <button className="link danger" onClick={() => remove(s)}>удалить</button>
            </div>
          </div>
          {s.parents.length > 0 && (
            <div className="small">
              Родители:{" "}
              {s.parents.map((p, i) => (
                <span key={p.id}>
                  {i > 0 && ", "}
                  <button className="link" onClick={() => editParent(parents.find((x) => x.id === p.id)!)}>
                    {p.full_name}
                  </button>
                  {p.phone && <span className="muted"> {p.phone}</span>}
                </span>
              ))}
            </div>
          )}
        </div>
      ))}
      {students.length === 0 && !form && <div className="empty">Добавьте учеников и их родителей</div>}
    </div>
  );
}
