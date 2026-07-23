# -*- coding: utf-8 -*-
"""Expanded offline food packs (fallback when Grok is unavailable).

Middag ≥15, lunch ≥10, with dish_category stamps and ≥3 wildcards each.
"""

from __future__ import annotations

from typing import Any


def _dish(
    suggestion: str,
    justification: str,
    *,
    meal_type: str,
    minutes: int,
    ingredients: list[str],
    dish_category: str,
    wildcard: bool = False,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "suggestion": suggestion,
        "justification": justification,
        "meta": {
            "meal_type": meal_type,
            "active_minutes": minutes,
            "ingredients": list(ingredients),
            "dish_category": dish_category,
        },
    }
    if wildcard:
        row["wildcard"] = True
    return row


def dinner_pack(language: str = "sv") -> list[dict[str, Any]]:
    """≥15 distinct middag dishes across categories."""
    sv = language == "sv"
    return [
        _dish(
            "Krämig tomatsås-pasta" if sv else "Creamy tomato pasta",
            "Varmt, enkelt och klart på 20 minuter." if sv else "Warm, simple, done in 20 minutes.",
            meal_type="middag",
            minutes=20,
            ingredients=[
                "pasta", "krossade tomater", "gul lök", "vitlök", "parmesan",
                "olja", "salt", "peppar", "oregano",
            ],
            dish_category="pasta",
        ),
        _dish(
            "Etiopisk-inspirerad linsgryta" if sv else "Ethiopian-inspired lentil stew",
            "Varm krydda hemma — linser, kokosmjölk och grönt." if sv else "Warm spice at home — lentils and coconut milk.",
            meal_type="middag",
            minutes=30,
            ingredients=[
                "röda linser", "gul lök", "vitlök", "morot", "spenat",
                "kokosmjölk", "ris", "curry", "olja", "salt", "peppar",
            ],
            dish_category="stew",
            wildcard=True,
        ),
        _dish(
            "Proteinomelett med grönt" if sv else "Protein omelette with greens",
            "Snabb, mättande — ägg och grönt." if sv else "Fast and filling — eggs and greens.",
            meal_type="middag",
            minutes=15,
            ingredients=["ägg", "mjölk", "tomat", "spenat", "ost", "smör", "salt", "peppar"],
            dish_category="egg",
        ),
        _dish(
            "Kycklingwok med ris" if sv else "Chicken wok with rice",
            "Vardagsfavorit — kyckling och grönt." if sv else "Weeknight classic — chicken and veg.",
            meal_type="middag",
            minutes=25,
            ingredients=[
                "kycklingfilé", "gul lök", "vitlök", "morot", "broccoli",
                "paprika (färsk)", "ris", "sojasås", "olja", "salt", "peppar",
            ],
            dish_category="chicken",
        ),
        _dish(
            "Klassisk burgare hemma" if sv else "Classic burger at home",
            "Komfort utan krångel." if sv else "Comfort without fuss.",
            meal_type="middag",
            minutes=25,
            ingredients=[
                "nötfärs", "hamburgerbröd", "ost", "sallad", "tomat",
                "gul lök", "olja", "salt", "peppar",
            ],
            dish_category="burger",
        ),
        _dish(
            "Ugnsbakad lax med potatis" if sv else "Oven-baked salmon with potatoes",
            "Sätt in och glöm — klar på 25 min." if sv else "Set and forget — done in 25 min.",
            meal_type="middag",
            minutes=25,
            ingredients=["laxfilé", "potatis", "citron", "dill", "smör", "salt", "peppar"],
            dish_category="fish",
        ),
        _dish(
            "Tacos med kryddig färs" if sv else "Spicy mince tacos",
            "Bygg själv vid bordet — alltid en hit." if sv else "Build-your-own at the table.",
            meal_type="middag",
            minutes=25,
            ingredients=[
                "nötfärs", "tacoskal", "sallad", "tomat", "gul lök",
                "gräddfil", "tacokrydda", "olja", "salt",
            ],
            dish_category="mexican",
            wildcard=True,
        ),
        _dish(
            "Kikärtscurry med ris" if sv else "Chickpea curry with rice",
            "Skafferi-vänligt och mättande." if sv else "Pantry-friendly and filling.",
            meal_type="middag",
            minutes=25,
            ingredients=[
                "kikärtor", "kokosmjölk", "gul lök", "vitlök", "tomatpuré",
                "ris", "curry", "olja", "salt", "peppar",
            ],
            dish_category="stew",
        ),
        _dish(
            "Pannstekta korvar med potatismos" if sv else "Pan-fried sausages with mash",
            "Klassisk svensk vardag." if sv else "Classic comfort dinner.",
            meal_type="middag",
            minutes=30,
            ingredients=["korv", "potatis", "mjölk", "smör", "salt", "peppar"],
            dish_category="sausage",
        ),
        _dish(
            "Fiskgratäng med broccoli" if sv else "Fish gratin with broccoli",
            "Gräddig ugnsrätt — lite lyx på vardagen." if sv else "Creamy oven bake — weeknight treat.",
            meal_type="middag",
            minutes=35,
            ingredients=[
                "torskfilé", "broccoli", "grädde", "ost", "gul lök",
                "smör", "salt", "peppar",
            ],
            dish_category="fish",
        ),
        _dish(
            "Spaghetti carbonara" if sv else "Spaghetti carbonara",
            "Få råvaror, stor smak." if sv else "Few ingredients, big flavour.",
            meal_type="middag",
            minutes=20,
            ingredients=["spaghetti", "bacon", "ägg", "parmesan", "svartpeppar", "salt"],
            dish_category="pasta",
        ),
        _dish(
            "Kycklinggryta med grädde" if sv else "Creamy chicken stew",
            "Mjuk och trygg — ris eller potatis till." if sv else "Soft and safe — rice or potatoes on the side.",
            meal_type="middag",
            minutes=30,
            ingredients=[
                "kycklingfilé", "grädde", "gul lök", "vitlök", "morot",
                "kycklingbuljong", "olja", "salt", "peppar",
            ],
            dish_category="chicken",
        ),
        _dish(
            "Vegetarisk lasagne" if sv else "Vegetarian lasagna",
            "Gör en plåt — äter du i två dagar." if sv else "One tray — eats for two days.",
            meal_type="middag",
            minutes=45,
            ingredients=[
                "lasagneplattor", "krossade tomater", "zucchini", "gul lök",
                "vitlök", "ost", "mjölk", "smör", "mjöl", "salt", "peppar",
            ],
            dish_category="pasta",
            wildcard=True,
        ),
        _dish(
            "Ramen med ägg och grönsaker" if sv else "Ramen with egg and vegetables",
            "Snabbt asiatiskt — buljong och toppings." if sv else "Fast Asian bowl — broth and toppings.",
            meal_type="middag",
            minutes=20,
            ingredients=[
                "nudlar", "ägg", "pak choi", "sojasås", "vitlök",
                "ingefära", "sesamolja", "salt",
            ],
            dish_category="noodles",
        ),
        _dish(
            "Köttbullar med gräddsås" if sv else "Meatballs with cream sauce",
            "Svensk klassiker — potatis eller pasta till." if sv else "Swedish classic — potatoes or pasta.",
            meal_type="middag",
            minutes=35,
            ingredients=[
                "nötfärs", "grädde", "gul lök", "ägg", "ströbröd",
                "smör", "salt", "peppar", "lingonsylt",
            ],
            dish_category="meatballs",
        ),
        _dish(
            "Halloumiburgare med sötpotatis" if sv else "Halloumi burger with sweet potato",
            "Vegetariskt med krisp och sälta." if sv else "Vegetarian with crunch and salt.",
            meal_type="middag",
            minutes=30,
            ingredients=[
                "halloumi", "hamburgerbröd", "sötpotatis", "sallad",
                "tomat", "olja", "salt", "peppar",
            ],
            dish_category="burger",
            wildcard=True,
        ),
    ]


