"""WFC adjacency consistency: no illegal neighbour pairs after collapse."""

from hide_and_seek.world.config import GeneratorParams
from hide_and_seek.world.generator import generate_map
from hide_and_seek.world.tiles import COMPAT, N_TILES, OPP, TILES, compatible
from hide_and_seek.world.validate import adjacency_violations


def test_compat_table_is_symmetric():
    for a in range(N_TILES):
        for b in range(N_TILES):
            for d in range(4):
                ab = compatible(a, b, d)
                ba = compatible(b, a, OPP[d])
                assert ab == ba, f"{TILES[a].name} dir={d} vs {TILES[b].name}"


def test_compat_matches_sockets():
    for a, ta in enumerate(TILES):
        for b, tb in enumerate(TILES):
            for d in range(4):
                expect = ta.sockets[d] == tb.sockets[OPP[d]]
                assert bool(int(COMPAT[d, a]) & (1 << b)) == expect


def test_generated_maps_have_no_illegal_neighbours():
    params = GeneratorParams()
    for seed in range(20):
        game_map = generate_map(seed, params)
        bad = adjacency_violations(game_map.tiles)
        assert bad == [], f"seed={seed} illegal pairs={bad[:8]}"
