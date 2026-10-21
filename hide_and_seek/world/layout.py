"""Coarse room / corridor layout (pass 1)."""

from __future__ import annotations

from dataclasses import dataclass
from heapq import heappop, heappush

import numpy as np

from hide_and_seek.world.config import GeneratorParams
from hide_and_seek.world.tiles import DELTA

# Coarse cell kinds
VOID = 0
ROOM = 1
ROOM_WALL = 2
CORRIDOR = 3
DOOR = 4

OPEN_KINDS = {ROOM, CORRIDOR, DOOR}


@dataclass
class Room:
    id: int
    kind: str
    x: int
    y: int
    w: int
    h: int
    floor_variant: int  # 0, 1, 2 → ROOM_FLOOR_A/B/C

    @property
    def center(self) -> tuple[float, float]:
        return (self.x + (self.w - 1) / 2.0, self.y + (self.h - 1) / 2.0)

    @property
    def center_tile(self) -> tuple[int, int]:
        return (self.x + self.w // 2, self.y + self.h // 2)

    def contains(self, x: int, y: int) -> bool:
        return self.x <= x < self.x + self.w and self.y <= y < self.y + self.h

    def wall_box(self) -> tuple[int, int, int, int]:
        return (self.x - 1, self.y - 1, self.w + 2, self.h + 2)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "kind": self.kind,
            "x": self.x,
            "y": self.y,
            "w": self.w,
            "h": self.h,
            "floor_variant": self.floor_variant,
        }


@dataclass
class CorridorLink:
    room_a: int
    room_b: int
    path: list[tuple[int, int]]
    width: int
    doors: list[tuple[int, int]]


@dataclass
class CoarseLayout:
    grid: np.ndarray
    rooms: list[Room]
    links: list[CorridorLink]
    room_of: np.ndarray
    extra_edges: int

    @property
    def loops(self) -> int:
        n = len(self.rooms)
        e = len(self.links)
        return e - n + 1 if n else 0


def _boxes_overlap(ax: int, ay: int, aw: int, ah: int, bx: int, by: int, bw: int, bh: int) -> bool:
    return ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah


def _manhattan_c(a: tuple[float, float], b: tuple[float, float]) -> float:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


class _UF:
    def __init__(self, n: int) -> None:
        self.p = list(range(n))
        self.r = [0] * n

    def find(self, x: int) -> int:
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a: int, b: int) -> bool:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return False
        if self.r[ra] < self.r[rb]:
            ra, rb = rb, ra
        self.p[rb] = ra
        if self.r[ra] == self.r[rb]:
            self.r[ra] += 1
        return True


def _fits(rooms: list[Room], x: int, y: int, w: int, h: int, size: int) -> bool:
    if x < 1 or y < 1 or x + w > size - 1 or y + h > size - 1:
        return False
    ax, ay, aw, ah = x - 1, y - 1, w + 2, h + 2
    for r in rooms:
        bx, by, bw, bh = r.wall_box()
        if _boxes_overlap(ax, ay, aw, ah, bx, by, bw, bh):
            return False
    return True


def _place_one(
    rng: np.random.Generator,
    rooms: list[Room],
    w: int,
    h: int,
    size: int,
    x_lo: int,
    x_hi: int,
    y_lo: int,
    y_hi: int,
    random_tries: int = 40,
) -> tuple[int, int] | None:
    x_lo = max(1, x_lo)
    y_lo = max(1, y_lo)
    x_hi = min(x_hi, size - w - 1)
    y_hi = min(y_hi, size - h - 1)
    if x_lo > x_hi or y_lo > y_hi:
        return None
    for _ in range(random_tries):
        x = int(rng.integers(x_lo, x_hi + 1))
        y = int(rng.integers(y_lo, y_hi + 1))
        if _fits(rooms, x, y, w, h, size):
            return x, y
    xs = np.arange(x_lo, x_hi + 1)
    ys = np.arange(y_lo, y_hi + 1)
    rng.shuffle(xs)
    rng.shuffle(ys)
    for y in ys:
        for x in xs:
            if _fits(rooms, int(x), int(y), w, h, size):
                return int(x), int(y)
    return None


