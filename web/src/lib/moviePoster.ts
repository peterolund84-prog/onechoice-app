/** Vite-hosted posters under /public/posters — no TMDB dependency on the phone. */

const POSTER_FILES: Record<string, string> = {
  seinfeld: "seinfeld.jpg",
  wednesday: "wednesday.jpg",
  vanner: "vanner.jpg",
  "vänner": "vanner.jpg",
  friends: "friends.jpg",
  "the night agent": "the-night-agent.jpg",
  andor: "andor.jpg",
  "the bear": "the-bear.jpg",
  succession: "succession.jpg",
  dune: "dune.jpg",
  "det sista kapitlet": "det-sista-kapitlet.jpg",
  "top gun maverick": "top-gun-maverick.jpg",
  bonusfamiljen: "bonusfamiljen.jpg",
  "our planet": "our-planet.jpg",
  "my octopus teacher": "my-octopus-teacher.jpg",
  hilda: "hilda.jpg",
  "kung fu panda": "kung-fu-panda.jpg",
  explained: "explained.jpg",
};

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

/** Resolve a local poster path, e.g. `/posters/seinfeld.jpg`. */
export function resolveMoviePosterPath(title: string | null | undefined): string | null {
  const norm = normalizeTitle(title || "");
  if (!norm) return null;

  const direct = POSTER_FILES[norm] || POSTER_FILES[title?.trim().toLowerCase() || ""];
  if (direct) return `/posters/${direct}`;

  // Substring match for "Seinfeld S9E3" / enriched display titles.
  const entries = Object.entries(POSTER_FILES).sort((a, b) => b[0].length - a[0].length);
  for (const [cue, file] of entries) {
    const cueN = normalizeTitle(cue);
    if (cueN && (norm === cueN || norm.includes(cueN) || cueN.includes(norm))) {
      return `/posters/${file}`;
    }
  }
  return null;
}

/** Title case for card display when API returns lowercase catalog keys. */
export function displayMovieTitle(title: string | null | undefined): string {
  const raw = (title || "").trim();
  if (!raw) return "—";
  if (raw !== raw.toLowerCase()) return raw;
  return raw
    .split(/\s+/)
    .map((w) => (w ? w[0].toUpperCase() + w.slice(1) : w))
    .join(" ");
}
