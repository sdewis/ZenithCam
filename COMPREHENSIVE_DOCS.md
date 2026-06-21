# ZenithCam Studio: Plasma Edition
## Comprehensive Project Documentation (March 2026)

### 1. Project Overview
ZenithCam Studio is a high-performance, AI-driven streaming application for Linux. It combines real-time Computer Vision (YOLOv11), hardware-accelerated rendering (ModernGL), and a robust FFmpeg streaming backend into a cohesive, KDE Plasma-inspired desktop environment.

The project is the result of a successful merger between the **ZenithCam PTZ SDK** (AI tracking/privacy) and the **Plasma Linux Studio** (Streaming engine/UX logic).

---

### 2. Architecture & Tech Stack
- **Languages**: Python 3.14+ (Core), C++ (OBSBOT SDK Bridge), GLSL (Rendering Shaders).
- **UI Framework**: PyQt6 (Plasma/Fluent Design System).
- **Inference Engine**: ONNX Runtime (CPU/GPU) with YOLOv11 for detection.
- **PTZ Logic**: Kalman Filter + Optical Flow for smooth "Cinematic" camera movement.
- **Rendering**: ModernGL (Standalone Context) for Gaussian Blur and ROI overlays.
- **Streaming Engine**: Native FFmpeg (/usr/bin/ffmpeg) with direct stdin frame piping.
- **Audio**: PulseAudio/PipeWire-Pulse for real-time microphone capture.

---

### 3. UX/UI Design: Plasma Desktop Environment
The interface has been completely rebuilt to act as a **Modular Workspace** following Plasma and Fluent Design principles.

#### 🛠️ **Modular Docking System**
- **QDockWidget Integration**: Every UI component is a "Dock".
- **Draggable Workspace**: Click and drag any panel's title bar to rearrange your workspace.
- **Swapping (Tabify)**: Drop a dock into the center of another to create a tabbed stack (replacing the current view with a toggle).
- **Floating Panels**: Docks can be pulled out of the window to float independently.

#### 📊 **Components & Widgets**
- **Plasma Taskbar**: Anchored to the bottom. Contains dock toggles, a digital clock, and the Engine Start button.
- **Launcher (💠)**: Mimics the KDE Start Menu for system actions (About, Shutdown).
- **System Tray**: Persistent icon in the OS tray area for quick status monitoring and restoration.
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
    - **Action-Aware QoS (Auto)**: Dynamically scales FFmpeg bitrate up to 8000kbps when YOLO detects high-motion (`make_love` class) and drops it during static scenes to conserve bandwidth.

#### 🎙️ **Audio-Visual Sensor Fusion**
- **OBSBOT DOA Integration**: By tapping into the OBSBOT SDK's `doa_set` (Direction of Arrival) microphone array struct, ZenithCam's PTZ controller calculates sound origin vectors.
- **Out-of-Frame Tracking**: If a subject moves too fast and escapes the YOLO bounding box, the Kalman filter seamlessly falls back to audio vectors, steering the camera toward the sound until the subject is visually re-acquired.

#### 🛡️ **Engine Stability**
- **Deterministic FSM**: Utilizes a strict PyQt6 `QState` machine ensuring 100% crash-free teardowns, fully resolving the `v4l2loopback` [Errno 22] locking bugs and thread synchronization faults.

#### 🤖 **AI Auto-Focus & Privacy**
- **YOLO Detection**: Real-time identification of actions and private parts.
- **Privacy Shield**: Auto-blurring of sensitive classes via hardware shaders.
- **Robot PTZ**: Direct integration with OBSBOT hardware via C++ SDK.
- **Kalman Filtering**: Eliminates camera jitter during high-action sequences.

---

### 5. Advanced Streaming Configuration
The FFmpeg backend is pre-configured for **Stripchat/XHamsterLive** optimized for zerolatency.

**Command Template:**
```bash
ffmpeg -y -thread_queue_size 1024   -f rawvideo -vcodec rawvideo -s 1280x720 -pix_fmt rgb24 -framerate 30 -i -   -f pulse -i default   -c:v libx264 -preset veryfast -tune zerolatency -profile:v main -bf 0   -b:v {bitrate} -maxrate {bitrate} -bufsize {bitrate}   -pix_fmt yuv420p -g 60 -keyint_min 60   -c:a aac -b:a 128k -ar 48000 -ac 2   -f flv rtmp://{server}/{key}
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
