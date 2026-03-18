#!/bin/bash
set -e

echo "Starting build process for v2.0.8 (Native Python 3.12 Download)..." > /home/sean/zenithcam_build.log

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

echo "Downloading dependencies (using Native Python 3.12)..." >> /home/sean/zenithcam_build.log
mkdir -p /home/sean/zenithcam_deb_local/opt/zenithcam/vendor

# Create a temporary venv using the system's python3.12
/usr/bin/python3 -m venv /tmp/dl_venv
source /tmp/dl_venv/bin/activate
pip install --upgrade pip setuptools wheel >> /home/sean/zenithcam_build.log 2>&1

# Now use this cp312 pip to download everything!
pip download pip setuptools wheel -d /home/sean/zenithcam_deb_local/opt/zenithcam/vendor >> /home/sean/zenithcam_build.log 2>&1
pip download -r /home/sean/CodeFolder/ZenithCam_SDK_Integrated/app/requirements.txt -d /home/sean/zenithcam_deb_local/opt/zenithcam/vendor >> /home/sean/zenithcam_build.log 2>&1

deactivate
rm -rf /tmp/dl_venv

echo "Creating metadata..." >> /home/sean/zenithcam_build.log
echo "Package: zenithcam
Version: 2.0.8
Section: video
Priority: optional
Architecture: amd64
Maintainer: Sean <sean@local>
Depends: python3, python3-venv, ffmpeg, v4l2loopback-dkms, libxcb-cursor0, libxcb-xinerama0, libgl1-mesa-glx, libglib2.0-0, gcc, python3-dev
Description: AI-Powered PTZ Tracking and Streaming
 ZenithCam provides high-precision object tracking (tuned for person and NSFW parts)
 using OBSBOT PTZ cameras and YOLO11. Includes integrated streaming support.
" > /home/sean/zenithcam_deb_local/DEBIAN/control

# CORRECTED postinst logic using python zipapp bootstrap
cat <<'EOFPOST' > /home/sean/zenithcam_deb_local/DEBIAN/postinst
#!/bin/bash
set -e
APP_DIR="/opt/zenithcam"
VENV_DIR="$APP_DIR/venv"
VENDOR_DIR="$APP_DIR/vendor"

echo "🔧 Setting up ZenithCam environment..."

# 1. Clean any broken venv state
rm -rf "$VENV_DIR"

# 2. Create venv WITHOUT pip
python3 -m venv --without-pip "$VENV_DIR"
source "$VENV_DIR/bin/activate"

# 3. Force reinstall pip from the vendor folder using the python module directly 
echo "📦 Bootstrapping pip/setuptools from bundled wheels..."
PIP_WHL=$(ls "$VENDOR_DIR" | grep ^pip- | head -n 1)
python3 "$VENDOR_DIR/$PIP_WHL/pip" install --upgrade --force-reinstall --no-index --find-links="$VENDOR_DIR" pip setuptools wheel

# 4. Install the application requirements offline
echo "📥 Installing application dependencies (offline)..."
# We removed --no-index to allow pip to build source packages natively
pip install --find-links="$VENDOR_DIR" -r "$APP_DIR/requirements.txt"

# 5. Fix permissions
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
rm -f /home/sean/zenithcam_2.0.8_amd64.deb
dpkg-deb -Znone --build /home/sean/zenithcam_deb_local /home/sean/zenithcam_2.0.8_amd64.deb >> /home/sean/zenithcam_build.log 2>&1

echo "Moving to Ventoy1..." >> /home/sean/zenithcam_build.log
mv /home/sean/zenithcam_2.0.8_amd64.deb /media/sean/Ventoy1/zenithcam_2.0.8_amd64.deb

echo "Cleaning up..." >> /home/sean/zenithcam_build.log
rm -rf /home/sean/zenithcam_deb_local
# Keep 2.0.8, delete older broken ones
rm -f /media/sean/Ventoy1/zenithcam_2.0.7_amd64.deb 2>/dev/null
rm -f /media/sean/Ventoy1/zenithcam_2.0.6_amd64.deb 2>/dev/null
rm -f /media/sean/Ventoy1/zenithcam_2.0.5_amd64.deb 2>/dev/null

echo "DONE" >> /home/sean/zenithcam_build.log
