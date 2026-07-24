import { isLoggedIn } from "./auth";
import { getUserId, isGuestId } from "./user";
import type { Decision, ShoppingItem, UserProfile } from "./types";

/**
 * Prefer same-origin (Vite proxy → API) so httpOnly cookies work on LAN.
 * Absolute VITE_API_BASE is only for special setups without the proxy.
 */
function resolveApiBase(): string {
  const env = (import.meta.env.VITE_API_BASE as string | undefined)?.trim();
  if (env && !/127\.0\.0\.1|localhost/i.test(env)) {
    return env.replace(/\/$/, "");
  }
  // Empty = same origin (dev proxy / production reverse proxy).
  return "";
}

const API_BASE = resolveApiBase();

function identityHeaders(): Record<string, string> {
  // Authenticated sessions: never send a client id — JWT cookie is source of truth.
  if (isLoggedIn()) return {};
  const uid = getUserId();
  if (!isGuestId(uid)) return {};
  return { "X-User-Id": uid };
}

function guestUserId(): string | undefined {
  if (isLoggedIn()) return undefined;
  const uid = getUserId();
  return isGuestId(uid) ? uid : undefined;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...identityHeaders(),
    ...(init?.headers as Record<string, string> | undefined),
  };
  const ctrl = new AbortController();
  const timeoutMs = 25000;
  const timer = window.setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers,
      credentials: "include",
      signal: init?.signal ?? ctrl.signal,
    });
    if (!res.ok) {
      const text = await res.text();
      throw new Error(text || `HTTP ${res.status}`);
    }
    const ct = res.headers.get("content-type") || "";
    if (ct.includes("application/json")) {
      return res.json() as Promise<T>;
    }
    return (await res.text()) as T;
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") {
      throw new Error(
        `API svarade inte (${API_BASE || "same-origin"}). Kolla att uvicorn kör.`,
      );
    }
    if (e instanceof TypeError) {
      throw new Error(
        `Kunde inte nå API (${API_BASE || "same-origin"}). Starta API + Vite-proxy.`,
      );
    }
    throw e;
  } finally {
    window.clearTimeout(timer);
  }
}

function withUid(path: string): string {
  const uid = guestUserId();
  if (!uid) return path;
  const sep = path.includes("?") ? "&" : "?";
  return `${path}${sep}user_id=${encodeURIComponent(uid)}`;
}

export type DecideBody = {
  question?: string;
  domain_hint?: string | null;
  meal_type?: string | null;
  format?: string | null;
  mood?: string | null;
  in_progress_series?: string | null;
  occasion?: string | null;
  intent?: string | null;
  source?: string | null;
  available_ingredients?: string[] | null;
  previous_suggestion?: string | null;
  language?: string;
  reroll?: boolean;
  reroll_index?: number;
  previous_decision_id?: number | null;
};

