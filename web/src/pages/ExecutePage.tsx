import { useMemo, useState } from "react";
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
  extractRecipe,
  extractShopping,
  flattenToBuy,
  mealAllowsShopping,
  metaLine,
  nutritionLine,
  recipeIngredients,
  recipeSteps,
  selectedToBuy,
} from "../lib/foodContext";
import type { Decision } from "../lib/types";

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

  if (!decision?.suggestion) {
    return (
      <section className="oc-result">
        <h1 className="oc-result-title">Inget recept ännu</h1>
        <p className="oc-result-sub">Gå tillbaka och gör ett matval först.</p>
        <button type="button" className="oc-cta" onClick={() => navigate("/")}>
          Till Hem
        </button>
      </section>
    );
  }

  const id = decisionId(decision);
  const recipe = extractRecipe(decision);
  const shop = extractShopping(decision);
  const showShop = mealAllowsShopping(decision);
  const items = showShop ? flattenToBuy(shop) : [];
  const steps = recipeSteps(recipe);
  const ings = recipeIngredients(recipe);
  const src = mediaSrc(decision);
  const showImage = Boolean(src) && !imgFailed;
  const meta = metaLine(recipe, decision);
  const nut = nutritionLine(recipe);
  const checkedN = items.filter((i) => checked[i.key]).length;

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

      <h1 className="oc-result-title">{decision.suggestion}</h1>
      <div className="oc-lock">Låst</div>
      {meta ? <p className="oc-exec-meta">{meta}</p> : null}

      {showShop && items.length > 0 ? (
        <div className="oc-shop-card">
          <div className="oc-shop-title">Vad behöver du?</div>
          <p className="oc-result-sub">Bocka i det du ska handla.</p>
          <ul className="oc-shop-list">
            {items.map((item) => (
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
                  <span>{item.name}</span>
                </label>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      <div className="oc-recipe">
        <div className="oc-shop-title-row">
          <div className="oc-shop-title">
            {showShop ? "Tillagning" : "Recept"}
          </div>
          {nut ? <span className="oc-nut-per">{nut}</span> : null}
        </div>

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
            <button
              type="button"
              className="oc-cta"
              onClick={() => navigate("/lista")}
            >
              Öppna listan →
            </button>
          ) : (
            <button
              type="button"
              className="oc-cta"
              disabled={busy || checkedN <= 0}
              onClick={onCreateList}
            >
              {checkedN > 0 ? `Lägg ${checkedN} i listan` : "Välj varor först"}
            </button>
          )
        ) : null}
        <button
          type="button"
          className="oc-btn oc-btn-ghost"
          onClick={() => navigate("/")}
        >
          Till Hem
        </button>
      </div>

      {msg ? <p className="oc-ok">{msg}</p> : null}
      {error ? <p className="oc-error">{error}</p> : null}
    </section>
  );
}
