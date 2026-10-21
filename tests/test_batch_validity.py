"""100 consecutive seeds must each produce a valid map."""

import time

from hide_and_seek.world.config import GeneratorParams
from hide_and_seek.world.generator import generate_map


def test_one_hundred_consecutive_seeds():
    params = GeneratorParams()
    times = []
    for seed in range(100):
        t0 = time.perf_counter()
        game_map = generate_map(seed, params)
        times.append(time.perf_counter() - t0)
        assert game_map.validation.ok, f"seed={seed} {game_map.validation.reason}"
    mean_ms = sum(times) / len(times) * 1000.0
    # Well under the 100 ms/map budget; keep a generous CI bound.
    assert mean_ms < 80.0, f"mean {mean_ms:.1f} ms/map is too slow"
    print(f"\n100 seeds: mean {mean_ms:.2f} ms/map  max {max(times)*1000:.1f} ms")
