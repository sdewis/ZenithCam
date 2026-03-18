#!/bin/bash
set -e

echo "Starting build process for v2.0.4..." > /home/sean/zenithcam_build.log

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
cp /home/sean/CodeFolder/ZenithCam_SDK_Integrated/models/erax_nsfw/erax_nsfw_yolo11n.onnx /home/sean/zenithcam_deb_local/opt/zenithcam/models/erax_nsfw_yolo11n.onnx

echo "Downloading dependencies (this takes a while)..." >> /home/sean/zenithcam_build.log
mkdir -p /home/sean/zenithcam_deb_local/opt/zenithcam/vendor
# Download dependencies, including pip, setuptools, wheel for offline upgrades
pip download -r /home/sean/CodeFolder/ZenithCam_SDK_Integrated/app/requirements.txt pip setuptools wheel -d /home/sean/zenithcam_deb_local/opt/zenithcam/vendor >> /home/sean/zenithcam_build.log 2>&1

echo "Creating metadata..." >> /home/sean/zenithcam_build.log
echo "Package: zenithcam
Version: 2.0.4
Section: video
Priority: optional
Architecture: amd64
Maintainer: Sean <sean@local>
Depends: python3, python3-venv, ffmpeg, v4l2loopback-dkms, libxcb-cursor0, libxcb-xinerama0, libgl1-mesa-glx, libglib2.0-0
Description: AI-Powered PTZ Tracking and Streaming
 ZenithCam provides high-precision object tracking (tuned for person and NSFW parts)
 using OBSBOT PTZ cameras and YOLO11. Includes integrated streaming support.
" > /home/sean/zenithcam_deb_local/DEBIAN/control

# CORRECTED postinst logic using standard venv bootstrap
cat <<'EOFPOST' > /home/sean/zenithcam_deb_local/DEBIAN/postinst
#!/bin/bash
set -e
APP_DIR="/opt/zenithcam"
VENV_DIR="$APP_DIR/venv"
VENDOR_DIR="$APP_DIR/vendor"

echo "🔧 Setting up ZenithCam environment..."

# 1. Standard venv creation (auto-installs base pip via ensurepip)
python3 -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"

# 2. Upgrade core tools using bundled offline wheels
echo "📦 Upgrading pip/setuptools from bundled wheels..."
python3 -m pip install --upgrade --no-index --find-links="$VENDOR_DIR" pip setuptools wheel

# 3. Install the application requirements offline
echo "📥 Installing application dependencies (offline)..."
python3 -m pip install --no-index --find-links="$VENDOR_DIR" -r "$APP_DIR/requirements.txt"

# 4. Fix permissions
chown -R 1000:1000 "$APP_DIR"
chmod +x "$APP_DIR/start_cam.sh"

echo "✅ Installation complete. Start with: zenithcam"
EOFPOST
chmod 755 /home/sean/zenithcam_deb_local/DEBIAN/postinst

echo -e "#!/bin/bash
cd /opt/zenithcam
./start_cam.sh" > /home/sean/zenithcam_deb_local/usr/bin/zenithcam
chmod +x /home/sean/zenithcam_deb_local/usr/bin/zenithcam
cp /home/sean/CodeFolder/ZenithCam_SDK_Integrated/app/Screenshot_20260225_210834.png /home/sean/zenithcam_deb_local/opt/zenithcam/icon.png
echo "[Desktop Entry]
Name=ZenithCam
Exec=zenithcam
Icon=/opt/zenithcam/icon.png
Type=Application
Categories=Video;" > /home/sean/zenithcam_deb_local/usr/share/applications/zenithcam.desktop

echo "Building Debian package (this takes a while)..." >> /home/sean/zenithcam_build.log
rm -f /home/sean/zenithcam_2.0.4_amd64.deb
dpkg-deb -Znone --build /home/sean/zenithcam_deb_local /home/sean/zenithcam_2.0.4_amd64.deb >> /home/sean/zenithcam_build.log 2>&1

echo "Moving to Ventoy1..." >> /home/sean/zenithcam_build.log
mv /home/sean/zenithcam_2.0.4_amd64.deb /media/sean/Ventoy1/zenithcam_2.0.4_amd64.deb

echo "Cleaning up..." >> /home/sean/zenithcam_build.log
rm -rf /home/sean/zenithcam_deb_local
# Keep 2.0.4, delete older broken ones
rm -f /media/sean/Ventoy1/zenithcam_2.0.3_amd64.deb 2>/dev/null
rm -f /media/sean/Ventoy1/zenithcam_2.0.2_amd64.deb 2>/dev/null
rm -f /media/sean/Ventoy1/zenithcam_2.0.1_amd64.deb 2>/dev/null

echo "DONE" >> /home/sean/zenithcam_build.log
