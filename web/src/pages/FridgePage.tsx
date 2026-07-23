import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../lib/api";
import { saveDecision } from "../lib/decisionStorage";
import type { Decision } from "../lib/types";

export function FridgePage() {
  const navigate = useNavigate();
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    const items = text
      .split(/[,;\n]+/)
      .map((x) => x.trim())
      .filter(Boolean);
    if (items.length < 2) {
      setError("Skriv minst två råvaror, t.ex. ägg, mjölk, pasta");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const result = await api.decide({
        domain_hint: "food",
        source: "fridge_photo",
        available_ingredients: items,
        meal_type: "middag",
      });
      const decision: Decision = {
        ...result,
        decision_id: result.decision_id ?? result.id ?? null,
      };
      saveDecision(decision);
      navigate("/resultat", { state: { decision } });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Kunde inte laga från kylen");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="oc-page">
      <h1 className="oc-page-title">Fota kylen</h1>
      <p className="oc-page-sub">
        Kameraskanning kommer snart. Skriv vad du har hemma så lagar jag från det.
      </p>
      <form className="oc-stack" onSubmit={onSubmit} style={{ maxWidth: 420 }}>
        <textarea
          className="oc-input oc-textarea"
          rows={5}
          placeholder="ägg, mjölk, pasta, tomat…"
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
        <button type="submit" className="oc-cta" disabled={busy}>
          {busy ? "Bestämmer…" : "Laga från det här"}
        </button>
      </form>
      {error ? <p className="oc-error">{error}</p> : null}
    </section>
  );
}