def _place_rooms(rng: np.random.Generator, params: GeneratorParams) -> list[Room] | None:
    size = params.grid_size
    rooms: list[Room] = []
    n_large = int(rng.integers(params.large_rooms_min, params.large_rooms_max + 1))
    n_small = int(rng.integers(params.small_rooms_min, params.small_rooms_max + 1))
    mid = size // 2

    # Spread the first large rooms across opposite halves so exit distance is reachable.
    quadrants = [
        (1, mid - 1, 1, mid - 1),
        (mid, size - 1, mid, size - 1),
        (mid, size - 1, 1, mid - 1),
        (1, mid - 1, mid, size - 1),
    ]
    q0 = int(rng.integers(0, 4))
    q_order = [(q0 + i) % 4 for i in range(4)]

    for i in range(n_large):
        # Bias toward the larger end of the spec range so open-floor ratio lands in band.
        w = int(max(rng.integers(params.large_room_min_size, params.large_room_max_size + 1),
                    rng.integers(params.large_room_min_size, params.large_room_max_size + 1)))
        h = int(max(rng.integers(params.large_room_min_size, params.large_room_max_size + 1),
                    rng.integers(params.large_room_min_size, params.large_room_max_size + 1)))
        x_lo, x_hi, y_lo, y_hi = quadrants[q_order[i % 4]]
        pos = _place_one(rng, rooms, w, h, size, x_lo, x_hi, y_lo, y_hi)
        if pos is None:
            pos = _place_one(rng, rooms, w, h, size, 1, size - 1, 1, size - 1)
        if pos is None:
            return None
        rooms.append(
            Room(len(rooms), "large", pos[0], pos[1], w, h, int(rng.integers(0, 3)))
        )

    placed_small = 0
    for _ in range(n_small):
        w = int(max(rng.integers(params.small_room_min_size, params.small_room_max_size + 1),
                    rng.integers(params.small_room_min_size, params.small_room_max_size + 1)))
        h = int(max(rng.integers(params.small_room_min_size, params.small_room_max_size + 1),
                    rng.integers(params.small_room_min_size, params.small_room_max_size + 1)))
        pos = _place_one(rng, rooms, w, h, size, 1, size - 1, 1, size - 1)
        if pos is None:
            break
        rooms.append(
            Room(len(rooms), "small", pos[0], pos[1], w, h, int(rng.integers(0, 3)))
        )
        placed_small += 1
    if placed_small < params.small_rooms_min:
        return None

    return rooms


def _paint_rooms(size: int, rooms: list[Room]) -> tuple[np.ndarray, np.ndarray]:
    grid = np.full((size, size), VOID, dtype=np.int8)
    room_of = np.full((size, size), -1, dtype=np.int16)
    for r in rooms:
        wx, wy, ww, wh = r.wall_box()
        grid[wy : wy + wh, wx : wx + ww] = ROOM_WALL
        grid[r.y : r.y + r.h, r.x : r.x + r.w] = ROOM
        room_of[r.y : r.y + r.h, r.x : r.x + r.w] = r.id
    return grid, room_of


def _wall_cells(room: Room) -> list[tuple[int, int, int]]:
    """Return (x, y, side) where side is N/E/S/W of the room interior."""
    cells: list[tuple[int, int, int]] = []
    for x in range(room.x, room.x + room.w):
        cells.append((x, room.y - 1, 0))  # N
        cells.append((x, room.y + room.h, 2))  # S
    for y in range(room.y, room.y + room.h):
        cells.append((room.x + room.w, y, 1))  # E
        cells.append((room.x - 1, y, 3))  # W
    return cells


def _outside(x: int, y: int, side: int) -> tuple[int, int]:
    dx, dy = DELTA[side]
    return x + dx, y + dy


def _in_bounds(x: int, y: int, size: int) -> bool:
    return 0 <= x < size and 0 <= y < size


def _door_candidates(
    room: Room, target: tuple[float, float], grid: np.ndarray, k: int = 6
) -> list[tuple[int, int, int]]:
    size = grid.shape[0]
    scored: list[tuple[float, int, int, int]] = []
    for x, y, side in _wall_cells(room):
        ox, oy = _outside(x, y, side)
        if not _in_bounds(ox, oy, size):
            continue
        if grid[oy, ox] == ROOM:
            continue
        if grid[y, x] not in (ROOM_WALL, DOOR):
            continue
        # A* starts on the outside cell; it must already be a carve-able tile
        # or we will start on the door itself.
        if grid[oy, ox] not in (VOID, CORRIDOR, DOOR, ROOM_WALL):
            continue
        d = abs(x - target[0]) + abs(y - target[1])
        scored.append((d, x, y, side))
    scored.sort(key=lambda t: t[0])
    return [(x, y, side) for _, x, y, side in scored[:k]]


def _cell_cost(kind: int) -> int | None:
    # Prefer open space so MST links become real corridors; rooms are a last resort
    # so a blocked VOID component cannot fail the whole layout.
    if kind in (VOID, CORRIDOR, DOOR):
        return 1
    if kind == ROOM_WALL:
        return 8
    if kind == ROOM:
        return 14
    return None


