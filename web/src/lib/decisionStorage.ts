import type { Decision } from "./types";

export function readDecision(): Decision | null {
  try {
    const raw = sessionStorage.getItem("oc_last_decision");
    if (!raw) return null;
    return JSON.parse(raw) as Decision;
  } catch {
    return null;
  }
}

export function saveDecision(d: Decision) {
  try {
    const { image_data_url: _img, ...slim } = d;
    sessionStorage.setItem("oc_last_decision", JSON.stringify(slim));
  } catch {
    /* ignore quota */
  }
}

export function decisionId(d: Decision | null): number | null {
  if (!d) return null;
  const id = d.id ?? d.decision_id;
  return id == null ? null : Number(id);
}

export function goesToExecute(d: Decision): boolean {
  const domain = String(d.domain || "");
  const exec = String(d.execution_type || "");
  return domain === "food" || exec === "recipe" || exec === "workout";
}
