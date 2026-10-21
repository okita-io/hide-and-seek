"""Orthographic 16-grey surface render and colour debug overlay."""

from __future__ import annotations

import colorsys

import numpy as np
from PIL import Image, ImageDraw

from hide_and_seek.world.tiles import TILES

GREY_SCALE = 17  # 0..15 → 0, 17, ..., 255


def _hash_dot(tx: int, ty: int, px: int, py: int, mod: int, target: int) -> bool:
    h = (tx * 16 + px) * 13 + (ty * 16 + py) * 7 + tx * 31 + ty
    return h % mod == target


def _room_floor_pattern(variant: int, tx: int, ty: int) -> np.ndarray:
    base = (8, 9, 10)[variant]
    alt = (9, 10, 9)[variant]
    dim = (7, 8, 9)[variant]
    g = np.full((16, 16), base, dtype=np.uint8)
    for py in range(16):
        for px in range(16):
            if _hash_dot(tx, ty, px, py, 17, 0):
                g[py, px] = alt
            elif _hash_dot(tx, ty, px, py, 23, 1):
                g[py, px] = dim
    return g


def _corridor_pattern(name: str, tx: int, ty: int) -> np.ndarray:
    g = np.full((16, 16), 7, dtype=np.uint8)
    # Subtle grit so corridors read as a different surface from rooms.
    for py in range(16):
        for px in range(16):
            if _hash_dot(tx, ty, px, py, 19, 0):
                g[py, px] = 6
    # Orientation stripe.
    if "NS" in name or name.endswith("_N") or name.endswith("_S") or name == "CORRIDOR_CROSS":
        g[0:16, 7:9] = 6
    if "EW" in name or name.endswith("_E") or name.endswith("_W") or name == "CORRIDOR_CROSS":
        g[7:9, 0:16] = 6
    if name in {"CORRIDOR_NE", "CORRIDOR_SE", "CORRIDOR_SW", "CORRIDOR_NW"}:
        g[7:9, 7:9] = 5
    return g


def _door_pattern(name: str) -> np.ndarray:
    g = np.full((16, 16), 7, dtype=np.uint8)
    if name == "DOORWAY_NS":
        g[:, 0:2] = 4
        g[:, 14:16] = 4
        g[6:10, 2:14] = 8
    else:
        g[0:2, :] = 4
        g[14:16, :] = 4
        g[2:14, 6:10] = 8
    return g


def _crate_pattern() -> np.ndarray:
    g = np.full((16, 16), 8, dtype=np.uint8)
    g[3:13, 3:13] = 12
    g[3, 3:13] = 13
    g[12, 3:13] = 10
    g[3:13, 3] = 13
    g[3:13, 12] = 10
    g[7:9, 3:13] = 11
    return g


def _pillar_pattern() -> np.ndarray:
    g = np.full((16, 16), 8, dtype=np.uint8)
    yy, xx = np.ogrid[:16, :16]
    d = (xx - 7.5) ** 2 + (yy - 7.5) ** 2
    g[d <= 28] = 11
    g[d <= 12] = 12
    g[(d <= 28) & (yy <= 5)] = 13
    return g


def _table_pattern() -> np.ndarray:
    g = np.full((16, 16), 8, dtype=np.uint8)
    g[5:11, 2:14] = 12
    g[5, 2:14] = 13
    g[10, 2:14] = 10
    g[11:14, 3] = 9
    g[11:14, 12] = 9
    return g


def _debris_pattern(tx: int, ty: int) -> np.ndarray:
    g = np.full((16, 16), 8, dtype=np.uint8)
    for py in range(16):
        for px in range(16):
            if _hash_dot(tx, ty, px, py, 11, 0):
                g[py, px] = 6
            elif _hash_dot(tx, ty, px, py, 13, 2):
                g[py, px] = 5
    return g


def _exit_pattern() -> np.ndarray:
    g = np.full((16, 16), 8, dtype=np.uint8)
    yy, xx = np.ogrid[:16, :16]
    d = np.abs(xx - 7.5) + np.abs(yy - 7.5)
    g[d <= 7] = 14
    g[d <= 5] = 4
    g[d <= 3] = 15
    g[d <= 1] = 14
    # Chevrons so the silhouette is unique even at a glance.
    g[1, 6:10] = 15
    g[14, 6:10] = 15
    g[6:10, 1] = 15
    g[6:10, 14] = 15
    return g


def _wall_pattern(tid: int) -> np.ndarray:
    # tid 0..15 == orthogonal floor-neighbor mask (1=N,2=E,4=S,8=W)
    g = np.full((16, 16), 3, dtype=np.uint8)
    g[0, :] = 5
    g[1, :] = 4
    mask = tid & 15
    if mask == 0:
        # faint brick so large wall masses aren't a flat field
        g[::4, :] = 2
        g[:, ::8] = 2
    if mask & 1:  # floor north
        g[0, :] = 6
        g[1, :] = 5
    if mask & 4:  # floor south
        g[15, :] = 2
        g[14, :] = 2
    if mask & 2:  # floor east
        g[:, 15] = 4
    if mask & 8:  # floor west
        g[:, 0] = 4
    # Outer-corner notch so corners read as corners, not a flat block.
    if mask == 3:  # NE
        g[0:4, 12:16] = 6
    elif mask == 6:  # SE
        g[12:16, 12:16] = 2
    elif mask == 12:  # SW
        g[12:16, 0:4] = 2
    elif mask == 9:  # NW
        g[0:4, 0:4] = 6
    return g


