# OneChoice + Supabase

AI that makes **one** everyday decision — never a list.  
Streamlit UI · Supabase Auth + Postgres · premium mobile design.

## Projektstruktur

```
app.py                 # Streamlit UI (login, beslut, historik)
pipeline.py            # decide() — one-decision engine
db.py                  # SQLite (demo) + router till Supabase
supabase_client.py     # Auth (sign up / sign in)
supabase_store.py      # Profiles, decisions, preferences via Supabase
supabase/schema.sql    # SQL att köra i Supabase
test_pipeline.py       # Unit tests (SQLite)
.streamlit/secrets.toml
requirements.txt
```

## 1) Skapa Supabase-projekt

1. Gå till [https://supabase.com](https://supabase.com) → **New project**
2. Vänta tills projektet är klart
3. **Project Settings → API**
   - kopiera **Project URL** → `SUPABASE_URL`
   - kopiera **anon public** key → `SUPABASE_KEY`

## 2) Kör SQL-schemat

1. Öppna **SQL Editor** i Supabase
2. Klistra in hela filen `supabase/schema.sql`
3. Klicka **Run**

Schemat skapar:
- `profiles` (kopplad till `auth.users`)
- `decisions`
- `preferences`
- trigger som skapar profil vid signup
- **Row Level Security** så varje användare bara ser sin data

## 3) Auth-inställningar

1. **Authentication → Providers → Email** → aktivera
2. För snabb demo: **Authentication → Providers → Email**  
   stäng av “Confirm email” (annars måste användare bekräfta mail innan login)

## 4) Secrets lokalt

```bash
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
```

Redigera `.streamlit/secrets.toml`:

```toml
SUPABASE_URL = "https://xxxx.supabase.co"
SUPABASE_KEY = "eyJhbGciOi..."   # anon public key

GROK_API_KEY = "xai-..."         # valfritt
STRIPE_SECRET_KEY = "sk_test-..." # valfritt
```

> Använd **anon/public** key i Streamlit-klienten (RLS skyddar datan).  
> Dela aldrig `service_role` key i frontend.

## 5) Installera & kör

```bash
pip install -r requirements.txt
python -m streamlit run app.py
```

- Med Supabase-nycklar → inloggningssida (email/lösenord)
- Utan nycklar → **gästläge** med lokal SQLite (bra för demo/tester)

## 6) Streamlit Cloud

1. Pusha repo till GitHub
2. Deploya på Streamlit Cloud
3. Under **App settings → Secrets** klistra in samma `secrets.toml`-innehåll

## Funktioner

| Funktion | Beskrivning |
|----------|-------------|
| Login / signup | Supabase Auth |
| Ett beslut | Aldrig lista — `pipeline.decide()` |
| Spara beslut | Supabase `decisions` (+ SQLite i gästläge) |
| Historik | Hämtas per inloggad användare (RLS) |
| Preferenser | Accept/reject → scored preferences |
| Design | Premium koreansk estetik, mobil grid-nav |

## Tester

```bash
python -m unittest test_pipeline.py
```

Unit tests kör alltid mot SQLite (isolerad temp-db).
