# C28 done — pack as a dependable dependency

**Date:** 2026-09-23  
**Branch:** `eco/c28`  
**Checks:** `check-contract` (+ `--self-test`)

---

## Published

| | |
|---|---|
| `pack.json` `version` | **1.0.0** |
| `CHANGELOG.md` | C19→C28 newest-first |
| `contract.json` | required manifest fields, raster decode, frame, instances, collision, compatibility baseline |
| `docs/consuming-the-pack.md` | load / place / decode / instances / collision — real numbers |

Decode worked example: `twi.png` pixel (124,164)=8497 → **2.020466** (npz Δ < 0.001). Frame EN (260.82, 267.76) round-trips. Removing a baseline layer without a major bump fails the check.
