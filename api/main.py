# -*- coding: utf-8 -*-
"""OneChoice HTML + FastAPI entrypoint (Streamlit-free UI)."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from api.routes import auth, decide, decision, history, home, lista, media, profile, share

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
DISHES = ROOT / "assets" / "dishes"
POSTERS = ROOT / "assets" / "posters"

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
if DISHES.is_dir():
    app.mount("/assets/dishes", StaticFiles(directory=str(DISHES)), name="dishes")
if POSTERS.is_dir():
    app.mount("/assets/posters", StaticFiles(directory=str(POSTERS)), name="posters")


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


# Convenience: old Streamlit habit
@app.get("/app")
def app_redirect() -> RedirectResponse:
    return RedirectResponse("/", status_code=302)
