"""Seeded two-pass map generator: coarse layout + WFC + validation."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from hide_and_seek.world.config import GeneratorParams
from hide_and_seek.world.layout import (
    CoarseLayout,
    Room,
    build_layout,
    coarse_open_ratio,
    corridor_graph_dict,
    open_mask_at,
    room_graph_degrees,
)
from hide_and_seek.world.render import render_surface
from hide_and_seek.world.tiles import DELTA, TILES, legend, tile_id
from hide_and_seek.world.validate import ValidationReport, bfs, validate_map, walkable_mask
from hide_and_seek.world.wfc import run_wfc


class GenerationError(RuntimeError):
    pass


@dataclass
class GameMap:
    seed: int
    params: GeneratorParams
    tiles: np.ndarray
    rooms: list[Room]
    corridor_graph: dict
    exit: tuple[int, int]
    runner_spawns: list[tuple[int, int]]
    monster_spawn: tuple[int, int]
    lamp_sockets: list[tuple[int, int]]
    validation: ValidationReport
    attempts: int
    rejection_reasons: list[str] = field(default_factory=list)
    wfc_attempts: int = 1

    @property
    def surface(self) -> np.ndarray:
        return render_surface(self.tiles, self.params.tile_size)

    def to_dict(self) -> dict:
        materials = [
            [TILES[int(self.tiles[y, x])].material.to_dict() for x in range(self.tiles.shape[1])]
            for y in range(self.tiles.shape[0])
        ]
        return {
            "seed": self.seed,
            "params": self.params.to_dict(),
            "size": self.params.grid_size,
            "tile_size": self.params.tile_size,
            "pixel_size": self.params.pixel_size,
            "tiles": self.tiles.astype(int).tolist(),
            "tile_legend": legend(),
            "materials": materials,
            "rooms": [r.to_dict() for r in self.rooms],
            "corridor_graph": self.corridor_graph,
            "exit": [self.exit[0], self.exit[1]],
            "spawns": {
                "runners": [[x, y] for x, y in self.runner_spawns],
                "monster": [self.monster_spawn[0], self.monster_spawn[1]],
            },
            "lamp_sockets": [[x, y] for x, y in self.lamp_sockets],
            "validation": {
                **self.validation.to_dict(),
                "attempts": self.attempts,
                "wfc_attempts": self.wfc_attempts,
                "rejection_reasons": self.rejection_reasons,
            },
        }


def _interior_tiles(room: Room) -> list[tuple[int, int]]:
    return [(x, y) for y in range(room.y, room.y + room.h) for x in range(room.x, room.x + room.w)]


def _manhattan(a: tuple[int, int], b: tuple[int, int]) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def _pick_spawn_room(layout: CoarseLayout) -> int | None:
    """Prefer a corner-most room with two or more connections (avoids a dead-end spawn)."""
    deg = room_graph_degrees(layout)
    size = layout.grid.shape[0]
    corners = ((1, 1), (1, size - 2), (size - 2, 1), (size - 2, size - 2))

    def corner_dist(room: Room) -> float:
        cx, cy = room.center
        return min(abs(cx - x) + abs(cy - y) for x, y in corners)

    ranked = sorted(
        layout.rooms,
        key=lambda r: (
            0 if deg[r.id] >= 2 else 1,
            0 if r.kind == "large" else 1,
            corner_dist(r),
            -r.w * r.h,
        ),
    )
    return ranked[0].id if ranked else None


def _farthest_walkable(
    from_src: dict[tuple[int, int], int],
    walk: np.ndarray,
    room_of: np.ndarray,
    forbidden: set[tuple[int, int]],
    rooms_only: bool,
) -> tuple[int, int] | None:
    best = None
    best_d = -1
    size = walk.shape[0]
    for y in range(size):
        for x in range(size):
            p = (x, y)
            if p in forbidden or p not in from_src or not walk[y, x]:
                continue
            if rooms_only and int(room_of[y, x]) < 0:
                continue
            d = from_src[p]
            if d > best_d:
                best_d = d
                best = p
    return best


def _pick_monster(
    from_spawn: dict[tuple[int, int], int],
    from_exit: dict[tuple[int, int], int],
    walk: np.ndarray,
    room_of: np.ndarray,
    forbidden: set[tuple[int, int]],
    min_runner: float,
    min_exit: float,
) -> tuple[int, int] | None:
    best = None
    best_score = -1.0
    size = walk.shape[0]
    for y in range(size):
        for x in range(size):
            p = (x, y)
            if p in forbidden or not walk[y, x]:
                continue
            ds = from_spawn.get(p)
            de = from_exit.get(p)
            if ds is None or de is None:
                continue
            if ds < min_runner or de < min_exit:
                continue
            score = float(ds + de)
            if int(room_of[y, x]) >= 0:
                score += 4.0
            if score > best_score:
                best_score = score
                best = p
    return best


def _pick_tiles_near_center(room: Room, count: int, avoid: set[tuple[int, int]]) -> list[tuple[int, int]]:
    tiles = [p for p in _interior_tiles(room) if p not in avoid]
    cx, cy = room.center_tile
    tiles.sort(key=lambda p: (_manhattan(p, (cx, cy)), p[1], p[0]))
    return tiles[:count]


def _door_clearance(layout: CoarseLayout) -> set[tuple[int, int]]:
    reserved: set[tuple[int, int]] = set()
    size = layout.grid.shape[0]
    for y in range(size):
        for x in range(size):
            if int(layout.grid[y, x]) != 4:  # DOOR
                continue
            for dx, dy in DELTA:
                nx, ny = x + dx, y + dy
                if 0 <= nx < size and 0 <= ny < size and int(layout.room_of[ny, nx]) >= 0:
                    reserved.add((nx, ny))
    return reserved


def _plus(p: tuple[int, int], room: Room) -> list[tuple[int, int]]:
    x, y = p
    out = []
    for q in ((x, y), (x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
        if room.contains(*q):
            out.append(q)
    return out


def _place_lamps(
    rng: np.random.Generator,
    layout: CoarseLayout,
    tiles: np.ndarray,
    exit_cell: tuple[int, int],
    params: GeneratorParams,
) -> list[tuple[int, int]] | None:
    walk = walkable_mask(tiles)
    size = tiles.shape[0]
    candidates: list[tuple[int, int, int]] = []  # priority, x, y

    for r in layout.rooms:
        cx, cy = r.center_tile
        if walk[cy, cx]:
            candidates.append((0, cx, cy))
        else:
            for p in _pick_tiles_near_center(r, 4, set()):
                if walk[p[1], p[0]]:
                    candidates.append((0, p[0], p[1]))
                    break

    for y in range(size):
        for x in range(size):
            kind = int(layout.grid[y, x])
            if not walk[y, x]:
                continue
            if kind == 4:  # door
                candidates.append((1, x, y))
            elif kind == 3 and bin(open_mask_at(layout.grid, x, y)).count("1") >= 3:
                candidates.append((2, x, y))

    order = np.arange(len(candidates))
    rng.shuffle(order)
    shuffled = [candidates[int(i)] for i in order]
    shuffled.sort(key=lambda t: t[0])

    target = int(rng.integers(params.lamp_count_min, params.lamp_count_max + 1))
    chosen: list[tuple[int, int]] = []
    spacing = params.lamp_min_spacing

    def ok(p: tuple[int, int]) -> bool:
        return all(_manhattan(p, q) >= spacing for q in chosen)

    for _, x, y in shuffled:
        p = (x, y)
        if p in chosen or not ok(p):
            continue
        chosen.append(p)
        if len(chosen) >= target:
            break

    if params.exit_lamp:
        if all(_manhattan(exit_cell, q) >= spacing for q in chosen):
            if len(chosen) < params.lamp_count_max and walk[exit_cell[1], exit_cell[0]]:
                # Prefer a neighbour of the exit so the tile itself stays the silhouette.
                placed = False
                for dx, dy in DELTA:
                    nx, ny = exit_cell[0] + dx, exit_cell[1] + dy
                    if 0 <= nx < size and 0 <= ny < size and walk[ny, nx] and ok((nx, ny)):
                        chosen.append((nx, ny))
                        placed = True
                        break
                if not placed and ok(exit_cell):
                    chosen.append(exit_cell)
        # else a socket is already near the exit

    if len(chosen) < params.lamp_count_min:
        return None
    return chosen[: params.lamp_count_max]


def generate_map(
    seed: int,
    params: GeneratorParams | None = None,
) -> GameMap:
    """Generate a validated map. Same seed + params ⇒ identical map."""
    params = params or GeneratorParams()
    rng = np.random.default_rng(int(seed))
    reasons: list[str] = []

    for attempt in range(1, params.max_generate_attempts + 1):
        layout = build_layout(rng, params)
        if layout is None:
            reasons.append("layout")
            continue
        if layout.loops < params.min_loops:
            reasons.append("loops")
            continue
        ratio = coarse_open_ratio(layout.grid)
        # Leave a little slack for solid props.
        if ratio < params.open_floor_min or ratio > params.open_floor_max + 0.04:
            reasons.append("coarse_open_ratio")
            continue

        spawn_id = _pick_spawn_room(layout)
        if spawn_id is None:
            reasons.append("roles")
            continue
        spawn_room = layout.rooms[spawn_id]

        reserved = _door_clearance(layout)
        runners = _pick_tiles_near_center(spawn_room, 4, set())
        if len(runners) < 4:
            reasons.append("runner_tiles")
            continue
        for p in runners:
            reserved.update(_plus(p, spawn_room))

        # Exit is stamped after collapse so we can pick the farthest walkable tile.
        wfc = run_wfc(layout, params, rng, reserved, exit_cell=None)
        if wfc is None:
            reasons.append("wfc")
            continue

        walk = walkable_mask(wfc.tiles)
        from_spawn, _ = bfs(walk, runners)
        forbidden = set(runners)
        deg = room_graph_degrees(layout)
        looped = {r.id for r in layout.rooms if deg[r.id] >= 2}

        def farthest(room_ids: set[int] | None) -> tuple[int, int] | None:
            best = None
            best_d = -1
            size = walk.shape[0]
            for y in range(size):
                for x in range(size):
                    p = (x, y)
                    if p in forbidden or p not in from_spawn or not walk[y, x]:
                        continue
                    rid = int(layout.room_of[y, x])
                    if rid < 0:
                        continue
                    if room_ids is not None and rid not in room_ids:
                        continue
                    d = from_spawn[p]
                    if d > best_d:
                        best_d = d
                        best = p
            return best

        exit_cell = farthest(looped)
        if exit_cell is None or from_spawn[exit_cell] < params.min_exit_path:
            alt = farthest(None)
            if alt is not None and (exit_cell is None or from_spawn[alt] > from_spawn[exit_cell]):
                exit_cell = alt
        if exit_cell is None:
            exit_cell = _farthest_walkable(from_spawn, walk, layout.room_of, forbidden, rooms_only=False)
        if exit_cell is None:
            reasons.append("exit_tile")
            continue
        wfc.tiles[exit_cell[1], exit_cell[0]] = tile_id("EXIT")

        from_exit, _ = bfs(walk, exit_cell)
        monster = _pick_monster(
            from_spawn,
            from_exit,
            walk,
            layout.room_of,
            forbidden | {exit_cell},
            params.min_monster_runner_path,
            params.min_monster_exit_path,
        )
        if monster is None:
            reasons.append("monster_tile")
            continue

        lamps = _place_lamps(rng, layout, wfc.tiles, exit_cell, params)
        if lamps is None:
            reasons.append("lamps")
            continue

        report = validate_map(
            wfc.tiles,
            params,
            exit_cell,
            runners,
            monster,
            layout.loops,
        )
        if not report.ok:
            reasons.append(report.reason)
            continue

        return GameMap(
            seed=int(seed),
            params=params,
            tiles=wfc.tiles,
            rooms=layout.rooms,
            corridor_graph=corridor_graph_dict(layout),
            exit=exit_cell,
            runner_spawns=runners,
            monster_spawn=monster,
            lamp_sockets=lamps,
            validation=report,
            attempts=attempt,
            rejection_reasons=reasons,
            wfc_attempts=wfc.attempts,
        )

    raise GenerationError(
        f"failed to generate a valid map for seed={seed} after "
        f"{params.max_generate_attempts} attempts; reasons={reasons[-12:]}"
    )
