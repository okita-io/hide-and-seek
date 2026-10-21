# hide-and-seek

A top-down, greyscale, flashlight hide-and-seek game where every character is a small learned agent that plays from pixels. Four runners with flashlights try to find the exit in a dark, procedurally generated maze, and one shadow crab hunts them by sight and sound.

Built in public.

- Design: [docs/greyscale-flashlight-game.md](docs/greyscale-flashlight-game.md)
- Task breakdown: [docs/tasks.md](docs/tasks.md)
- Sample maps: [docs/gallery/](docs/gallery/)

Status: Task 1 (wave function collapse world generation) is implemented. Later tasks add lighting, sound, simulation and training.

## Setup

Python 3.10+ (3.12 is fine). From the repo root:

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

Dependencies are kept light: `numpy`, `Pillow`, `PyYAML`. Dev extra adds `pytest`. Later tasks will add Gymnasium / PettingZoo and PyTorch.

## Generate maps

```bash
# One map (seed 7) → JSON + 16-grey surface PNG/NPY + colour debug overlay
generate --seed 7 --count 1 --out out/

# Batch: K consecutive seeds, prints mean time and rejection rate
generate --seed 0 --count 100 --out out/maps/

# Curriculum knobs (room counts, corridor width, loops, exit distance, …)
generate --seed 0 --count 16 --out docs/gallery/ --params params.yaml
```

Equivalent module form: `python -m hide_and_seek --seed 7 --count 1 --out out/`. If `generate` is not on your `PATH` after install, use the module form or add the scripts directory (often `~/.local/bin`).

On this machine, 100 consecutive seeds (0–99) each produced a valid map in **24 ms/map** mean, with a 23% internal reject-and-retry rate. That is well under the ~100 ms budget.

Each seed writes:

- `map_<seed>.json` — 32×32 tile ids, per-tile materials, rooms, corridor graph, exit, spawns, lamp sockets, validation report
- `map_<seed>_surface.png` — 512×512 viewable 16-grey *litable surface* (what each pixel looks like if lit; no lighting yet)
- `map_<seed>_surface.npy` — raw 4-bit (stored as uint8, values 0–15) array
- `map_<seed>_debug.png` — colour overlay (rooms, corridor graph, spawns, exit path, lamp sockets, chokepoints)

`params.yaml` holds every generator parameter. Those knobs are the curriculum: early training can ask for fewer, larger rooms, wider corridors, more loops and a shorter exit path.

## Tests

```bash
pytest
```

Coverage: WFC adjacency consistency, spawn/exit connectivity and the other validation invariants, and determinism (same seed → identical map). A batch test generates 100 consecutive seeds.

## Importing from later tasks

```python
from hide_and_seek import generate_map, GeneratorParams

m = generate_map(seed=42)
tiles = m.tiles            # (32, 32) int tile ids
surface = m.surface        # (512, 512) uint8 greys 0–15
materials = m.to_dict()["materials"]
```
