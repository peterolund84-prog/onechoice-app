import { useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { Heart, Share2 } from "lucide-react";
import { api } from "../lib/api";
import {
  decisionId,
  readDecision,
  saveDecision,
} from "../lib/decisionStorage";
import { resolveDishPublicPath } from "../lib/dishImage";
import {
  amountMap,
  assumedLine,
  decisionContext,
  extractRecipe,
  extractShopping,
  flattenToBuy,
  mealAllowsShopping,
  metaLine,
  nutritionStats,
  recipeIngredients,
  recipeSteps,
  selectedToBuy,
  type Recipe,
  type ShoppingBundle,
} from "../lib/foodContext";
import type { Decision } from "../lib/types";

type WorkoutBlock = {
  name?: string;
  type?: string;
  sets?: number;
  reps?: number;
  seconds?: number;
  rest_seconds?: number;
  cue?: string;
};

type Workout = {
  title?: string;
  total_minutes?: number;
  blocks?: WorkoutBlock[];
};

function dishHint(d: Decision): string | null {
  const ctx = d.context;
  if (!ctx || typeof ctx !== "object") return null;
  const hint = ctx.dish_category ?? ctx.category;
  return typeof hint === "string" ? hint : null;
}

function mediaSrc(d: Decision): string | null {
  if (d.domain === "food" && d.suggestion) {
    const local = resolveDishPublicPath(d.suggestion, dishHint(d));
    if (local) return local;
    if (typeof d.image_data_url === "string" && d.image_data_url.startsWith("data:")) {
      return d.image_data_url;
    }
    const q = new URLSearchParams({ title: d.suggestion });
    const hint = dishHint(d);
    if (hint) q.set("hint", hint);
    return `${api.base}/v1/media/dish?${q}`;
  }
  return null;
}

function WorkoutExecute({
  decision,
  workout,
}: {
  decision: Decision;
  workout: Workout;
}) {
  const navigate = useNavigate();
  const blocks = workout.blocks || [];
  const [phase, setPhase] = useState<"overview" | "play" | "done">("overview");
  const [blockI, setBlockI] = useState(0);
  const [setI, setSetI] = useState(0);
  const [restLeft, setRestLeft] = useState<number | null>(null);

  useEffect(() => {
    if (restLeft == null || restLeft <= 0) return;
    const t = window.setTimeout(() => setRestLeft((n) => (n == null ? null : n - 1)), 1000);
    return () => window.clearTimeout(t);
  }, [restLeft]);

  const current = blocks[blockI];

  function nextSet() {
    if (!current) return;
    const sets = Math.max(1, Number(current.sets || 1));
    const rest = Math.max(0, Number(current.rest_seconds || 0));
    if (setI + 1 < sets) {
      setSetI((s) => s + 1);
      if (rest > 0) setRestLeft(rest);
      return;
    }
    if (blockI + 1 < blocks.length) {
      setBlockI((i) => i + 1);
      setSetI(0);
      if (rest > 0) setRestLeft(rest);
      return;
    }
    setPhase("done");
  }

  return (
    <section className="oc-result oc-execute">
      <h1 className="oc-result-title">{decision.suggestion}</h1>
      <div className="oc-lock">Låst</div>
      {workout.total_minutes ? (
        <p className="oc-exec-meta">Ca {workout.total_minutes} min</p>
      ) : null}

      {phase === "overview" ? (
        <>
          <div className="oc-recipe">
            <div className="oc-shop-title">Passet</div>
            <ol>
              {blocks.map((b, i) => (
                <li key={`${i}-${b.name}`}>
                  <strong>{b.name}</strong>
                  {" — "}
                  {(b.type || "reps") === "time"
                    ? `${b.sets || 1}×${b.seconds || 30}s`
                    : `${b.sets || 1}×${b.reps || 10}`}
                  {b.cue ? <div className="oc-muted-line">{b.cue}</div> : null}
                </li>
              ))}
            </ol>
          </div>
          <button type="button" className="oc-cta" onClick={() => setPhase("play")}>
            Kör
          </button>
        </>
      ) : null}

      {phase === "play" && current ? (
        <div className="oc-recipe">
          <div className="oc-shop-title">{current.name}</div>
          <p className="oc-exec-meta">
            Block {blockI + 1}/{blocks.length} · Set {setI + 1}/
            {Math.max(1, Number(current.sets || 1))}
          </p>
          <p className="oc-result-body">
            {(current.type || "reps") === "time"
              ? `${current.seconds || 30} sekunder`
              : `${current.reps || 10} reps`}
          </p>
          {current.cue ? <p className="oc-page-sub">{current.cue}</p> : null}
          {restLeft != null && restLeft > 0 ? (
            <p className="oc-ok">Vila {restLeft}s</p>
          ) : (
            <button type="button" className="oc-cta" onClick={nextSet}>
              Nästa
            </button>
          )}
        </div>
      ) : null}

      {phase === "done" ? (
        <div className="oc-stack" style={{ maxWidth: 320 }}>
          <p className="oc-ok">Klart — bra jobbat.</p>
          <button type="button" className="oc-cta" onClick={() => navigate("/")}>
            Till Hem
          </button>
        </div>
      ) : null}

      {phase !== "done" ? (
        <button
          type="button"
          className="oc-btn oc-btn-ghost"
          style={{ marginTop: 12 }}
          onClick={() => navigate("/resultat")}
        >
          Tillbaka
        </button>
      ) : null}
    </section>
  );
}

export function ExecutePage() {
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
  const [merged, setMerged] = useState(false);
  const [checked, setChecked] = useState<Record<string, boolean>>({});
  const [healedRecipe, setHealedRecipe] = useState<Recipe | null>(null);
  const [healedShop, setHealedShop] = useState<ShoppingBundle | null>(null);

  const isWorkout =
    decision?.domain === "workout" || decision?.execution_type === "workout";
  const workout = useMemo(() => {
    if (!decision || !isWorkout) return null;
    const ctx = decisionContext(decision);
    return (ctx.workout as Workout) || null;
  }, [decision, isWorkout]);

  useEffect(() => {
    if (!decision || isWorkout || decision.domain !== "food") return;
    let cancelled = false;
    const ctx = decisionContext(decision);
    api
      .executeFood({
        suggestion: String(decision.suggestion || ""),
        meal_type: String(ctx.meal_type || "middag"),
        context: ctx,
      })
      .then((res) => {
        if (cancelled) return;
        if (res.recipe) setHealedRecipe(res.recipe as Recipe);
        if (res.shopping) setHealedShop(res.shopping as ShoppingBundle);
      })
      .catch(() => {
        /* keep decide payload */
      });
    return () => {
      cancelled = true;
    };
  }, [decision?.suggestion, decision?.domain, isWorkout]);

  if (!decision?.suggestion) {
    return (
      <section className="oc-result">
        <h1 className="oc-result-title">Inget recept ännu</h1>
        <p className="oc-result-sub">Gå tillbaka och gör ett val först.</p>
        <button type="button" className="oc-cta" onClick={() => navigate("/")}>
          Till Hem
        </button>
      </section>
    );
  }

  if (isWorkout) {
    return (
      <WorkoutExecute
        decision={decision}
        workout={workout || { blocks: [], total_minutes: 20 }}
      />
    );
  }

  const id = decisionId(decision);
  const recipe = healedRecipe || extractRecipe(decision);
  const shop = healedShop || extractShopping(decision);
  const showShop = mealAllowsShopping({
    ...decision,
    context: {
      ...decisionContext(decision),
      shopping: shop || undefined,
      recipe: recipe || undefined,
    },
  });
  const amounts = amountMap(recipe);
  const rawItems = showShop ? flattenToBuy(shop) : [];
  const items = rawItems.map((item) => ({
    ...item,
    amount: amounts[item.name.toLowerCase()] || amounts[
      item.name
        .normalize("NFD")
        .replace(/\p{M}/gu, "")
        .toLowerCase()
        .replace(/[^a-z0-9\s]/g, " ")
        .replace(/\s+/g, " ")
        .trim()
    ],
  }));
  const steps = recipeSteps(recipe);
  const ings = recipeIngredients(recipe);
  const src = mediaSrc(decision);
  const showImage = Boolean(src) && !imgFailed;
  const meta = metaLine(recipe, decision);
  const stats = nutritionStats(recipe);
  const checkedN = items.filter((i) => checked[i.key]).length;
  const sections = Array.from(new Set(items.map((i) => i.section)));

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
    if (!decision?.suggestion) return;
    const text = `${decision.suggestion}\n${decision.justification || ""}\n— OneChoice`.trim();
    try {
      if (navigator.share) await navigator.share({ title: "OneChoice", text });
      else if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(text);
        setMsg("Kopierat!");
      }
    } catch {
      /* cancelled */
    }
  }

  async function onCreateList() {
    if (!showShop || checkedN <= 0) return;
    setBusy(true);
    setError(null);
    try {
      const toBuy = selectedToBuy(shop, checked);
      const res = await api.mergeShopping(id, toBuy);
      setMerged(true);
      setMsg(`Lade till ${res.count} varor i listan`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Kunde inte skapa listan");
    } finally {
      setBusy(false);
    }
  }

  function markAll() {
    const next: Record<string, boolean> = {};
    for (const item of items) next[item.key] = true;
    setChecked(next);
  }

  return (
    <section className="oc-result oc-execute">
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
          <button type="button" className="oc-media-action" aria-label="Dela" onClick={onShare}>
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

      <h1 className="oc-result-title">{decision.suggestion}</h1>
      <div className="oc-lock">Låst</div>
      {meta ? <p className="oc-exec-meta">{meta}</p> : null}

      {showShop && items.length > 0 ? (
        <div className="oc-shop-card">
          <div className="oc-shop-title-row">
            <div className="oc-shop-title">Vad behöver du?</div>
            <button type="button" className="oc-link-btn" onClick={markAll}>
              Markera alla
            </button>
          </div>
          <p className="oc-result-sub">Bocka i det du ska handla.</p>
          {sections.map((section) => (
            <div key={section}>
              <div className="oc-sec-label">{section}</div>
              <ul className="oc-shop-list">
                {items
                  .filter((i) => i.section === section)
                  .map((item) => (
                    <li key={item.key}>
                      <label className="oc-check-row oc-inline">
                        <input
                          type="checkbox"
                          checked={Boolean(checked[item.key])}
                          onChange={() =>
                            setChecked((prev) => ({
                              ...prev,
                              [item.key]: !prev[item.key],
                            }))
                          }
                        />
                        <span>
                          {item.name}
                          {item.skipHint ? " (hoppa över om du har)" : ""}
                          {item.amount ? ` — ${item.amount}` : ""}
                        </span>
                      </label>
                    </li>
                  ))}
              </ul>
            </div>
          ))}
          <p className="oc-assumed">{assumedLine(shop)}</p>
        </div>
      ) : null}

      <div className="oc-recipe">
        <div className="oc-shop-title-row">
          <div className="oc-shop-title">{showShop ? "Tillagning" : "Recept"}</div>
          {stats ? <span className="oc-nut-per">per portion</span> : null}
        </div>
        {stats ? (
          <div className="oc-nut-stats" role="group" aria-label="Näringsvärden per portion">
            <div className="oc-nut-stat">
              <span className="oc-nut-val">{stats.kcal}</span>
              <span className="oc-nut-lab">KCAL</span>
            </div>
            <div className="oc-nut-stat">
              <span className="oc-nut-val">{stats.protein_g} g</span>
              <span className="oc-nut-lab">PROTEIN</span>
            </div>
            <div className="oc-nut-stat">
              <span className="oc-nut-val">{stats.fat_g} g</span>
              <span className="oc-nut-lab">FETT</span>
            </div>
            <div className="oc-nut-stat">
              <span className="oc-nut-val">{stats.carbs_g} g</span>
              <span className="oc-nut-lab">KOLH</span>
            </div>
          </div>
        ) : null}

        {!showShop && ings.length > 0 ? (
          <>
            <div className="oc-sec">Ingredienser</div>
            <ul>
              {ings.map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
          </>
        ) : null}

        {steps.length > 0 ? (
          <>
            {!showShop ? <div className="oc-sec">Gör så här</div> : null}
            <ol>
              {steps.map((step, i) => (
                <li key={`${i}-${step.slice(0, 24)}`}>{step}</li>
              ))}
            </ol>
          </>
        ) : (
          <p className="oc-result-sub">
            Kunde inte bygga ett recept för den här rätten — prova Nytt förslag.
          </p>
        )}
      </div>

      <div className="oc-stack oc-exec-cta" style={{ width: "100%", maxWidth: 320 }}>
        {showShop ? (
          merged ? (
            <button type="button" className="oc-cta" onClick={() => navigate("/lista")}>
              Öppna listan →
            </button>
          ) : (
            <button
              type="button"
              className="oc-cta"
              disabled={busy || checkedN <= 0}
              onClick={onCreateList}
            >
              {checkedN > 0
                ? `Lägg till i handlingslista (${checkedN})`
                : "Välj varor först"}
            </button>
          )
        ) : null}
        <button type="button" className="oc-btn oc-btn-ghost" onClick={() => navigate("/")}>
          Till Hem
        </button>
      </div>

      {msg ? <p className="oc-ok">{msg}</p> : null}
      {error ? <p className="oc-error">{error}</p> : null}
    </section>
  );
}