export const api = {
  base: API_BASE || (typeof window !== "undefined" ? window.location.origin : ""),

  home: () => request<Record<string, unknown>>("/v1/home?language=sv"),

  domainMeta: () =>
    request<{
      meals: { id: string; label: string }[];
      formats: { id: string; label: string }[];
      moods: { id: string; label: string }[];
      occasions: { id: string; label: string }[];
      default_occasion: string;
    }>("/v1/meta/domains?language=sv"),

  decide: (body: DecideBody) =>
    request<Decision>("/v1/decide", {
      method: "POST",
      body: JSON.stringify({
        language: "sv",
        user_id: guestUserId(),
        ...body,
      }),
    }),

  executeFood: (body: {
    suggestion: string;
    meal_type?: string | null;
    context?: Record<string, unknown> | null;
  }) =>
    request<{
      ok: boolean;
      recipe: Record<string, unknown> | null;
      shopping: Record<string, unknown> | null;
    }>("/v1/execute/food", {
      method: "POST",
      body: JSON.stringify({ user_id: guestUserId(), ...body }),
    }),

  authStatus: () => request<{ configured: boolean }>("/v1/auth/status"),

  login: (email: string, password: string) =>
    request<{
      ok: boolean;
      user_id: string;
      email?: string;
    }>("/v1/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password, language: "sv" }),
    }),

  signup: (email: string, password: string, privacyConsent: boolean) =>
    request<{
      ok: boolean;
      user_id: string;
      email?: string;
      needs_confirmation?: boolean;
    }>("/v1/auth/signup", {
      method: "POST",
      body: JSON.stringify({
        email,
        password,
        language: "sv",
        privacy_consent: privacyConsent,
      }),
    }),

  logout: () =>
    request<{ ok: boolean }>("/v1/auth/logout", { method: "POST", body: "{}" }),

  acceptDecision: (decisionId: number, routeLogId?: number | null) =>
    request<{ ok: boolean; accepted: boolean; decision?: Decision }>(
      `/v1/decisions/${decisionId}/accept`,
      {
        method: "POST",
        body: JSON.stringify({
          user_id: guestUserId(),
          route_log_id: routeLogId ?? null,
        }),
      },
    ),

  setFavorite: (decisionId: number, favorite: boolean) =>
    request<{ ok: boolean; decision: Decision }>(
      `/v1/decisions/${decisionId}/favorite`,
      {
        method: "POST",
        body: JSON.stringify({ user_id: guestUserId(), favorite }),
      },
    ),

  listDecisions: (opts?: { favorite?: boolean; limit?: number }) => {
    const q = new URLSearchParams();
    const uid = guestUserId();
    if (uid) q.set("user_id", uid);
    if (opts?.favorite != null) q.set("favorite", String(opts.favorite));
    if (opts?.limit) q.set("limit", String(opts.limit));
    const qs = q.toString();
    return request<{ items: Decision[]; user_id: string }>(
      `/v1/decisions${qs ? `?${qs}` : ""}`,
    );
  },

  getDecision: (id: number) =>
    request<{ decision: Decision }>(withUid(`/v1/decisions/${id}`)),

  listShopping: () =>
    request<{ items: ShoppingItem[] }>(withUid("/v1/shopping")),

  addShopping: (name: string) =>
    request<{ item: ShoppingItem }>("/v1/shopping", {
      method: "POST",
      body: JSON.stringify({ name, user_id: guestUserId() }),
    }),

  toggleShopping: (itemId: number, checked: boolean) =>
    request<{ item: ShoppingItem }>(`/v1/shopping/${itemId}`, {
      method: "PATCH",
      body: JSON.stringify({ checked, user_id: guestUserId() }),
    }),

  clearCheckedShopping: (itemIds?: number[]) =>
    request<{ deleted: number }>("/v1/shopping/checked", {
      method: "DELETE",
      body: JSON.stringify({
        user_id: guestUserId(),
        item_ids: itemIds ?? null,
      }),
    }),

  mergeShopping: (decisionId: number | null, toBuy: Record<string, unknown>) =>
    request<{ added: ShoppingItem[]; count: number }>("/v1/shopping/merge", {
      method: "POST",
      body: JSON.stringify({
        user_id: guestUserId(),
        decision_id: decisionId,
        to_buy: toBuy,
      }),
    }),

  shoppingShareText: () =>
    request<string>(withUid("/v1/shopping/share-text?language=sv")),

  me: () => request<{ user: UserProfile; user_id: string }>(withUid("/v1/me")),

  patchMe: (body: {
    language?: string;
    is_pro?: number;
    profile_json?: Record<string, unknown>;
  }) =>
    request<{ user: UserProfile }>("/v1/me", {
      method: "PATCH",
      body: JSON.stringify({ user_id: guestUserId(), ...body }),
    }),

  exportMe: () =>
    request<Record<string, unknown>>(withUid("/v1/me/export")),

  deleteMe: () =>
    request<{ ok: boolean }>(withUid("/v1/me"), { method: "DELETE" }),
};
