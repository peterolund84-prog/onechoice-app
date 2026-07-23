import { useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { Heart, Share2 } from "lucide-react";
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
  try {
    const { image_data_url: _img, ...slim } = d;
    sessionStorage.setItem("oc_last_decision", JSON.stringify(slim));
  } catch {
    /* ignore quota */
  }
}

function decisionId(d: Decision | null): number | null {
  if (!d) return null;
  const id = d.id ?? d.decision_id;
  return id == null ? null : Number(id);
}

function dishHint(d: Decision): string | null {
  const ctx = d.context;
  if (!ctx || typeof ctx !== "object") return null;
  const hint = ctx.dish_category ?? ctx.category;
  return typeof hint === "string" ? hint : null;
}

function moviePoster(d: Decision): string | null {
  const ctx = d.context;
  if (!ctx || typeof ctx !== "object") return null;
  const url = ctx.movie_poster_url;
  return typeof url === "string" && url ? url : null;
}

function mediaSrc(d: Decision): string | null {
  if (typeof d.image_data_url === "string" && d.image_data_url.startsWith("data:")) {
    return d.image_data_url;
  }
  if (d.domain === "food" && d.suggestion) {
    const q = new URLSearchParams({ title: d.suggestion });
    const hint = dishHint(d);
    if (hint) q.set("hint", hint);
    return `${api.base}/v1/media/dish?${q}`;
  }
  if (d.domain === "movie") return moviePoster(d);
  return null;
}

export function ResultPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const initial = useMemo(() => {
    const fromNav = (location.state as { decision?: Decision } | null)?.decision;
    return fromNav ?? readDecision();
  }, [location.state]);
  const [decision, setDecision] = useState<Decision | null>(initial);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [imgFailed, setImgFailed] = useState(false);

  useEffect(() => {
    setImgFailed(false);
  }, [decision?.suggestion, decision?.domain, decision?.image_data_url]);

  // Hydrate dish image for older sessionStorage payloads (pre-embed).
  useEffect(() => {
    const current = decision;
    if (!current || current.domain !== "food" || current.image_data_url) return;
    if (!current.suggestion) return;
    let cancelled = false;
    const q = new URLSearchParams({ title: current.suggestion });
    const hint = dishHint(current);
    if (hint) q.set("hint", hint);
    const url = `${api.base}/v1/media/dish?${q}`;
    fetch(url)
      .then((res) => {
        if (!res.ok) throw new Error("no image");
        return res.blob();
      })
      .then(
        (blob) =>
          new Promise<string>((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => resolve(String(reader.result || ""));
            reader.onerror = () => reject(new Error("read failed"));
            reader.readAsDataURL(blob);
          }),
      )
      .then((dataUrl) => {
        if (cancelled || !dataUrl.startsWith("data:")) return;
        setDecision((prev) => {
          if (!prev) return prev;
          const next = { ...prev, image_data_url: dataUrl };
          saveDecision(next);
          return next;
        });
        setImgFailed(false);
      })
      .catch(() => {
        /* keep placeholder */
      });
    return () => {
      cancelled = true;
    };
  }, [decision?.suggestion, decision?.domain, decision?.image_data_url]);

  if (!decision) {
    return (
      <section className="oc-result">
        <h1 className="oc-result-title">Inget beslut ännu</h1>
        <p className="oc-result-sub">Gå tillbaka till Hem och tryck Bestäm åt mig.</p>
        <button type="button" className="oc-cta" onClick={() => navigate("/")}>
          Till Hem
        </button>
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
        <button type="button" className="oc-cta" onClick={() => navigate("/")}>
          Tillbaka
        </button>
      </section>
    );
  }

  const id = decisionId(decision);
  const rerolls = Number(decision.reroll_index || 0);
  const locked = Boolean(decision.locked) || rerolls >= MAX_REROLLS;
  const accepted = Boolean(decision.accepted);
  const src = mediaSrc(decision);
  const showImage = Boolean(src) && !imgFailed;
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
      const next = { ...current, accepted: true };
      saveDecision(next);
      setDecision(next);
      setMsg("Accepterat");
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
      navigate("/resultat", { state: { decision: next }, replace: true });
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

  async function onShare() {
    const current = decision;
    if (!current?.suggestion) return;
    const text = `${current.suggestion}\n${current.justification || ""}\n— OneChoice`.trim();
    try {
      if (navigator.share) {
        await navigator.share({ title: "OneChoice", text });
      } else if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(text);
        setMsg("Kopierat!");
      } else {
        setMsg(text);
      }
    } catch {
      /* user cancelled share */
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
      <div className="oc-media-card">
        {showImage ? (
          <img
            className="oc-media-img"
            src={src!}
            alt=""
            onError={() => setImgFailed(true)}
          />
        ) : (
          <div className="oc-media-img oc-media-ph" aria-hidden="true">
            <div className="oc-media-ph-circle" />
          </div>
        )}
        <div className="oc-media-actions">
          <button
            type="button"
            className="oc-media-action"
            aria-label="Dela"
            onClick={onShare}
          >
            <Share2 size={18} strokeWidth={1.75} />
          </button>
          <button
            type="button"
            className={`oc-media-action${decision.favorite ? " is-on" : ""}`}
            aria-label="Favorit"
            disabled={busy || id == null}
            onClick={onFavorite}
          >
            <Heart
              size={18}
              strokeWidth={1.75}
              fill={decision.favorite ? "currentColor" : "none"}
            />
          </button>
        </div>
      </div>

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
        ) : null}

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
      </div>

      {msg ? <p className="oc-ok">{msg}</p> : null}
      {error ? <p className="oc-error">{error}</p> : null}
    </section>
  );
}
