# Hex Server

Hex game engine server with MoHex (Benzene) and HexGUI, exposed via browser-based VNC and REST API.

**Live**: https://hex-server-493397232829.us-central1.run.app

## Quick Start

1. Open the URL in your browser to access HexGUI via VNC
2. Go to **Program > New Program**
3. Enter `mohex` as the command (the engine is at `/opt/benzene/build/src/mohex/mohex`)
4. Click OK - HexGUI is now connected to MoHex
5. Use **Program > Generate Move** to have MoHex play

## Connecting the Engine

HexGUI should auto-connect to MoHex on startup. If not connected:

1. **Program > New Program**
2. Name: `MoHex` (or anything)
3. Command: `mohex`
4. Click OK

To generate moves: **Program > Generate Move** (or use the toolbar button)

## REST API

The server also exposes a REST API for programmatic access:

### Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | Health check |
| `/api/gtp` | POST | Raw GTP command |
| `/api/boardsize` | POST | Set board size |
| `/api/clear` | POST | Clear the board |
| `/api/play` | POST | Play a move |
| `/api/genmove` | POST | Generate best move |
| `/api/play-game` | POST | Reset board and play a sequence of moves |
| `/api/param` | GET/POST | Get/set `param_mohex` params (alias for `/api/param/mohex`) |
| `/api/param/<group>` | GET/POST | Get/set params for any group (see below) |
| `/api/params` | GET | Get all params from every group in one call |
| `/api/showboard` | GET | Get board state |
| `/api/undo` | POST | Undo last move |

### Examples

```bash
# Health check
curl https://hex-server-493397232829.us-central1.run.app/api/health

# Set board size to 11x11
curl -X POST -H "Content-Type: application/json" \
  -d '{"size": 11}' \
  https://hex-server-493397232829.us-central1.run.app/api/boardsize

# Play a move (black at f6)
curl -X POST -H "Content-Type: application/json" \
  -d '{"color": "black", "move": "f6"}' \
  https://hex-server-493397232829.us-central1.run.app/api/play

# Generate move for white
curl -X POST -H "Content-Type: application/json" \
  -d '{"color": "white"}' \
  https://hex-server-493397232829.us-central1.run.app/api/genmove

# Generate move with 15-second wall-clock timeout
# If pre-search hangs, the engine restarts with reduced params
# and the response will include "degraded": true
curl -X POST -H "Content-Type: application/json" \
  -d '{"color": "black", "timeout": 15}' \
  https://hex-server-493397232829.us-central1.run.app/api/genmove

# Play a sequence of moves (alternating colors, starting with black)
curl -X POST -H "Content-Type: application/json" \
  -d '{"moves": ["a1", "b2", "c3"], "size": 11}' \
  https://hex-server-493397232829.us-central1.run.app/api/play-game

# Get all MoHex MCTS params (backward compatible)
curl https://hex-server-493397232829.us-central1.run.app/api/param

# Set MCTS params
curl -X POST -H "Content-Type: application/json" \
  -d '{"max_time": 5, "num_threads": 2}' \
  https://hex-server-493397232829.us-central1.run.app/api/param

# Get board-level params (ICE, VCs, decompositions)
curl https://hex-server-493397232829.us-central1.run.app/api/param/player_board

# Disable ICE to speed up ComputeAll phase
curl -X POST -H "Content-Type: application/json" \
  -d '{"use_ice": 0}' \
  https://hex-server-493397232829.us-central1.run.app/api/param/player_board

# Get ALL params from every group at once
curl https://hex-server-493397232829.us-central1.run.app/api/params

# Raw GTP command
curl -X POST -H "Content-Type: application/json" \
  -d '{"command": "showboard"}' \
  https://hex-server-493397232829.us-central1.run.app/api/gtp
```

### Timeout & Degraded Play

MoHex's `max_time` parameter only bounds the MCTS search phase.  The
pre-search phase (ICE inferior-cell computation, virtual-connection
building, and board decomposition) runs **before** MCTS with no time
limit and can hang for 60–120+ seconds on complex 11×11 positions.

To guarantee a wall-clock bound, pass `"timeout"` in the genmove request:

```json
{"color": "black", "timeout": 15}
```

**How it works:**