def render_tile(tid: int, tx: int, ty: int) -> np.ndarray:
    name = TILES[tid].name
    if tid < 16:
        return _wall_pattern(tid)
    if name == "ROOM_FLOOR_A":
        return _room_floor_pattern(0, tx, ty)
    if name == "ROOM_FLOOR_B":
        return _room_floor_pattern(1, tx, ty)
    if name == "ROOM_FLOOR_C":
        return _room_floor_pattern(2, tx, ty)
    if name.startswith("CORRIDOR_"):
        return _corridor_pattern(name, tx, ty)
    if name.startswith("DOORWAY_"):
        return _door_pattern(name)
    if name == "PROP_CRATE":
        return _crate_pattern()
    if name == "PROP_PILLAR":
        return _pillar_pattern()
    if name == "PROP_TABLE":
        return _table_pattern()
    if name == "PROP_DEBRIS":
        return _debris_pattern(tx, ty)
    if name == "EXIT":
        return _exit_pattern()
    return np.full((16, 16), TILES[tid].material.grey, dtype=np.uint8)


def render_surface(tiles: np.ndarray, tile_size: int = 16) -> np.ndarray:
    """512x512 uint8 array with values 0..15 (lit surface grey)."""
    h, w = tiles.shape
    out = np.zeros((h * tile_size, w * tile_size), dtype=np.uint8)
    for y in range(h):
        for x in range(w):
            out[y * tile_size : (y + 1) * tile_size, x * tile_size : (x + 1) * tile_size] = (
                render_tile(int(tiles[y, x]), x, y)
            )
    return out


def surface_to_preview(surface: np.ndarray) -> Image.Image:
    """Scale 0..15 to 0..255 so the PNG is viewable."""
    return Image.fromarray(np.clip(surface.astype(np.uint16) * GREY_SCALE, 0, 255).astype(np.uint8), mode="L")


def _hsv(h: float, s: float, v: float) -> tuple[int, int, int]:
    r, g, b = colorsys.hsv_to_rgb(h % 1.0, s, v)
    return int(r * 255), int(g * 255), int(b * 255)


def render_debug(
    tiles: np.ndarray,
    rooms: list,
    corridor_graph: dict,
    runner_spawns: list[tuple[int, int]],
    monster_spawn: tuple[int, int],
    exit_cell: tuple[int, int],
    exit_path: list[tuple[int, int]],
    lamp_sockets: list[tuple[int, int]],
    chokepoints: list[tuple[int, int]],
    tile_size: int = 16,
) -> Image.Image:
    surface = render_surface(tiles, tile_size)
    preview = surface_to_preview(surface).convert("RGB")
    arr = np.array(preview)
    # Tint room interiors.
    for r in rooms:
        hue = (0.12 + r.id * 0.17) % 1.0
        col = np.array(_hsv(hue, 0.45, 0.85), dtype=np.int16)
        y0, y1 = r.y * tile_size, (r.y + r.h) * tile_size
        x0, x1 = r.x * tile_size, (r.x + r.w) * tile_size
        patch = arr[y0:y1, x0:x1].astype(np.int16)
        arr[y0:y1, x0:x1] = np.clip((patch * 2 + col) // 3, 0, 255).astype(np.uint8)
    img = Image.fromarray(arr, mode="RGB")
    draw = ImageDraw.Draw(img)

    def cell_box(x: int, y: int, pad: int = 2) -> tuple[int, int, int, int]:
        x0 = x * tile_size + pad
        y0 = y * tile_size + pad
        return (x0, y0, x0 + tile_size - 2 * pad, y0 + tile_size - 2 * pad)

    def cell_center(x: int, y: int) -> tuple[int, int]:
        return (x * tile_size + tile_size // 2, y * tile_size + tile_size // 2)

    # Exit path
    if len(exit_path) >= 2:
        pts = [cell_center(x, y) for x, y in exit_path]
        draw.line(pts, fill=(255, 160, 40), width=3)

    # Corridor graph edges
    for edge in corridor_graph.get("edges", []):
        path = edge.get("path") or []
        if len(path) >= 2:
            pts = [cell_center(p[0], p[1]) for p in path]
            draw.line(pts, fill=(80, 200, 220), width=1)

    for x, y in chokepoints:
        draw.rectangle(cell_box(x, y, 1), outline=(255, 0, 220), width=2)

    for x, y in lamp_sockets:
        cx, cy = cell_center(x, y)
        draw.regular_polygon((cx, cy, 5), n_sides=4, rotation=45, fill=(255, 220, 60), outline=(80, 60, 0))

    for x, y in runner_spawns:
        draw.ellipse(cell_box(x, y, 3), fill=(40, 220, 80), outline=(10, 80, 20))

    mx, my = monster_spawn
    draw.ellipse(cell_box(mx, my, 2), fill=(220, 40, 40), outline=(80, 0, 0))

    ex, ey = exit_cell
    draw.rectangle(cell_box(ex, ey, 1), outline=(255, 255, 80), width=2)

    return img
