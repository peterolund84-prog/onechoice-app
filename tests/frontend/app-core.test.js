import { beforeEach, describe, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

/**
 * Load web/static/app.js into happy-dom as a classic script (sets window.OC).
 */
async function loadOc() {
  const src = readFileSync(resolve("web/static/app.js"), "utf8");
  const body = src.replace(/\/\/ Node\/vitest export[\s\S]*$/, "");
  // eslint-disable-next-line no-new-func
  const run = new Function(`${body}; return window.OC;`);
  return run();
}

function mockFetchSequence(handlers) {
  let i = 0;
  globalThis.fetch = vi.fn(async (url, opts = {}) => {
    const path = String(url);
    const handler = handlers[i] || handlers[handlers.length - 1];
    i += 1;
    const result = await handler(path, opts);
    return {
      ok: result.ok !== false,
      status: result.status || (result.ok === false ? 400 : 200),
      statusText: result.statusText || "OK",
      json: async () => result.body ?? {},
    };
  });
}

describe("OneChoice HTML core flow", () => {
  let OC;

  beforeEach(async () => {
    document.body.innerHTML = '<main class="app" id="app"></main>';
    vi.restoreAllMocks();
    Object.defineProperty(navigator, "serviceWorker", {
      value: undefined,
      configurable: true,
    });
    OC = await loadOc();
  });

  it("builds skeleton with rotating food status lines", () => {
    const html = OC.skeletonHtml("food");
    expect(html).toContain("oc-skel-card");
    expect(html).toContain("Kollar vad du åt senast…");
    expect(html).toContain("Sätter ihop receptet…");
  });

  it("decide → result → accept → execute (mocked fetch)", async () => {
    const calls = [];
    const navigations = [];
    OC.go = (page) => navigations.push(page);

    mockFetchSequence([
      (path) => {
        calls.push(path);
        if (path.includes("/api/auth/guest")) return { body: { ok: true } };
        if (path.includes("/api/decide")) {
          return {
            body: {
              ok: true,
              page: "result",
              decision: {
                domain: "food",
                suggestion: "Pasta",
                justification: "Snabb.",
                context: { meal_type: "middag" },
              },
            },
          };
        }
        if (path.includes("/api/decision/accept")) {
          return { body: { ok: true, page: "execute" } };
        }
        return { body: {} };
      },
    ]);

    await OC.ensureGuest();
    await OC.routeDecide({ domain_hint: "food" });
    expect(navigations).toContain("/result");

    const accept = await OC.api.post("/api/decision/accept", { open_execute: true });
    expect(accept.page).toBe("execute");
    expect(calls.some((c) => c.includes("/api/decide"))).toBe(true);
    expect(calls.some((c) => c.includes("/api/decision/accept"))).toBe(true);
  });

  it("lista toggle patches checked state", async () => {
    mockFetchSequence([() => ({ body: { ok: true, checked: true } })]);
    const res = await OC.api.patch("/api/lista/items/1", { checked: true });
    expect(res.checked).toBe(true);
    const [url, opts] = globalThis.fetch.mock.calls[0];
    expect(String(url)).toContain("/api/lista/items/1");
    expect(opts.method).toBe("PATCH");
    expect(JSON.parse(opts.body)).toEqual({ checked: true });
  });

  it("auth login and logout via mocked fetch", async () => {
    mockFetchSequence([
      (path) => {
        if (path.includes("/api/auth/login")) {
          return {
            body: {
              ok: true,
              session: { authenticated: true, email: "a@b.c", guest_mode: false },
            },
          };
        }
        if (path.includes("/api/auth/logout")) {
          return { body: { ok: true, guest_mode: true } };
        }
        return { body: {} };
      },
    ]);
    const login = await OC.api.post("/api/auth/login", {
      email: "a@b.c",
      password: "secret",
    });
    expect(login.session.authenticated).toBe(true);
    const logout = await OC.api.post("/api/auth/logout", {});
    expect(logout.guest_mode).toBe(true);
  });

  it("timeout surfaces honest retry message", async () => {
    globalThis.fetch = vi.fn(
      (_url, opts = {}) =>
        new Promise((_resolve, reject) => {
          const signal = opts.signal;
          if (!signal) return;
          const onAbort = () => {
            const err = new Error("Aborted");
            err.name = "AbortError";
            reject(err);
          };
          if (signal.aborted) onAbort();
          else signal.addEventListener("abort", onAbort, { once: true });
        })
    );
    await expect(
      OC.api.post("/api/decide", {}, { timeoutMs: 20 })
    ).rejects.toThrow(/för lång tid/i);
  });

  it("mediaUrl stays origin-relative (never localhost)", () => {
    expect(OC.mediaUrl("/assets/posters/foo.jpg")).toBe("/assets/posters/foo.jpg");
    expect(OC.mediaUrl("http://localhost:8080/assets/dishes/a.jpg")).toBe(
      "/assets/dishes/a.jpg"
    );
    expect(OC.mediaUrl("http://127.0.0.1:8080/api/media/poster?u=x")).toBe(
      "/api/media/poster?u=x"
    );
    expect(OC.imgOrPh(null, "movie-poster")).toContain("movie-poster-ph--compact");
    expect(OC.imgOrPh(null, "movie-poster")).toContain("film-glyph");
  });

  it("mountNav renders icon+label for all four tabs", () => {
    document.body.innerHTML =
      '<nav class="nav" id="app-nav" data-active="lista"></nav>';
    OC.mountNav("lista");
    const links = [...document.querySelectorAll("#app-nav a")];
    expect(links).toHaveLength(4);
    expect(links.every((a) => a.querySelector("svg"))).toBe(true);
    expect(links.map((a) => a.textContent.trim())).toEqual([
      "Hem",
      "Lista",
      "Historik",
      "Profil",
    ]);
    expect(document.querySelector('[data-nav="lista"]').classList.contains("active")).toBe(
      true
    );
  });
});
