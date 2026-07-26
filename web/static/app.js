/* OneChoice HTML client */
const DECIDE_SKELETON_MS = 400;
const DECIDE_TIMEOUT_MS = 20000;

const STATUS_LINES = {
  food: [
    "Kollar vad du åt senast…",
    "Väljer efter tid och väder…",
    "Sätter ihop receptet…",
    "Nästan klart…",
  ],
  movie: [
    "Kollar vad du sett senast…",
    "Matchar format och läge…",
    "Hittar något att titta på…",
    "Nästan klart…",
  ],
  clothes: [
    "Kollar vad du haft på dig…",
    "Väger in väder och tillfälle…",
    "Sätter ihop outfite…",
    "Nästan klart…",
  ],
  workout: [
    "Kollar senaste passen…",
    "Väljer efter energi och tid…",
    "Sätter ihop passet…",
    "Nästan klart…",
  ],
  weekend: [
    "Kollar helgläget…",
    "Väger in väder och energi…",
    "Väljer något att göra…",
    "Nästan klart…",
  ],
  generic: [
    "Tänker efter…",
    "Väger alternativen…",
    "Väljer åt dig…",
    "Nästan klart…",
  ],
};

const api = {
  async json(path, opts = {}) {
    const controller = opts.timeoutMs ? new AbortController() : null;
    const timer =
      controller && opts.timeoutMs
        ? setTimeout(() => controller.abort(), opts.timeoutMs)
        : null;
    try {
      const res = await fetch(path, {
        credentials: "include",
        headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
        ...opts,
        signal: controller ? controller.signal : opts.signal,
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        let msg = data.error || res.statusText || "Något gick fel";
        if (typeof data.detail === "string") msg = data.detail;
        else if (Array.isArray(data.detail)) {
          msg = data.detail.map((d) => d.msg || JSON.stringify(d)).join("; ");
        } else if (data.detail) msg = String(data.detail);
        const err = new Error(msg);
        err.status = res.status;
        err.data = data;
        throw err;
      }
      return data;
    } catch (err) {
      if (err && err.name === "AbortError") {
        const e = new Error("Det tog för lång tid — försök igen");
        e.status = 408;
        throw e;
      }
      throw err;
    } finally {
      if (timer) clearTimeout(timer);
    }
  },
  get: (p, opts) => api.json(p, opts),
  post: (p, body, opts) =>
    api.json(p, { method: "POST", body: JSON.stringify(body || {}), ...(opts || {}) }),
  patch: (p, body, opts) =>
    api.json(p, { method: "PATCH", body: JSON.stringify(body || {}), ...(opts || {}) }),
};

function go(page) {
  window.location.href = page;
}

function esc(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function navActive(name) {
  document.querySelectorAll(".nav a").forEach((a) => {
    a.classList.toggle("active", a.dataset.nav === name);
  });
}

const NAV_SVGS = {
  home: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 10.5 12 3l9 7.5"/><path d="M5 10v10a1 1 0 0 0 1 1h4v-6h4v6h4a1 1 0 0 0 1-1V10"/></svg>`,
  lista: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 6h11"/><path d="M9 12h11"/><path d="M9 18h11"/><path d="M4 6h.01"/><path d="M4 12h.01"/><path d="M4 18h.01"/></svg>`,
  history: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 12a9 9 0 1 0 3-6.7"/><path d="M3 4v5h5"/><path d="M12 7v5l3 2"/></svg>`,
  profile: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="8" r="4"/><path d="M4 20a8 8 0 0 1 16 0"/></svg>`,
};

const FILM_GLYPH = `<svg class="film-glyph" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="5" width="18" height="14" rx="2"/><path d="M7 5v14"/><path d="M17 5v14"/><path d="M3 9h4"/><path d="M3 15h4"/><path d="M17 9h4"/><path d="M17 15h4"/></svg>`;

/** Shared footer nav — ONE implementation used verbatim on every page. */
function mountNav(active) {
  const el = document.getElementById("app-nav");
  if (!el) return;
  const items = [
    ["home", "/", "Hem", NAV_SVGS.home],
    ["lista", "/lista", "Lista", NAV_SVGS.lista],
    ["history", "/history", "Historik", NAV_SVGS.history],
    ["profile", "/profile", "Profil", NAV_SVGS.profile],
  ];
  const current = active || el.getAttribute("data-active") || "";
  el.innerHTML = items
    .map(
      ([key, href, label, svg]) =>
        `<a href="${href}" data-nav="${key}"${
          key === current ? ' class="active"' : ""
        }>${svg}<span>${label}</span></a>`
    )
    .join("");
}

function mediaUrl(url) {
  if (!url) return "";
  const s = String(url).trim();
  if (!s) return "";
  try {
    if (s.startsWith("http://") || s.startsWith("https://")) {
      const u = new URL(s);
      // Never point phone clients at the Dell's localhost.
      if (
        u.hostname === "localhost" ||
        u.hostname === "127.0.0.1" ||
        u.hostname === "0.0.0.0"
      ) {
        return `${u.pathname}${u.search}`;
      }
      return s;
    }
  } catch (_) {}
  if (s.startsWith("//")) return s;
  if (s.startsWith("/")) return s;
  return `/${s}`;
}

const ICONS = {
  /* Bowl + chopsticks — premium home mockup */
  utensils: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 21a9 9 0 0 0 9-9H3a9 9 0 0 0 9 9Z"/><path d="M7 21h10"/><path d="M19.5 12 22 6"/><path d="M16.25 12 18 8"/><path d="M14.5 12l1-6"/></svg>`,
  hanger: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M9 5a3 3 0 1 1 5.1 2.1l-1.5 1.5A2 2 0 0 0 12 10v1"/><path d="M4 21a2 2 0 0 1-1.1-3.7L12 11l9.2 6.4A2 2 0 0 1 20 21Z"/></svg>`,
  clapper: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="m12.296 3.464 3.02 3.956"/><path d="M20.2 6 3 11l-.9-2.4c-.3-1.1.3-2.2 1.3-2.5l13.5-4c1.1-.3 2.2.3 2.5 1.3z"/><path d="M3 11h18v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><path d="m6.18 5.276 3.1 3.899"/><path d="M10 14.5v3l3-1.5z"/></svg>`,
  dumbbell: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M17.596 12.768a2 2 0 1 0 2.829-2.829l-1.768-1.767a2 2 0 0 0 2.828-2.829l-2.828-2.828a2 2 0 0 0-2.829 2.828l-1.767-1.768a2 2 0 1 0-2.829 2.829z"/><path d="m2.5 21.5 1.4-1.4"/><path d="m20.1 3.9 1.4-1.4"/><path d="M5.343 21.485a2 2 0 1 0 2.829-2.828l1.767 1.768a2 2 0 1 0 2.829-2.829l-6.364-6.364a2 2 0 1 0-2.829 2.829l1.768 1.767a2 2 0 0 0-2.828 2.829z"/><path d="m9.6 14.4 4.8-4.8"/></svg>`,
  suitcase: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><path d="M4 10h16"/><path d="M4 10v10a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V10"/><path d="M10 14h4"/></svg>`,
  gift: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M20 12v10H4V12"/><path d="M2 7h20v5H2z"/><path d="M12 22V7"/><path d="M12 7H7.5a2.5 2.5 0 0 1 0-5C11 2 12 7 12 7z"/><path d="M12 7h4.5a2.5 2.5 0 0 0 0-5C13 2 12 7 12 7z"/></svg>`,
};

const SPARK = `<svg class="cta-spark" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l1.4 5.2L18 9l-4 2.6L15.4 17 12 14.2 8.6 17 10 11.6 6 9l4.6-.8L12 3z"/></svg>`;

const TIP_ICO = `<svg viewBox="0 0 24 24" fill="none" stroke="#3B3BC4" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M10 9.5v5l4.5-2.5z"/></svg>`;

function statusLinesFor(domain) {
  const key = (domain || "generic").toLowerCase();
  return STATUS_LINES[key] || STATUS_LINES.generic;
}

function skeletonHtml(domain) {
  const lines = statusLinesFor(domain);
  const status = lines.map((m) => `<span>${esc(m)}</span>`).join("");
  const d = (domain || "food").toLowerCase();
  if (d === "movie") {
    return `
      <article class="panel decision-card movie-card oc-skel-card" aria-busy="true">
        <div class="movie-row">
          <div class="movie-poster oc-skel-shimmer" aria-hidden="true"></div>
          <div class="movie-col">
            <div class="oc-skel-bar is-title" style="width:70%"></div>
            <div class="oc-skel-bar" style="width:50%"></div>
            <div class="oc-skel-bar" style="width:40%"></div>
            <div class="oc-skel-status" aria-live="polite">${status}</div>
          </div>
        </div>
      </article>`;
  }
  return `
    <article class="panel decision-card food-card oc-skel-card" aria-busy="true">
      <div class="food-img oc-skel-shimmer" aria-hidden="true"></div>
      <div class="food-body">
        <div class="oc-skel-bar is-title" style="width:70%"></div>
        <div class="oc-skel-bar" style="width:50%"></div>
        <div class="oc-skel-bar" style="width:40%"></div>
        <div class="oc-skel-status" aria-live="polite">${status}</div>
      </div>
    </article>`;
}

function showDecideSkeleton(host, domain) {
  if (!host) return null;
  const wrap = document.createElement("div");
  wrap.id = "oc-decide-skel";
  wrap.className = "oc-decide-skel-host";
  wrap.innerHTML = skeletonHtml(domain);
  host.innerHTML = "";
  host.appendChild(wrap);
  return wrap;
}

function hideDecideSkeleton() {
  const el = document.getElementById("oc-decide-skel");
  if (el) el.remove();
}

async function withDecideLoading(host, domain, work) {
  let shown = false;
  const delay = setTimeout(() => {
    shown = true;
    showDecideSkeleton(host, domain);
  }, DECIDE_SKELETON_MS);
  try {
    const data = await work();
    clearTimeout(delay);
    hideDecideSkeleton();
    if (shown && host) {
      host.classList.add("oc-card-arrive");
      setTimeout(() => host.classList.remove("oc-card-arrive"), 450);
    }
    return data;
  } catch (err) {
    clearTimeout(delay);
    hideDecideSkeleton();
    throw err;
  }
}

async function ensureGuest() {
  try {
    await api.post("/api/auth/guest", {});
  } catch (_) {}
}

async function routeDecide(payload) {
  const domain = (payload && payload.domain_hint) || "food";
  const host = document.getElementById("app");
  const data = await withDecideLoading(host, domain, () =>
    api.post("/api/decide", payload || {}, { timeoutMs: DECIDE_TIMEOUT_MS })
  );
  const nav = (typeof window !== "undefined" && window.OC && window.OC.go) || go;
  const page = data.page || "result";
  if (page === "result" || page === "refused") nav("/result");
  else if (page === "clothes_occasion") {
    sessionStorage.setItem("oc_occasions", JSON.stringify(data.occasions || []));
    nav("/result?mode=occasion");
  } else if (page === "execute") nav("/execute");
  else nav("/result");
  return data;
}

function showToast(message) {
  try {
    const existing = document.getElementById("oc-toast");
    if (existing) existing.remove();
    const el = document.createElement("div");
    el.id = "oc-toast";
    el.setAttribute("role", "status");
    el.textContent = message || "Kopierat";
    el.className = "oc-toast";
    document.body.appendChild(el);
    setTimeout(() => {
      el.classList.add("fade");
      setTimeout(() => el.remove(), 350);
    }, 1500);
  } catch (_) {}
}

async function copyText(text) {
  const full = text || "";
  try {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(full);
      showToast("Kopierat");
      return;
    }
  } catch (_) {}
  try {
    const ta = document.createElement("textarea");
    ta.value = full;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand("copy");
    ta.remove();
    showToast("Kopierat");
  } catch (_) {
    showToast("Kunde inte kopiera");
  }
}

function absoluteUrl(pathOrUrl) {
  const s = String(pathOrUrl || "").trim();
  if (!s) return "";
  if (s.startsWith("http://") || s.startsWith("https://")) return s;
  return `${window.location.origin}${s.startsWith("/") ? s : `/${s}`}`;
}

function isAppleTouch() {
  try {
    return (
      /iPad|iPhone|iPod/.test(navigator.userAgent || "") ||
      (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1)
    );
  } catch (_) {
    return false;
  }
}

async function shareNative(title, text, url) {
  if (!navigator.share) return false;
  try {
    // iOS often rejects {text, url} together and needs the call inside the tap.
    if (isAppleTouch()) {
      const combined = [text, url].filter(Boolean).join("\n");
      await navigator.share({ text: combined || title || "OneChoice" });
      return true;
    }
    const data = { title: title || "OneChoice" };
    if (text) data.text = text;
    if (url) data.url = url;
    if (navigator.canShare && !navigator.canShare(data)) {
      await navigator.share({
        title: data.title,
        text: [text, url].filter(Boolean).join("\n"),
      });
    } else {
      await navigator.share(data);
    }
    return true;
  } catch (err) {
    if (err && err.name === "AbortError") return true;
    return false;
  }
}

function closeShareSheet() {
  const el = document.getElementById("oc-share-sheet");
  if (el) el.remove();
}

function openShareSheet(text, url) {
  closeShareSheet();
  const full = url ? `${text}\n${url}` : text;
  const encoded = encodeURIComponent(full);
  const smsHref = isAppleTouch()
    ? `sms:&body=${encoded}`
    : `sms:?body=${encoded}`;
  const waHref = `https://wa.me/?text=${encoded}`;
  // Messenger deep link works when the app is installed; link-only is the reliable bit.
  const msgHref = url
    ? `fb-messenger://share/?link=${encodeURIComponent(url)}`
    : `fb-messenger://`;

  const sheet = document.createElement("div");
  sheet.id = "oc-share-sheet";
  sheet.className = "oc-share-sheet";
  sheet.innerHTML = `
    <button type="button" class="oc-share-backdrop" aria-label="Stäng"></button>
    <div class="oc-share-panel" role="dialog" aria-label="Dela">
      <p class="oc-share-title">Dela</p>
      <a class="oc-share-opt" data-share="sms" href="${smsHref}">Meddelanden / SMS</a>
      <a class="oc-share-opt" data-share="wa" href="${waHref}" target="_blank" rel="noopener">WhatsApp</a>
      <a class="oc-share-opt" data-share="msg" href="${msgHref}">Messenger</a>
      <button type="button" class="oc-share-opt" data-share="copy">Kopiera text</button>
      <button type="button" class="oc-share-cancel" data-share="cancel">Avbryt</button>
    </div>`;
  document.body.appendChild(sheet);

  const onDone = () => closeShareSheet();
  sheet.querySelector(".oc-share-backdrop").onclick = onDone;
  sheet.querySelector('[data-share="cancel"]').onclick = onDone;
  sheet.querySelector('[data-share="copy"]').onclick = async () => {
    await copyText(full);
    onDone();
  };
  // SMS / WA / Messenger: let the <a> navigate; dismiss sheet shortly after.
  sheet.querySelectorAll("a.oc-share-opt").forEach((a) => {
    a.addEventListener("click", () => setTimeout(onDone, 300));
  });
}

async function shareDecision(fallbackText) {
  const btn =
    typeof document !== "undefined" ? document.getElementById("shareBtn") : null;
  let title = "OneChoice";
  // Prefer data already on the button so Web Share keeps the user gesture.
  let text = (btn && btn.dataset.shareText) || fallbackText || "";
  let url = absoluteUrl((btn && btn.dataset.shareUrl) || "");

  // Warm payload if missing (common on first tap).
  if (!url || !text) {
    try {
      const bundle = await api.get("/api/decision/share");
      title = bundle.title || title;
      text = bundle.text || text;
      if (bundle.url) url = absoluteUrl(bundle.url);
      if (btn) {
        if (text) btn.dataset.shareText = text;
        if (url) btn.dataset.shareUrl = url;
      }
    } catch (_) {}
  }

  // Secure contexts (HTTPS / localhost) get the OS sheet.
  // http://192.168.x.x has no navigator.share — show our own targets instead of only "Kopierat".
  if (await shareNative(title, text, url)) return;
  openShareSheet(text || title, url);
}

/** Prefetch share token/url onto #shareBtn so the next tap can open the sheet. */
async function warmShareButton() {
  try {
    const btn = document.getElementById("shareBtn");
    if (!btn) return;
    const bundle = await api.get("/api/decision/share");
    if (bundle.text) btn.dataset.shareText = bundle.text;
    if (bundle.url) btn.dataset.shareUrl = absoluteUrl(bundle.url);
  } catch (_) {}
}

async function toggleFavorite(btn) {
  try {
    const res = await api.post("/api/decision/favorite", {});
    const on = !!res.favorite;
    if (btn) {
      btn.classList.toggle("is-on", on);
      btn.setAttribute("aria-label", on ? "Ta bort favorit" : "Spara som favorit");
    }
    return on;
  } catch (e) {
    showToast(e.message || "Kunde inte spara favorit");
    return null;
  }
}

const HEART_SVG = `<svg class="icon-svg" viewBox="0 0 24 24" aria-hidden="true"><path d="M19 14c1.49-1.46 3-3.21 3-5.5A5.5 5.5 0 0 0 16.5 3c-1.76 0-3 .5-4.5 2-1.5-1.5-2.74-2-4.5-2A5.5 5.5 0 0 0 2 8.5c0 2.3 1.5 4.05 3 5.5l7 7Z"/></svg>`;
const SHARE_SVG = `<svg class="icon-svg" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 14V3"/><path d="M8 7l4-4 4 4"/><path d="M5 11v9a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-9"/></svg>`;

function cardActionsHtml({ isFavorite, shareText, shareUrl }) {
  const on = isFavorite ? " is-on" : "";
  const urlAttr = shareUrl ? ` data-share-url="${esc(shareUrl)}"` : "";
  return `
    <div class="card-actions-bar" aria-hidden="false">
      <button type="button" class="icon-btn fav-btn${on}" id="favBtn"
        aria-label="${isFavorite ? "Ta bort favorit" : "Spara som favorit"}">${HEART_SVG}</button>
      <button type="button" class="icon-btn share-btn" id="shareBtn"
        data-share-text="${esc(shareText || "")}"${urlAttr}
        aria-label="Dela">${SHARE_SVG}</button>
    </div>`;
}

function bindCardActions() {
  const fav = document.getElementById("favBtn");
  const share = document.getElementById("shareBtn");
  if (fav) fav.onclick = (e) => {
    e.preventDefault();
    e.stopPropagation();
    toggleFavorite(fav);
  };
  if (share) share.onclick = (e) => {
    e.preventDefault();
    e.stopPropagation();
    shareDecision(share.dataset.shareText || "");
  };
  warmShareButton();
}

function posterPhHtml() {
  return `<div class="movie-poster movie-poster-ph movie-poster-ph--compact" aria-hidden="true">${FILM_GLYPH}</div>`;
}

function phImg(img) {
  try {
    const cls = (img.className || "food-img").split(/\s+/)[0];
    const div = document.createElement("div");
    if (cls === "movie-poster") {
      div.className = "movie-poster movie-poster-ph movie-poster-ph--compact";
      div.setAttribute("aria-hidden", "true");
      div.innerHTML = FILM_GLYPH;
    } else {
      div.className = `${cls} ${cls}-ph`;
      div.setAttribute("aria-hidden", "true");
      div.innerHTML = '<div class="food-ph-circle"></div>';
    }
    img.replaceWith(div);
  } catch (_) {}
}

function imgOrPh(url, className) {
  const src = mediaUrl(url);
  if (!src) {
    if (className === "movie-poster") return posterPhHtml();
    return `<div class="${className} ${className}-ph" aria-hidden="true"><div class="food-ph-circle"></div></div>`;
  }
  return `<img class="${className}" src="${esc(src)}" alt="" loading="lazy" onerror="window.OC&&window.OC.phImg(this)" />`;
}

function registerServiceWorker() {
  try {
    if (!("serviceWorker" in navigator)) return;
    window.addEventListener("load", () => {
      navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch(() => {});
    });
  } catch (_) {}
}

registerServiceWorker();

// Shared footer — mount once from #app-nav so pages cannot drift to labels-only.
try {
  const bootNav = document.getElementById("app-nav");
  if (bootNav) mountNav(bootNav.getAttribute("data-active") || "");
} catch (_) {}

window.OC = {
  api,
  go,
  esc,
  navActive,
  mountNav,
  mediaUrl,
  ICONS,
  SPARK,
  TIP_ICO,
  ensureGuest,
  routeDecide,
  showToast,
  shareDecision,
  openShareSheet,
  closeShareSheet,
  warmShareButton,
  toggleFavorite,
  cardActionsHtml,
  bindCardActions,
  imgOrPh,
  phImg,
  posterPhHtml,
  skeletonHtml,
  showDecideSkeleton,
  hideDecideSkeleton,
  withDecideLoading,
  statusLinesFor,
  DECIDE_SKELETON_MS,
  DECIDE_TIMEOUT_MS,
  STATUS_LINES,
};

// Node/vitest export
if (typeof module !== "undefined" && module.exports) {
  module.exports = window.OC;
}
