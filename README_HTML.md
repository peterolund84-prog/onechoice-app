# OneChoice — HTML + FastAPI (Streamlit-fri UI)

Ny stack: **ren HTML/CSS/JS** mot **FastAPI**, samma `pipeline` / `db` / domäner som tidigare.

Streamlit-appen (`streamlit run app.py`) finns kvar under övergången. Den nya UI:n är defaultvägen framåt.

## Kör lokalt (låt den stå igång)

Som med Streamlit: **starta en gång**, låt processen köra, gör `git pull`, uppdatera telefonen.
`--reload` gör att Python-ändringar laddas om automatiskt (HTML/CSS/JS behöver bara refresh).

**Windows (Dell):**

```bat
cd C:\Users\DELL\Projekt\onechoice
run_html.bat
```

eller:

```bat
py -m uvicorn api.main:app --host 0.0.0.0 --port 8080 --reload
```

Öppna `http://192.168.x.x:8080` på telefonen.  
Efter `git pull`: hård-reloada (eller öppna Profil och kolla att Build-id bytts).

Du behöver **inte** döda/starta om varje gång — bara om porten är låst eller processen kraschat.

**macOS/Linux:**

```bash
pip install -r requirements.txt
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
```

## Secrets

Samma som tidigare — antingen miljövariabler eller `.streamlit/secrets.toml`
(HTML/API läser filen **utan** Streamlit):

```bat
copy .streamlit\secrets.toml.example .streamlit\secrets.toml
```

Lägg in:

- `GROK_API_KEY` — AI-beslut (annars offline)
- `SUPABASE_URL` / `SUPABASE_KEY` — login / konton
- `TMDB_API_KEY` — film-/serieposter + betyg (utan nyckel: begränsad offline-katalog)

Kontrollera status under **Profil → Integrationer** efter restart.

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
