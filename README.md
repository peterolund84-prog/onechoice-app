# OneChoice

AI that makes **one** everyday decision for you — never a list.

## Stack

- Frontend: Streamlit (premium mobile CSS)
- Database: SQLite (`onechoice.db`)
- LLM: Grok (xAI) via API — local fallback if no key
- Payments: Stripe (demo mode without key)

## Files

```
app.py           # Streamlit UI — one decision loop
pipeline.py      # decide() pipeline
db.py            # SQLite users / decisions / preferences
test_pipeline.py # Unit tests
```

## Data model

- **users** — language, pro, budget, dietary, location, wardrobe
- **decisions** — domain, suggestion, justification, accepted/rejected/locked, reroll index, context snapshot, execution link
- **preferences** — scored signals from accepts/rejects (the moat)

## Decision pipeline

`pipeline.decide(user_id, question, ...)`

1. Classify domain (or refuse high-stakes)
2. Collect context (time, weekday, weather, location, budget, dietary)
3. Load history + preferences
4. Generate ~5 internal candidates (Grok or local)
5. Rank with bandit (80% safe / 20% explore) + repetition guard
6. Return **only the top one** + execution step

Max 3 rerolls → lock: “It’s X. Go.”

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
