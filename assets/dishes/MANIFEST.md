# Dish image manifest

Local photos under `assets/dishes/{stem}.jpg`.

**Image selection is NOT done by the LLM.** `dish_images.resolve_dish_image(title, category_hint)`
picks files via a keyword→file map (longest match first). `category_hint` is used only when no
keyword matches. No confident match → `None` → tonal placeholder (never a wrong photo).

`generic.jpg` was deleted — a cooking-scene fallback made unmatched dishes look broken.

## Style bar (2026-07-22 row polish)

**tight crop, food ≥70% of frame, light neutral surface, no dark moody shots.**

All category jpgs are normalized toward a shared exposure (mean luminance ≈145, min ≥115):
center-weighted crop, lifted shadows on dark outliers, no crushed black plates.

Historik list thumbs use the resolved photo (`.oc-row-thumb`). When the resolver returns
`None`, Historik / cards render a tonal indigo placeholder (fork glyph).

## Keyword classics (must not contradict the photo)

| Title cue | File | Depicts |
|-----------|------|---------|
| carbonara | `pasta_gradde.jpg` | Cream-based spaghetti (not tomato penne) |
| pesto / pasta pesto | `pasta_pesto.jpg` | Green pesto pasta |
| tacos / taco | `tacos.jpg` | Tacos |
| lasagne / lasagna | `lasagne.jpg` | Lasagne bake |
| lins / linsgryta / lentil | `linser.jpg` | Lentil dal |
| köttbullar / meatballs | `kottbullar.jpg` | Swedish meatballs |
| wok / kycklingwok | `wok.jpg` | Wok |
| tomatsås-pasta / bolognese | `pasta.jpg` | Tomato pasta (penne) |

Full keyword map: `dish_images.KEYWORD_FILES`. Category-hint fallbacks: `dish_images.CATEGORY_FILES`.

## Local pack coverage gate

Every cookable title from `dinner_pack` / `lunch_pack` / frukost / kvällsmål candidates
(sv+en) must resolve to an existing file. Eating-out pins (`Lunch nära dig`) → `None`.

Enforced by `dish_images.assert_local_packs_resolve()` (tests).

## Audit 2026-07-22 (+ image resolver 2026-07-22)

| File | Depicts | Status |
|------|---------|--------|
| aggora.jpg | Scrambled eggs | ok · exposure normalized |
| bowl.jpg | Tofu Buddha bowl | ok |
| burgare.jpg | Burger | ok · exposure normalized |
| chili.jpg | Chili | ok · exposure normalized |
| curry.jpg | Curry | ok · exposure normalized |
| falafel.jpg | Falafel | ok |
| fisk.jpg | Fish | ok · exposure normalized |
| gratang.jpg | Gratin | ok |
| grot.jpg | Porridge | ok |
| **gryta.jpg** | Beef stew (was soup duplicate) | **replaced 2026-07-22** |
| korv.jpg | Sausage | ok · exposure normalized (was darkest outlier) |
| **kottbullar.jpg** | Swedish meatballs | **added 2026-07-22** (resolver) |
| kyckling.jpg | Chicken | ok · exposure normalized |
| **lasagne.jpg** | Lasagne (was gratang duplicate) | **replaced 2026-07-22** |
| **linser.jpg** | Lentil dal (was soup duplicate) | **replaced 2026-07-22** |
| matlada.jpg | Lunchbox | ok |
| musli.jpg | Muesli | ok |
| nudlar.jpg | Noodles | ok |
| omelett.jpg | Omelette | ok |
| padthai.jpg | Pad Thai | ok |
| pannkakor.jpg | Pancakes | ok |
| pasta.jpg | Tomato pasta (penne) | ok (tomato / bolognese) |
| **pasta_gradde.jpg** | Cream pasta / carbonara | **added 2026-07-22** |
| **pasta_pesto.jpg** | Pesto pasta | **added 2026-07-22** |
| pizza.jpg | Pizza | ok · exposure normalized |
| plocktallrik.jpg | Share plate | ok · exposure normalized |
| **poke.jpg** | Salmon poke (was bowl duplicate) | **replaced 2026-07-22** |
| potatis.jpg | Potato dish | ok |
| quesadilla.jpg | Quesadilla | ok |
| quiche.jpg | Quiche | ok |
| **ramen.jpg** | Ramen (was nudlar duplicate) | **replaced 2026-07-22** · exposure normalized |
| risotto.jpg | Risotto | ok · bright outlier toned down |
| sallad.jpg | Salad | ok |
| smorgas.jpg | Sandwich | ok · exposure normalized |
| soppa.jpg | Creamy orange soup | ok |
| stek.jpg | Steak | ok |
| sushi.jpg | Sushi | ok · exposure normalized |
| tacos.jpg | Tacos | ok |
| ugnsbakat.jpg | Oven bake | ok |
| wok.jpg | Wok | ok |
| wrap.jpg | Wrap | ok |
| yoghurt.jpg | Yoghurt bowl | ok |

~~generic.jpg~~ — **removed 2026-07-22** (resolver returns `None` → placeholder).

## Validation gate

- `normalize_dish_category` / `stamp_dish_category` reject unknown ids → `generic` (taxonomy only).
- `manifest_category_ids()` equals `DISH_CATEGORIES − {generic}` (no generic.jpg).
- `dish_images.assert_local_packs_resolve()` — every local pack cookable title → existing file.
