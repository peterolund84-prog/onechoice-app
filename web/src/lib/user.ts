const USER_KEY = "oc_user_id";

export function getUserId(): string {
  let id = localStorage.getItem(USER_KEY);
  if (!id) {
    id = `guest-${crypto.randomUUID().replace(/-/g, "").slice(0, 12)}`;
    localStorage.setItem(USER_KEY, id);
  }
  return id;
}

export function resetUserId(): string {
  localStorage.removeItem(USER_KEY);
  sessionStorage.removeItem("oc_last_decision");
  return getUserId();
}
