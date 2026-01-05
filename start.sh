#!/bin/bash
#
# Hex server startup script
#
# Launches: Xvfb → fluxbox → HexGUI → x11vnc → websockify → ttyd → API → nginx
#
set -euo pipefail

export DISPLAY="${DISPLAY:-:0}"
export NOVNC_LISTEN="${NOVNC_LISTEN:-6080}"
export TTYD_PORT="${TTYD_PORT:-7681}"

# Clean up all child processes on exit
trap 'kill 0' EXIT

# Ensure runtime directories exist
mkdir -p /var/log/nginx

# Start virtual display (16-bit color for better VNC performance)
Xvfb "$DISPLAY" -screen 0 1280x800x16 &
sleep 2

# Start window manager
fluxbox &
sleep 1

# Launch HexGUI with MoHex engine attached
java -jar /opt/hexgui/lib/hexgui.jar -program "/opt/benzene/build/src/mohex/mohex" &

# Start VNC server with optimizations
x11vnc -display "$DISPLAY" -localhost -shared -forever -rfbport 5900 -nopw \
    -threads -defer 10 -wait 10 -nonap -sb 0 -noxdamage &

# Start WebSocket-to-VNC bridge
websockify "$NOVNC_LISTEN" localhost:5900 &

# Start ttyd web terminal (accessible at /shell/)
ttyd -p "$TTYD_PORT" -i 127.0.0.1 --check-origin bash &

# Start Flask API server
gunicorn -b 127.0.0.1:8081 -w 1 app.main:app &

# Start nginx (foreground - main process)
nginx -g "daemon off;"
