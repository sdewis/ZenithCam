# ZenithCam Ninja-Level Features

ZenithCam has been upgraded with cutting-edge, "ninja-level" functionality integrating the AI backend with a web-based frontend through WebSockets.

## 1. Auto-Privacy via AI (NSFW Trigger)
**How it works:** 
The `ml_pipeline` continuously runs inference using the `erax_nsfw_yolo11s` ONNX model. If an NSFW class (e.g. `make_love`) is detected with high confidence, the pipeline emits an `nsfw_detected` signal to the `MainWindow`.
**Action:** 
The `MainWindow` broadcasts a `{"type": "brb_trigger", "active": true}` payload over the local WebSocket (`ws://0.0.0.0:8765`). The Tampermonkey UserScript intercepts this and instantly replaces the WebRTC camera stream with a "BRB - PRIVACY SHIELD ON" placeholder, saving the streamer from a TOS violation.

## 2. Gesture-Based Commands
**How it works:**
Using Google's `MediaPipe HandLandmarker`, the AI tracks the streamer's fingers even at 60+ FPS. Based on the relative Y-coordinates of the finger tips and PIP joints, it detects specific gestures.
**Actions:**
* ✌️ **Peace Sign:** Toggles the "BRB Shield" overlay in the browser.
* ✋ **Open Palm:** Immediately stops the OBSBOT gimbal (halts tracking).

## 3. "Safe Zone" Geofencing
**How it works:**
A 10% normalized margin `[0.1, 0.1, 0.9, 0.9]` is set in the AI config.
**Action:**
If a person or face is detected outside of this central 80% bounding box (e.g. someone walking in the background near the edge of the room), the tracking system ignores them. The camera will only lock onto subjects who enter the "Safe Zone".

## 4. Cinematic Auto-B-Roll
**How it works:**
When the `FaceLandmarker` loses sight of the streamer, a timeout counter starts.
**Action:**
If the streamer is lost for ~3-5 seconds (30 inference frames), the system triggers a `broll_callback`. The camera stops erratic searching and smoothly transitions into a slow, cinematic horizontal pan (`speed: 5.0`). As soon as the streamer steps back into frame, normal tracking resumes instantly.

## 5. Web PTZ "Mini-Map" Telemetry
**How it works:**
A `QTimer` in the backend polls the OBSBOT hardware (`get_gimbal_attitude()`) every 500ms for exact pan and tilt coordinates.
**Action:**
This telemetry is streamed to the browser via WebSocket. The UserScript draws a stylized "Radar" mini-map in the overlay, with a glowing pink dot showing exactly where the physical camera is pointing relative to its maximum limits.

## 6. Chat-Driven Reactions (Tip Integration)
**How it works:**
The Tampermonkey script injects a `MutationObserver` into the broadcasting page to monitor chat DOM elements.
**Action:**
If a chat message containing the word "tip", "tokens", or "$" appears, the script fires a `reaction` command back to the ZenithCam app. The OBSBOT camera instantly performs a 3-second "Dramatic Zoom" directly onto the streamer's face, then smoothly resets.

## 7. WASD / Arrow Key Smooth Pan Integration
**How it works:**
The UserScript listens for global `keydown` and `keyup` events (ignoring text inputs).
**Action:**
Streamers can use `W A S D` or `Arrow Keys` to smoothly pan the camera while typing or gaming. The camera moves continuously on key down, and stops the millisecond the key is released.

## 8. Elgato Stream Deck API (Local WS)
Because ZenithCam uses a unified WebSocket architecture, you can connect an **Elgato Stream Deck** to `ws://localhost:8765` using any generic WebSocket plugin.
**Commands you can send:**
* `{"command": "ptz", "action": "up"}`
* `{"command": "ptz", "action": "stop"}`
* `{"command": "reaction", "action": "zoom_action"}`

## 9. Unified Studio Chat Aggregator
**How it works:**
The Tampermonkey UserScript uses a `MutationObserver` to watch the DOM for incoming chat messages across multiple platforms (Stripchat, XHamsterLive, Chaturbate).
**Action:**
It extracts the platform name, username, and message text, sending it via WebSocket to ZenithCam Studio. The messages are aggregated into a unified "💬 Live Chat" dock in the desktop UI, allowing the streamer to read all chats without looking at the browser.

## 10. Hardware-Accelerated Stylized Privacy Shaders
**How it works:**
Instead of standard CPU blurring, ZenithCam utilizes a standalone `ModernGL` context to push pixel manipulation directly to the GPU via custom GLSL fragment shaders.
**Action:**
Streamers can select premium privacy masks like "Cyber-Glitch" (RGB splitting, chromatic aberration, digital noise) or "Neon Edge-Glow" (TRON-style cyan outlines using a Sobel filter) with zero impact on CPU overhead.

## 11. Posture-Triggered PTZ Presets
**How it works:**
The `ml_pipeline` utilizes Google's `MediaPipe PoseLandmarker` to track 33 body landmarks. It calculates the aspect ratio between the shoulders and hips to determine if the streamer is Upright (Sitting/Standing) or Reclined (Lying down).
**Action:**
If a transition to "Reclined" is detected, ZenithCam automatically sends a command to the OBSBOT camera to recall preset `P2` (e.g., pointing at a bed/floor). When they stand up, it recalls the `Home` preset.

## 12. FPS-Style Analog Mouse Look
**How it works:**
The browser UserScript captures raw `mousemove` deltas (`e.movementX`, `e.movementY`) when the user holds down the `Alt` key over the broadcast window.
**Action:**
It translates precise pixel movement into instantaneous variable-speed analog pan/tilt commands for the physical OBSBOT gimbal, mimicking the fluid camera controls of a First-Person Shooter video game.

## 13. "Hype Train" Camera Shake
**How it works:**
When the Chat Aggregator detects specific tip keywords in the DOM, it fires a `{"command": "reaction", "action": "hype_train"}` payload.
**Action:**
Instead of damaging the physical OBSBOT motors with rapid vibration, ZenithCam applies high-frequency Perlin-style noise directly to the software-defined Kalman Filter virtual crop coordinates, generating a cinematic 5-second "earthquake" effect on the output broadcast.

## 14. Idle Auto-Pilot (Wander Mode)
**How it works:**
A 5-minute software watchdog timer monitors all incoming chat messages, tips, and manual PTZ interactions. 
**Action:**
If the stream goes completely dead for 5 minutes, ZenithCam disengages the AI tracking and initiates a slow, smooth horizontal sweep of the room to simulate a live camera operator and encourage chat interaction. Any new message instantly snaps the camera back to the streamer.