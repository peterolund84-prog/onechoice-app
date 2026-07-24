import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import { OCCASION_OPTIONS } from "../lib/domainMeta";
import { saveDecision } from "../lib/decisionStorage";
import type { Decision } from "../lib/types";

export function ClothesPage() {
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const hour = new Date().getHours();
  const defaultId =
    hour >= 7 && hour <= 9
      ? "jobb"
      : hour >= 17 && hour <= 19
        ? "middag"
        : hour >= 20
          ? "fest"
          : "vardag";

  async function pick(occasion: string) {
    setBusy(true);
    setError(null);
    try {
      const result = await api.decide({
        domain_hint: "clothes",
        occasion,
        intent: "wear",
      });
      const decision: Decision = {
        ...result,
        decision_id: result.decision_id ?? result.id ?? null,
      };
      saveDecision(decision);
      navigate("/resultat", { state: { decision } });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Kunde inte bestämma");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="oc-page">
      <h1 className="oc-page-title">Vart ska du?</h1>
      <p className="oc-page-sub">Ett tryck — jag bygger outfiten.</p>
      <div className="oc-meal-seg oc-meal-seg--dense" role="list" aria-label="Tillfälle">
        {OCCASION_OPTIONS.map((o) => (
          <button
            key={o.id}
            type="button"
            className={o.id === defaultId ? "is-active" : undefined}
            disabled={busy}
            onClick={() => void pick(o.id)}
          >
            {o.label}
          </button>
        ))}
      </div>
      {error ? <p className="oc-error">{error}</p> : null}
      {busy ? <p className="oc-page-sub">Bestämmer outfit…</p> : null}
    </section>
  );
}
