# Dish image manifest

Local photos under `assets/dishes/{category}.jpg`.  
`food_categories.dish_image_path()` only accepts ids in `DISH_CATEGORIES`; unknown → `generic.jpg`.

## Style bar (2026-07-22 row polish)

**tight crop, food ≥70% of frame, light neutral surface, no dark moody shots.**

All category jpgs are normalized toward a shared exposure (mean luminance ≈145, min ≥115):
center-weighted crop, lifted shadows on dark outliers, no crushed black plates.

Historik list thumbs use the photo directly (`.oc-row-thumb` — no plate wrapper).  
When `dish_category` is `generic`/missing, Historik renders a tonal indigo placeholder (fork glyph) — not `generic.jpg`.

## Audit 2026-07-22

| File | Depicts | Status |
|------|---------|--------|
| aggora.jpg | Scrambled eggs | ok · exposure normalized |
| bowl.jpg | Tofu Buddha bowl | ok |
| burgare.jpg | Burger | ok · exposure normalized |
| chili.jpg | Chili | ok · exposure normalized |
| curry.jpg | Curry | ok · exposure normalized |
| falafel.jpg | Falafel | ok |
| fisk.jpg | Fish | ok · exposure normalized |
| generic.jpg | Neutral plate fallback (cards only) | ok |
| gratang.jpg | Gratin | ok |
| grot.jpg | Porridge | ok |
| **gryta.jpg** | Beef stew (was soup duplicate) | **replaced 2026-07-22** |
| korv.jpg | Sausage | ok · exposure normalized (was darkest outlier) |
| kyckling.jpg | Chicken | ok · exposure normalized |
| **lasagne.jpg** | Lasagne (was gratang duplicate) | **replaced 2026-07-22** |
| **linser.jpg** | Lentil dal (was soup duplicate) | **replaced 2026-07-22** — also used for linsgryta / linssoppa (pulse identity beats gryta/soppa cues) |
| matlada.jpg | Lunchbox | ok |
| musli.jpg | Muesli | ok |
| nudlar.jpg | Noodles | ok |
| omelett.jpg | Omelette | ok |
| padthai.jpg | Pad Thai | ok |
| pannkakor.jpg | Pancakes | ok |
| pasta.jpg | Tomato pasta (penne) | ok (category-level) |
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
| soppa.jpg | Creamy orange soup | ok (kept; was shared wrongly by gryta/linser) |
| stek.jpg | Steak | ok |
| sushi.jpg | Sushi | ok · exposure normalized |
| tacos.jpg | Tacos | ok |
| ugnsbakat.jpg | Oven bake | ok |
| wok.jpg | Wok | ok |
| wrap.jpg | Wrap | ok |
| yoghurt.jpg | Yoghurt bowl | ok |

## Replaced files this round

1. `gryta.jpg` — was identical to soup photo; now beef stew  
2. `linser.jpg` — was soup duplicate; now lentil dal  
3. `poke.jpg` — was identical to `bowl.jpg`; now salmon poke  
4. `ramen.jpg` — was identical to `nudlar.jpg`; now ramen bowl  
5. `lasagne.jpg` — was identical to `gratang.jpg`; now lasagne bake  

## Exposure pass (row polish)

Batch normalize: tight crop + brightness lift for dark moody shots (korv/fisk/aggora/…); risotto pulled down. Style bar recorded above.

## Validation gate

`normalize_dish_category` / `stamp_dish_category` reject unknown ids → `generic`.  
`manifest_category_ids()` must equal `DISH_CATEGORIES` (enforced in tests).
