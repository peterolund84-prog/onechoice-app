import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Clapperboard, Dumbbell, Soup, TreePalm } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { api } from "../lib/api";

type DomainId = "food" | "clothes" | "movie" | "workout" | "weekend" | "fridge";

type HomePayload = {
  headline: string;
  sub: string;
  cta: string;
  section_label: string;
  something_else: string;
  meal_type?: string;
  domains: { id: DomainId; label: string }[];
};

const ICONS: Partial<Record<DomainId, LucideIcon>> = {
  food: Soup,
  movie: Clapperboard,
  workout: Dumbbell,
  weekend: TreePalm,
};

function DomainIcon({ id }: { id: DomainId }) {
  if (id === "clothes") {
    return (
      <svg
        className="oc-domain-icon"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden
      >
        <path d="M9 5a3 3 0 1 1 5.1 2.1l-1.5 1.5A2 2 0 0 0 12 10v1" />
        <path d="M4 21a2 2 0 0 1-1.1-3.7L12 11l9.2 6.4A2 2 0 0 1 20 21Z" />
      </svg>
    );
  }
  if (id === "fridge") {
    return (
      <svg
        className="oc-domain-icon"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden
      >
        <rect x="6" y="3" width="12" height="18" rx="2" />
        <path d="M6 10h12" />
        <path d="M9 6.5v1" />
        <path d="M9 13.5v2" />
      </svg>
    );
  }
  const Icon = ICONS[id];
  if (!Icon) return null;
  return <Icon className="oc-domain-icon" strokeWidth={1.5} aria-hidden />;
}

const FALLBACK: HomePayload = {
  headline: "Middag?",
  sub: "Ett tryck — jag tar beslutet.",
  cta: "Bestäm åt mig",
  section_label: "Eller välj själv",
  something_else: "Något annat?",
  meal_type: "middag",
  domains: [
    { id: "food", label: "Mat" },
    { id: "clothes", label: "Kläder" },
    { id: "movie", label: "Film" },
    { id: "workout", label: "Träning" },
    { id: "weekend", label: "Helg" },
    { id: "fridge", label: "Fota kylen" },
  ],
};

export function HomePage() {
  const navigate = useNavigate();
  const [home, setHome] = useState<HomePayload>(FALLBACK);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [freeOpen, setFreeOpen] = useState(false);
  const [freeText, setFreeText] = useState("");

  useEffect(() => {
    let cancelled = false;
    api
      .home()
      .then((data) => {
        if (!cancelled) setHome(data as HomePayload);
      })
      .catch(() => {
        /* offline / API down — keep fallback copy */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function runDecide(opts: {
    domain_hint?: string | null;
    question?: string;
    meal_type?: string | null;
  }) {
    setBusy(true);
    setError(null);
    try {
      const result = await api.decide({
        question: opts.question ?? "",
        domain_hint: opts.domain_hint ?? null,
        meal_type: opts.meal_type ?? home.meal_type ?? null,
      });
      sessionStorage.setItem(
        "oc_last_decision",
        JSON.stringify({
          ...result,
          decision_id: (result as { id?: number }).id ?? null,
        }),
      );
      navigate("/resultat");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Kunde inte bestämma just nu.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="oc-home">
      <div className="oc-hero-glow" aria-hidden="true" />
      <h1 className="oc-hero-title">{home.headline}</h1>
      <p className="oc-hero-sub">{home.sub}</p>
      <button
        type="button"
        className="oc-cta"
        disabled={busy}
        onClick={() =>
          runDecide({ domain_hint: "food", meal_type: home.meal_type ?? null })
        }
      >
        {busy ? "Bestämmer…" : home.cta}
      </button>

      <p className="oc-section-label">{home.section_label}</p>
      <div className="oc-domain-grid">
        {home.domains.map((d) => (
          <button
            key={d.id}
            type="button"
            className="oc-domain"
            disabled={busy}
            onClick={() => {
              if (d.id === "fridge") {
                navigate("/profil"); // fridge capture comes next iteration
                return;
              }
              runDecide({
                domain_hint: d.id,
                meal_type: d.id === "food" ? home.meal_type ?? null : null,
              });
            }}
          >
            <DomainIcon id={d.id} />
            <span>{d.label}</span>
          </button>
        ))}
      </div>

      <button
        type="button"
        className="oc-something-else"
        onClick={() => setFreeOpen((v) => !v)}
      >
        {home.something_else}
      </button>

      {freeOpen && (
        <form
          className="oc-free"
          onSubmit={(e) => {
            e.preventDefault();
            const q = freeText.trim();
            if (!q) return;
            runDecide({ question: q, domain_hint: null });
          }}
        >
          <input
            value={freeText}
            onChange={(e) => setFreeText(e.target.value)}
            placeholder="Vad ska du bestämma?"
            maxLength={200}
            aria-label="Fri text"
          />
          <button type="submit" className="oc-cta" disabled={busy || !freeText.trim()}>
            Bestäm åt mig
          </button>
        </form>
      )}

      {error && <p className="oc-error">{error}</p>}
    </section>
  );
}