def lunch_pack(language: str = "sv") -> list[dict[str, Any]]:
    """≥10 distinct lunch dishes (offline / pin pack)."""
    sv = language == "sv"
    return [
        _dish(
            "Äggmacka och kaffe" if sv else "Egg sandwich and coffee",
            "Snabbt vardagslunch — klart på några minuter." if sv else "Fast weekday lunch — done in minutes.",
            meal_type="lunch",
            minutes=8,
            ingredients=["ägg", "bröd", "smör"],
            dish_category="sandwich",
        ),
        _dish(
            "Sallad med tonfisk" if sv else "Tuna salad",
            "Lätt lunch — burk och grönt." if sv else "Light lunch — pantry tuna and greens.",
            meal_type="lunch",
            minutes=10,
            ingredients=["tonfisk", "sallad", "gurka", "olja", "salt", "peppar"],
            dish_category="salad",
        ),
        _dish(
            "Soppa på rester" if sv else "Leftover soup",
            "Värm och ät — noll diskdrama." if sv else "Heat and eat — zero dish drama.",
            meal_type="lunch",
            minutes=10,
            ingredients=["grönsaker", "buljong", "salt", "peppar"],
            dish_category="soup",
        ),
        _dish(
            "Wrap med kyckling" if sv else "Chicken wrap",
            "Rullar ihop på 10 min." if sv else "Rolls up in 10 minutes.",
            meal_type="lunch",
            minutes=12,
            ingredients=["tortilla", "kycklingfilé", "sallad", "tomat", "yoghurt"],
            dish_category="wrap",
        ),
        _dish(
            "Ris med stekt ägg och grönt" if sv else "Rice with fried egg and greens",
            "Enkelt och mättande." if sv else "Simple and filling.",
            meal_type="lunch",
            minutes=15,
            ingredients=["ris", "ägg", "spenat", "sojasås", "olja", "salt"],
            dish_category="egg",
            wildcard=True,
        ),
        _dish(
            "Pasta pesto" if sv else "Pesto pasta",
            "Skafferiklassiker på 15 min." if sv else "Pantry classic in 15 min.",
            meal_type="lunch",
            minutes=15,
            ingredients=["pasta", "pesto", "parmesan", "salt"],
            dish_category="pasta",
        ),
        _dish(
            "Quinoasallad med feta" if sv else "Quinoa salad with feta",
            "Förbereds dagen innan — äts kall." if sv else "Prep ahead — eat cold.",
            meal_type="lunch",
            minutes=15,
            ingredients=["quinoa", "fetaost", "gurka", "tomat", "olja", "salt", "peppar"],
            dish_category="salad",
            wildcard=True,
        ),
        _dish(
            "Toast med avokado" if sv else "Avocado toast",
            "Fem minuter, klart." if sv else "Five minutes, done.",
            meal_type="lunch",
            minutes=5,
            ingredients=["bröd", "avokado", "citron", "salt", "peppar"],
            dish_category="sandwich",
        ),
        _dish(
            "Nudelwok med grönsaker" if sv else "Vegetable noodle wok",
            "Het panna, snabb lunch." if sv else "Hot pan, fast lunch.",
            meal_type="lunch",
            minutes=15,
            ingredients=["nudlar", "morot", "paprika (färsk)", "sojasås", "olja", "vitlök"],
            dish_category="noodles",
            wildcard=True,
        ),
        _dish(
            "Kikärtssallad med citron" if sv else "Chickpea salad with lemon",
            "Ingen spis — bara blanda." if sv else "No stove — just mix.",
            meal_type="lunch",
            minutes=8,
            ingredients=["kikärtor", "citron", "gul lök", "olja", "salt", "peppar", "persilja"],
            dish_category="salad",
        ),
        _dish(
            "Lunch nära dig" if sv else "Lunch nearby",
            "Ät ute i dag — öppna kartan." if sv else "Eat out today — open the map.",
            meal_type="lunch",
            minutes=0,
            ingredients=[],
            dish_category="other",
        ),
    ]
