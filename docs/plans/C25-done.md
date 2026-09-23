# C25 done — draw cost, tree instances, LOD harden

**Date:** 2026-09-23  
**Branch:** `eco/c25`  
**Generators:** `scripts/build-tree-instances.py`, `scripts/build-budget.py`, `scripts/build-lods.py`  
**Checks:** `check-budget` (+ `check-lods`)

---

## C25.1 — trees that are actually our trees

`@dgreenheck/ez-tree` (MIT) is the preferred procedural generator. Node/npm on this
host failed TLS (`UNABLE_TO_VERIFY_LEAF_SIGNATURE` / npm exit-handler), so the pack
ships **fitted parametric oak archetypes** from `scripts/build-tree-instances.py`
instead — same contract, not vendored ez-tree source.

| | |
|---|---|
| archetypes | **16** (`models/trees/oak-arch-*.glb`) |
| instances | **3,663** (= `trees.csv` row count) |
| worst-case dimensional error | **3.93 m** (crown radius; height ≤ 1.20 m) |
| error bound published | 4.0 m |
| authority / evidence | `generated` / `modelled` |
| measured inputs | `trees.csv` positions + height + crown radius |

Uniform scale per tree minimises max(height error, crown error) against its archetype.

---

## C25.2 — budget.json

Per drawable pack-layers row: bytes, feature/cell counts, appear/disappear bands.
Per model LOD: triangle and byte totals. Scene bands:

| band | distance | model tris (approx) |
|---|---|---:|
| near | 0–60 m | full |
| mid | 60–250 m | lod1 |
| far | 250 m+ | lod2 |

---

## C25.3 — LOD harden

Rebuilt with meshoptimizer **gltfpack** (already in-tree). Where simplify can reduce,
lod2 < lod1 < full and ratios are printed. Nine low-poly massings hit a **simplify floor**
(lod2 tris = lod1); documented in the check. Visual error remains the check-lods
centre/extent metres (all green after floor copies).

glTF-Transform / KTX2 not applied this phase — npm TLS blocked the toolchain; gltfpack
path recorded as the working optimiser.

---

## Check

`check-budget`: every manifest layer has a row; instance count = trees.csv; archetype
ids resolve; worst-case error under bound; layer byte sum matches; LOD reduction or
documented floor. `--self-test` drops a budget row and proves rejection.
