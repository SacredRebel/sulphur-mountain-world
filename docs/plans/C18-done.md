# C18 done — light LOD models

**Date:** 2026-09-22  
**Tool:** meshoptimizer **gltfpack** v0.25 (MIT). `gltf-transform` CLI could not be installed (npm TLS intercept); gltfpack is the meshoptimizer simplify path the brief asks for. No Draco, no KTX2.

---

## Bytes

| | |
|---|---|
| full models | **1,300,212** B |
| LOD extras | **927,512** B |
| pack + LODs | **2,227,724** B |

## Triangles in view (all models at band)

| band | triangles |
|---|---|
| 0–60 m (full) | **19,071** |
| 60–250 m (LOD1) | **14,801** |
| 250 m+ (LOD2) | **14,801** |

Many massings are already hard-edged low-poly; with silhouette lock (`-slb`) and error cap (`-se 0.02`), LOD1 and LOD2 often meet the same floor (still lighter than full for larger meshes such as oak-leaf / site-grounds / creek).

`models.json` `lods`: full → 60 m, LOD1 → 250 m, LOD2 beyond.

## Checks

`scripts/check-lods.py`: world bbox (dequantized) centre within **0.05 m** (LOD1) / **0.5 m** (LOD2); extents within 15–25%; bytes/tris match models.json. **OK.**

Generator: `scripts/build-lods.py`. Binary: `tools/gltfpack/gltfpack.exe`.
