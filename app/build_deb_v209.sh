#!/bin/bash
set -e

echo "Starting build process for ZenithCam Ninja Update (v2.0.9)..." > /home/sean/zenithcam_build.log

# 1. Re-scaffold the structure
rm -rf /home/sean/zenithcam_deb_local
mkdir -p /home/sean/zenithcam_deb_local/DEBIAN
mkdir -p /home/sean/zenithcam_deb_local/opt/zenithcam
mkdir -p /home/sean/zenithcam_deb_local/usr/bin
mkdir -p /home/sean/zenithcam_deb_local/usr/share/applications

echo "Copying app files..." >> /home/sean/zenithcam_build.log
cp -r /home/sean/CodeFolder/ZenithCam_SDK_Integrated/app/* /home/sean/zenithcam_deb_local/opt/zenithcam/
rm -rf /home/sean/zenithcam_deb_local/opt/zenithcam/venv
mkdir -p /home/sean/zenithcam_deb_local/opt/zenithcam/models

# Copy all necessary models (YOLO + MediaPipe)
cp /home/sean/CodeFolder/ZenithCam_SDK_Integrated/models/erax_nsfw/erax_nsfw_yolo11s.onnx /home/sean/zenithcam_deb_local/opt/zenithcam/models/ 2>/dev/null || true

echo "Downloading dependencies (using Native Python 3.12)..." >> /home/sean/zenithcam_build.log
mkdir -p /home/sean/zenithcam_deb_local/opt/zenithcam/vendor

# Create a temporary venv using the system's python3.12
/usr/bin/python3 -m venv /tmp/dl_venv
source /tmp/dl_venv/bin/activate
pip install --upgrade pip setuptools wheel >> /home/sean/zenithcam_build.log 2>&1

# Ensure mediapipe and moderngl are included in the download cache!
pip download pip setuptools wheel -d /home/sean/zenithcam_deb_local/opt/zenithcam/vendor >> /home/sean/zenithcam_build.log 2>&1
pip download -r /home/sean/CodeFolder/ZenithCam_SDK_Integrated/app/requirements.txt websockets mediapipe moderngl -d /home/sean/zenithcam_deb_local/opt/zenithcam/vendor >> /home/sean/zenithcam_build.log 2>&1

deactivate
rm -rf /tmp/dl_venv

echo "Creating metadata..." >> /home/sean/zenithcam_build.log
echo "Package: zenithcam
Version: 2.0.9
Section: video
Priority: optional
Architecture: amd64
Maintainer: Sean <sean@local>
Depends: python3, python3-venv, ffmpeg, v4l2loopback-dkms, libxcb-cursor0, libxcb-xinerama0, libgl1-mesa-glx, libglib2.0-0, gcc, python3-dev
Description: AI-Powered PTZ Tracking and Streaming (Niri Edition)
 ZenithCam provides high-precision object tracking with custom GLSL shaders, 
 MediaPipe gesture/posture integration, and OBSBOT PTZ cameras.
" > /home/sean/zenithcam_deb_local/DEBIAN/control

# Postinst logic
cat <<'EOFPOST' > /home/sean/zenithcam_deb_local/DEBIAN/postinst
#!/bin/bash
set -e
APP_DIR="/opt/zenithcam"
VENV_DIR="$APP_DIR/venv"
VENDOR_DIR="$APP_DIR/vendor"

echo "🔧 Setting up ZenithCam environment..."
rm -rf "$VENV_DIR"
python3 -m venv --without-pip "$VENV_DIR"
source "$VENV_DIR/bin/activate"

echo "📦 Bootstrapping pip/setuptools from bundled wheels..."
PIP_WHL=$(ls "$VENDOR_DIR" | grep ^pip- | head -n 1)
python3 "$VENDOR_DIR/$PIP_WHL/pip" install --upgrade --force-reinstall --no-index --find-links="$VENDOR_DIR" pip setuptools wheel

echo "📥 Installing application dependencies (offline)..."
pip install --find-links="$VENDOR_DIR" -r "$APP_DIR/requirements.txt" websockets mediapipe moderngl

chown -R 1000:1000 "$APP_DIR"
chmod +x "$APP_DIR/start_cam.sh"
chmod +x "$APP_DIR/panic.py"
EOFPOST
chmod 755 /home/sean/zenithcam_deb_local/DEBIAN/postinst

# Setup Executables
echo -e "#!/bin/bash\ncd /opt/zenithcam\n./start_cam.sh" > /home/sean/zenithcam_deb_local/usr/bin/zenithcam
chmod +x /home/sean/zenithcam_deb_local/usr/bin/zenithcam

echo -e "#!/bin/bash\n/opt/zenithcam/venv/bin/python3 /opt/zenithcam/panic.py" > /home/sean/zenithcam_deb_local/usr/bin/zenithcam-panic
chmod +x /home/sean/zenithcam_deb_local/usr/bin/zenithcam-panic

cp /home/sean/CodeFolder/ZenithCam_SDK_Integrated/zenithcam.desktop /home/sean/zenithcam_deb_local/usr/share/applications/zenithcam.desktop 2>/dev/null || true

echo "Building Debian package..." >> /home/sean/zenithcam_build.log
rm -f /home/sean/zenithcam_2.0.9_amd64.deb
dpkg-deb -Znone --build /home/sean/zenithcam_deb_local /home/sean/zenithcam_2.0.9_amd64.deb >> /home/sean/zenithcam_build.log 2>&1

mv /home/sean/zenithcam_2.0.9_amd64.deb /media/sean/Ventoy1/zenithcam_2.0.9_amd64.deb 2>/dev/null || echo "Could not move to Ventoy, file is at /home/sean/"

rm -rf /home/sean/zenithcam_deb_local
echo "DONE" >> /home/sean/zenithcam_build.log