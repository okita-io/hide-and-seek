# Greyscale Flashlight Hide-and-Seek: Design and Agent Training Concepts

Status: concept draft (2026-10-20). Nothing here is built yet.

## 1. The pitch

A top-down 2D hide-and-seek / horror game in a dark world. Several **runners** carry flashlights and try to complete objectives and escape. One **monster** hunts them. Every character is a learned agent that plays from **pixels**, seeing only what its character could see, so darkness, shadows, smoke and camouflage really fool it the way they fool a human player.

The core idea is that the flashlight is a self-controlled cone of vision. Where an agent points it shows where it is paying attention, and players can read that intent.

## 2. World and rendering

- **Top-down 2D**, tile or polygon walls, doors, crates, open rooms and corridors.
- **16 levels of grey (4 bits per pixel)** for everything the agents see.
  - Brightness is the main signal. Dark areas are low values, lit areas are high values.
  - Reserve ordered ramps: floor greys, wall greys, a smoke ramp (thinning over several steps) and a light falloff ramp.
  - Camo means matching the floor's grey closely but not exactly. Tune the gap so camo is strong but not perfect.
  - Identify things by **silhouette, size, texture and motion** rather than colour: the monster is big and jagged, runners are round, walls are blocky.
- **Lighting**
  - The base map is dark, with low ambient light.
  - Each flashlight is a cone, lit by raycasting so walls cast hard shadows.
  - Light falls off with distance, and smoke attenuates light passing through it.
  - **Environment point lights**: small fixed lamps placed sparsely by the map generator (section 2b), leaving most of the map dark. Each lights a small pool (radius about 2 to 4 tiles) with falloff and casts hard shadows from walls and props, raycast like the flashlights.
    - Since the crab carries no light, these pools are where runners can spot it without using their flashlight, and where the crab is exposed.
    - Optional flicker (random dimming) makes pools unreliable and adds tension.
- Keep a **separate colour debug render** for humans, showing the true scene next to each agent's view.

## 2a. v1 setup (decided 2026-10-20)

- **Map**: 512x512 world pixels, procedurally generated every episode (section 2b).
- **One exit**: a single exit somewhere on the map. Runners don't know where it is at the start, so finding it is part of the game. Randomize its location across episodes so agents learn to search instead of memorizing.
- **One monster**, separate network.
- **Four runners**, sharing one network.
- **Win conditions**: a runner escapes by reaching the exit; the monster scores by catching runners. The episode ends when every runner has escaped or been caught, or at a time limit.
- **Observation scale**: each agent sees a 128x128 world-pixel window around itself, downsampled 2x to a 64x64 observation. That's a view radius of 64 world pixels, about 1/8 of the map width, so the map feels big and dark, and memory and search matter. Tune the window if it's too hard.
- **Not in v1 yet**: generators/keys that unlock the exit, pings and other signals, smoke. Add them in later curriculum stages (section 8).

## 2b. Procedural map generation (wave function collapse)

Every episode gets a new map, so agents learn general skills (search, use cover, find the exit) instead of memorizing layouts.

### Grid and tiles
- The 512x512 map is a **32x32 grid of 16x16-pixel tiles**. Corridors can be 1 or 2 tiles wide; door gaps are 1 tile.
- **Tile set** (each with edge "sockets" that say what can sit next to it):
  - solid wall, wall edges and corners (inner and outer)
  - room floor (several grey textures so rooms look different)
  - corridor floor (straight, corner, T, cross, dead end)
  - doorway (a room-to-corridor connector)
  - props for cover: crate, pillar, table (block movement and light)
  - optional: dark patch tiles (unlit-floor variants) and debris
- **Adjacency rules** come from the sockets: floor only meets floor or doorways, a wall edge must face floor on one side and wall on the other, and so on. Rules can be hand-written or learned from a few hand-drawn example maps (overlapping WFC).

### How WFC builds the map
1. Every cell starts with all tiles possible.
2. Pick the cell with the fewest options left (lowest entropy), and collapse it to one tile, chosen by weighted random. Weights control the look: more floor means more open maps, more props means more cover.
3. Propagate: remove now-impossible tiles from neighbours, and repeat until every cell is decided.
4. On a contradiction (a cell with no options), backtrack a few steps or restart with a new seed.

