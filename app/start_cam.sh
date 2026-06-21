#!/bin/bash

# Reset Virtual Camera Module
echo "🔄 Resetting v4l2loopback module..."
sudo rmmod v4l2loopback 2>/dev/null
# sudo modprobe v4l2loopback devices=1 video_nr=20 card_label="ZenithCam" exclusive_caps=1
sudo modprobe v4l2loopback devices=5 video_nr=0,10,20,30,40 card_label="Iriun Webcam,OBS Virtual Camera,ZenithCam,Virtcam30,Virtcam40" exclusive_caps=1
# ZenithCam Integrated Starter Script
# Automates environment setup and runs the integrated OBSBOT/YOLO application.

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB_DIR="$APP_DIR/libs"
VIRTUAL_DEV="/dev/video20"

echo "------------------------------------------------"
echo "🚀 ZenithCam: Starting Integrated SDK Version"
echo "------------------------------------------------"

echo "🔍 Checking for virtual device $VIRTUAL_DEV..."
if [ ! -e "$VIRTUAL_DEV" ]; then
    echo "⚠️ Virtual device $VIRTUAL_DEV not found."
    echo "💡 Please ensure your v4l2loopback module is loaded correctly."
    echo "   You may need to run your system's camera fix script (e.g. force_fix_iriun.sh) if configured."
else
    echo "✅ Virtual device $VIRTUAL_DEV is ready."
    
    # Check if device is in use and offer to kill
    V_USERS=$(fuser "$VIRTUAL_DEV" 2>/dev/null)
    if [ ! -z "$V_USERS" ]; then
        echo "⚠️  Device $VIRTUAL_DEV is in use by PID(s): $V_USERS"
        echo "💡 This will cause [Errno 22] Invalid argument in the application."
        echo "🔥 Killing blocking processes..."
        fuser -k "$VIRTUAL_DEV"
        sleep 1
    fi
fi

# 2. Verify SDK Libraries
if [ ! -f "$LIB_DIR/libobsbot_bridge.so" ] || [ ! -f "$LIB_DIR/libdev.so" ]; then
    echo "❌ Error: SDK Libraries not found in $LIB_DIR"
    exit 1
fi

# 3. Set Library Path for OBSBOT SDK
export LD_LIBRARY_PATH="$LIB_DIR:$LD_LIBRARY_PATH"
echo "✅ Library path configured: $LIB_DIR"

# 4. Check for Models
if [ ! -f "$APP_DIR/models/face_landmarker.task" ]; then
    echo "⚠️  Warning: MediaPipe face model not found in $APP_DIR/models/"
fi

# 5. Run the Application
echo "🎬 Launching ZenithCam GUI..."
cd "$APP_DIR"

if [ -d "$APP_DIR/venv" ]; then
    echo "✅ Activating virtual environment..."
    source "$APP_DIR/venv/bin/activate"
fi

python3 main.py

# Final Check
if [ $? -ne 0 ]; then
    echo "------------------------------------------------"
    echo "❌ Application exited with an error."
    echo "💡 Check if your virtual environment is active or if dependencies are installed:"
    echo "   pip install -r requirements.txt"
else
    echo "------------------------------------------------"
    echo "✅ ZenithCam closed cleanly."
fi
