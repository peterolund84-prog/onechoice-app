# OneChoice

AI that makes **one** everyday decision for you — never a list.

## Stack

- Frontend: Streamlit (premium mobile CSS)
- Database: SQLite (`onechoice.db`)
- LLM: Grok (xAI) via API — local fallback if no key
- Payments: Stripe (demo mode without key)

## Files

```
app.py                # Streamlit UI — one decision loop
pipeline.py           # decide() shared pipeline
feasibility.py        # Domain validators (never show broken decisions)
mocks.py              # V1 Zalando stock + JustWatch streaming catalogs
db.py                 # SQLite users / decisions / preferences (+ profile_json)
DOMAIN_SPEC.md        # Canonical domain specification
test_pipeline.py      # Pipeline unit tests
test_feasibility.py   # Feasibility unit tests
```

## Data model

- **users** — language, pro, budget, dietary, location, wardrobe, `profile_json` (food/clothes/movie/workout/weekend onboarding)
- **decisions** — domain, suggestion, justification, accepted/rejected/locked, reroll index, context snapshot, execution link
- **preferences** — scored signals from accepts/rejects (the moat)

## Decision pipeline

`pipeline.decide(user_id, question, ...)`

1. Classify domain (or refuse high-stakes)
2. Collect context + parse domain profile
3. Load history + preferences (7-day repetition guard)
4. Generate ~5 internal candidates (Grok or local)
5. **Feasibility gate** — discard anything that fails the domain validator
6. Rank survivors (80% close to history / 20% wildcard)
7. Return **only the top one** + one-line justification + execution step

Max 3 rerolls → lock.

See `DOMAIN_SPEC.md` for per-domain rules. Clothing stock and streaming availability are **mocked in V1** (`mocks.py`); swap in Zalando affiliate + JustWatch later.

## Domains

Food · Clothes · Movie · Workout · Weekend activity

High-stakes (jobs, relationships, money, health) → hard refuse.

## Run

```bash
pip install -r requirements.txt
python -m streamlit run app.py
python -m unittest test_pipeline.py
```

## Secrets (`.streamlit/secrets.toml`)

```toml
GROK_API_KEY = "xai-..."
STRIPE_SECRET_KEY = "sk_test_..."
```
