"""Same integer seed must reproduce an identical map."""

import numpy as np

from hide_and_seek.world.config import GeneratorParams
from hide_and_seek.world.generator import generate_map
from hide_and_seek.world.render import render_surface


def _snapshot(game_map):
    return {
        "tiles": game_map.tiles.copy(),
        "exit": game_map.exit,
        "runners": list(game_map.runner_spawns),
        "monster": game_map.monster_spawn,
        "lamps": list(game_map.lamp_sockets),
        "rooms": [(r.id, r.x, r.y, r.w, r.h, r.kind, r.floor_variant) for r in game_map.rooms],
        "surface": render_surface(game_map.tiles, game_map.params.tile_size),
    }


def test_same_seed_identical_map():
    params = GeneratorParams()
    for seed in (0, 1, 11, 42, 99):
        a = _snapshot(generate_map(seed, params))
        b = _snapshot(generate_map(seed, params))
        assert np.array_equal(a["tiles"], b["tiles"]), f"seed={seed} tiles differ"
        assert a["exit"] == b["exit"]
        assert a["runners"] == b["runners"]
        assert a["monster"] == b["monster"]
        assert a["lamps"] == b["lamps"]
        assert a["rooms"] == b["rooms"]
        assert np.array_equal(a["surface"], b["surface"]), f"seed={seed} surface differs"


def test_different_seeds_usually_differ():
    params = GeneratorParams()
    a = generate_map(0, params).tiles
    b = generate_map(1, params).tiles
    assert not np.array_equal(a, b)
