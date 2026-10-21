"""All generator parameters in one place — later used as curriculum knobs."""

from __future__ import annotations

from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class GeneratorParams:
    grid_size: int = 32
    tile_size: int = 16

    large_rooms_min: int = 2
    large_rooms_max: int = 3
    large_room_min_size: int = 6
    large_room_max_size: int = 10

    small_rooms_min: int = 5
    small_rooms_max: int = 8
    small_room_min_size: int = 3
    small_room_max_size: int = 5

    corridor_width_min: int = 1
    corridor_width_max: int = 2

    extra_connections_min: int = 3
    extra_connections_max: int = 5

    min_loops: int = 3
    max_chokepoints: int = 1

    open_floor_min: float = 0.35
    open_floor_max: float = 0.55

    exit_distance_frac: float = 0.60
    monster_runner_distance_frac: float = 0.40
    monster_exit_distance_frac: float = 0.20

    lamp_count_min: int = 6
    lamp_count_max: int = 12
    lamp_min_spacing: int = 6
    exit_lamp: bool = True

    prop_density: float = 0.07
    debris_density: float = 0.03

    max_layout_attempts: int = 80
    max_wfc_attempts: int = 8
    max_generate_attempts: int = 250

    @property
    def pixel_size(self) -> int:
        return self.grid_size * self.tile_size

    @property
    def map_diagonal_tiles(self) -> float:
        return self.grid_size * (2.0**0.5)

    @property
    def min_exit_path(self) -> float:
        return self.exit_distance_frac * self.map_diagonal_tiles

    @property
    def min_monster_runner_path(self) -> float:
        return self.monster_runner_distance_frac * self.map_diagonal_tiles

    @property
    def min_monster_exit_path(self) -> float:
        return self.monster_exit_distance_frac * self.map_diagonal_tiles

    def to_dict(self) -> dict[str, Any]:
        return {f.name: getattr(self, f.name) for f in fields(self)}

    @classmethod
    def from_mapping(cls, data: dict[str, Any] | None) -> "GeneratorParams":
        if not data:
            return cls()
        allowed = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in allowed})

    @classmethod
    def from_yaml(cls, path: str | Path) -> "GeneratorParams":
        with open(path, encoding="utf-8") as fh:
            loaded = yaml.safe_load(fh) or {}
        if not isinstance(loaded, dict):
            raise ValueError(f"params file must be a mapping: {path}")
        return cls.from_mapping(loaded)
