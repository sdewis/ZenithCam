# ZenithCam Studio: Niri Edition
## Comprehensive Project Documentation (v2.1 Ninja Update)

### 1. Project Overview
ZenithCam Studio is a high-performance, AI-driven streaming application for Linux. It combines real-time Computer Vision (YOLOv11), hardware-accelerated rendering (ModernGL), and a robust FFmpeg streaming backend into a cohesive, modular desktop environment tailored for Wayland window managers like Niri.

The project is the result of a successful merger between the **ZenithCam PTZ SDK** (AI tracking/privacy) and a native Linux streaming engine.

---

### 2. Architecture & Tech Stack
- **Languages**: Python 3.14+ (Core), C++ (OBSBOT SDK Bridge), GLSL (Rendering Shaders).
- **UI Framework**: PyQt6 (Modular/Fluent Design System).
- **Inference Engine**: ONNX Runtime (YOLOv11 NSFW) & MediaPipe (Face, Hands, Pose Landmarkers).
- **PTZ Logic**: Kalman Filter + Procedural Noise for smooth "Cinematic" camera movement and FX.
- **Rendering**: ModernGL (Standalone Context) for Gaussian Blur and ROI overlays.
- **Streaming Engine**: Native FFmpeg (/usr/bin/ffmpeg) with direct stdin frame piping.
- **Audio**: PulseAudio/PipeWire-Pulse for real-time microphone capture.

---

### 3. UX/UI Design: Multi-Window Desktop Environment
The interface has been completely rebuilt as a **Multi-Window Workspace** to naturally align with Wayland tiling compositors like Niri.

#### 🛠️ **Window System**
- **Floating Entities**: Every UI component is an independent, top-level window.
- **Tile-Friendly**: Because they are standard Wayland windows, your compositor can seamlessly tile, group, and route them to different virtual workspaces.
- **State Memory**: ZenithCam automatically saves the position and geometry of every panel, completely reconstructing your studio exactly as you left it.

#### 📊 **Components & Widgets**
- **Control Hub (Taskbar)**: The main application window acts simply as a floating control strip containing dock toggles, a digital clock, and the Engine Start button.
- **Launcher (💠)**: Central menu for system actions (About, Workspace Reset, Shutdown).
- **System Tray**: Persistent icon in the OS tray area for quick status monitoring and restoration.
- **✨ Studio Effects**: Dedicated dock for configuring GPU Shaders, Hype Train FX, and Idle Auto-Pilot.
- **💬 Live Chat**: Unified aggregator dock that pulls real-time chat messages from XHamster, Stripchat, and Chaturbate via WebSocket.
- **Translucency & Blurs**: Uses rgba styling for a "glass" effect on panels.

---

### 4. Features & Capabilities

#### 📡 **Broadcast & Multi-Streaming**
- **Profile Manager**: Save and manage unlimited streaming profiles (URL, Key, Platform).
- **Simultaneous Streaming**: Check up to **3 profiles** at once. ZenithCam will spawn parallel FFmpeg instances to broadcast to multiple sites (e.g., Stripchat + XHamster + YouTube) from a single camera feed.
- **WiFi Optimization**: A "Quality" toggle allows switching between:
    - **Fast/WiFi (3000 kbps)**: Stabilizes streams on wireless connections.
    - **Medium (4500 kbps)**: Standard quality.
    - **High/Ethernet (6000 kbps)**: Maximum CBR 720p/1080p quality.

#### 🤖 **AI Auto-Focus & Privacy**
- **YOLO Detection**: Real-time identification of actions and private parts.
- **Stylized GPU Shaders**: Choose from Gaussian Blur, 8-Bit Pixelation, Cyber-Glitch, or Neon Edge-Glow to mask private parts.
- **Posture Triggers**: Uses MediaPipe Pose to automatically recall specific PTZ presets if the streamer transitions from standing to lying down.
- **Robot PTZ**: Direct integration with OBSBOT hardware via C++ SDK.
- **Kalman Filtering**: Eliminates camera jitter during high-action sequences.

#### 🌐 **Browser Integration (Tampermonkey)**
- **PTZ UI Overlay**: A draggable overlay injected directly into adult broadcast sites, communicating with ZenithCam Studio via a local WebSocket bridge (`ptz_web_bridge.py`).
- **Stream Hijack (Be Right Back)**: Intercepts `navigator.mediaDevices.getUserMedia()` locally. If the YOLO pipeline detects an NSFW class, it forces the browser to replace the video track with an opaque HTML5 "BRB" canvas instantly.
- **Resolution Enforcer**: Tampermonkey automatically rewrites getUserMedia constraints to strict 1280x720 parameters, ensuring UI compatibility with the strict 16:9 ZenithCam pipeline.
- **FPS Mouse Look**: Hold `Alt` in the browser to turn the mouse into a high-precision analog stick to freely aim the OBSBOT camera.

#### 🚨 **OS Integration & Stream Deck**
- **Global Panic Button**: A bundled `panic.py` script allows users to bind a global OS shortcut (or Elgato Stream Deck button) to instantly fire the BRB Privacy shield.

---

### 5. Advanced Streaming Configuration
The FFmpeg backend is pre-configured for **Stripchat/XHamsterLive** optimized for zerolatency. You can select between CPU and Hardware Encoding directly from the UI to dramatically reduce system load while broadcasting.

**Supported Encoders:**
- **CPU (x264)**: Maximum compatibility (`-c:v libx264 -preset veryfast -tune zerolatency`).
- **NVIDIA (NVENC)**: High-performance hardware encoding for NVIDIA GPUs (`-c:v h264_nvenc -preset p2 -tune ull`).
- **AMD/Intel (VA-API)**: Native Wayland/Linux hardware encoding (`-vaapi_device /dev/dri/renderD128 -c:v h264_vaapi`).

**Command Template:**
```bash
ffmpeg -y -thread_queue_size 1024 -vaapi_device /dev/dri/renderD128 -f rawvideo -vcodec rawvideo -s 1280x720 -pix_fmt rgb24 -framerate 30 -i - -thread_queue_size 1024 -f pulse -i default -vf format=nv12,hwupload -c:v h264_vaapi -profile:v main -bf 0 -b:v {bitrate} -maxrate {bitrate} -bufsize {bitrate} -g 60 -keyint_min 60 -c:a aac -b:a 128k -ar 48000 -ac 2 -f flv rtmp://{server}/{key}
```

---

### 6. Installation & Usage

#### **Prerequisites**
- v4l2loopback kernel module (for virtual camera output).
- ffmpeg (compiled with --enable-libpulse).
- libobsbot_bridge.so (included in /libs).

#### **Launching**
1. **Configure Hardware**: Ensure your virtual device (default /dev/video20) is loaded.
2. **Start Engine**:
   ```bash
   cd app && ./start_cam.sh
   ```
3. **Setup Profiles**: Click the **Profiles** button on the right panel, enter your RTMP details, and hit **Save (💾)**.
4. **Go Live**: Select your profiles and click **Start Broadcast**.

---

### 7. Troubleshooting & Maintenance
- **Indentation Errors**: Use autopep8 --indent-size 4 to fix layout issues in main.py.
- **Display Detach**: If the window doesn't appear on Wayland, launch via ./start_cam.sh without backgrounding the final python call manually.
- **FFmpeg Logs**: Toggle **Debug Mode** in the taskbar to see live stderr from FFmpeg inside the app.
