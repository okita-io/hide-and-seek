"""Write map JSON, 4-bit surface array, viewable PNG, and debug overlay."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from hide_and_seek.world.generator import GameMap
from hide_and_seek.world.render import render_debug, render_surface, surface_to_preview


def write_map(game_map: GameMap, out_dir: str | Path, prefix: str | None = None) -> dict[str, Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    prefix = prefix or f"map_{game_map.seed}"
    paths = {
        "json": out / f"{prefix}.json",
        "surface_png": out / f"{prefix}_surface.png",
        "surface_npy": out / f"{prefix}_surface.npy",
        "debug_png": out / f"{prefix}_debug.png",
    }

    with paths["json"].open("w", encoding="utf-8") as fh:
        json.dump(game_map.to_dict(), fh, indent=2)

    surface = render_surface(game_map.tiles, game_map.params.tile_size)
    np.save(paths["surface_npy"], surface)
    surface_to_preview(surface).save(paths["surface_png"])

    debug = render_debug(
        game_map.tiles,
        game_map.rooms,
        game_map.corridor_graph,
        game_map.runner_spawns,
        game_map.monster_spawn,
        game_map.exit,
        game_map.validation.exit_path,
        game_map.lamp_sockets,
        game_map.validation.chokepoint_tiles,
        game_map.params.tile_size,
    )
    debug.save(paths["debug_png"])
    return paths
