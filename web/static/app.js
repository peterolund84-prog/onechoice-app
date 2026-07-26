/* OneChoice HTML client */
const api = {
  async json(path, opts = {}) {
    const res = await fetch(path, {
      credentials: "include",
      headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
      ...opts,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const err = new Error(data.detail || data.error || res.statusText);
      err.status = res.status;
      err.data = data;
      throw err;
    }
    return data;
  },
  get: (p) => api.json(p),
  post: (p, body) => api.json(p, { method: "POST", body: JSON.stringify(body || {}) }),
  patch: (p, body) => api.json(p, { method: "PATCH", body: JSON.stringify(body || {}) }),
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

const ICONS = {
  utensils: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M3 2v7c0 1.1.9 2 2 2h4a2 2 0 0 0 2-2V2"/><path d="M7 2v20"/><path d="M21 15V2v0a5 5 0 0 0-5 5v6c0 1.1.9 2 2 2h3Zm0 0v7"/></svg>`,
  hanger: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M9 5a3 3 0 1 1 5.1 2.1l-1.5 1.5A2 2 0 0 0 12 10v1"/><path d="M4 21a2 2 0 0 1-1.1-3.7L12 11l9.2 6.4A2 2 0 0 1 20 21Z"/></svg>`,
  clapper: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="m12.296 3.464 3.02 3.956"/><path d="M20.2 6 3 11l-.9-2.4c-.3-1.1.3-2.2 1.3-2.5l13.5-4c1.1-.3 2.2.3 2.5 1.3z"/><path d="M3 11h18v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><path d="m6.18 5.276 3.1 3.899"/></svg>`,
  dumbbell: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M17.596 12.768a2 2 0 1 0 2.829-2.829l-1.768-1.767a2 2 0 0 0 2.828-2.829l-2.828-2.828a2 2 0 0 0-2.829 2.828l-1.767-1.768a2 2 0 1 0-2.829 2.829z"/><path d="m2.5 21.5 1.4-1.4"/><path d="m20.1 3.9 1.4-1.4"/><path d="M5.343 21.485a2 2 0 1 0 2.829-2.828l1.767 1.768a2 2 0 1 0 2.829-2.829l-6.364-6.364a2 2 0 1 0-2.829 2.829l1.768 1.767a2 2 0 0 0-2.828 2.829z"/><path d="m9.6 14.4 4.8-4.8"/></svg>`,
  suitcase: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><path d="M4 10h16"/><path d="M4 10v10a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V10"/><path d="M10 14h4"/></svg>`,
  gift: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M20 12v10H4V12"/><path d="M2 7h20v5H2z"/><path d="M12 22V7"/><path d="M12 7H7.5a2.5 2.5 0 0 1 0-5C11 2 12 7 12 7z"/><path d="M12 7h4.5a2.5 2.5 0 0 0 0-5C13 2 12 7 12 7z"/></svg>`,
};

const SPARK = `<svg class="cta-spark" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l1.4 5.2L18 9l-4 2.6L15.4 17 12 14.2 8.6 17 10 11.6 6 9l4.6-.8L12 3z"/></svg>`;

const TIP_ICO = `<svg viewBox="0 0 24 24" fill="none" stroke="#3B3BC4" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M10 9.5v5l4.5-2.5z"/></svg>`;

async function ensureGuest() {
  try {
    await api.post("/api/auth/guest", {});
  } catch (_) {}
}

async function routeDecide(payload) {
  const data = await api.post("/api/decide", payload);
  const page = data.page || "result";
  if (page === "result") go("/result");
  else if (page === "clothes_occasion") {
    sessionStorage.setItem("oc_occasions", JSON.stringify(data.occasions || []));
    go("/result?mode=occasion");
  } else if (page === "execute") go("/execute");
  else go("/result");
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

async function shareDecision(fallbackText) {
  let title = "OneChoice";
  let text = fallbackText || "";
  let url = "";
  try {
    const bundle = await api.get("/api/decision/share");
    title = bundle.title || title;
    text = bundle.text || text;
    if (bundle.url) {
      url = bundle.url.startsWith("http")
        ? bundle.url
        : `${window.location.origin}${bundle.url}`;
    }
  } catch (_) {}
  const full = url ? `${text}\n${url}` : text;
  try {
    if (navigator.share) {
      await navigator.share({ title, text, url: url || undefined });
      return;
    }
  } catch (err) {
    if (err && err.name === "AbortError") return;
  }
  await copyText(full);
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

function cardActionsHtml({ isFavorite, shareText }) {
  const on = isFavorite ? " is-on" : "";
  return `
    <div class="card-actions-bar" aria-hidden="false">
      <button type="button" class="icon-btn fav-btn${on}" id="favBtn"
        aria-label="${isFavorite ? "Ta bort favorit" : "Spara som favorit"}">${HEART_SVG}</button>
      <button type="button" class="icon-btn share-btn" id="shareBtn"
        data-share-text="${esc(shareText || "")}"
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
}

function phImg(img) {
  try {
    const cls = (img.className || "food-img").split(/\s+/)[0];
    const div = document.createElement("div");
    div.className = `${cls} ${cls}-ph`;
    div.setAttribute("aria-hidden", "true");
    div.innerHTML = '<div class="food-ph-circle"></div>';
    img.replaceWith(div);
  } catch (_) {}
}

function imgOrPh(url, className) {
  if (!url) {
    return `<div class="${className} ${className}-ph" aria-hidden="true"><div class="food-ph-circle"></div></div>`;
  }
  return `<img class="${className}" src="${esc(url)}" alt="" loading="lazy" onerror="window.OC&&window.OC.phImg(this)" />`;
}

window.OC = {
  api,
  go,
  esc,
  navActive,
  ICONS,
  SPARK,
  TIP_ICO,
  ensureGuest,
  routeDecide,
  showToast,
  shareDecision,
  toggleFavorite,
  cardActionsHtml,
  bindCardActions,
  imgOrPh,
  phImg,
};
