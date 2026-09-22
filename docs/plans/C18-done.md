# C18 done — light LOD models

**Date:** 2026-09-22  
**Tool:** meshoptimizer **gltfpack** v0.25 (MIT). `gltf-transform` CLI could not be installed here (npm TLS intercept); gltfpack is the same meshoptimizer simplify path. No Draco, no KTX2.

---

## Bytes

| | |
|---|---|
| full models | **1,300,212** B |
| LOD extras (lod1+lod2) | **347,852** B |
| pack models + LODs | **1,648,064** B |

## Triangles in view (if every model uses its band)

| band | triangles |
|---|---|
| 0–60 m (full) | **19,071** |
| 60–250 m (LOD1) | **11,999** |
| 250 m+ (LOD2) | **11,723** |

## Per-model note

Most programme massings are already hard-edged low-poly. gltfpack weld+simplify hits a topology floor (LOD1 ≈ LOD2 for several). **site-grounds** reduced clearly: 5952 → 1704 / 1428 tris. Silhouettes kept; extras.walk may be stripped by gltfpack on LODs (world uses full GLB for walking).

`models.json` `lods`: full to 60 m, LOD1 to 250 m, LOD2 beyond.

## Checks

`scripts/check-lods.py`: bbox centre within **0.05 m**; bytes/tris match models.json.

Generator: `scripts/build-lods.py`. Binary: `tools/gltfpack/gltfpack.exe` (from zeux/meshoptimizer releases).
