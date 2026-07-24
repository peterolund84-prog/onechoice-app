import { useEffect, useState } from "react";

const FOOD_LINES = [
  "Kollar vad du åt senast…",
  "Väger tid, smak och vad som finns hemma…",
  "Väljer en rätt du faktiskt kan laga nu…",
];

const MOVIE_LINES = [
  "Kollar vad som finns på dina appar…",
  "Matchar format och läge…",
  "Väljer något du orkar titta på…",
];

const DEFAULT_LINES = [
  "Tänker…",
  "Väger alternativen…",
  "Bestämmer…",
];

export function DecideSkeleton({
  domain,
}: {
  domain?: string | null;
}) {
  const lines =
    domain === "food"
      ? FOOD_LINES
      : domain === "movie"
        ? MOVIE_LINES
        : DEFAULT_LINES;
  const [idx, setIdx] = useState(0);

  useEffect(() => {
    const t = window.setInterval(() => {
      setIdx((i) => (i + 1) % lines.length);
    }, 1600);
    return () => window.clearInterval(t);
  }, [lines.length]);

  return (
    <section className="oc-result oc-skel" aria-busy="true" aria-live="polite">
      <div className="oc-media-card oc-skel-block" />
      <div className="oc-skel-line oc-skel-line--title" />
      <div className="oc-skel-line" />
      <div className="oc-skel-line oc-skel-line--short" />
      <p className="oc-skel-status">{lines[idx]}</p>
    </section>
  );
}
