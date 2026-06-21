#!/bin/bash
# ZenithCam Private Remote (Tailscale)
PROJECT_ROOT="/home/sean/CodeFolder/ZenithCam"
cd "$PROJECT_ROOT/web-remote"

echo "--- Initializing Private Mesh ---"
# Ensure tailscale is up (will prompt for sudo if needed)
sudo tailscale up --accept-dns=false

TS_IP=$(tailscale ip -4)
echo "✅ Private IP: $TS_IP"
echo "🔗 URL: http://$TS_IP:3000"

# Optional: Notify the desktop
notify-send "ZenithCam Remote" "Private access at http://$TS_IP:3000"

# Start the web backend
npm start
