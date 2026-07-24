import type { Decision } from "./types";

export type Recipe = {
  title?: string;
  steps?: string[];
  ingredient_lines?: string[];
  ingredients?: string[];
  ingredients_structured?: { name?: string; amount?: string | number; unit?: string }[];
  active_minutes?: number | null;
  total_minutes?: number | null;
  portioner?: number | null;
  portions?: number | null;
  kcal_per_portion?: number | null;
  protein_g_per_portion?: number | null;
  fat_g_per_portion?: number | null;
  carbs_g_per_portion?: number | null;
  nutrition?: {
    kcal?: number | null;
    protein_g?: number | null;
    fat_g?: number | null;
    carbs_g?: number | null;
    kcal_per_portion?: number | null;
    protein_g_per_portion?: number | null;
    fat_g_per_portion?: number | null;
    carbs_g_per_portion?: number | null;
  } | null;
};

export type ShoppingBundle = {
  to_buy?: Record<string, string[] | string>;
  assumed_at_home?: string[];
  recipe?: Recipe;
};

export type NutritionStats = {
  kcal: number;
  protein_g: number;
  fat_g: number;
  carbs_g: number;
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
  return asRecord(ctx.shopping) as ShoppingBundle | null;
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

function normName(s: string): string {
  return s
    .normalize("NFD")
    .replace(/\p{M}/gu, "")
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

export function amountMap(recipe: Recipe | null): Record<string, string> {
  const out: Record<string, string> = {};
  if (!recipe) return out;
  const structured = recipe.ingredients_structured;
  if (Array.isArray(structured)) {
    for (const ing of structured) {
      if (!ing || typeof ing !== "object") continue;
      const name = normName(String(ing.name || ""));
      if (!name) continue;
      const amt = [ing.amount, ing.unit].filter((x) => x != null && String(x)).join(" ");
      if (amt) out[name] = amt.trim();
    }
  }
  for (const line of recipeIngredients(recipe)) {
    const parts = line.split(/\s*[—–-]\s*/);
    if (parts.length < 2) continue;
    const name = normName(parts[0] || "");
    const amt = parts.slice(1).join(" — ").trim();
    if (name && amt && !out[name]) out[name] = amt;
  }
  return out;
}

export function splitShopLabel(raw: string): { name: string; skipHint: boolean } {
  const text = String(raw || "").trim();
  const low = text.toLowerCase();
  const skipHint = low.includes("hoppa över") || low.includes("skip if");
  const parts = text.split(/\s*[—–-]\s*/);
  return { name: (parts[0] || text).trim(), skipHint };
}

export function flattenToBuy(
  shop: ShoppingBundle | null,
): { section: string; name: string; key: string; amount?: string; skipHint: boolean }[] {
  if (!shop?.to_buy || typeof shop.to_buy !== "object") return [];
  const out: {
    section: string;
    name: string;
    key: string;
    amount?: string;
    skipHint: boolean;
  }[] = [];
  let idx = 0;
  for (const [section, raw] of Object.entries(shop.to_buy)) {
    const items = typeof raw === "string" ? [raw] : Array.isArray(raw) ? raw : [];
    for (const item of items) {
      const { name, skipHint } = splitShopLabel(String(item || ""));
      if (!name) continue;
      out.push({ section, name, key: `${idx}:${name}`, skipHint });
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
  // Prefer API flag (Python food_domain.show_shopping) — one source of truth.
  if (typeof d.allows_shopping === "boolean") {
    return d.allows_shopping;
  }
  const shop = extractShopping(d);
  return Boolean(shop?.to_buy && Object.keys(shop.to_buy).length);
}

export function nutritionStats(recipe: Recipe | null): NutritionStats | null {
  if (!recipe) return null;
  const nut = recipe.nutrition || {};
  const num = (...keys: (string | number | null | undefined)[]): number | null => {
    for (const k of keys) {
      if (k == null || k === "") continue;
      const n = Number(k);
      if (Number.isFinite(n)) return Math.round(n);
    }
    return null;
  };
  const kcal = num(
    recipe.kcal_per_portion,
    nut.kcal_per_portion,
    nut.kcal,
  );
  const protein = num(
    recipe.protein_g_per_portion,
    nut.protein_g_per_portion,
    nut.protein_g,
  );
  if (kcal == null || protein == null) return null;
  return {
    kcal,
    protein_g: protein,
    fat_g: num(recipe.fat_g_per_portion, nut.fat_g_per_portion, nut.fat_g) ?? 0,
    carbs_g: num(recipe.carbs_g_per_portion, nut.carbs_g_per_portion, nut.carbs_g) ?? 0,
  };
}

export function assumedLine(shop: ShoppingBundle | null): string {
  const items = shop?.assumed_at_home?.length
    ? shop.assumed_at_home
    : ["salt", "peppar", "olja"];
  return `Hemma antas: ${items.join(", ")}.`;
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
