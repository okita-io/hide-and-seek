# Hide-and-Seek: Task Breakdown

Design reference: `docs/greyscale-flashlight-game.md`. Tasks are ordered so each one produces something visible and testable before the next starts.

## Task 1: World generation (WFC maze with exit) — START HERE

**Goal**: generate a 512x512 top-down map with walls, corridors, large and small rooms, cover props and a single exit, and render a flat orthographic view of it. The render is a **descriptor of what can be lit**: the surface grey of every pixel *if* light reached it. No lighting, shadows, sound or agents yet.

### Scope
- Grid: 32x32 tiles, 16x16 px each (512x512 px).
- Two-pass generation (design doc section 2b):
  1. **Coarse layout**: place 2 to 3 large rooms (6x6 to 10x10 tiles) and several small rooms (3x3 to 5x5 tiles), connect with a minimum spanning tree, then add extra connections for loops. Corridors 1 or 2 tiles wide.
  2. **WFC detail pass**: pre-seed room floors, corridor paths, room borders and doorway gaps from the layout, then run wave function collapse (lowest-entropy cell first, weighted random, propagate, backtrack/restart on contradiction) to fill walls, edges, corners, floor texture variants and props.
- Tile set (with edge sockets / adjacency rules): solid wall, wall edges and corners, room floor (2 to 3 texture variants), corridor floor (straight, corner, T, cross, dead end), doorway, props (crate, pillar, table), exit.
- Each tile carries **material properties** for later tasks:
  - `solid` (blocks movement and line of sight), `blocks_light`
  - `sound_damping` in levels (wall = block, closed door/thin wall = 5, crate/furniture = 3, curtain/debris = 1, open = 0)
  - `grey` value(s) 0 to 15: the lit surface value
- **Exit**: one exit tile with a distinct silhouette or pattern, placed at a validated location.
- **Spawn regions** (marked in output, not used yet): a runner spawn area for 4 runners and a monster spawn.
- **Lamp sockets** (positions only, no lighting yet): 6 to 12 candidate lamp positions at junctions, doorways and room centres, spaced 6+ tiles apart.
- **Seeded**: same integer seed gives the identical map.

### Validation (reject and regenerate on failure)
- Flood fill from the exit reaches every runner spawn tile and the monster spawn.
- Exit path distance from the runner spawn is at least ~60% of the map diagonal.
- Monster spawn is far from runners by path distance and not near the exit.
- At least N independent loops (edges - nodes + 1 on the room/corridor graph), N configurable (default 3).
- At most one chokepoint shared by all exit paths.
- Open-floor ratio within a configurable range (default 35 to 55%).

### Render: top-down orthographic "litable surface" view
- 512x512, 16 grey levels (0 to 15), one value per pixel: the surface grey if fully lit.
  - walls: darkest-to-mid wall greys with a lighter top edge
  - floors: a few distinct greys and simple textures per room type; corridors their own grey
  - props: mid greys with clear silhouettes
  - exit: a unique pattern
- Export both the 4-bit grey PNG (scaled to 0-255 for viewing) and the raw 4-bit array.
- Optional debug overlay PNG in colour: room ids, corridor graph, spawns, exit path, lamp sockets, chokepoints.

### Outputs
- `map_<seed>.json`: tiles (32x32 tile ids), per-tile material properties, rooms, corridor graph, exit, spawns, lamp sockets, validation report.
- `map_<seed>_surface.png` and `.npy` (or similar): the 512x512 grey surface render.
- `map_<seed>_debug.png`: colour overlay.
- A CLI: `generate --seed N --count K --out dir/ [--params params.yaml]`.
- A batch mode that generates and validates many seeds (target: well under 100 ms per map) and reports the rejection rate.

### Done when
- 100 consecutive seeds produce valid maps with a sample gallery of 16 surface renders checked by eye.
- The same seed reproduces an identical map.
- Generator parameters (room counts and sizes, corridor width, loop count, prop density, exit distance) are in one config file, ready to act as curriculum knobs later.
- Unit tests cover WFC adjacency consistency (no illegal neighbours), connectivity, and determinism.

### Out of scope for Task 1
Lighting, flashlights, sound, agents, physics, the precomputed visibility and damping tables (Task 3).

## Task 2: Lighting renderer
Point lamps from lamp sockets (radius 2 to 4 tiles, falloff, optional flicker), ambient level, flashlight cones by raycast, hard shadows from `blocks_light` tiles. Output: final 16-grey lit frame = surface grey x light, quantized. Validate darkness coverage (75 to 85% of floor unlit by lamps) and no fully lit spawn-to-exit path; feed failures back into Task 1 validation.

## Task 3: Precomputed visibility and sound tables
Per map: tile-to-tile line of sight (bits) and tile-to-tile damping (levels). Sound ring simulation: loudness 0 to 15, minus 1 per tile, minus material damping, clipped by walls, passing through openings. Rings drawn under characters (sound silhouettes) in the observer view.

## Task 4: Game simulation and controls
Runner and shadow-crab bodies, twin-stick movement (crab: fast sideways, slow forward and turning), flashlight direction and on/off (0.3 s cooldown, click loudness 2), pincer attack (wind-up, short range, cooldown), footstep sounds by speed, exit and catch rules, episode end. Human-playable with keyboard/gamepad.

## Task 5: Observer view
Spectator render: lit world, all sound rings, crab red eyes (observer only), optional agent-view toggle. Replays from seed plus action log.

## Task 6: Agent observations and environment API
Egocentric 128x128 window downsampled to 64x64, grey + sound channels, 4-frame stack, small vector inputs. Multi-agent API (PettingZoo-style), fast headless mode, many parallel environments. Leak audit.

## Task 7: Models and training
Small ViT (or CNN baseline) + GRU + typed heads. PPO/MAPPO for 4 shared-weight runners, separate crab network, centralized critic, opponent pools, balance controller, curriculum via generator knobs, held-out evaluation seeds.

## Task 8: Export and web embed
Quantize (int8, then try int4), verify behaviour on held-out seeds, ONNX Runtime Web build, 480x480 spectator embed for an X player card.