### Hybrid layout: coarse plan first, WFC for detail
Plain WFC is great at local detail but weak at big structure like "a few large rooms connected by corridors". So generate in two passes:
1. **Coarse layout**: place rooms of mixed size (for example 2 to 3 large halls of 6x6 to 10x10 tiles, plus several small rooms of 3x3 to 5x5 tiles) using random placement or BSP (binary space partitioning, recursively splitting the map). Connect them with a minimum spanning tree, then **add a few extra connections so the map has loops**. Loops matter: with pure tree mazes runners get trapped in dead ends and the monster wins trivially.
2. **Pre-seed WFC** with that plan: fix room interiors to floor tiles, corridor paths to corridor tiles, and the room borders to wall tiles with doorway gaps. WFC then fills in walls, corners, textures and cover props consistently.

### Validation (reject and regenerate if any check fails)
- **Connectivity**: flood fill from the exit reaches every runner spawn and the monster spawn.
- **Exit distance**: the exit is at least about 60% of the map's diagonal from the runner spawn area, measured by path length, not straight-line distance.
- **Monster spawn**: far from runners (both path distance and out of initial view), but not right on the exit.
- **Loops**: at least N independent cycles (count with graph edges minus nodes plus one) so there are always escape routes.
- **Balance**: no single chokepoint on every exit path, or at most one.
- **Open-floor ratio** within a target range, so the map is neither all corridors nor all one big room.
- **Darkness coverage**: at least about 75 to 85% of floor tiles stay unlit by environment lamps.
- **No safe-route lighting**: there is no fully lit path from the runner spawn to the exit.

