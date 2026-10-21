"""Wave function collapse for wall edges/corners, floor variants and props."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from hide_and_seek.world.config import GeneratorParams
from hide_and_seek.world.layout import CORRIDOR, DOOR, ROOM, CoarseLayout, open_mask_at
from hide_and_seek.world.tiles import (
    COMPAT,
    DEBRIS_MASK,
    DELTA,
    EXIT_MASK,
    FLOOR_VARIANT_IDS,
    PROP_MASK,
    WALKABLE_MASK,
    WEIGHTS,
    bits_of,
    corridor_id_for_open_mask,
    doorway_id_for_open_mask,
    tile_id,
    wall_id_for_floor_mask,
)


@dataclass
class WFCResult:
    tiles: np.ndarray
    attempts: int


def _single(tid: int) -> int:
    return 1 << tid


def _prop_mask(params: GeneratorParams) -> int:
    # Weighted later via TILES[].weight; density is applied by scaling those weights.
    mask = 0
    if params.prop_density > 0:
        mask |= PROP_MASK
    if params.debris_density > 0:
        mask |= DEBRIS_MASK
    return mask


def seed_domains(
    layout: CoarseLayout,
    params: GeneratorParams,
    reserved_floor: set[tuple[int, int]],
    exit_cell: tuple[int, int] | None,
) -> np.ndarray:
    """Per-cell bitmasks of allowed tiles, pre-seeded from the coarse plan."""
    grid = layout.grid
    size = params.grid_size
    domains = np.zeros((size, size), dtype=np.uint64)
    props = _prop_mask(params)
    room_of = layout.room_of

    for y in range(size):
        for x in range(size):
            kind = int(grid[y, x])
            if exit_cell is not None and (x, y) == exit_cell:
                domains[y, x] = np.uint64(EXIT_MASK)
                continue
            if kind == ROOM:
                rid = int(room_of[y, x])
                variant = layout.rooms[rid].floor_variant
                floor = _single(FLOOR_VARIANT_IDS[variant])
                if (x, y) in reserved_floor:
                    domains[y, x] = np.uint64(floor)
                else:
                    domains[y, x] = np.uint64(floor | props)
            elif kind == CORRIDOR:
                domains[y, x] = np.uint64(_single(corridor_id_for_open_mask(open_mask_at(grid, x, y))))
            elif kind == DOOR:
                domains[y, x] = np.uint64(_single(doorway_id_for_open_mask(open_mask_at(grid, x, y))))
            else:
                # VOID and ROOM_WALL become walls; type is the orthogonal floor mask.
                # Use the coarse grid so wall sockets already match planned openings.
                domains[y, x] = np.uint64(_single(wall_id_for_floor_mask(open_mask_at(grid, x, y))))
    return domains


def _entropy(mask: int, noise: float) -> float:
    n = mask.bit_count()
    if n <= 1:
        return n + noise * 0.01
    return float(n) + noise


def _choose(mask: int, weights: np.ndarray, rng: np.random.Generator) -> int:
    ids = bits_of(mask)
    w = weights[ids].astype(np.float64)
    total = float(w.sum())
    if total <= 0:
        return int(ids[int(rng.integers(0, len(ids)))])
    w /= total
    return int(rng.choice(ids, p=w))


def _effective_weights(params: GeneratorParams) -> np.ndarray:
    w = WEIGHTS.copy()
    # Scale cover relative to a typical room-floor weight of 12.
    crate = tile_id("PROP_CRATE")
    pillar = tile_id("PROP_PILLAR")
    table = tile_id("PROP_TABLE")
    debris = tile_id("PROP_DEBRIS")
    cover = max(params.prop_density, 0.0) * 12.0
    w[crate] = cover * 0.45
    w[pillar] = cover * 0.25
    w[table] = cover * 0.30
    w[debris] = max(params.debris_density, 0.0) * 12.0
    return w


def _allowed_neighbors(mask: int, direction: int) -> int:
    allowed = 0
    remaining = mask
    while remaining:
        bit = remaining & -remaining
        allowed |= int(COMPAT[direction, bit.bit_length() - 1])
        remaining ^= bit
    return allowed


def collapse(
    domains: np.ndarray,
    params: GeneratorParams,
    rng: np.random.Generator,
) -> np.ndarray | None:
    """Lowest-entropy WFC with propagation. Restarts are handled by the caller."""
    size = domains.shape[0]
    wave = domains.copy()
    collapsed = np.full((size, size), -1, dtype=np.int16)
    nopts = np.zeros((size, size), dtype=np.int16)
    weights = _effective_weights(params)
    noise = rng.random((size, size))
    stack: list[tuple[int, int]] = []

    for y in range(size):
        for x in range(size):
            m = int(wave[y, x])
            n = m.bit_count()
            nopts[y, x] = n
            if n == 0:
                return None
            if n == 1:
                collapsed[y, x] = bits_of(m)[0]
                stack.append((x, y))

    def propagate() -> bool:
        while stack:
            x, y = stack.pop()
            mask = int(wave[y, x])
            if mask == 0:
                return False
            for d, (dx, dy) in enumerate(DELTA):
                nx, ny = x + dx, y + dy
                if not (0 <= nx < size and 0 <= ny < size):
                    continue
                neigh = int(wave[ny, nx])
                nxt = neigh & _allowed_neighbors(mask, d)
                if nxt == 0:
                    return False
                if nxt != neigh:
                    wave[ny, nx] = np.uint64(nxt)
                    n = nxt.bit_count()
                    nopts[ny, nx] = n
                    stack.append((nx, ny))
                    if n == 1:
                        collapsed[ny, nx] = bits_of(nxt)[0]
        return True

    if not propagate():
        return None

    pending = [(x, y) for y in range(size) for x in range(size) if collapsed[y, x] < 0]
    # Floor / prop / debris / exit all share F sockets, so they cannot constrain
    # each other. Collapse them independently (equivalent to sequential WFC).
    independent = WALKABLE_MASK | PROP_MASK
    if pending and all((int(wave[y, x]) & ~independent) == 0 for x, y in pending):
        for x, y in pending:
            chosen = _choose(int(wave[y, x]), weights, rng)
            wave[y, x] = np.uint64(_single(chosen))
            nopts[y, x] = 1
            collapsed[y, x] = chosen
        return collapsed.astype(np.int32)

    while pending:
        best = None
        best_e = 1e18
        live: list[tuple[int, int]] = []
        for x, y in pending:
            if collapsed[y, x] >= 0:
                continue
            n = int(nopts[y, x])
            if n == 0:
                return None
            live.append((x, y))
            e = _entropy(int(wave[y, x]), float(noise[y, x]))
            if e < best_e:
                best_e = e
                best = (x, y)
        if not live:
            break
        assert best is not None
        x, y = best
        chosen = _choose(int(wave[y, x]), weights, rng)
        wave[y, x] = np.uint64(_single(chosen))
        nopts[y, x] = 1
        collapsed[y, x] = chosen
        stack.append((x, y))
        if not propagate():
            return None
        pending = live

    if np.any(collapsed < 0):
        return None
    return collapsed.astype(np.int32)


def run_wfc(
    layout: CoarseLayout,
    params: GeneratorParams,
    rng: np.random.Generator,
    reserved_floor: set[tuple[int, int]],
    exit_cell: tuple[int, int] | None,
) -> WFCResult | None:
    domains = seed_domains(layout, params, reserved_floor, exit_cell)
    for attempt in range(1, params.max_wfc_attempts + 1):
        tiles = collapse(domains, params, rng)
        if tiles is not None:
            return WFCResult(tiles=tiles, attempts=attempt)
    return None
