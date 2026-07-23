const API_BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    ...init,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  home: () => request<Record<string, unknown>>("/v1/home?language=sv"),
  decide: (body: {
    question?: string;
    domain_hint?: string | null;
    meal_type?: string | null;
    language?: string;
  }) =>
    request<Record<string, unknown>>("/v1/decide", {
      method: "POST",
      body: JSON.stringify({ language: "sv", ...body }),
    }),
};
