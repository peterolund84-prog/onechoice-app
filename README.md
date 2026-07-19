# OneChoice + Supabase

AI that makes **one** everyday decision — never a list.  
Streamlit UI · Supabase Auth + Postgres · premium mobile design.

## Projektstruktur

```
app.py                 # Streamlit UI (login, beslut, historik)
pipeline.py            # decide() — shared one-decision pipeline
feasibility.py         # Domain validators (never show broken decisions)
mocks.py               # V1 Zalando stock + JustWatch streaming catalogs
db.py                  # SQLite (demo) + router till Supabase
supabase_client.py     # Auth (sign up / sign in)
supabase_store.py      # Profiles, decisions, preferences via Supabase
supabase/schema.sql    # SQL att köra i Supabase
DOMAIN_SPEC.md         # Canonical domain specification
test_pipeline.py       # Unit tests (SQLite)
test_feasibility.py    # Feasibility unit tests
.streamlit/secrets.toml
requirements.txt
```

## 1) Skapa Supabase-projekt

1. Gå till [https://supabase.com](https://supabase.com) → **New project**
2. **Välj EU-region** (t.ex. Frankfurt `eu-central-1` eller Stockholm) — går inte att flytta senare (GDPR)
3. Vänta tills projektet är klart
4. **Project Settings → API**
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

## Free-text router + query logging

Every free-text input goes through `router.route_question` → `pipeline.handle_free_text` (no bypass):

| Route | Behavior |
|-------|----------|
| `IN_DOMAIN` | Normal domain pipeline + feasibility |
| `NEAR_DOMAIN` | Generic one-decision engine, **no** feasibility |
| `HIGH_STAKES` | Refuse — exact copy; log only route/timestamp/user_id |
| `AMBIGUOUS` | Show 5 domain chips + **Annat** |
| `NOT_A_DECISION` | “Jag tar beslut, inte frågor…” |

Logged in `routed_queries` (+ view `near_domain_demand`). Raw text auto-nulls after 90 days.

Max input: **200 characters**.


`pipeline.decide(user_id, question, ...)`

1. Classify domain (or refuse high-stakes)
2. Collect context + parse domain profile
3. Load history + preferences (7-day repetition guard)
4. Generate ~5 internal candidates (Grok or local)
5. **Feasibility gate** — discard anything that fails the domain validator
6. Rank survivors (80% close to history / 20% wildcard)
7. Return **only the top one** + one-line justification + execution step

Max 3 rerolls → lock. See `DOMAIN_SPEC.md`.

## Funktioner

| Funktion | Beskrivning |
|----------|-------------|
| Login / signup | Supabase Auth + samtycke till [integritetspolicy](PRIVACY.md) |
| Ett beslut | Aldrig lista — `pipeline.decide()` |
| Feasibility | Trasiga beslut visas aldrig |
| Spara beslut | Supabase `decisions` (+ SQLite i gästläge) |
| Historik | Hämtas per inloggad användare (RLS) |
| Preferenser | Accept/reject → scored preferences |
| GDPR | Exportera JSON + radera konto (Profil); AI får aldrig `user_id`/e-post |
| Design | Premium koreansk estetik, mobil grid-nav |

## GDPR (före publik lansering)

1. Kör `supabase/schema.sql` (eller `migrations/20260719_gdpr.sql` på äldre projekt)
2. Bekräfta EU-region i Supabase Dashboard
3. Schemalägg `purge_routed_query_raw_text(90)` och `purge_expired_user_photos()` (pg_cron / Edge Function)
4. Läs `PRIVACY.md` — byt till egen `PRIVACY_URL` om policyn hostas externt

## Tester

```bash
python -m unittest test_pipeline.py test_feasibility.py test_gdpr.py test_router.py
```

Unit tests kör alltid mot SQLite (isolerad temp-db).
