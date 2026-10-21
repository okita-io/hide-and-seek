"""Tile set, material properties, and WFC adjacency (edge sockets)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np

# Sound: walls block completely. Other values match design-doc section 3a.
SOUND_BLOCK = -1

N, E, S, W = 0, 1, 2, 3
OPP = (2, 3, 0, 1)
DELTA = ((0, -1), (1, 0), (0, 1), (-1, 0))  # (dx, dy) for N,E,S,W

# Socket letters: equal sockets may touch.
#   W = wall, F = floor / opening
SOCK_W = "W"
SOCK_F = "F"


@dataclass(frozen=True)
class Material:
    solid: bool
    blocks_light: bool
    sound_damping: int
    grey: int

    def to_dict(self) -> dict:
        return {
            "solid": self.solid,
            "blocks_light": self.blocks_light,
            "sound_damping": self.sound_damping,
            "grey": self.grey,
        }


WALL_MAT = Material(True, True, SOUND_BLOCK, 3)
FLOOR_A_MAT = Material(False, False, 0, 8)
FLOOR_B_MAT = Material(False, False, 0, 9)
FLOOR_C_MAT = Material(False, False, 0, 10)
CORRIDOR_MAT = Material(False, False, 0, 7)
DOOR_MAT = Material(False, False, 0, 7)
CRATE_MAT = Material(True, True, 3, 12)
PILLAR_MAT = Material(True, True, 3, 11)
TABLE_MAT = Material(True, True, 3, 12)
DEBRIS_MAT = Material(False, False, 1, 6)
EXIT_MAT = Material(False, False, 0, 15)


@dataclass(frozen=True)
class TileDef:
    name: str
    sockets: tuple[str, str, str, str]
    material: Material
    category: str
    weight: float = 1.0


def _wall_name(mask: int) -> str:
    names = {
        0: "SOLID_WALL",
        1: "WALL_EDGE_N",
        2: "WALL_EDGE_E",
        3: "WALL_CORNER_NE_OUTER",
        4: "WALL_EDGE_S",
        5: "WALL_THIN_NS",
        6: "WALL_CORNER_SE_OUTER",
        7: "WALL_T_W",  # floors N,E,S — inner / T
        8: "WALL_EDGE_W",
        9: "WALL_CORNER_NW_OUTER",
        10: "WALL_THIN_EW",
        11: "WALL_T_S",
        12: "WALL_CORNER_SW_OUTER",
        13: "WALL_T_E",
        14: "WALL_T_N",
        15: "WALL_ISLAND",
    }
    return names[mask]


def _wall_sockets(floor_mask: int) -> tuple[str, str, str, str]:
    # floor_mask bits: 1=N, 2=E, 4=S, 8=W
    socks = [SOCK_W, SOCK_W, SOCK_W, SOCK_W]
    if floor_mask & 1:
        socks[N] = SOCK_F
    if floor_mask & 2:
        socks[E] = SOCK_F
    if floor_mask & 4:
        socks[S] = SOCK_F
    if floor_mask & 8:
        socks[W] = SOCK_F
    return (socks[0], socks[1], socks[2], socks[3])


def _build_tile_list() -> list[TileDef]:
    tiles: list[TileDef] = []
    for mask in range(16):
        tiles.append(
            TileDef(_wall_name(mask), _wall_sockets(mask), WALL_MAT, "wall", 1.0)
        )

    floor_all = (SOCK_F, SOCK_F, SOCK_F, SOCK_F)
    tiles.extend(
        [
            TileDef("ROOM_FLOOR_A", floor_all, FLOOR_A_MAT, "room_floor", 12.0),
            TileDef("ROOM_FLOOR_B", floor_all, FLOOR_B_MAT, "room_floor", 12.0),
            TileDef("ROOM_FLOOR_C", floor_all, FLOOR_C_MAT, "room_floor", 12.0),
            TileDef("CORRIDOR_NS", floor_all, CORRIDOR_MAT, "corridor", 1.0),
            TileDef("CORRIDOR_EW", floor_all, CORRIDOR_MAT, "corridor", 1.0),
            TileDef("CORRIDOR_NE", floor_all, CORRIDOR_MAT, "corridor", 1.0),
            TileDef("CORRIDOR_SE", floor_all, CORRIDOR_MAT, "corridor", 1.0),
            TileDef("CORRIDOR_SW", floor_all, CORRIDOR_MAT, "corridor", 1.0),
            TileDef("CORRIDOR_NW", floor_all, CORRIDOR_MAT, "corridor", 1.0),
            TileDef("CORRIDOR_T_N", floor_all, CORRIDOR_MAT, "corridor", 1.0),
            TileDef("CORRIDOR_T_E", floor_all, CORRIDOR_MAT, "corridor", 1.0),
            TileDef("CORRIDOR_T_S", floor_all, CORRIDOR_MAT, "corridor", 1.0),
            TileDef("CORRIDOR_T_W", floor_all, CORRIDOR_MAT, "corridor", 1.0),
            TileDef("CORRIDOR_CROSS", floor_all, CORRIDOR_MAT, "corridor", 1.0),
            TileDef("CORRIDOR_DEAD_N", floor_all, CORRIDOR_MAT, "corridor", 1.0),
            TileDef("CORRIDOR_DEAD_E", floor_all, CORRIDOR_MAT, "corridor", 1.0),
            TileDef("CORRIDOR_DEAD_S", floor_all, CORRIDOR_MAT, "corridor", 1.0),
            TileDef("CORRIDOR_DEAD_W", floor_all, CORRIDOR_MAT, "corridor", 1.0),
            TileDef("DOORWAY_NS", floor_all, DOOR_MAT, "door", 1.0),
            TileDef("DOORWAY_EW", floor_all, DOOR_MAT, "door", 1.0),
            TileDef("PROP_CRATE", floor_all, CRATE_MAT, "prop", 1.0),
            TileDef("PROP_PILLAR", floor_all, PILLAR_MAT, "prop", 1.0),
            TileDef("PROP_TABLE", floor_all, TABLE_MAT, "prop", 1.0),
            TileDef("PROP_DEBRIS", floor_all, DEBRIS_MAT, "debris", 1.0),
            TileDef("EXIT", floor_all, EXIT_MAT, "exit", 1.0),
        ]
    )
    return tiles


TILES: list[TileDef] = _build_tile_list()
assert len(TILES) <= 64
N_TILES = len(TILES)
NAME_TO_ID = {t.name: i for i, t in enumerate(TILES)}

# Floor-neighbor bit masks for the 16 wall tiles (id == mask).
WALL_MASK_COUNT = 16


def tile_id(name: str) -> int:
    return NAME_TO_ID[name]


def _bit(i: int) -> int:
    return 1 << i


def _mask_for(names: Iterable[str]) -> int:
    m = 0
    for name in names:
        m |= _bit(NAME_TO_ID[name])
    return m


WALL_MASK = (1 << WALL_MASK_COUNT) - 1
ROOM_FLOOR_MASK = _mask_for(["ROOM_FLOOR_A", "ROOM_FLOOR_B", "ROOM_FLOOR_C"])
CORRIDOR_MASK = _mask_for(
    [
        "CORRIDOR_NS",
        "CORRIDOR_EW",
        "CORRIDOR_NE",
        "CORRIDOR_SE",
        "CORRIDOR_SW",
        "CORRIDOR_NW",
        "CORRIDOR_T_N",
        "CORRIDOR_T_E",
        "CORRIDOR_T_S",
        "CORRIDOR_T_W",
        "CORRIDOR_CROSS",
        "CORRIDOR_DEAD_N",
        "CORRIDOR_DEAD_E",
        "CORRIDOR_DEAD_S",
        "CORRIDOR_DEAD_W",
    ]
)
DOOR_MASK = _mask_for(["DOORWAY_NS", "DOORWAY_EW"])
PROP_MASK = _mask_for(["PROP_CRATE", "PROP_PILLAR", "PROP_TABLE"])
DEBRIS_MASK = _mask_for(["PROP_DEBRIS"])
EXIT_MASK = _mask_for(["EXIT"])
WALKABLE_MASK = (
    ROOM_FLOOR_MASK | CORRIDOR_MASK | DOOR_MASK | DEBRIS_MASK | EXIT_MASK
)

FLOOR_VARIANT_IDS = (
    NAME_TO_ID["ROOM_FLOOR_A"],
    NAME_TO_ID["ROOM_FLOOR_B"],
    NAME_TO_ID["ROOM_FLOOR_C"],
)

CORRIDOR_BY_OPEN_MASK = {
    1: NAME_TO_ID["CORRIDOR_DEAD_N"],
    2: NAME_TO_ID["CORRIDOR_DEAD_E"],
    4: NAME_TO_ID["CORRIDOR_DEAD_S"],
    8: NAME_TO_ID["CORRIDOR_DEAD_W"],
    5: NAME_TO_ID["CORRIDOR_NS"],
    10: NAME_TO_ID["CORRIDOR_EW"],
    3: NAME_TO_ID["CORRIDOR_NE"],
    6: NAME_TO_ID["CORRIDOR_SE"],
    12: NAME_TO_ID["CORRIDOR_SW"],
    9: NAME_TO_ID["CORRIDOR_NW"],
    11: NAME_TO_ID["CORRIDOR_T_N"],  # N,E,W
    7: NAME_TO_ID["CORRIDOR_T_E"],  # N,E,S
    14: NAME_TO_ID["CORRIDOR_T_S"],  # E,S,W
    13: NAME_TO_ID["CORRIDOR_T_W"],  # N,S,W
    15: NAME_TO_ID["CORRIDOR_CROSS"],
    0: NAME_TO_ID["CORRIDOR_CROSS"],
}

WEIGHTS = np.array([t.weight for t in TILES], dtype=np.float64)


def _build_compat() -> np.ndarray:
    """compat[dir, tile] = bitmask of tiles allowed in that direction."""
    compat = np.zeros((4, N_TILES), dtype=np.uint64)
    for a, ta in enumerate(TILES):
        for b, tb in enumerate(TILES):
            for d in range(4):
                if ta.sockets[d] == tb.sockets[OPP[d]]:
                    compat[d, a] |= np.uint64(_bit(b))
    return compat


COMPAT = _build_compat()


def bits_of(mask: int) -> list[int]:
    out: list[int] = []
    while mask:
        bit = mask & -mask
        out.append(bit.bit_length() - 1)
        mask ^= bit
    return out


def compatible(tile_a: int, tile_b: int, direction: int) -> bool:
    """True if tile_b may sit in `direction` of tile_a."""
    return bool(int(COMPAT[direction, tile_a]) & _bit(tile_b))


def wall_id_for_floor_mask(floor_mask: int) -> int:
    """Wall tile id equals the 4-bit orthogonal floor-neighbor mask."""
    return int(floor_mask) & 15


def corridor_id_for_open_mask(open_mask: int) -> int:
    return CORRIDOR_BY_OPEN_MASK.get(open_mask & 15, NAME_TO_ID["CORRIDOR_CROSS"])


def doorway_id_for_open_mask(open_mask: int) -> int:
    ns = bool(open_mask & 1) or bool(open_mask & 4)
    ew = bool(open_mask & 2) or bool(open_mask & 8)
    if ew and not ns:
        return NAME_TO_ID["DOORWAY_EW"]
    return NAME_TO_ID["DOORWAY_NS"]


def is_solid(tile: int) -> bool:
    return TILES[tile].material.solid


def legend() -> dict[str, dict]:
    return {
        str(i): {
            "name": t.name,
            "category": t.category,
            **t.material.to_dict(),
            "sockets": list(t.sockets),
        }
        for i, t in enumerate(TILES)
    }
