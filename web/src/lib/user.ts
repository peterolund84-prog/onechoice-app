const USER_KEY = "oc_user_id";

/** Works on iOS Safari over http://LAN-IP (crypto.randomUUID needs secure context). */
function guestId(): string {
  const c = globalThis.crypto;
  if (c && typeof c.randomUUID === "function") {
    return `guest-${c.randomUUID().replace(/-/g, "").slice(0, 12)}`;
  }
  if (c && typeof c.getRandomValues === "function") {
    const bytes = new Uint8Array(12);
    c.getRandomValues(bytes);
    const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
    return `guest-${hex}`;
  }
  return `guest-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 10)}`;
}

export function getUserId(): string {
  let id = localStorage.getItem(USER_KEY);
  if (!id) {
    id = guestId();
    localStorage.setItem(USER_KEY, id);
  }
  return id;
}

export function resetUserId(): string {
  localStorage.removeItem(USER_KEY);
  sessionStorage.removeItem("oc_last_decision");
  return getUserId();
}
