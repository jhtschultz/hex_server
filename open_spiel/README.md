# OpenSpiel Adapter — MoHex (Hex)

## Overview

Wraps the MoHex/Benzene engine as an OpenSpiel bot via the HTTP GTP API.

- **OpenSpiel game**: `hex`
- **Engine**: MoHex (Benzene)
- **Protocol**: GTP over HTTP

## Files

- `bot.py` — `HexBot` with `step(state) -> action`
- `client.py` — HTTP client wrapping GTP commands (clear_board, play, genmove)
- `hex_utils.py` — Coordinate conversion between OpenSpiel actions and GTP notation

## Configuration

| Env Var | Default | Description |
|---------|---------|-------------|
| `HEX_ENDPOINT` | Cloud Run URL | HTTP endpoint for the MoHex GTP service |

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
```