def _astar(
    grid: np.ndarray,
    start: tuple[int, int],
    goal: tuple[int, int],
    prefer_new: bool = False,
) -> list[tuple[int, int]] | None:
    size = grid.shape[0]
    sx, sy = start
    gx, gy = goal
    if not _in_bounds(sx, sy, size) or not _in_bounds(gx, gy, size):
        return None
    if _cell_cost(int(grid[sy, sx])) is None or _cell_cost(int(grid[gy, gx])) is None:
        return None
    if start == goal:
        return [start]

    def heur(x: int, y: int) -> int:
        return abs(x - gx) + abs(y - gy)

    open_h: list[tuple[int, int, int, int]] = []
    heappush(open_h, (heur(sx, sy), 0, sx, sy))
    came: dict[tuple[int, int], tuple[int, int]] = {}
    gscore = {start: 0}
    closed: set[tuple[int, int]] = set()

    while open_h:
        _, g, x, y = heappop(open_h)
        if (x, y) in closed:
            continue
        closed.add((x, y))
        if (x, y) == goal:
            path = [(x, y)]
            while (x, y) in came:
                x, y = came[(x, y)]
                path.append((x, y))
            path.reverse()
            return path
        for dx, dy in DELTA:
            nx, ny = x + dx, y + dy
            if not _in_bounds(nx, ny, size):
                continue
            kind = int(grid[ny, nx])
            step = _cell_cost(kind)
            if step is None:
                continue
            if prefer_new and kind == CORRIDOR:
                step += 4
            ng = g + step
            prev = gscore.get((nx, ny))
            if prev is None or ng < prev:
                gscore[(nx, ny)] = ng
                came[(nx, ny)] = (x, y)
                heappush(open_h, (ng + heur(nx, ny), ng, nx, ny))
    return None


def _l_path(start: tuple[int, int], goal: tuple[int, int]) -> list[tuple[int, int]]:
    sx, sy = start
    gx, gy = goal
    path = [(sx, sy)]
    x, y = sx, sy
    step = 1 if gx >= x else -1
    while x != gx:
        x += step
        path.append((x, y))
    step = 1 if gy >= y else -1
    while y != gy:
        y += step
        path.append((x, y))
    return path


def _dilate_path(
    grid: np.ndarray, path: list[tuple[int, int]], width: int
) -> list[tuple[int, int]]:
    if width < 2 or len(path) < 2:
        return []
    extra: list[tuple[int, int]] = []
    size = grid.shape[0]
    for i, (x, y) in enumerate(path):
        if i + 1 < len(path):
            dx = path[i + 1][0] - x
            dy = path[i + 1][1] - y
        else:
            dx = x - path[i - 1][0]
            dy = y - path[i - 1][1]
        # Perpendicular offsets.
        offs = [(-dy, dx), (dy, -dx)]
        for ox, oy in offs:
            nx, ny = x + ox, y + oy
            if not _in_bounds(nx, ny, size):
                continue
            if grid[ny, nx] in (VOID, CORRIDOR, DOOR):
                extra.append((nx, ny))
            # Do not chew room interiors or turn extra walls into doors here.
    return extra


def _carve_link(
    rng: np.random.Generator,
    grid: np.ndarray,
    rooms: list[Room],
    a: int,
    b: int,
    width: int,
    prefer_new: bool = False,
) -> CorridorLink | None:
    ra, rb = rooms[a], rooms[b]
    cands_a = _door_candidates(ra, rb.center, grid)
    cands_b = _door_candidates(rb, ra.center, grid)
    if not cands_a or not cands_b:
        return None

    # Try closer door pairs first; shuffle slightly so seeds vary.
    pairs: list[tuple[int, tuple[int, int, int], tuple[int, int, int]]] = []
    for da in cands_a:
        for db in cands_b:
            d = abs(da[0] - db[0]) + abs(da[1] - db[1])
            pairs.append((d, da, db))
    pairs.sort(key=lambda t: t[0])
    if len(pairs) > 8:
        head = pairs[:4]
        tail = pairs[4:]
        order = np.arange(len(tail))
        rng.shuffle(order)
        pairs = head + [tail[int(i)] for i in order[:4]]

    for _, da, db in pairs:
        start = _outside(da[0], da[1], da[2])
        goal = _outside(db[0], db[1], db[2])
        if not _in_bounds(*start, grid.shape[0]) or _cell_cost(int(grid[start[1], start[0]])) is None:
            start = (da[0], da[1])
        if not _in_bounds(*goal, grid.shape[0]) or _cell_cost(int(grid[goal[1], goal[0]])) is None:
            goal = (db[0], db[1])
        path = _astar(grid, start, goal, prefer_new=prefer_new)
        if path is None:
            path = _l_path(start, goal)
            if any(_cell_cost(int(grid[y, x])) is None for x, y in path):
                continue
        doors = [(da[0], da[1]), (db[0], db[1])]
        extra = _dilate_path(grid, path, width)
        for x, y in path + extra:
            kind = int(grid[y, x])
            if kind == VOID:
                grid[y, x] = CORRIDOR
            elif kind == ROOM_WALL:
                grid[y, x] = DOOR
                doors.append((x, y))
        for x, y in list(doors):
            if grid[y, x] in (ROOM_WALL, DOOR):
                grid[y, x] = DOOR
        # unique doors
        doors = list(dict.fromkeys(doors))
        return CorridorLink(a, b, path, width, doors)
    return None


