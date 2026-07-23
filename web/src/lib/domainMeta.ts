export const MEAL_OPTIONS = [
  { id: "frukost", label: "Frukost" },
  { id: "lunch", label: "Lunch" },
  { id: "middag", label: "Middag" },
  { id: "kvallsmal", label: "Kvällsmål" },
] as const;

export const FORMAT_OPTIONS = [
  { id: "avsnitt", label: "Avsnitt" },
  { id: "film", label: "Film" },
  { id: "ny_serie", label: "Ny serie" },
] as const;

export const MOOD_OPTIONS = [
  { id: "avkopplat", label: "Avkopplat" },
  { id: "spanning", label: "Spänning" },
  { id: "skratta", label: "Skratta" },
  { id: "lar_mig", label: "Lär mig" },
  { id: "med_barnen", label: "Med barnen" },
] as const;

export const STREAMING_SERVICE_OPTIONS = [
  { id: "netflix", label: "Netflix" },
  { id: "svt_play", label: "SVT Play" },
  { id: "hbo_max", label: "HBO Max" },
  { id: "disney_plus", label: "Disney+" },
  { id: "prime", label: "Prime Video" },
  { id: "tv4_play", label: "TV4 Play" },
  { id: "viaplay", label: "Viaplay" },
] as const;

export const SERVICE_LABELS: Record<string, string> = Object.fromEntries(
  STREAMING_SERVICE_OPTIONS.map((s) => [s.id, s.label]),
);

export const OCCASION_OPTIONS = [
  { id: "jobb", label: "Jobb" },
  { id: "vardag", label: "Vardag hemma" },
  { id: "fest", label: "Fest" },
  { id: "middag", label: "Middag ute" },
  { id: "traffa", label: "Träffa folk" },
  { id: "barnkalas", label: "Barnkalas & familj" },
] as const;
