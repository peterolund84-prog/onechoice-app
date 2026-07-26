# -*- coding: utf-8 -*-
"""OneChoice HTML + FastAPI entrypoint (Streamlit-free UI)."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from api.routes import auth, decide, decision, history, home, lista, media, profile, share

log = logging.getLogger("onechoice.assets")

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
DISHES = ROOT / "assets" / "dishes"
POSTERS = ROOT / "assets" / "posters"

_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


def _count_images(directory: Path) -> int:
    if not directory.is_dir():
        return 0
    return sum(
        1
        for p in directory.iterdir()
        if p.is_file() and p.suffix.lower() in _IMAGE_SUFFIXES
    )


app = FastAPI(title="OneChoice", version="html-mvp-1")

app.include_router(auth.router)
app.include_router(home.router)
app.include_router(decide.router)
app.include_router(decision.router)
app.include_router(lista.router)
app.include_router(history.router)
app.include_router(media.router)
app.include_router(share.router)
app.include_router(profile.router)

app.mount("/static", StaticFiles(directory=str(WEB / "static")), name="static")

_DISHES_MOUNTED = False
_POSTERS_MOUNTED = False

if DISHES.is_dir():
    app.mount("/assets/dishes", StaticFiles(directory=str(DISHES)), name="dishes")
    _DISHES_MOUNTED = True
    log.warning(
        "StaticFiles mount /assets/dishes → %s (%d image files)",
        DISHES.resolve(),
        _count_images(DISHES),
    )
else:
    log.error(
        "MISSING dish assets — /assets/dishes will 404. Expected directory: %s",
        DISHES.resolve(),
    )

if POSTERS.is_dir():
    app.mount("/assets/posters", StaticFiles(directory=str(POSTERS)), name="posters")
    _POSTERS_MOUNTED = True
    log.warning(
        "StaticFiles mount /assets/posters → %s (%d image files)",
        POSTERS.resolve(),
        _count_images(POSTERS),
    )
else:
    log.error(
        "MISSING poster assets — /assets/posters will 404. Expected directory: %s",
        POSTERS.resolve(),
    )


def _page(name: str) -> FileResponse:
    path = WEB / name
    if not path.is_file():
        path = WEB / "index.html"
    # Avoid sticky phone caches of HTML that point at old CSS/JS.
    return FileResponse(
        path,
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate",
            "Pragma": "no-cache",
        },
    )


@app.get("/")
def index() -> FileResponse:
    return _page("index.html")


@app.get("/result")
def result_page() -> FileResponse:
    return _page("result.html")


@app.get("/execute")
def execute_page() -> FileResponse:
    return _page("execute.html")


@app.get("/lista")
def lista_page() -> FileResponse:
    return _page("lista.html")


@app.get("/history")
def history_page() -> FileResponse:
    return _page("history.html")


@app.get("/profile")
def profile_page() -> FileResponse:
    return _page("profile.html")


@app.get("/auth")
def auth_page() -> FileResponse:
    return _page("auth.html")


@app.get("/share")
def share_page() -> FileResponse:
    return _page("share.html")


@app.get("/health")
def health() -> dict:
    return {"ok": True, "stack": "html+fastapi"}


@app.get("/health/assets")
def health_assets() -> dict:
    """Verify dish/poster static mounts without guessing."""
    dishes_count = _count_images(DISHES)
    posters_count = _count_images(POSTERS)
    return {
        "ok": bool(_DISHES_MOUNTED and _POSTERS_MOUNTED and dishes_count > 0),
        "dishes": {
            "path": str(DISHES.resolve()),
            "mounted": _DISHES_MOUNTED,
            "count": dishes_count,
        },
        "posters": {
            "path": str(POSTERS.resolve()),
            "mounted": _POSTERS_MOUNTED,
            "count": posters_count,
        },
    }


@app.get("/api/health/llm")
def health_llm() -> dict:
    """Probe LLM reachability — same signal Streamlit showed as AI: … ✓."""
    import llm_config
    from api.secrets import grok_api_key

    key = (grok_api_key() or "").strip()
    if len(key) < 8:
        return {"ok": False, "model": "", "detail": "API-nyckel saknas"}

    # Prefer a fresh probe so Profile reflects reality, not a stale key check.
    ok, detail = llm_config.llm_health_check(key, timeout=8)
    if ok:
        model = detail
        llm_config.DIAGNOSTICS.update(status="ok", model=model, detail="health_probe")
        return {"ok": True, "model": model, "detail": "probed"}

    # Fall back to candidate resolve (one probe) then report.
    try:
        model = llm_config.resolve_text_model(key, max_probes=1)
    except Exception as exc:
        return {"ok": False, "model": "", "detail": f"resolve_error:{exc}"}

    d = llm_config.DIAGNOSTICS
    status = d.get("status") or ""
    if status in ("ok", "override") and d.get("model"):
        return {"ok": True, "model": d["model"], "detail": d.get("detail") or status}
    if status == "no_key":
        return {"ok": False, "model": "", "detail": "API-nyckel saknas"}
    return {
        "ok": False,
        "model": model or d.get("model") or "",
        "detail": detail or d.get("detail") or "ingen modell svarade",
    }


@app.get("/manifest.webmanifest")
def manifest() -> FileResponse:
    return FileResponse(
        WEB / "manifest.webmanifest",
        media_type="application/manifest+json",
        headers={"Cache-Control": "public, max-age=3600"},
    )


@app.get("/sw.js")
def service_worker() -> FileResponse:
    # Service workers must be served from the site root scope.
    return FileResponse(
        WEB / "sw.js",
        media_type="application/javascript",
        headers={
            "Cache-Control": "no-cache",
            "Service-Worker-Allowed": "/",
        },
    )


# Convenience: old Streamlit habit
@app.get("/app")
def app_redirect() -> RedirectResponse:
    return RedirectResponse("/", status_code=302)
