const AUTH_KEY = "oc_auth";
const USER_KEY = "oc_user_id";
const GUEST_BACKUP = "oc_guest_backup";

export type AuthSession = {
  user_id: string;
  email?: string | null;
  access_token: string;
  refresh_token: string;
};

export function readAuth(): AuthSession | null {
  try {
    const raw = localStorage.getItem(AUTH_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as AuthSession;
    if (!parsed?.access_token || !parsed?.refresh_token || !parsed?.user_id) {
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
}

export function writeAuth(session: AuthSession) {
  localStorage.setItem(AUTH_KEY, JSON.stringify(session));
  const prev = localStorage.getItem(USER_KEY);
  if (prev && prev.startsWith("guest-")) {
    localStorage.setItem(GUEST_BACKUP, prev);
  }
  localStorage.setItem(USER_KEY, session.user_id);
}

export function clearAuth() {
  localStorage.removeItem(AUTH_KEY);
  const backup = localStorage.getItem(GUEST_BACKUP);
  if (backup) {
    localStorage.setItem(USER_KEY, backup);
  } else {
    localStorage.removeItem(USER_KEY);
  }
}

export function isLoggedIn(): boolean {
  return Boolean(readAuth());
}

export function authHeaders(): Record<string, string> {
  const sess = readAuth();
  if (!sess) return {};
  return {
    "X-Access-Token": sess.access_token,
    "X-Refresh-Token": sess.refresh_token,
  };
}
