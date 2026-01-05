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

# Raw GTP command
curl -X POST -H "Content-Type: application/json" \
  -d '{"command": "showboard"}' \
  https://hex-server-493397232829.us-central1.run.app/api/gtp
```

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
