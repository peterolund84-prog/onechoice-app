import rawDishFiles from "./dishFiles.json";

type DishFiles = {
  files: string[];
  keywords: Record<string, string>;
  categories: Record<string, string>;
};

const dishFiles = rawDishFiles as DishFiles;

function stripDiacritics(s: string): string {
  return s.normalize("NFD").replace(/\p{M}/gu, "");
}

function normalizeTitle(title: string): string {
  let s = stripDiacritics((title || "").trim().toLowerCase());
  s = s.replace(/ä/g, "a").replace(/å/g, "a").replace(/ö/g, "o");
  s = s.replace(/[^a-z0-9\s-]/g, " ");
  s = s.replace(/\s+/g, " ").trim();
  return s;
}

/** Resolve a Vite-public dish image path, e.g. `/dishes/yoghurt.jpg`. */
export function resolveDishPublicPath(
  title: string,
  categoryHint?: string | null,
): string | null {
  const files = Array.isArray(dishFiles?.files) ? dishFiles.files : [];
  const keywordMap =
    dishFiles?.keywords && typeof dishFiles.keywords === "object"
      ? dishFiles.keywords
      : {};
  const categoryMap =
    dishFiles?.categories && typeof dishFiles.categories === "object"
      ? dishFiles.categories
      : {};

  const norm = normalizeTitle(title);
  if (!norm || files.length === 0) return null;

  const keywords = Object.entries(keywordMap).sort(
    (a, b) => b[0].length - a[0].length,
  );
  for (const [cue, file] of keywords) {
    const cueN = normalizeTitle(cue);
    if (!cueN) continue;
    if (cueN.length <= 3) {
      const re = new RegExp(`(?:^|[^a-z0-9])${cueN}(?:[^a-z0-9]|$)`);
      if (!re.test(norm)) continue;
    } else if (!norm.includes(cueN)) {
      continue;
    }
    if (files.includes(file)) return `/dishes/${file}`;
  }

  const hint = normalizeTitle(categoryHint || "");
  if (hint && hint !== "generic" && hint !== "other") {
    const file =
      categoryMap[hint] || (hint.endsWith(".jpg") ? hint : `${hint}.jpg`);
    if (files.includes(file)) return `/dishes/${file}`;
  }
  return null;
}
