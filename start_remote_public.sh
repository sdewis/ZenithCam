#!/bin/bash
# ZenithCam Public Remote (Localtunnel)
PROJECT_ROOT="/home/sean/CodeFolder/ZenithCam"
cd "$PROJECT_ROOT/web-remote"

echo "--- Spinning Up Public Tunnel ---"
echo "URL will be: https://zenith-cam-remote.loca.lt"

# Start the web server and the tunnel concurrently
# Tunnel requires a few seconds to initialize
npm run tunnel &
TUNNEL_PID=$!

# Let the tunnel start first
sleep 3
npm start

# Clean up tunnel on exit
trap "kill $TUNNEL_PID" EXIT
