import { Capacitor } from "@capacitor/core";

export interface PersonBrief {
  id: number;
  full_name: string;
}
export interface StudentBrief extends PersonBrief {
  group_name: string | null;
}
export interface ParentBrief extends PersonBrief {
  phone: string | null;
}
export interface Student extends StudentBrief {
  monthly_fee: number;
  notes: string | null;
  active: boolean;
  parents: ParentBrief[];
}
export interface Parent extends ParentBrief {
  notes: string | null;
  students: StudentBrief[];
}
export interface Payment {
  id: number;
  amount: number | null;
  currency: string;
  paid_at: string | null;
  payer_name: string | null;
  payer_phone: string | null;
  purpose: string | null;
  bank: string | null;
  operation_id: string | null;
  raw_text: string | null;
  source: "photo" | "text" | "manual" | "telegram";
  attachment: "image" | "pdf" | null;
  status: "confirmed" | "needs_review";
  confidence: number;
  created_at: string;
  student: StudentBrief | null;
  parent: ParentBrief | null;
}
export interface Candidate {
  student: StudentBrief | null;
  parent: ParentBrief | null;
  score: number;
  reasons: string[];
}
export interface RecognizeItem {
  payment: Payment;
  candidates: Candidate[];
  auto_confirmed: boolean;
  duplicate_of: number | null;
  message: string;
}
export interface RecognizeResult {
  items: RecognizeItem[];
  message: string;
}
export interface MonthReport {
  month: string;
  total: number;
  rows: { student: StudentBrief; monthly_fee: number; paid: number; debt: number; payments: number }[];
  parent_only: { parent: ParentBrief; paid: number }[];
  needs_review: number;
}
export interface User {
  id: number;
  name: string;
  username: string | null;
  is_owner: boolean;
  approved: boolean;
}
export type PollResult =
  | { status: "waiting" | "pending" | "expired" }
  | { status: "ok"; token: string; user: User };

export interface Health {
  status: string;
  auth_required: boolean;
  auth_mode: "telegram" | "token" | "none";
  ai_recognition: boolean;
  server_ocr: boolean;
  telegram_bot: boolean;
  telegram_mode: "polling" | "webhook";
  persistent_storage: boolean;
  max_upload_mb: number;
}

const SERVER_KEY = "buh.server";
const TOKEN_KEY = "buh.token";

function read(key: string): string {
  try {
    return localStorage.getItem(key) ?? "";
  } catch {
    return "";
  }
}

function write(key: string, value: string) {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* хранилище недоступно — настройки будут действовать до перезапуска */
  }
}

let serverUrl = read(SERVER_KEY) || import.meta.env.VITE_API_URL || "";
let token = read(TOKEN_KEY);

export const isNative = Capacitor.isNativePlatform();

export function getSettings() {
  return { serverUrl, token };
}

export function saveSettings(next: { serverUrl: string; token: string }) {
  peopleCache = null;
  serverUrl = next.serverUrl.trim().replace(/\/+$/, "");
  token = next.token.trim();
  write(SERVER_KEY, serverUrl);
  write(TOKEN_KEY, token);
}

/** Сохранить сессию после входа через Telegram (или очистить при выходе). */
export function saveToken(next: string) {
  peopleCache = null;
  token = next;
  write(TOKEN_KEY, token);
}

/** Сервер ответил «нужно войти» — приложение покажет экран входа. */
export const UNAUTHORIZED_EVENT = "buh:unauthorized";

/** В приложении без адреса сервера работать нельзя — сайт же обслуживается самим сервером. */
export function needsSetup() {
  return isNative && !serverUrl;
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");
  let res: Response;
  try {
    res = await fetch(`${serverUrl}/api${path}`, { ...init, headers });
  } catch {
    throw new ApiError(0, "Нет связи с сервером. Проверьте адрес сервера и интернет.");
  }
  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => null);
  if (res.status === 401) window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
  if (!res.ok) {
    const detail = data?.detail;
    const msg = typeof detail === "string" ? detail : `Ошибка сервера (${res.status})`;
    throw new ApiError(res.status, msg);
  }
  return data as T;
}

const json = (body: unknown) => JSON.stringify(body);

/** Ученики и родители нужны в каждой карточке «на проверке» — грузим один раз. */
let peopleCache: Promise<{ students: Student[]; parents: Parent[] }> | null = null;

export function people() {
  if (!peopleCache) {
    peopleCache = Promise.all([api.students(), api.parents()]).then(([students, parents]) => ({ students, parents }));
    peopleCache.catch(() => (peopleCache = null));
  }
  return peopleCache;
}

