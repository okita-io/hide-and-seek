"""CLI: generate --seed N --count K --out dir/ [--params params.yaml]."""

from __future__ import annotations

import argparse
import sys
import time
from collections import Counter
from pathlib import Path

from hide_and_seek.world.config import GeneratorParams
from hide_and_seek.world.export import write_map
from hide_and_seek.world.generator import GenerationError, generate_map


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="generate",
        description="Generate seeded 512x512 hide-and-seek maps (Task 1 world generation).",
    )
    p.add_argument("--seed", type=int, default=0, help="First integer seed (inclusive).")
    p.add_argument("--count", type=int, default=1, help="How many consecutive seeds to generate.")
    p.add_argument("--out", type=Path, default=Path("out"), help="Output directory.")
    p.add_argument(
        "--params",
        type=Path,
        default=None,
        help="YAML file of generator parameters (curriculum knobs).",
    )
    p.add_argument(
        "--no-write",
        action="store_true",
        help="Validate only; do not write JSON/PNG/NPY.",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.count < 1:
        print("error: --count must be >= 1", file=sys.stderr)
        return 2

    params = GeneratorParams.from_yaml(args.params) if args.params else GeneratorParams()
    reasons: Counter[str] = Counter()
    times: list[float] = []
    ok = 0
    failed_seeds: list[int] = []

    for i in range(args.count):
        seed = args.seed + i
        t0 = time.perf_counter()
        try:
            game_map = generate_map(seed, params)
        except GenerationError as exc:
            times.append(time.perf_counter() - t0)
            failed_seeds.append(seed)
            print(f"FAIL seed={seed}: {exc}", file=sys.stderr)
            continue
        dt = time.perf_counter() - t0
        times.append(dt)
        ok += 1
        reasons.update(game_map.rejection_reasons)
        if not args.no_write:
            write_map(game_map, args.out)
        extra = f" retries={game_map.attempts - 1}" if game_map.attempts > 1 else ""
        print(
            f"ok seed={seed}  {dt * 1000:.1f} ms  "
            f"open={game_map.validation.open_floor_ratio:.2f}  "
            f"exit_path={game_map.validation.exit_path_length}  "
            f"loops={game_map.validation.loops}  "
            f"lamps={len(game_map.lamp_sockets)}{extra}"
        )

    total_attempts = ok + sum(reasons.values())
    rejected = sum(reasons.values())
    mean_ms = (sum(times) / len(times) * 1000.0) if times else 0.0
    reject_rate = (rejected / total_attempts) if total_attempts else 0.0
    print()
    print(f"generated {ok}/{args.count} maps from seeds {args.seed}..{args.seed + args.count - 1}")
    print(f"mean time: {mean_ms:.2f} ms/map")
    print(f"internal rejection rate: {reject_rate:.1%}  ({rejected} rejected / {total_attempts} attempts)")
    if reasons:
        top = ", ".join(f"{k}={v}" for k, v in reasons.most_common(8))
        print(f"rejection reasons: {top}")
    if failed_seeds:
        print(f"unrecoverable seeds: {failed_seeds}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
