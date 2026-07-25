# OneChoice — HTML + FastAPI (Streamlit-fri UI)

Ny stack: **ren HTML/CSS/JS** mot **FastAPI**, samma `pipeline` / `db` / domäner som tidigare.

Streamlit-appen (`streamlit run app.py`) finns kvar under övergången. Den nya UI:n är defaultvägen framåt.

## Kör lokalt

```bash
pip install -r requirements.txt
uvicorn api.main:app --reload --port 8000
```

Öppna [http://127.0.0.1:8000](http://127.0.0.1:8000).

## Secrets

Samma som tidigare — antingen miljövariabler eller `.streamlit/secrets.toml`:

- `GROK_API_KEY`
- `SUPABASE_URL` / `SUPABASE_KEY` (för login)

## Struktur

```
api/                 # FastAPI
  main.py
  routes/            # auth, home, decide, decision, lista, history, profile
  services/          # decide_service (port av run_decision)
web/                 # HTML-sidor + static/
  index.html         # Hem (mockup)
  result.html
  execute.html
  lista.html
  history.html
  profile.html
  auth.html
  static/app.css
  static/app.js
```

## API (MVP)

| Metod | Path | Syfte |
|-------|------|--------|
| GET | `/api/home` | Hero + domänkort |
| POST | `/api/decide` | Ett beslut |
| GET | `/api/decision/current` | Aktivt beslut |
| POST | `/api/decision/accept` | Acceptera → execute |
| GET | `/api/lista` | Inköpslista |
| GET | `/api/history` | Historik |
| GET | `/api/profile` | Profil + AI-status |

## Tester

```bash
pytest test_api_html.py -q
```
