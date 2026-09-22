# C15 done — true metres, material world names, three placements

**Date:** 2026-09-22  
**Order:** C15.3 → C15.2 → C15.1 (as briefed). Oak Leaf origin / altitude / footprint untouched.

---

## C15.3 — pack frame → WGS84 at origin_lat

| | before | after |
|---|---|---|
| `metres_per_deg_lng` | 91,818.211 | **91,916.198** |
| `metres_per_deg_lat` | 110,540 | **110,930.184** |

Derived from WGS84 meridional / prime-vertical radii at `origin_lat` 34.4304373° (`a=6378137`, `f=1/298.257223563`), three decimals.

- `trees.csv` and `cultivated.csv`: old EN → lng/lat (old constants) → new EN (new constants). Ground positions unchanged (worst tree shift **0.08 mm**).
- Baseline: `analysis/trees-lnglat-baseline.json`.
- Model footprints recomputed from each GLB `footprint_en_m` + new frame (**except** `oak-leaf-massing` and `site-grounds`).
- Generator: `scripts/fix-frame.py`. Check: `scripts/check-frame.py`.

**check-frame.py:** OK — 3663 trees; all 11 survey calls within 0.1 ft of `distance_ft`.

---

## C15.2 — material `world` field

Every `materials.json` surface carries a `world` alias matching the world's wall/roof vocabulary (`stucco`→`plaster`, `living_roof`→`living`, `board_and_batten`→`wood`, …).

**check-materials.py:** OK — 23 surfaces; 17 used by scripts; all map to world words.

---

## C15.1 — three placements (no footprint overlap)

| model | before origin | after origin | why |
|---|---|---|---|
| `farmstead-produce-stand` | −119.156935, 34.432483 | **−119.15725, 34.4324** | road edge, outside creek banks (was wholly inside creek) |
| `beekeeping-program` | −119.15582, 34.433477 | **−119.1557, 34.43352** | beside agricultural hub (was 11/21 m² inside it) |
| `infrastructure` | −119.155966, 34.432386 (origin kept) | same origin; **disposal lobe NE** of utility core | clears ceremonial (was 10 m² overlap) and retreat; ≥100 ft well/creek |

Infrastructure disposal (programme massing, not engineering):

| | |
|---|---|
| leach SW (local EN) | **(20, 40)** — 12×8 m |
| min well → disposal pad | **41.4 m** (≥ 30.5 m) |
| min disposal pad → creek | **31.8 m** (≥ 30.5 m) |
| overlap ceremonial / retreat | **0 m²** |

Design of each model unchanged (produce stand / bee shed / utility kit). Notes mark pads cleared.

**check-overlaps.py:** OK — 15 footprints; no building pair overlap > 0.5 m². Creek × glamping reported only (~581 m²). Moved-set trunks either none or notes say cleared.

**validate-model.py:** produce-stand, beekeeping, infrastructure — all `ok: true`.

**check-paths.py:** site-grounds OK.

---

## New scripts

| script | role |
|---|---|
| `scripts/check-frame.py` | survey calls ≤0.1 ft; trees ≤1 cm on ground |
| `scripts/check-materials.py` | every used surface has a world word |
| `scripts/check-overlaps.py` | footprint pairs ≤0.5 m²; strict trees on moved set |
| `scripts/fix-frame.py` | one-shot frame + tree/cultivated reproject |
| `scripts/recompute-footprint.py` | GLB `footprint_en_m` → models.json lng/lat |
