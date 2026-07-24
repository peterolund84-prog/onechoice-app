const AUTH_META_KEY = "oc_auth_meta";
const GUEST_BACKUP = "oc_guest_backup";
const USER_KEY = "oc_user_id";

/** Non-secret session meta only — tokens live in httpOnly cookies. */
export type AuthSession = {
  user_id: string;
  email?: string | null;
};

export function readAuth(): AuthSession | null {
  try {
    const raw = localStorage.getItem(AUTH_META_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as AuthSession;
    if (!parsed?.user_id) return null;
    return parsed;
  } catch {
    return null;
  }
}

export function writeAuth(session: AuthSession) {
  const prev = localStorage.getItem(USER_KEY);
  if (prev && prev.startsWith("guest-")) {
    localStorage.setItem(GUEST_BACKUP, prev);
  }
  localStorage.setItem(AUTH_META_KEY, JSON.stringify(session));
  // Do not store auth UUID as X-User-Id — server derives id from cookie JWT.
}

export function clearAuth() {
  localStorage.removeItem(AUTH_META_KEY);
  // Clear legacy token bags if present from older builds.
  localStorage.removeItem("oc_auth");
  const backup = localStorage.getItem(GUEST_BACKUP);
  if (backup) {
    localStorage.setItem(USER_KEY, backup);
  }
}

export function isLoggedIn(): boolean {
  return Boolean(readAuth()?.user_id);
}

/** @deprecated Tokens are httpOnly cookies; kept as no-op for gradual cleanup. */
export function authHeaders(): Record<string, string> {
  return {};
}
