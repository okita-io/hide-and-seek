"""Connectivity and the other reject-and-regenerate checks."""

from hide_and_seek.world.config import GeneratorParams
from hide_and_seek.world.generator import generate_map
from hide_and_seek.world.tiles import TILES, is_solid
from hide_and_seek.world.validate import bfs, walkable_mask


def test_exit_reaches_all_spawns():
    params = GeneratorParams()
    for seed in range(20):
        game_map = generate_map(seed, params)
        walk = walkable_mask(game_map.tiles)
        dist, _ = bfs(walk, game_map.exit)
        for p in game_map.runner_spawns:
            assert p in dist, f"seed={seed} runner {p} not reachable from exit"
        assert game_map.monster_spawn in dist, f"seed={seed} monster not reachable"
        assert game_map.validation.connected
        assert game_map.validation.ok


def test_validation_invariants_hold():
    params = GeneratorParams()
    for seed in range(16):
        m = generate_map(seed, params)
        v = m.validation
        assert v.exit_path_length >= params.min_exit_path
        assert v.monster_runner_path >= params.min_monster_runner_path
        assert v.monster_exit_path >= params.min_monster_exit_path
        assert v.loops >= params.min_loops
        assert v.chokepoint_count <= params.max_chokepoints
        assert params.open_floor_min <= v.open_floor_ratio <= params.open_floor_max
        assert 6 <= len(m.lamp_sockets) <= 12
        assert len(m.runner_spawns) == 4
        assert TILES[int(m.tiles[m.exit[1], m.exit[0]])].name == "EXIT"
        assert not is_solid(int(m.tiles[m.monster_spawn[1], m.monster_spawn[0]]))
        for p in m.runner_spawns:
            assert not is_solid(int(m.tiles[p[1], p[0]]))


def test_one_exit_and_in_bounds():
    m = generate_map(7, GeneratorParams())
    exits = [
        (x, y)
        for y in range(m.tiles.shape[0])
        for x in range(m.tiles.shape[1])
        if TILES[int(m.tiles[y, x])].name == "EXIT"
    ]
    assert exits == [m.exit]
    size = m.params.grid_size
    for x, y in [m.exit, m.monster_spawn, *m.runner_spawns, *m.lamp_sockets]:
        assert 0 <= x < size and 0 <= y < size
