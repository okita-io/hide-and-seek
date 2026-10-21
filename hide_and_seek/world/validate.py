"""Reject-and-regenerate checks for a finished map."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import numpy as np

from hide_and_seek.world.config import GeneratorParams
from hide_and_seek.world.tiles import DELTA, is_solid


@dataclass
class ValidationReport:
    ok: bool
    reason: str = ""
    connected: bool = False
    exit_path_length: int = 0
    exit_path_min: float = 0.0
    monster_runner_path: int = 0
    monster_exit_path: int = 0
    loops: int = 0
    chokepoint_count: int = 0
    open_floor_ratio: float = 0.0
    exit_path: list[tuple[int, int]] = field(default_factory=list)
    chokepoint_tiles: list[tuple[int, int]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "reason": self.reason,
            "connected": self.connected,
            "exit_path_length": self.exit_path_length,
            "exit_path_min": self.exit_path_min,
            "monster_runner_path": self.monster_runner_path,
            "monster_exit_path": self.monster_exit_path,
            "loops": self.loops,
            "chokepoint_count": self.chokepoint_count,
            "open_floor_ratio": round(self.open_floor_ratio, 4),
        }


def walkable_mask(tiles: np.ndarray) -> np.ndarray:
    size = tiles.shape[0]
    walk = np.zeros((size, size), dtype=bool)
    for y in range(size):
        for x in range(size):
            walk[y, x] = not is_solid(int(tiles[y, x]))
    return walk


def bfs(
    walk: np.ndarray,
    start: tuple[int, int] | list[tuple[int, int]],
) -> tuple[dict[tuple[int, int], int], dict[tuple[int, int], tuple[int, int]]]:
    size = walk.shape[0]
    starts = [start] if isinstance(start, tuple) else list(start)
    dist: dict[tuple[int, int], int] = {}
    prev: dict[tuple[int, int], tuple[int, int]] = {}
    q: deque[tuple[int, int]] = deque()
    for sx, sy in starts:
        if (sx, sy) in dist:
            continue
        dist[(sx, sy)] = 0
        q.append((sx, sy))
    while q:
        x, y = q.popleft()
        for dx, dy in DELTA:
            nx, ny = x + dx, y + dy
            if not (0 <= nx < size and 0 <= ny < size):
                continue
            if not walk[ny, nx] or (nx, ny) in dist:
                continue
            dist[(nx, ny)] = dist[(x, y)] + 1
            prev[(nx, ny)] = (x, y)
            q.append((nx, ny))
    return dist, prev


def reconstruct(
    prev: dict[tuple[int, int], tuple[int, int]], start: tuple[int, int], goal: tuple[int, int]
) -> list[tuple[int, int]]:
    if start == goal:
        return [start]
    path = [goal]
    cur = goal
    while cur != start:
        if cur not in prev:
            return []
        cur = prev[cur]
        path.append(cur)
    path.reverse()
    return path


def reachable(walk: np.ndarray, start: tuple[int, int], goal: tuple[int, int], blocked: set[tuple[int, int]] | None = None) -> bool:
    size = walk.shape[0]
    if start == goal:
        return True
    seen = {start}
    q = deque([start])
    while q:
        x, y = q.popleft()
        for dx, dy in DELTA:
            nx, ny = x + dx, y + dy
            if not (0 <= nx < size and 0 <= ny < size):
                continue
            if (nx, ny) in seen or (blocked and (nx, ny) in blocked):
                continue
            if not walk[ny, nx]:
                continue
            if (nx, ny) == goal:
                return True
            seen.add((nx, ny))
            q.append((nx, ny))
    return False


def find_st_cut_vertices(
    walk: np.ndarray, src: tuple[int, int], dst: tuple[int, int]
) -> list[tuple[int, int]]:
    """Vertices that lie on every src→dst path (articulation points in the s-t subgraph)."""
    from_s, _ = bfs(walk, src)
    from_t, _ = bfs(walk, dst)
    if dst not in from_s:
        return []
    nodes = {p for p in from_s if p in from_t}
    adj: dict[tuple[int, int], list[tuple[int, int]]] = {p: [] for p in nodes}
    for x, y in nodes:
        for dx, dy in DELTA:
            n = (x + dx, y + dy)
            if n in nodes:
                adj[(x, y)].append(n)

    time = 0
    disc: dict[tuple[int, int], int] = {}
    low: dict[tuple[int, int], int] = {}
    parent: dict[tuple[int, int], tuple[int, int] | None] = {}
    arts: set[tuple[int, int]] = set()

    def dfs(u: tuple[int, int]) -> None:
        nonlocal time
        children = 0
        time += 1
        disc[u] = low[u] = time
        for v in adj[u]:
            if v not in disc:
                parent[v] = u
                children += 1
                dfs(v)
                low[u] = min(low[u], low[v])
                if parent.get(u) is None and children > 1:
                    arts.add(u)
                if parent.get(u) is not None and low[v] >= disc[u]:
                    arts.add(u)
            elif v != parent.get(u):
                low[u] = min(low[u], disc[v])

    parent[src] = None
    dfs(src)
    # Only keep vertices whose removal actually separates src from dst.
    return [v for v in arts if v != src and v != dst and not reachable(walk, src, dst, blocked={v})]


def cluster_tiles(tiles: list[tuple[int, int]]) -> list[list[tuple[int, int]]]:
    remaining = set(tiles)
    clusters: list[list[tuple[int, int]]] = []
    while remaining:
        start = remaining.pop()
        comp = [start]
        q = deque([start])
        while q:
            x, y = q.popleft()
            for dx, dy in DELTA:
                n = (x + dx, y + dy)
                if n in remaining:
                    remaining.remove(n)
                    comp.append(n)
                    q.append(n)
        clusters.append(comp)
    return clusters


def open_floor_ratio(tiles: np.ndarray) -> float:
    walk = walkable_mask(tiles)
    return float(walk.sum()) / float(tiles.size)


def validate_map(
    tiles: np.ndarray,
    params: GeneratorParams,
    exit_cell: tuple[int, int],
    runner_spawns: list[tuple[int, int]],
    monster_spawn: tuple[int, int],
    loops: int,
) -> ValidationReport:
    report = ValidationReport(ok=False, loops=loops, exit_path_min=params.min_exit_path)
    walk = walkable_mask(tiles)

    if not walk[exit_cell[1], exit_cell[0]]:
        report.reason = "exit_not_walkable"
        return report
    for p in runner_spawns:
        if not walk[p[1], p[0]]:
            report.reason = "runner_spawn_blocked"
            return report
    if not walk[monster_spawn[1], monster_spawn[0]]:
        report.reason = "monster_spawn_blocked"
        return report

    from_exit, prev_exit = bfs(walk, exit_cell)
    for p in runner_spawns:
        if p not in from_exit:
            report.reason = "exit_unreachable_runner"
            return report
    if monster_spawn not in from_exit:
        report.reason = "exit_unreachable_monster"
        return report
    report.connected = True

    # Path distance from the runner *region* = nearest runner spawn to the exit.
    nearest = min(runner_spawns, key=lambda p: from_exit[p])
    report.exit_path_length = from_exit[nearest]
    report.exit_path = reconstruct(prev_exit, exit_cell, nearest)
    if report.exit_path_length < params.min_exit_path:
        report.reason = "exit_too_close"
        return report

    from_runner, _ = bfs(walk, runner_spawns)
    report.monster_runner_path = from_runner.get(monster_spawn, -1)
    report.monster_exit_path = from_exit[monster_spawn]
    if report.monster_runner_path < params.min_monster_runner_path:
        report.reason = "monster_near_runners"
        return report
    if report.monster_exit_path < params.min_monster_exit_path:
        report.reason = "monster_near_exit"
        return report

    if loops < params.min_loops:
        report.reason = "too_few_loops"
        return report

    cuts = find_st_cut_vertices(walk, nearest, exit_cell)
    clusters = cluster_tiles(cuts)
    report.chokepoint_tiles = cuts
    report.chokepoint_count = len(clusters)
    if report.chokepoint_count > params.max_chokepoints:
        report.reason = "too_many_chokepoints"
        return report

    report.open_floor_ratio = open_floor_ratio(tiles)
    if not (params.open_floor_min <= report.open_floor_ratio <= params.open_floor_max):
        report.reason = "open_floor_ratio"
        return report

    report.ok = True
    report.reason = "ok"
    return report


def adjacency_violations(tiles: np.ndarray) -> list[tuple[int, int, int, int, int]]:
    """Return (x, y, nx, ny, dir) for each illegal neighbour pair."""
    from hide_and_seek.world.tiles import compatible

    size = tiles.shape[0]
    bad: list[tuple[int, int, int, int, int]] = []
    for y in range(size):
        for x in range(size):
            a = int(tiles[y, x])
            for d, (dx, dy) in enumerate(DELTA):
                nx, ny = x + dx, y + dy
                if not (0 <= nx < size and 0 <= ny < size):
                    continue
                b = int(tiles[ny, nx])
                if not compatible(a, b, d):
                    bad.append((x, y, nx, ny, d))
    return bad