def _degree(n_rooms: int, links: list[CorridorLink]) -> list[int]:
    deg = [0] * n_rooms
    for link in links:
        deg[link.room_a] += 1
        deg[link.room_b] += 1
    return deg


def _already_linked(links: list[CorridorLink], a: int, b: int) -> bool:
    lo, hi = (a, b) if a < b else (b, a)
    for link in links:
        x, y = (link.room_a, link.room_b) if link.room_a < link.room_b else (link.room_b, link.room_a)
        if x == lo and y == hi:
            return True
    return False


def _pair_distances(rooms: list[Room]) -> list[tuple[float, int, int]]:
    pairs: list[tuple[float, int, int]] = []
    for i, ra in enumerate(rooms):
        for j in range(i + 1, len(rooms)):
            pairs.append((_manhattan_c(ra.center, rooms[j].center), i, j))
    pairs.sort()
    return pairs


def _connect_rooms(
    rng: np.random.Generator,
    grid: np.ndarray,
    rooms: list[Room],
    params: GeneratorParams,
) -> list[CorridorLink] | None:
    n = len(rooms)
    pairs = _pair_distances(rooms)
    uf = _UF(n)
    links: list[CorridorLink] = []

    def width() -> int:
        return int(rng.integers(params.corridor_width_min, params.corridor_width_max + 1))

    # MST
    for _, i, j in pairs:
        if uf.find(i) == uf.find(j):
            continue
        link = _carve_link(rng, grid, rooms, i, j, width(), prefer_new=False)
        if link is None:
            return None
        uf.union(i, j)
        links.append(link)

    if any(uf.find(i) != uf.find(0) for i in range(n)):
        return None

    n_extra = int(rng.integers(params.extra_connections_min, params.extra_connections_max + 1))
    n_extra = max(n_extra, params.min_loops)

    # Prefer connecting leaves so we do not create two dead-end chokepoints.
    def try_extra(a: int, b: int) -> bool:
        if a == b or _already_linked(links, a, b):
            return False
        link = _carve_link(rng, grid, rooms, a, b, width(), prefer_new=True)
        if link is None:
            return False
        links.append(link)
        return True

    # First: lift leaves.
    guard = 0
    while guard < n * 3:
        guard += 1
        deg = _degree(n, links)
        leaves = [i for i, d in enumerate(deg) if d <= 1]
        if len(leaves) <= 1:
            break
        leaf = leaves[int(rng.integers(0, len(leaves)))]
        others = [i for i in range(n) if i != leaf and not _already_linked(links, leaf, i)]
        others.sort(key=lambda i: _manhattan_c(rooms[leaf].center, rooms[i].center))
        added = False
        for other in others:
            if try_extra(leaf, other):
                added = True
                break
        if not added:
            break

    # Then: extra loops up to n_extra (counting every non-MST edge).
    extras_needed = n_extra - (len(links) - (n - 1))
    if extras_needed > 0:
        leftover = [
            (d, i, j)
            for d, i, j in pairs
            if not _already_linked(links, i, j)
        ]
        order = np.arange(len(leftover))
        rng.shuffle(order)
        leftover = [leftover[int(i)] for i in order]
        leftover.sort(key=lambda t: t[0])
        for _, i, j in leftover:
            if extras_needed <= 0:
                break
            if try_extra(i, j):
                extras_needed -= 1

    if len(links) - (n - 1) < params.min_loops:
        return None
    return links


def _room_door_count(grid: np.ndarray, room: Room) -> int:
    n = 0
    for x, y, _side in _wall_cells(room):
        if 0 <= x < grid.shape[0] and 0 <= y < grid.shape[0] and int(grid[y, x]) == DOOR:
            n += 1
    return n