function changed<T>(p: Promise<T>): Promise<T> {
  return p.finally(() => (peopleCache = null));
}

export const api = {
  health: () => request<Health>("/health"),
  authStart: () => request<{ code: string; url: string }>("/auth/start", { method: "POST" }),
  authPoll: (code: string) => request<PollResult>(`/auth/poll?code=${encodeURIComponent(code)}`),
  me: () => request<{ mode: string; user: User | null }>("/auth/me"),
  users: () => request<User[]>("/auth/users"),
  approveUser: (id: number) => request<User>(`/auth/users/${id}/approve`, { method: "POST" }),
  removeUser: (id: number) => request<void>(`/auth/users/${id}`, { method: "DELETE" }),
  telegramSetup: () => request<{ url: string; bot: string }>("/telegram/setup", { method: "POST" }),

  students: () => request<Student[]>("/students"),
  createStudent: (body: unknown) => changed(request<Student>("/students", { method: "POST", body: json(body) })),
  updateStudent: (id: number, body: unknown) =>
    changed(request<Student>(`/students/${id}`, { method: "PUT", body: json(body) })),
  deleteStudent: (id: number) => changed(request<void>(`/students/${id}`, { method: "DELETE" })),

  parents: () => request<Parent[]>("/parents"),
  createParent: (body: unknown) => changed(request<Parent>("/parents", { method: "POST", body: json(body) })),
  updateParent: (id: number, body: unknown) =>
    changed(request<Parent>(`/parents/${id}`, { method: "PUT", body: json(body) })),
  deleteParent: (id: number) => changed(request<void>(`/parents/${id}`, { method: "DELETE" })),

  /** file — сам чек (для хранения), ocrText — его текст, прочитанный на устройстве. */
  recognize: (file: Blob | null, text: string, ocrText = "") => {
    const form = new FormData();
    if (file) form.append("file", file, file instanceof File ? file.name : "receipt.jpg");
    if (text.trim()) form.append("text", text.trim());
    if (ocrText.trim()) form.append("ocr_text", ocrText.trim());
    return request<RecognizeResult>("/payments/recognize", { method: "POST", body: form });
  },
  payments: (params: { status?: string; month?: string; student_id?: string; parent_id?: string }) => {
    const q = new URLSearchParams(Object.entries(params).filter(([, v]) => v) as [string, string][]);
    return request<Payment[]>(`/payments?${q}`);
  },
  candidates: (id: number) => request<Candidate[]>(`/payments/${id}/candidates`),
  updatePayment: (id: number, body: unknown) =>
    request<Payment>(`/payments/${id}`, { method: "PATCH", body: json(body) }),
  deletePayment: (id: number) => request<void>(`/payments/${id}`, { method: "DELETE" }),
  manualPayment: (body: unknown) => request<Payment>("/payments/manual", { method: "POST", body: json(body) }),
  report: (month: string) => request<MonthReport>(`/reports/month?month=${month}`),

  imageUrl: (id: number) =>
    `${serverUrl}/api/payments/${id}/image${token ? `?token=${encodeURIComponent(token)}` : ""}`,
  exportUrl: (month: string) =>
    `${serverUrl}/api/payments/export.csv?month=${month}${token ? `&token=${encodeURIComponent(token)}` : ""}`,
};

/** Уменьшает фото перед отправкой: меньше трафика и быстрее распознавание. PDF отправляется как есть. */
export async function shrinkImage(file: File, maxSide = 2000): Promise<Blob> {
  if (!file.type.startsWith("image/") || file.type === "image/gif") return file;
  try {
    const bitmap = await createImageBitmap(file);
    const scale = Math.min(1, maxSide / Math.max(bitmap.width, bitmap.height));
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(bitmap.width * scale);
    canvas.height = Math.round(bitmap.height * scale);
    canvas.getContext("2d")!.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    const blob = await new Promise<Blob | null>((r) => canvas.toBlob(r, "image/jpeg", 0.85));
    return blob ?? file;
  } catch {
    return file;
  }
}

export const money = (v: number | null | undefined) =>
  v == null ? "—" : `${v.toLocaleString("ru-RU", { maximumFractionDigits: 2 })} ₽`;

export const fmtDate = (v: string | null) =>
  v ? new Date(v + "T00:00:00").toLocaleDateString("ru-RU") : "—";

export const currentMonth = () => new Date().toISOString().slice(0, 7);
