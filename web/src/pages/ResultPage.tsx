import { useMemo } from "react";
import { Link } from "react-router-dom";

type DecisionPayload = {
  ok?: boolean;
  suggestion?: string;
  justification?: string;
  domain?: string | null;
  execution_label?: string | null;
  execution_url?: string | null;
  refused?: boolean;
  refusal_message?: string | null;
  ui_message?: string | null;
  needs_domain_pick?: boolean;
};

function readDecision(): DecisionPayload | null {
  try {
    const raw = sessionStorage.getItem("oc_last_decision");
    if (!raw) return null;
    return JSON.parse(raw) as DecisionPayload;
  } catch {
    return null;
  }
}

export function ResultPage() {
  const decision = useMemo(() => readDecision(), []);

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

  return (
    <section className="oc-result">
      <p className="oc-result-kicker">Ditt beslut</p>
      <h1 className="oc-result-title">{decision.suggestion || "—"}</h1>
      {decision.justification ? (
        <p className="oc-result-body">{decision.justification}</p>
      ) : null}
      {decision.execution_url && decision.execution_label ? (
        <a
          className="oc-cta oc-cta-link"
          href={decision.execution_url}
          target="_blank"
          rel="noreferrer"
        >
          {decision.execution_label}
        </a>
      ) : null}
      <Link className="oc-text-link" to="/">
        Nytt beslut
      </Link>
    </section>
  );
}
