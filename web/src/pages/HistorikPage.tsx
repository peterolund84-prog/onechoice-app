import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Heart } from "lucide-react";
import { api } from "../lib/api";
import type { Decision } from "../lib/types";

type Segment = "historik" | "favoriter";

function decisionKey(d: Decision): number | null {
  const id = d.id ?? d.decision_id;
  return id == null ? null : Number(id);
}

export function HistorikPage() {
  const navigate = useNavigate();
  const [items, setItems] = useState<Decision[]>([]);
  const [segment, setSegment] = useState<Segment>("historik");
  const [showAll, setShowAll] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const data = await api.listDecisions({
        favorite: segment === "favoriter" ? true : undefined,
        limit: 80,
      });
      setItems(data.items);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Kunde inte ladda historik");
    }
  }, [segment]);

  useEffect(() => {
    void load();
  }, [load]);

  const visible = useMemo(() => {
    if (segment === "favoriter") return items;
    if (showAll) return items;
    return items.filter((d) =>
      ["accepted", "locked"].includes(String(d.status || "")),
    );
  }, [items, segment, showAll]);

  async function toggleFavorite(d: Decision) {
    const id = decisionKey(d);
    if (id == null) return;
    const next = !Boolean(d.favorite);
    setItems((prev) =>
      prev.map((x) => (decisionKey(x) === id ? { ...x, favorite: next } : x)),
    );
    try {
      await api.setFavorite(id, next);
      if (segment === "favoriter") await load();
    } catch {
      await load();
    }
  }

  function openDecision(d: Decision) {
    sessionStorage.setItem(
      "oc_last_decision",
      JSON.stringify({
        ...d,
        ok: true,
        decision_id: decisionKey(d),
      }),
    );
    navigate("/resultat");
  }

  return (
    <section className="oc-page">
      <h1 className="oc-page-title">Historik</h1>
      <div className="oc-seg">
        <button
          type="button"
          className={segment === "historik" ? "is-active" : undefined}
          onClick={() => setSegment("historik")}
        >
          Historik
        </button>
        <button
          type="button"
          className={segment === "favoriter" ? "is-active" : undefined}
          onClick={() => setSegment("favoriter")}
        >
          Favoriter
        </button>
      </div>

      {segment === "historik" ? (
        <label className="oc-check-row oc-inline">
          <input
            type="checkbox"
            checked={showAll}
            onChange={(e) => setShowAll(e.target.checked)}
          />
          <span>Visa alla</span>
        </label>
      ) : null}

      {visible.length === 0 ? (
        <p className="oc-empty">
          {segment === "favoriter"
            ? "Inga favoriter ännu — hjärta ett beslut efteråt."
            : "Inga beslut ännu."}
        </p>
      ) : (
        <ul className="oc-hist">
          {visible.map((d) => {
            const id = decisionKey(d);
            return (
              <li key={id ?? `${d.suggestion}-${d.created_at}`}>
                <button
                  type="button"
                  className="oc-hist-main"
                  onClick={() => openDecision(d)}
                >
                  <strong>{d.suggestion || "—"}</strong>
                  <span>
                    {d.domain || "—"}
                    {d.created_at ? ` · ${String(d.created_at).slice(0, 10)}` : ""}
                  </span>
                </button>
                <button
                  type="button"
                  className="oc-icon-btn"
                  aria-label="Favorit"
                  onClick={() => toggleFavorite(d)}
                >
                  <Heart
                    size={20}
                    strokeWidth={1.5}
                    fill={d.favorite ? "currentColor" : "none"}
                  />
                </button>
              </li>
            );
          })}
        </ul>
      )}

      {error ? <p className="oc-error">{error}</p> : null}
    </section>
  );
}
