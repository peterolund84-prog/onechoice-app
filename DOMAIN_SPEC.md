# OneChoice — domain specification (canonical)

Core principle: return **one** decision the user can execute **today** without hitting
an obstacle. Candidates that fail `feasibility_check` are discarded before display —
never show a broken decision, never show substitution notes, never push a problem
back to the user.

## Shared pipeline

```
question → classify domain → profile + context + history
→ generate ~5 candidates → feasibility_check (domain validator)
→ rank survivors (80% close to accepted history / 20% wildcard "Vildkort")
→ display ONE + one-line justification + execution step
```

- Repetition guard: no repeat within **7 days** per domain
- Max **3 rerolls**, then lock
- Refusal (jobs / relationships / money / health):
  `Onechoice tar vardagsbesluten. Det här beslutet är ditt.`
- Tone: confident, warm, zero hedging. Never “du kan också…”.

## Domains

| Domain | Key feasibility rules |
|--------|------------------------|
| **food** | Swedish supermarket basics only; ≤30 min weekday / 60 min weekend; shopping list by store layout; wildcard = flavor not sourcing |
| **clothes** | Section (herr/dam/båda) + sizes; wear from wardrobe or category; buy = in-stock at SE retailers; weather hard constraint |
| **movie** | Format (Avsnitt/Film/Ny serie) + mood (not genre); subscribed services only; deep link; Med barnen = hard age gate; log format+mood every decision |
| **workout** | Only available equipment/context; time window; weather/dark for outdoor; limitations absolute; written plan in Swedish |
| **weekend** | Travel distance / car; open & in season; age-appropriate; budget; map + “ta med” |

## V1 mocks → later APIs

| Need | V1 | Later |
|------|----|--------|
| Clothing stock | `mocks.CLOTHING_CATALOG` (Zalando-style size stock) | Zalando affiliate / retailer feeds |
| Streaming availability | `mocks.STREAMING_CATALOG` (JustWatch-style) | JustWatch API |

## Code map

- `food_domain.py` / `clothes_domain.py` / `movie_domain.py` / `workout_domain.py` — domain inputs
- `feasibility.py` — validators + profile parsing
- `mocks.py` — stock + streaming catalogs
- `pipeline.py` — shared decide() flow
- `db.py` — `profile_json` for domain onboarding fields