def ensure_second_doors(grid: np.ndarray, rooms: list[Room]) -> None:
    """Punch a second opening on rooms that still have only one door."""
    size = grid.shape[0]
    for room in rooms:
        if _room_door_count(grid, room) >= 2:
            continue
        # Prefer a wall opposite an existing door, facing VOID/CORRIDOR.
        candidates = []
        for x, y, side in _wall_cells(room):
            if not _in_bounds(x, y, size) or int(grid[y, x]) != ROOM_WALL:
                continue
            ox, oy = _outside(x, y, side)
            if not _in_bounds(ox, oy, size):
                continue
            if int(grid[oy, ox]) in (VOID, CORRIDOR, DOOR):
                candidates.append((x, y, ox, oy))
        if not candidates:
            continue
        # Farthest from room center so the two doors sit on different sides.
        cx, cy = room.center
        candidates.sort(key=lambda t: -(abs(t[0] - cx) + abs(t[1] - cy)))
        x, y, ox, oy = candidates[0]
        grid[y, x] = DOOR
        if int(grid[oy, ox]) == VOID:
            grid[oy, ox] = CORRIDOR


def thicken_corridors(grid: np.ndarray, target_ratio: float) -> None:
    """Widen existing corridors into adjacent VOID until the open-floor ratio is met."""
    size = grid.shape[0]
    guard = 0
    while coarse_open_ratio(grid) < target_ratio and guard < 8:
        guard += 1
        adds: list[tuple[int, int]] = []
        for y in range(1, size - 1):
            for x in range(1, size - 1):
                if int(grid[y, x]) != VOID:
                    continue
                if any(int(grid[y + dy, x + dx]) in (CORRIDOR, DOOR) for dx, dy in DELTA):
                    adds.append((x, y))
        if not adds:
            break
        for x, y in adds:
            grid[y, x] = CORRIDOR
            if coarse_open_ratio(grid) >= target_ratio:
                return


def build_layout(rng: np.random.Generator, params: GeneratorParams) -> CoarseLayout | None:
    rooms = _place_rooms(rng, params)
    if rooms is None or len(rooms) < 4:
        return None
    grid, room_of = _paint_rooms(params.grid_size, rooms)
    links = _connect_rooms(rng, grid, rooms, params)
    if links is None:
        return None
    ensure_second_doors(grid, rooms)
    # Aim a bit above the minimum so solid props still leave us in-band.
    target = min(params.open_floor_max - 0.03, max(params.open_floor_min + 0.06, 0.42))
    thicken_corridors(grid, target)
    extra = len(links) - (len(rooms) - 1)
    return CoarseLayout(grid=grid, rooms=rooms, links=links, room_of=room_of, extra_edges=extra)


def open_mask_at(grid: np.ndarray, x: int, y: int) -> int:
    """Bit mask of orthogonal neighbors that are room / corridor / door."""
    size = grid.shape[0]
    mask = 0
    bits = (1, 2, 4, 8)
    for d, (dx, dy) in enumerate(DELTA):
        nx, ny = x + dx, y + dy
        if 0 <= nx < size and 0 <= ny < size and int(grid[ny, nx]) in OPEN_KINDS:
            mask |= bits[d]
    return mask


def coarse_open_ratio(grid: np.ndarray) -> float:
    open_cells = np.isin(grid, (ROOM, CORRIDOR, DOOR)).sum()
    return float(open_cells) / float(grid.size)


def room_graph_degrees(layout: CoarseLayout) -> list[int]:
    return _degree(len(layout.rooms), layout.links)


def corridor_graph_dict(layout: CoarseLayout) -> dict:
    nodes = []
    for r in layout.rooms:
        cx, cy = r.center_tile
        nodes.append({"id": f"room_{r.id}", "type": "room", "pos": [cx, cy], "room_id": r.id})
    junctions: set[tuple[int, int]] = set()
    grid = layout.grid
    size = grid.shape[0]
    for y in range(size):
        for x in range(size):
            if grid[y, x] != CORRIDOR:
                continue
            if bin(open_mask_at(grid, x, y)).count("1") >= 3:
                junctions.add((x, y))
    for i, (x, y) in enumerate(sorted(junctions)):
        nodes.append({"id": f"j_{x}_{y}", "type": "junction", "pos": [x, y], "room_id": None})
    edges = []
    for i, link in enumerate(layout.links):
        edges.append(
            {
                "id": f"c_{i}",
                "a": f"room_{link.room_a}",
                "b": f"room_{link.room_b}",
                "path": [[x, y] for x, y in link.path],
                "width": link.width,
                "doors": [[x, y] for x, y in link.doors],
            }
        )
    return {
        "nodes": nodes,
        "edges": edges,
        "loops": layout.loops,
    }