### Point light placement
- Place a small number of lamps per map (for example 6 to 12 on the 32x32 grid), with a minimum spacing (for example 6+ tiles apart) so pools never merge into lit areas.
- Prefer meaningful spots: corridor junctions, room centres, doorways, so pools sit on routes and become decision points.
- Randomize count, radius, brightness and flicker per map.
- Possibly one dim lamp near the exit as a faint beacon, or none; make it a generator option.
- Light map is precomputed per map (static lamps don't move), so rendering stays cheap; only flashlights are raycast per frame.

### Spawns and the exit
- Runners spawn together or in pairs in one region, the monster in a distant region, and the exit at a validated distance.
- The exit is a distinct tile (unique silhouette or grey pattern) that is only visible when lit or within ambient range.

### Training considerations
- **Seeds**: every map comes from an integer seed, so any interesting episode can be replayed exactly.
- **Speed**: WFC on a 32x32 grid is fast, but to keep the simulator from waiting, pre-generate a large pool of validated maps (for example 10k to 100k seeds) and keep a background worker adding more. Hold out a separate set of seeds for evaluation, to check agents generalize to unseen maps.
- **Curriculum knobs**: generator parameters double as difficulty settings:
  - early: few, large rooms, wide corridors, many loops, short exit distance, more and brighter lamps
  - later: more small rooms, narrow corridors, fewer loops, more cover and dead ends, longer exit distance, fewer, dimmer and flickering lamps
- **Variety vs learnability**: if training stalls, narrow the generator's range for a while, then widen it again.

### Rendering in 16 greys
- Walls are darkest-to-mid wall greys with a lit edge, floors use a few distinct floor greys and textures per room type, and props cast hard shadows under flashlight light.
- Darkness is still the dominant feature: tile greys are what you see when lit, and ambient light leaves most of the map near black.

## 3. What an agent sees (observation)

- An **egocentric crop**, about 64x64 pixels, centered on the agent and optionally rotated so its facing direction is "up". It is rendered from that agent's point of view: only lit or ambient-visible pixels show, and occluded areas are dark.
- A **frame stack** of the last 3 or 4 frames so it can perceive motion.
- **Sound channel**: expanding noise rings (section 3a), drawn in their own input channel so darkness never hides them; only walls do.
- **Small vector inputs**: own health or stamina, battery level, objective direction (runners), cooldowns.
- **No leaks.** Never pass true positions, enemy counts or a full-map minimap. A learned agent will find and exploit any input that carries hidden truth.

## 3a. Sound as expanding rings

Noise is visual: every noisy event spawns a ring that expands from its source and fades.

### Making noise: a 4-bit loudness scale
Sound uses the same 0 to 15 range as the 16 greys, so the sound channel is also 4 bits per pixel.

- A sound starts at its source with a **loudness level** (its "brightness").
- The ring expands **one tile per step** (one sim tick per tile is a good start), and its brightness **drops by 1 per tile** travelled.
- When brightness reaches 0 the ring is gone. So **loudness = reach in tiles**: a level-12 sound travels 12 tiles, a level-8 sound travels 8.

| Source | Starting loudness | Reach |
|---|---|---|
| Crab pincer snap | 14 | 14 tiles |
| Runner running (per step) | 12 | 12 tiles |
| Door breaking | 12 | 12 tiles |
| Crab scuttle | 6 to 8 (tuning knob) | 6 to 8 tiles |
| Runner walking (per step) | 8 at full walk, down to about 4 when creeping | 4 to 8 tiles |
| Door opening | 6 | 6 tiles |
| Flashlight click | 2 | 2 tiles |
| Standing still | none | |

- Movement loudness can scale with stick deflection, so creeping is quieter than walking, which is quieter than running.
- Overlapping rings: each pixel in the sound channel keeps the maximum brightness of any ring passing through it.

### How the ring travels (propagation)
- A ring is a **wavefront** expanding from the source, not a single point. Each part of the ring only exists where the sound can actually reach.
- **Solid walls stop the wavefront.** Behind a wall, that part of the ring is missing (a sound shadow).
- **Openings let it through.** Where the ring meets an open doorway or gap, the part of it passing through the opening keeps expanding on the other side as an arc (a wedge fanning out from the doorway).
- **Dampening materials** weaken or shorten it instead of stopping it. When the wavefront passes through one, that part of the ring loses extra brightness levels, which also shortens its remaining reach.

| Material | Effect on sound passing through |
|---|---|
| Solid wall | blocks completely |
| Open doorway / gap | no effect |
| Closed door, thin wall | minus 5 levels |
| Crate, furniture, pillar | minus 3 levels |
| Curtain, debris pile | minus 1 level |

Damping subtracts levels on top of the normal 1 per tile, so a level-12 run step that passes a closed door 2 tiles out continues at 12 - 2 - 5 = 5 and dies 5 tiles later.

(Values are starting guesses for tuning.)

### Who hears it
- **Human observer**: sees every ring, including the clipped and dampened shapes, in the spectator or debug view.
- **Agents**: an agent hears a sound when it has **mechanical line of sight to any part of the ring wavefront**, not to the source. Darkness never blocks this; only walls (and solid props) block the agent's line of sight to the ring.
  - Example: a runner steps next to an open doorway in the next room. The crab can't see the runner's position through the wall, but it sees the arc of the ring sweep past the doorway, so it knows roughly where the noise came from.
  - Seeing only an arc gives direction and rough distance (from its brightness, its curvature and how far it has expanded), not an exact position. Brightness also hints at what made it: a bright arc far from its source means something loud. Good listeners learn to triangulate from several steps.
- Rings from just outside an agent's 128x128 view still show up as arcs entering the view edge.

### Implementation notes
- Work at **tile resolution** (32x32 grid) for sound, then draw rings at pixel resolution for display and observation.
- For each map, precompute:
  - **tile-to-tile visibility** (1,024 tiles, about a million pairs, stored as bits, roughly 128 KB per map), used both for "which ring parts exist" (from the source) and "which ring parts an agent can see" (from the agent)
  - **tile-to-tile damping**: the total levels subtracted by materials along the straight line between tiles
- At runtime, a ring at radius r covers the tiles at distance r from the source that are reachable from it, each with brightness = loudness - r - damping (dropped if 0 or less). An agent's sound channel draws the ring tiles that are also visible from the agent. This is all table lookups, so it's cheap for many parallel games.
- Simpler first version: straight-line propagation only (sound doesn't bend around corners except through openings). Later option: geodesic propagation, a flood fill through open space, so sound also curls around corners and down corridors, which is more realistic but costlier.

### Draw order: rings under characters (sound silhouettes)
- Sound rings are drawn on a **layer beneath the characters**. Each body is drawn on top as a dark shape, so as a ring radiates out from a footstep, the character standing at its centre shows up as a **silhouette cut out of the bright ring**. Each step briefly outlines the crab's claws or a runner's round body, even in total darkness.
- Anyone a ring passes over also shows up as a silhouette against it, for that moment.
- Bodies only hide the ring visually; they do **not** block or damp the sound itself (propagation rules above are unchanged).

**Observer view (v1):** always on. It's a striking look for the spectator and the X embed: footsteps pulse out of the dark, and bodies flicker into view as outlines.

**Agent view (optional mechanic, off in v1):** if the same layering is applied to an agent's sound channel, sound becomes a kind of echolocation.
- A ring that sweeps across a silent, dark crab reveals its outline to any agent who can see that part of the ring. One runner's careless sprint could expose the crab lurking near another runner.
- That's a big gameplay change (standing still in the dark no longer guarantees hiding), so treat it as a later experiment and compare win rates with it on and off.
- Implementation: when rendering an agent's sound channel, zero out (or set to a fixed low value) the ring pixels covered by any character body.

### Why a separate channel
- The visual channel is 16 greys of light; mixing rings into it would let rings light up darkness.
- The sound channel is the same 64x64 grid with ring brightness 0 to 15 (4 bits, like the greys), stacked with the visual frames. The model learns to combine them: "I can't see it, but something big is scuttling behind that crate."

### Expected behaviour
- Runners walk when the crab may be close and only sprint when they're sure it's far or when they're already spotted.
- The crab freezes to listen, then closes in on rings, and approaches around walls to stay unheard.
- Runners use walls to break both sight and sound, and the crab learns to listen at doorways.
- Optional later: decoy noise (throwing an object) creates rings away from the runner.

### Later options
- Geodesic propagation, so sound curls around corners and along corridors.
- Surface types: some floor tiles (debris, metal) make bigger rings.

## 4. What an agent does (actions): twin-stick controls

Both agents (and human players) use the same two-stick layout, so humans can later take over any character.

| | Left stick | Right stick | Buttons |
|---|---|---|---|
| **Runner** | flashlight direction | movement | **flashlight on/off (v1)**; later: cone width (narrow-long vs wide-short), sprint, interact, decoy, ping |
| **Monster (shadow crab)** | pincer attack direction | movement | roar / special ability |

Note: this is the reverse of the usual twin-stick convention (left = move, right = aim). Keep the mapping configurable for human players; for agents it makes no difference.

### Runner
- **Left stick = flashlight.** The stick angle sets where the cone points; a neutral stick keeps the last direction. The light is independent of movement, so a runner can flee one way and glance back the other.
- **Right stick = movement.** Angle sets direction, deflection sets speed (walk to run). Running is louder (sound channel) and maybe drains stamina.
- **Flashlight switch (on/off), in v1.** This is the core stealth move: switch off and hide in the shadows while the crab passes.
  - **Off**: the runner sees only ambient light, environment lamp pools and other runners' beams, plus sound rings. It is invisible to the crab unless it stands in a lamp pool or is caught in another runner's beam.
  - **On**: the runner can see, but its beam (and the runner itself) is visible from far away, and the crab is drawn to it.
  - **The click makes noise** (loudness 2, so audible only very close), so switching right next to the crab is risky.
  - **Darkness doesn't hide footsteps.** To truly hide, a runner has to switch off *and* stand still or creep, since walking still makes level 4 to 8 rings.
  - A short toggle cooldown (for example 0.3 s) stops agents from strobing the light as an exploit.
  - Encoded as its own binary action head (Bernoulli), separate from the left stick's direction, so the model can keep aiming while dark and come back on pointing the right way.

### Monster: the shadow crab
- **Body**: a dark, low, wide shape with two claws, almost invisible unless lit. (The human observer also sees two red eye dots on it; see section 11. Agents never see them.) It has a distinct jagged silhouette in the 16-grey view so runners can learn to recognize it when the light hits it.
- **Right stick = movement**, with crab asymmetry: **fast sideways scuttle, slower forward and back, and slow turning.** Runners can learn to exploit this by making it turn, and it learns to approach sideways.
- **Left stick = pincer attack.** Pushing the stick past a threshold snaps the claws in that direction.
  - **Short range**: about 1 to 1.5 tiles (16 to 24 px) in a narrow arc.
  - **Wind-up tell**: a brief claw-open pose (around 0.2 to 0.3 s) before the snap, visible when lit, so runners can dodge if they're watching.
  - **Cooldown and recovery**: around 1 s, during which it moves slower. Missing has a cost, so it learns to close distance before striking.
  - **Hit**: a catch (runner out), or start with damage/stun (two hits = caught) for more forgiving early training.
- **Senses**: it carries no light, so it relies on darkness and has to cross or skirt the environment's light pools. Pick its main sense from section 6 (light attraction, hearing, scent); light attraction fits a shadow creature best.

### Light pools and behaviour we expect
- The crab learns to skirt lit pools and ambush from their dark edges, and to cross them quickly sideways when it must.
- Runners learn that a pool is both a safe-looking place to check surroundings and a place where they are easy to see.
- If the crab's main sense is light attraction, make it attracted to **moving or flashlight light and lit runners**, not static lamps, or it will just sit under lamps.

### Encoding sticks for the model
- Each stick is a **2D continuous action** (x, y in -1..1), sampled from a Gaussian policy; or discretize to 8 or 16 directions plus 3 magnitude levels if continuous training is unstable.
- The pincer triggers when left-stick magnitude crosses a threshold (for example 0.8) and it is off cooldown, so attack direction and timing come from one head.
- Add a small "neutral" option (magnitude near zero) so agents can choose not to act.

The value head (expected outcome) doubles as a **fear / confidence meter** that can drive animation and UI. Calibrated probabilities mean an unsure agent hesitates, searches or calls for help instead of acting blindly.

## 5. Model architecture

1. **Encoder ("the eye")**: a small ViT (Vision Transformer). The 64x64 grey frame is cut into 8x8 patches, giving 64 visual tokens. Each patch is embedded, gets position info, and passes through a few attention layers. A small CNN is a fine alternative or front-end.
   - Speed comes from **fewer tokens and a smaller model**, not from fewer colours. The 4-bit greyscale input mainly saves memory, bandwidth and render time and makes learning easier.
   - Pretrained encoders like DINOv3 expect natural images, so train this small encoder from scratch.
2. **Memory**: a GRU/LSTM (recurrent layers that carry state between steps) so agents remember where they last saw something, such as a monster stepping into smoke or a corner checked during the last sweep. A fading "last known position" belief is learned implicitly.
3. **Heads**: policy heads (section 4), a value head, and optional auxiliary heads (section 7).

## 6. Agents and their asymmetry

### Runners (several)
- **Goals**: survive, complete objectives (for example, power generators or collect keys) that unlock the exit, then escape.
- **Senses**: flashlight vision plus hearing.
- **Tradeoff**: a lit flashlight lets you see but also makes you visible, and may attract the monster. Agents must learn when to go dark.

### Monster (one)
- **Its own nature, not just "chase"**: mixed goals like guarding a nest, growing hunger over time, and attraction to light and noise.
- **Different senses**, pick one or more:
  - sees poorly in the dark but is strongly drawn to flashlight beams
  - hears well
  - follows a fading scent trail
- **Different body**: a shadow crab (section 4) with a fast sideways scuttle, slower forward movement and slow turning, a short-range pincer attack with a visible wind-up and cooldown, and possibly the ability to break doors runners must open.
- It must be **stronger than in a one-on-one match** to balance several runners. Tune toward roughly half of runners surviving on average.

## 7. Rewards

### Runners
- small reward per second survived
- reward for completing objectives and for escaping
- penalty for being caught, smaller penalty for damage
- **team vs self**: mostly individual reward plus a team bonus (for example, a share of each teammate's escape). This gives the most human-looking mix of helping when it's cheap and bailing when it's not.
  - pure shared reward pushes toward cooperation: splitting up, decoys, sacrifice
  - pure individual reward gives "I only have to outrun you" behaviour
- early on, a small **exploration / discovery bonus** for lighting new areas or spotting threats, so agents learn to look before they learn to flee

### Monster
- reward for catches, a smaller reward for damage or chasing
- goal-specific rewards (nest guarded, hunger satisfied)
- a small exploration bonus to avoid camping one spot forever

### Auxiliary prediction heads (speed up learning)
- predict distance or time until the monster reaches you (runners), trained against the true value during training only
- predict runner positions from what's heard and seen (monster)

These give a readable danger signal even when the threat is out of view.

## 8. Training setup

- **Environment**: a headless, fast simulation with a Gymnasium / PettingZoo-style multi-agent API (`reset`, `step`), many copies in parallel. The simulation, not the network, is usually the bottleneck, and a palette-indexed greyscale renderer helps.
- **Algorithm**: PPO, with **MAPPO** (multi-agent PPO) for runners.
  - All runners **share one network**. Each acts on its own view, and experience is pooled.
  - Use a **centralized critic**: during training the value head sees the whole team's state, so credit assignment for team wins works. At play time each agent uses only its own view.
- **Self-play with opponent pools**: train runners and monster at the same time, and keep snapshots of past versions of each. Sample opponents from the pool so they don't cycle by forgetting and relearning tricks.
- **Balance controller**: if either side's win rate drifts far from about 50%, adjust monster speed, senses, map size or objective count, or give the losing side more training time.
- **Curriculum**:
  1. small open maps, slow monster, flashlight locked to movement direction (on/off switch available from the start)
  2. unlock independent flashlight control, add doors and cover
  3. add smoke, darkness variation and camo
  4. larger maze-like maps, faster and smarter monster, full objectives
- **Domain randomization**: vary map layouts, smoke density and shape, grey values within each ramp, and lighting so agents learn concepts ("hide in dark", "smoke blocks sight") instead of memorizing specifics.
- **Data augmentation**: random small shifts and crops of frames (the DrQ trick) for robust visual features.

### Faster bootstrapping (optional)
1. **Grid first, pixels second**: train on clean multi-channel grids (walls, agents, light, smoke) to get the behaviour, then train the pixel agent to imitate the grid agent (teacher-student distillation) before fine-tuning with RL.
2. **Imitation from humans**: record human play (frames plus inputs) and pretrain on it to get human-like habits, then refine with RL.

## 9. Behaviours we hope emerge

- over-the-shoulder flicks of the flashlight while fleeing, then back to lighting the path
- runners switching off and freezing in the shadows as the crab passes, then switching back on once its scuttle rings fade
- runners going dark before rounding corners or when the monster is near
- one runner baiting the monster with its light while others finish objectives
- runners spreading out on purpose; rescue attempts under a team bonus
- the monster ambushing popular routes, camping objectives or the exit, and targeting isolated runners
- if signals are enabled: invented meanings for pings ("monster here", "help"), and the monster learning to eavesdrop
- different monster "personalities" (patient stalker vs aggressive charger) from slightly different goal mixes

## 10. Failure modes to watch

- **Information leaks** in observations (true positions, counts) lead to cheating.
- **Degenerate strategies** like hiding in one corner forever or camping the exit. Fix with objectives, exploration bonuses and map variety.
- **Cycling** between strategies without improvement. Fix with opponent pools.
- **Imbalance** stopping learning for the losing side. Fix with the balance controller.
- **Unfair tricks**: neural nets can be fooled in non-human ways (a weird pattern makes a bot ignore someone in plain sight). Playtest that expected tricks work and absurd ones don't.
- **Over-flat greyscale**: camo too perfect or too useless, or smoke a solid block. Tune ramps, and use dithering for smoke.

## 11. Debugging and visualization

- **Crab's red eyes (observer only)**: in the human spectator/debug view the crab always shows two small red dots for eyes on top of its body, even in total darkness, so you can track it at a glance.
  - They are never drawn into any agent's observation. Agents see only the 16-grey light render and the sound channel, so the eyes give runners no hint.
  - Red is the one non-grey colour in the observer view, which keeps it clearly a debug overlay. Optionally the eyes point the way the crab faces and brighten during the pincer wind-up.
- side-by-side view: true colour scene, each agent's 16-grey observation, and its flashlight cone
- attention maps (ViT) or saliency maps (CNN) showing which pixels drove each decision, and whether the model is "watching" the edge of its light
- value-head fear meter and auxiliary danger prediction over time
- per-match stats: survival rate, objective completion, catches, time spent dark vs lit, signal usage

## 12. Starting parameters (first prototype)

- map: 512x512 world pixels (32x32 grid of 16px tiles), procedurally generated per episode with coarse room layout plus WFC, one exit (random, validated location), 1 monster, 4 runners
- observation: 128x128 world-pixel window downsampled to 64x64, 16 grey levels, 4-frame stack, plus a sound-ring channel (wavefront clipped by walls, dampened by materials; heard when the agent has line of sight to any part of the ring, never blocked by darkness)
- encoder: ViT, 8x8 patches (64 tokens), about 4 layers, width 128 to 192 (or a 3-layer CNN baseline)
- memory: GRU, 256 units
- runners: 4 sharing weights; monster: 1 separate network
- training: PPO/MAPPO, 64+ parallel environments, opponent pool snapshot every N updates
- hardware: one RTX 3090 should handle the networks; parallelize the simulation on CPU

## 13. Open questions

- What should the monster's primary sense be: light attraction, hearing or scent? (Light attraction suits the shadow crab.)
- Tune damping values per material; should sound later bend around corners (geodesic propagation)?
- Can lamps be switched off or broken by runners or the crab (later stage)?
- Pincer hit: instant catch, or damage/stun with two hits to catch?
- How much should runners care about each other: what team bonus weight?
- Is communication (pings) in v1 or later? (Current plan: later.)
- Learn WFC adjacency rules from hand-drawn example maps, or hand-write sockets?
- Sound silhouettes in the agent view (echolocation): try it on, or keep it observer-only?
- Should the exit always be open, or locked until objectives are done (later stage)?
- Do agents get a coarse map memory, or only learned memory?
- Should humans be able to take over a runner or the monster for mixed human-AI play?
