#!/usr/bin/env python3
"""Browser proof: nutrition banner shows ≈ kcal after toggle (kvällsmål + middag)."""
from __future__ import annotations

import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://localhost:8501"
OUT = Path(__file__).resolve().parent.parent / "artifacts"


def run_meal(page, meal: str, accept: str) -> bool:
    page.goto(f"{BASE}/?domain=food", wait_until="networkidle")
    page.wait_for_timeout(2000)
    page.get_by_text(meal, exact=True).first.click()
    page.wait_for_timeout(800)
    btn = page.get_by_role("button", name=re.compile(accept, re.I))
    if not btn.count():
        return False
    btn.first.click()
    page.wait_for_timeout(2500)

    banner = page.locator(".oc-nut-banner")
    if not banner.count():
        print(f"FAIL {meal}: no .oc-nut-banner")
        return False
    before = banner.first.inner_text()
    print(f"{meal} banner before:", repr(before[:80]))

    # Nutrition switch — collapsed label; click the switch row
    nut_switch = page.locator('[data-testid="stCheckbox"] input[role="switch"]').first
    if not nut_switch.count():
        nut_switch = page.locator('[data-testid="stCheckbox"] input[type="checkbox"]').first
    nut_switch.click(force=True)
    page.wait_for_timeout(3000)

    banner_after = page.locator(".oc-nut-banner").first.inner_text()
    print(f"{meal} banner after:", repr(banner_after[:80]))
    ok = bool(re.search(r"≈\s*\d+\s*kcal", banner_after))
    page.screenshot(path=str(OUT / f"nutrition_{meal.lower()}_after.png"), full_page=True)
    return ok


def main() -> int:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 430, "height": 900})
        ok1 = run_meal(page, "Kvällsmål", "Ät nu")
        ok2 = run_meal(page, "Middag", "Handla")
        browser.close()
    if ok1 and ok2:
        print("OK: nutrition banner shows kcal in browser (both flows)")
        return 0
    print("FAIL: nutrition banner missing values")
    return 1


if __name__ == "__main__":
    sys.exit(main())
