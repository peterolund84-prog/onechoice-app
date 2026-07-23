import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Heart } from "lucide-react";
import { api } from "../lib/api";
import type { Decision } from "../lib/types";

const MAX_REROLLS = 3;

function readDecision(): Decision | null {
  try {
    const raw = sessionStorage.getItem("oc_last_decision");
    if (!raw) return null;
    return JSON.parse(raw) as Decision;
  } catch {
    return null;
  }
}

function saveDecision(d: Decision) {
  sessionStorage.setItem("oc_last_decision", JSON.stringify(d));
}

function decisionId(d: Decision | null): number | null {
  if (!d) return null;
  const id = d.id ?? d.decision_id;
  return id == null ? null : Number(id);
}

export function ResultPage() {
  const navigate = useNavigate();
  const initial = useMemo(() => readDecision(), []);
  const [decision, setDecision] = useState<Decision | null>(initial);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  if (!decision) {
    return (
      <section className="oc-result">
        <h1 className="oc-result-title">Inget beslut ännu</h1>
        <p className="oc-result-sub">Gå tillbaka till Hem och tryck Bestäm åt mig.</p>
        <Link className="oc-cta oc-cta-link" to="/">
          Till Hem
        </Link>
      </section>
    );
  }

  if (decision.refused || decision.ui_message) {
    return (
      <section className="oc-result">
        <h1 className="oc-result-title">Ett ögonblick</h1>
        <p className="oc-result-body">
          {decision.refusal_message || decision.ui_message}
        </p>
        <Link className="oc-cta oc-cta-link" to="/">
          Tillbaka
        </Link>
      </section>
    );
  }

  const id = decisionId(decision);
  const rerolls = Number(decision.reroll_index || 0);
  const locked = Boolean(decision.locked) || rerolls >= MAX_REROLLS;
  const accepted = Boolean(decision.accepted);
  const toBuy =
    decision.context &&
    typeof decision.context === "object" &&
    decision.context.shopping &&
    typeof decision.context.shopping === "object"
      ? (decision.context.shopping as { to_buy?: Record<string, unknown> }).to_buy
      : undefined;

  async function onAccept() {
    const current = decision;
    if (!current) return;
    if (id == null) {
      setDecision(() => {
        const next = { ...current, accepted: true };
        saveDecision(next);
        return next;
      });
      setMsg("Accepterat (saknar decision_id — sparat lokalt)");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await api.acceptDecision(id, current.route_log_id);
      const next = { ...current, accepted: true, status: "accepted" };
      saveDecision(next);
      setDecision(next);
      setMsg("Accepterat");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Kunde inte acceptera");
    } finally {
      setBusy(false);
    }
  }

  async function onReroll() {
    const current = decision;
    if (!current || locked) return;
    setBusy(true);
    setError(null);
    try {
      const next = await api.decide({
        question: "",
        domain_hint: current.domain ?? null,
        reroll: true,
        reroll_index: rerolls + 1,
        previous_decision_id: id,
      });
      saveDecision(next);
      setDecision(next);
      setMsg(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Kunde inte ge nytt förslag");
    } finally {
      setBusy(false);
    }
  }

  async function onFavorite() {
    const current = decision;
    if (!current || id == null) return;
    setBusy(true);
    try {
      const nextFav = !Boolean(current.favorite);
      await api.setFavorite(id, nextFav);
      const next = { ...current, favorite: nextFav };
      saveDecision(next);
      setDecision(next);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Kunde inte spara favorit");
    } finally {
      setBusy(false);
    }
  }

  async function onMergeList() {
    if (!toBuy) return;
    setBusy(true);
    try {
      const res = await api.mergeShopping(id, toBuy);
      setMsg(`Lade till ${res.count} varor i listan`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Kunde inte lägga i listan");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="oc-result">
      <p className="oc-result-kicker">
        {accepted || locked ? "Ditt beslut" : "Förslag"}
        {decision.domain ? ` · ${decision.domain}` : ""}
      </p>
      <h1 className="oc-result-title">{decision.suggestion || "—"}</h1>
      {decision.justification ? (
        <p className="oc-result-body">{decision.justification}</p>
      ) : null}

      <div className="oc-reroll-dots" aria-label="Omrullningar">
        {Array.from({ length: MAX_REROLLS }).map((_, i) => (
          <span key={i} className={i < rerolls ? "is-used" : undefined} />
        ))}
      </div>

      <div className="oc-stack" style={{ width: "100%", maxWidth: 320 }}>
        {!accepted && !locked ? (
          <button type="button" className="oc-cta" disabled={busy} onClick={onAccept}>
            Acceptera
          </button>
        ) : null}

        {!locked ? (
          <button
            type="button"
            className="oc-btn oc-btn-ghost"
            disabled={busy}
            onClick={onReroll}
          >
            Nytt förslag
          </button>
        ) : (
          <p className="oc-page-sub">Låst — max antal förslag nått.</p>
        )}

        {decision.execution_url && decision.execution_label ? (
          <a
            className="oc-btn oc-btn-ghost"
            href={decision.execution_url}
            target="_blank"
            rel="noreferrer"
          >
            {decision.execution_label}
          </a>
        ) : null}

        {toBuy ? (
          <button type="button" className="oc-btn" disabled={busy} onClick={onMergeList}>
            Lägg till i listan
          </button>
        ) : null}

        {id != null ? (
          <button
            type="button"
            className="oc-icon-btn"
            aria-label="Favorit"
            disabled={busy}
            onClick={onFavorite}
            style={{ alignSelf: "center" }}
          >
            <Heart
              size={22}
              strokeWidth={1.5}
              fill={decision.favorite ? "currentColor" : "none"}
            />
          </button>
        ) : null}

        <button type="button" className="oc-text-link" onClick={() => navigate("/")}>
          Nytt beslut
        </button>
        <Link className="oc-text-link" to="/lista">
          Till listan
        </Link>
      </div>

      {msg ? <p className="oc-ok">{msg}</p> : null}
      {error ? <p className="oc-error">{error}</p> : null}
    </section>
  );
}
