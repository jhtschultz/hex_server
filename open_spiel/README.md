# OpenSpiel Adapter — MoHex (Hex)

## Overview

Wraps the MoHex/Benzene engine as an OpenSpiel bot via the HTTP GTP API.

- **OpenSpiel game**: `hex`
- **Engine**: MoHex (Benzene)
- **Protocol**: GTP over HTTP

## Files

- `bot.py` — `HexBot` with `step(state) -> action`
- `client.py` — HTTP client wrapping GTP commands (clear_board, play, play-game, genmove, param)
- `hex_utils.py` — Coordinate conversion between OpenSpiel actions and GTP notation

## Configuration

| Env Var | Default | Description |
|---------|---------|-------------|
| `HEX_ENDPOINT` | Cloud Run URL | HTTP endpoint for the MoHex GTP service |

### MoHex Engine Parameters

All `param_mohex` parameters can be passed as keyword arguments to `HexBot`.
They are applied once before the first move via the `/api/param` endpoint.

| Parameter | Default | Description |
|-----------|---------|-------------|
| `max_time` | 10 | Seconds per move |
| `max_games` | 99999999 | Max MCTS simulations per move |
| `max_nodes` | 11363636 | Max tree nodes |
| `max_memory` | ~2GB | Memory limit in bytes |
| `num_threads` | 1 | Parallel search threads |
| `use_rave` | 1 | Use RAVE values |
| `reuse_subtree` | 1 | Reuse search tree between moves |
| `uct_bias_constant` | 0.22 | UCT exploration constant |
| `expand_threshold` | 10 | Min visits before expanding |
| `knowledge_threshold` | 256 | Visits before using knowledge |
| `first_play_urgency` | 0.35 | FPU value for unvisited nodes |
| `ponder` | 0 | Think on opponent's time |

See `GET /api/param` for the full list of 36 parameters.

## State Synchronization

The MoHex server maintains a single global board. Every call to `step()` sends
the full game history via `play-game` before requesting a move — this ensures
the engine is always in the correct position regardless of whether the server
is shared, restarted, or modified by other callers. The cost is ~40ms per sync,
which is negligible compared to move generation time.

## Starting the server locally

```bash
cd /path/to/hex_server
gunicorn -b 127.0.0.1:8081 -w 1 app.main:app
```

Note: The working directory must be set so gunicorn can resolve `app.main:app`.

## Usage

```python
from open_spiel.bot import HexBot
import pyspiel

game = pyspiel.load_game("hex")
state = game.new_initial_state()

bot = HexBot(endpoint="http://localhost:8081")
action = bot.step(state)

# With engine parameters
bot = HexBot(
    endpoint="http://localhost:8081",
    max_time=5,
    num_threads=2,
    uct_bias_constant=0.3,
)
action = bot.step(state)
```
