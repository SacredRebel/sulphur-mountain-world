"""
Terrarium DEM sampler for the pack's committed terrain tiles.

  Elevation is metres in the USGS 3DEP frame the tiles were baked from.
  Pack plan (east, north) ↔ lng/lat via pack.json frame.

    from terrain import elevation_en, elevation_lnglat
"""
from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path

from PIL import Image

_ROOT = Path(__file__).resolve().parents[1]
_PACK = json.loads((_ROOT / 'pack.json').read_text(encoding='utf-8'))
_OL = float(_PACK['frame']['origin_lng'])
_OA = float(_PACK['frame']['origin_lat'])
_MX = float(_PACK['frame']['metres_per_deg_lng'])
_MY = float(_PACK['frame']['metres_per_deg_lat'])
_MAXZ = int(_PACK['layers']['terrain'].get('maxzoom', 17))


def en_to_lnglat(e: float, n: float) -> tuple[float, float]:
    return _OL + e / _MX, _OA + n / _MY


def lnglat_to_en(lng: float, lat: float) -> tuple[float, float]:
    return (lng - _OL) * _MX, (lat - _OA) * _MY


def _lnglat_to_pixel(lng: float, lat: float, z: int, tile_size: int = 256) -> tuple[float, float]:
    n = 2 ** z
    x = (lng + 180.0) / 360.0 * n * tile_size
    siny = math.sin(math.radians(lat))
    # clamp for numeric safety near poles (irrelevant here)
    siny = min(max(siny, -0.9999), 0.9999)
    y = (0.5 - math.log((1 + siny) / (1 - siny)) / (4 * math.pi)) * n * tile_size
    return x, y


def _terrarium(rgb) -> float:
    r, g, b = rgb[:3]
    return (r * 256 + g + b / 256.0) - 32768.0


@lru_cache(maxsize=64)
def _tile(z: int, tx: int, ty: int):
    path = _ROOT / 'terrain' / str(z) / str(tx) / f'{ty}.png'
    if not path.exists():
        return None
    return Image.open(path).convert('RGB')


def elevation_lnglat(lng: float, lat: float, z: int | None = None) -> float:
    """Sample terrarium elevation (metres) at a WGS84 point."""
    z = _MAXZ if z is None else z
    px, py = _lnglat_to_pixel(lng, lat, z)
    tx, ty = int(px // 256), int(py // 256)
    ix, iy = int(px % 256), int(py % 256)
    im = _tile(z, tx, ty)
    if im is None:
        # fall back one zoom
        if z > 13:
            return elevation_lnglat(lng, lat, z - 1)
        raise FileNotFoundError(f'no terrain tile for {lng},{lat} at z{z} ({tx}/{ty})')
    w, h = im.size
    ix = min(max(ix, 0), w - 1)
    iy = min(max(iy, 0), h - 1)
    return _terrarium(im.getpixel((ix, iy)))


def elevation_en(e: float, n: float, z: int | None = None) -> float:
    lng, lat = en_to_lnglat(e, n)
    return elevation_lnglat(lng, lat, z)