1. The engine attempts `genmove` normally.
2. If the call exceeds the timeout, the engine process is killed and
   restarted.  The board position is replayed and params are restored,
   but ICE, VCS, decompositions, and pre-search are disabled.
3. `genmove` is retried with these reduced settings.
4. The response includes `"degraded": true` and a `"warning"` message.

**Important:** short time controls may produce significantly weaker
play because the engine loses its primary positional-analysis features.
Without ICE and VCS, MoHex cannot prune inferior cells or reason about
virtual connections, so the MCTS search operates on a much larger
(unpruned) game tree.  This is the expected trade-off for guaranteed
response times.

If the retry also times out (unlikely with analysis features disabled),
the endpoint returns HTTP 504 with an error message.

### Engine Parameters

Parameters are organized into groups matching MoHex's GTP param commands.
Use `/api/param/<group>` to get or set params for a specific group, or
`/api/params` to read all groups at once.

Benzene source reference: [benzene-vanilla-cmake](https://github.com/cgao3/benzene-vanilla-cmake)

#### `mohex` — MCTS Search Parameters

Endpoint: `/api/param/mohex` (or `/api/param` for backward compatibility)

GTP command: `param_mohex` — registered in
[MoHexEngine.cpp](https://github.com/cgao3/benzene-vanilla-cmake/blob/master/src/mohex/MoHexEngine.cpp)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `max_time` | 10 | Max seconds for MCTS search (does NOT bound total genmove time) |
| `max_games` | 99999999 | Max MCTS simulations per move |
| `max_nodes` | 11363636 | Max tree nodes |
| `max_memory` | ~2GB | Memory limit in bytes |
| `num_threads` | 1 | Parallel search threads |
| `use_rave` | 1 | Use RAVE values |
| `reuse_subtree` | 1 | Reuse search tree between moves |
| `uct_bias_constant` | 0.22 | UCT exploration constant |
| `expand_threshold` | 10 | Min visits before expanding a node |
| `knowledge_threshold` | "256" | Visits before using knowledge (quoted string, can be multi-value) |
| `first_play_urgency` | 0.35 | FPU value for unvisited nodes |
| `ponder` | 0 | Think on opponent's time |
| `progressive_bias` | 2.47 | Progressive bias weight |
| `rave_weight_initial` | 2.12 | Initial RAVE weight |
| `rave_weight_final` | 830 | Final RAVE weight |
| `virtual_loss` | 1 | Virtual loss for parallel search |
| `perform_pre_search` | 1 | Run 1-ply win/loss search before MCTS |
| `use_root_data` | 1 | Use fillin and consider set in root state |
| `use_time_management` | 0 | Use time control for per-move allocation |
| `use_parallel_solver` | 0 | Run DFPN solver in parallel with MCTS |
| `search_singleton` | 0 | Search even when mustplay has one move |
| `backup_ice_info` | 1 | Backup ICE info during pre-search |
| `extend_unstable_search` | 1 | Extend search when best move is unstable |
| `lock_free` | 1 | Lock-free parallel search (requires atomic builtins) |
| `lazy_delete` | 0 | Lazy deletion in search tree |
| `prior_pruning` | 1 | Prune moves using prior knowledge |
| `use_livegfx` | 0 | Send live graphics updates (for HexGUI) |
| `weight_rave_updates` | 1 | Weight RAVE updates |
| `bias_term` | 0 | Bias term constant |
| `fillin_map_bits` | 16 | Bits for fillin hash map |
| `number_playouts_per_visit` | 1 | Playouts per tree visit |
| `move_select` | count | Move selection strategy (value/count/bound/estimate) |
| `time_control_override` | -1 | Override estimated moves remaining for time control |
| `playout_global_gamma_cap` | varies | Cap on global gamma values in playout |
| `vcm_gamma` | varies | Gamma value for VCM |
| `randomize_rave_frequency` | 0 | Frequency of RAVE randomization |

#### `player_board` — Board-Level Parameters

Endpoint: `/api/param/player_board`

GTP command: `param_player_board` — registered in
[HexEnvironment.cpp](https://github.com/cgao3/benzene-vanilla-cmake/blob/master/src/hex/HexEnvironment.cpp)

These control the `ComputeAll()` phase that runs **before** MCTS search.
This phase has no time limit and can be slow on complex 11×11 positions.

| Parameter | Default | Description |
|-----------|---------|-------------|
| `use_ice` | 1 | Enable Inferior Cell Engine. Disabling skips inferior cell computation in ComputeAll(). |
| `use_vcs` | 1 | Enable Virtual Connection computation. Disabling skips VC building in ComputeAll(). |
| `use_decompositions` | 1 | Enable board decomposition analysis |
| `backup_ice_info` | 1 | Back up ICE information when trying moves |

#### `player_ice` — ICE (Inferior Cell Engine) Parameters

Endpoint: `/api/param/player_ice`

GTP command: `param_player_ice` — registered in
[HexEnvironment.cpp](https://github.com/cgao3/benzene-vanilla-cmake/blob/master/src/hex/HexEnvironment.cpp)

Fine-grained control over which inferior cell analyses run during ComputeAll().

| Parameter | Default | Description |
|-----------|---------|-------------|
| `find_all_pattern_superiors` | 1 | Find all pattern-based superior cells |
| `find_all_pattern_killers` | 1 | Find all pattern-based killer cells |
| `find_presimplicial_pairs` | 1 | Find presimplicial pairs |
| `find_three_sided_dead_regions` | 1 | Find three-sided dead regions |
| `iterative_dead_regions` | 1 | Iteratively find dead regions |
| `use_capture` | 1 | Use captured cell analysis |
| `find_reversible` | 1 | Find reversible cells |
| `use_s_reversible_as_reversible` | 0 | Treat strongly-reversible cells as reversible |

#### `player_vc` — Virtual Connection Builder Parameters

Endpoint: `/api/param/player_vc`

GTP command: `param_player_vc` — registered in
[HexEnvironment.cpp](https://github.com/cgao3/benzene-vanilla-cmake/blob/master/src/hex/HexEnvironment.cpp)

Controls how virtual connections are built during ComputeAll().

| Parameter | Default | Description |
|-----------|---------|-------------|
| `and_over_edge` | 1 | AND rule over edge connections |
| `use_patterns` | 1 | Use patterns in VC construction |
| `use_non_edge_patterns` | 1 | Use non-edge patterns |
| `incremental_builds` | 1 | Build VCs incrementally |
| `limit_fulls` | 0 | Limit full VC connections |
| `limit_or` | 0 | Limit OR rule applications |

#### `mohex_policy` — Playout Policy Parameters

Endpoint: `/api/param/mohex_policy`

GTP command: `param_mohex_policy` — registered in
[MoHexEngine.cpp](https://github.com/cgao3/benzene-vanilla-cmake/blob/master/src/mohex/MoHexEngine.cpp)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `pattern_heuristic` | 1 | Use pattern-based heuristic in playouts |

#### `game` — Game Parameters

Endpoint: `/api/param/game`

GTP command: `param_game` — registered in
[HexHtpEngine.cpp](https://github.com/cgao3/benzene-vanilla-cmake/blob/master/src/hex/HexHtpEngine.cpp)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `allow_swap` | 1 | Allow the swap rule |
| `on_little_golem` | 0 | Little Golem compatibility mode |
| `game_time` | 0 | Game time in seconds (0 = unlimited, must set before first move) |

## Architecture

- **MoHex**: MCTS-based Hex engine from the Benzene project (CPU-only, no GPU required)
- **HexGUI**: Java GUI for playing Hex, connects to MoHex via GTP protocol
- **VNC Stack**: Xvfb + fluxbox + x11vnc + noVNC for browser access
- **Flask API**: REST wrapper around MoHex GTP commands

## Fluxbox Menu

Right-click on the desktop to access:
- **HexGUI + MoHex**: Launch HexGUI with engine attached
- **HexGUI Only**: Launch HexGUI without engine
- **MoHex Terminal**: Run MoHex in interactive terminal
- **Terminal**: Open xterm

## Local Development

```bash
# Build
docker build -t hex-server .

# Run
docker run --rm -p 8080:8080 hex-server

# Access at http://localhost:8080
```

## Deploy to Cloud Run

```bash
gcloud builds submit --tag gcr.io/PROJECT/hex-server --timeout=30m

gcloud run deploy hex-server \
    --image gcr.io/PROJECT/hex-server \
    --memory 2Gi --cpu 2 --port 8080 \
    --concurrency=1 \
    --allow-unauthenticated
```
