# OneChoice — agent notes

## Streamlit pitfalls

**Anchor-based navigation causes full page reloads.** Domain cards, hero CTAs, and any `<a href="?domain=...">` trigger a real browser navigation → Streamlit starts a **new** Python session → `session_state` is wiped.

Any state that must survive user taps (auth, active decision, checklist toggles) needs **cookie or DB persistence** — never `session_state` alone.

Prefer session-safe widgets (`st.button`, `st.pills`, `on_click`) for in-app navigation. When anchors are kept for design reasons, persist auth via browser cookie (`auth_cookie.py` + Supabase refresh token).
