import { getInitData } from "./telegram";
import type { User } from "./types";

const BASE = (import.meta.env.VITE_API_URL as string | undefined) || "/api/v1";

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details: unknown = null,
  ) {
    super(message);
  }
}

let token: string | null = null;

export async function authenticate(): Promise<User> {
  const initData = getInitData();
  if (!initData) throw new ApiError(401, "no_init_data", "Откройте приложение через Telegram");
  const res = await raw<{ token: string; user: User }>("POST", "/auth/telegram", { init_data: initData }, false);
  token = res.token;
  return res.user;
}

async function raw<T>(method: string, path: string, body?: unknown, auth = true, headers: Record<string, string> = {}): Promise<T> {
  const h: Record<string, string> = { ...headers };
  if (body !== undefined) h["Content-Type"] = "application/json";
  if (auth && token) h.Authorization = `Bearer ${token}`;
  let res: Response;
  try {
    res = await fetch(BASE + path, { method, headers: h, body: body === undefined ? undefined : JSON.stringify(body) });
  } catch {
    throw new ApiError(0, "network", "Нет соединения с сервером. Проверьте интернет и попробуйте ещё раз.");
  }
  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    const err = data?.error;
    throw new ApiError(res.status, err?.code ?? `http_${res.status}`, err?.message ?? "Что-то пошло не так", err?.details);
  }
  return data as T;
}

/** Запрос с авторизацией; при истёкшей сессии один раз переавторизуется по initData. */
export async function request<T>(method: string, path: string, body?: unknown, headers?: Record<string, string>): Promise<T> {
  try {
    return await raw<T>(method, path, body, true, headers);
  } catch (e) {
    if (e instanceof ApiError && e.status === 401 && getInitData()) {
      await authenticate();
      return raw<T>(method, path, body, true, headers);
    }
    throw e;
  }
}

export const api = {
  get: <T>(path: string) => request<T>("GET", path),
  post: <T>(path: string, body?: unknown, headers?: Record<string, string>) => request<T>("POST", path, body ?? {}, headers),
  patch: <T>(path: string, body: unknown) => request<T>("PATCH", path, body),
  put: <T>(path: string, body: unknown) => request<T>("PUT", path, body),
  del: <T>(path: string) => request<T>("DELETE", path),
};

export function qs(params: Record<string, string | number | boolean | null | undefined | string[]>): string {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === null || v === undefined || v === "") continue;
    if (Array.isArray(v)) v.forEach((x) => p.append(k, x));
    else p.set(k, String(v));
  }
  const s = p.toString();
  return s ? `?${s}` : "";
}

export function newIdempotencyKey(): string {
  return crypto.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}
