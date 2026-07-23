import type { Decision } from "./types";

export type Recipe = {
  title?: string;
  steps?: string[];
  ingredient_lines?: string[];
  ingredients?: string[];
  active_minutes?: number | null;
  total_minutes?: number | null;
  portioner?: number | null;
  portions?: number | null;
  kcal_per_portion?: number | null;
  protein_g_per_portion?: number | null;
  nutrition?: {
    kcal?: number | null;
    protein_g?: number | null;
    kcal_per_portion?: number | null;
    protein_g_per_portion?: number | null;
  } | null;
};

export type ShoppingBundle = {
  to_buy?: Record<string, string[] | string>;
  recipe?: Recipe;
};

export function asRecord(value: unknown): Record<string, unknown> | null {
  if (!value) return null;
  if (typeof value === "object" && !Array.isArray(value)) {
    return value as Record<string, unknown>;
  }
  if (typeof value === "string") {
    try {
      const parsed = JSON.parse(value) as unknown;
      if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
        return parsed as Record<string, unknown>;
      }
    } catch {
      return null;
    }
  }
  return null;
}

export function decisionContext(d: Decision): Record<string, unknown> {
  return asRecord(d.context) || {};
}

export function extractShopping(d: Decision): ShoppingBundle | null {
  const ctx = decisionContext(d);
  const shop = asRecord(ctx.shopping);
  return shop as ShoppingBundle | null;
}

export function extractRecipe(d: Decision): Recipe | null {
  const ctx = decisionContext(d);
  const shop = extractShopping(d);
  const fromCtx = asRecord(ctx.recipe) as Recipe | null;
  if (fromCtx && (fromCtx.steps?.length || fromCtx.ingredient_lines?.length)) {
    return fromCtx;
  }
  const fromShop = shop?.recipe ? (asRecord(shop.recipe) as Recipe | null) : null;
  if (fromShop) return fromShop;
  return fromCtx;
}

export function recipeIngredients(recipe: Recipe | null): string[] {
  if (!recipe) return [];
  const lines = recipe.ingredient_lines || recipe.ingredients || [];
  return lines.map((x) => String(x)).filter(Boolean);
}

export function recipeSteps(recipe: Recipe | null): string[] {
  if (!recipe) return [];
  return (recipe.steps || []).map((x) => String(x)).filter(Boolean);
}

export function flattenToBuy(
  shop: ShoppingBundle | null,
): { section: string; name: string; key: string }[] {
  if (!shop?.to_buy || typeof shop.to_buy !== "object") return [];
  const out: { section: string; name: string; key: string }[] = [];
  let idx = 0;
  for (const [section, raw] of Object.entries(shop.to_buy)) {
    const items = typeof raw === "string" ? [raw] : Array.isArray(raw) ? raw : [];
    for (const item of items) {
      const name = String(item || "").trim();
      if (!name) continue;
      out.push({ section, name, key: `${idx}:${name}` });
      idx += 1;
    }
  }
  return out;
}

export function selectedToBuy(
  shop: ShoppingBundle | null,
  checked: Record<string, boolean>,
): Record<string, string[]> {
  const items = flattenToBuy(shop);
  const out: Record<string, string[]> = {};
  for (const item of items) {
    if (!checked[item.key]) continue;
    if (!out[item.section]) out[item.section] = [];
    out[item.section].push(item.name);
  }
  return out;
}

export function mealAllowsShopping(d: Decision): boolean {
  const ctx = decisionContext(d);
  const meal = String(ctx.meal_type || "middag");
  if (meal === "frukost" || meal === "kvallsmal") return false;
  const shop = extractShopping(d);
  return Boolean(shop?.to_buy && Object.keys(shop.to_buy).length);
}

export function nutritionLine(recipe: Recipe | null): string | null {
  if (!recipe) return null;
  const nut = recipe.nutrition;
  const kcal =
    recipe.kcal_per_portion ?? nut?.kcal_per_portion ?? nut?.kcal ?? null;
  const protein =
    recipe.protein_g_per_portion ??
    nut?.protein_g_per_portion ??
    nut?.protein_g ??
    null;
  const parts: string[] = [];
  if (kcal != null) parts.push(`ca ${Math.round(Number(kcal))} kcal`);
  if (protein != null) parts.push(`${Math.round(Number(protein))} g protein`);
  return parts.length ? parts.join(" · ") + " / portion" : null;
}

export function metaLine(recipe: Recipe | null, d: Decision): string | null {
  const parts: string[] = [];
  const mins =
    recipe?.active_minutes ??
    recipe?.total_minutes ??
    (decisionContext(d).max_active_minutes as number | undefined);
  if (mins != null && Number(mins) > 0) parts.push(`Ca ${Number(mins)} min`);
  const portions = recipe?.portioner ?? recipe?.portions;
  if (portions != null && Number(portions) > 0) {
    parts.push(`${Number(portions)} portioner`);
  }
  return parts.length ? parts.join(" · ") : null;
}
