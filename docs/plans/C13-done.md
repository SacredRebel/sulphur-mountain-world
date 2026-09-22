# C13 done — organic builds + drainage

**Date:** 2026-09-22

---

## C13.1 — organic build properties

Pack checks and README accept world organic / shell / flatten fields and do not strip extras.

| addition | where |
|---|---|
| floor `organic` (OrganicSpec + `perimeter` + `pad_id`) | README + `scripts/check-edits.py` |
| wall `smooth`, `openings`, `assembly` | same |
| roof `form: shell` + eaves/rise/overhang/finish/solar + `assembly` | same |
| terrain flatten `structure` | same |
| materials `cob` `hempcrete` `strawbale` `rammed_earth` `bamboo` `steel` | `materials.json` (with `world`) |

Fixture: `fixtures/organic-edit.geojson` (demo pad / floor / wall / roof).

**check-edits.py:** OK on `edits.geojson` and the fixture.

Field ranges: [organic-spec.md](https://github.com/SacredRebel/spatial-map/blob/main/docs/organic-spec.md).

---

## C13.2 — drainage from the 1 m ground

| | |
|---|---|
| method | sink-fill (priority-flood), D8, flow accumulation |
| channel threshold | **≥ 2,000 m²** contributing area |
| simplify | **~1 m** |
| attributes | `accum_m2`, `slope_pct`, `order` (Strahler) |
| lines | **7** |
| main (nearest ford) accum | **2,498 m²**, order 1 |
| ford → main channel | **1.26 m** (limit 8 m) — OK |

Outputs: `drainage.geojson`, `analysis/drainage.png`. Layer `layers.drainage` (`authority: derived`, `captured: 2018`).

Generator: `scripts/drainage.py`.
