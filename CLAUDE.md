# OneChoice — agent notes

## Streamlit pitfalls

**Anchor-based navigation causes full page reloads.** Domain cards, hero CTAs, and any `<a href="?domain=...">` trigger a real browser navigation → Streamlit starts a **new** Python session → `session_state` is wiped.

Any state that must survive user taps (auth, active decision, checklist toggles) needs **cookie or DB persistence** — never `session_state` alone.

Prefer session-safe widgets (`st.button`, `st.pills`, `on_click`) for in-app navigation. When anchors are kept for design reasons, persist auth via browser cookie (`auth_cookie.py` + Supabase refresh token).

**Widget labels render visibly by default and steal layout width** — every non-decorative widget needs `label_visibility="collapsed"` (and a blank `" "` label, never the widget key). Covered by `test_no_widget_label_leaks`.

**Never style `stPills > *` with `display:flex` / grid on the meal control.** That selector is more specific than label-hide rules and re-shows the collapsed label as a grid cell (the `"meal_pills"` leak). The meal control uses four `st.button` columns instead of `st.pills` for this reason.
