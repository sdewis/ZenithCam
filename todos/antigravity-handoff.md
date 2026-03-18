# ZenithCam SDK Integrated - Development Handoff

## 📌 Project Status Thus Far
We have been integrating a unified auto-zoom and face-blur pipeline into a PyQt6 interface, utilizing the OBSBOT C++ SDK for hardware PTZ control and `v4l2loopback` (via `pyfakewebcam`) for virtual camera output.

**Recent Major Milestones:**
1. **Unified Pipeline**: Implemented `MLPipeline` (ONNX YOLO + MediaPipe FaceLandmarker + Optical Flow) running asynchronously, feeding a `PTZCamera` (Kalman Filter smoothing) and a `Renderer` (ModernGL hardware acceleration).
2. **Aspect Ratio Lock**: Enforced a strict 16:9 (1280x720) ratio across the entire stack. Inputs are automatically center-cropped to 16:9, and the UI previews maintain proper scaling without layout thrashing.
3. **Handle Leaks & "Device Busy" (`Errno 22`) Fixes**:
   - `start_cam.sh` now automatically runs `fuser -k` on the virtual device to kill zombie blocking processes.
   - Refactored the `OBSBOT_Sample` C++ bridge to include an `obsbot_disconnect()` function to release internal libusb/V4L2 handles.
   - Created a centralized `HardwareManager` in Python to orchestrate `cv2.VideoCapture`, `pyfakewebcam.FakeWebcam`, and `Renderer` lifecycles, ensuring a strict "Close-Before-Open" policy.
4. **Thread Teardown Stability**: Transitioned from a fragile `QThread` subclass to a `QObject` Worker pattern (`ZenithWorker` moved to `QThread`).

## 🚨 Current Critical Issue (The Crash)
The application is currently crashing with a core dump during the Stop/Start tracking cycle.
**Error Trace:**
```python
Traceback (most recent call last):
File "/home/sean/CodeFolder/ZenithCam_SDK_Integrated/app/main.py", line 726, in toggle_tracking
if self.thread.isRunning():
^^^^^^^^^^^^^^^^^^^^^
AttributeError: 'NoneType' object has no attribute 'isRunning'
```
**Context of Crash:**
When stopping the tracking, `self._on_worker_finished` is called as a slot from `self.worker.finished`. Inside `_on_worker_finished`, `self.thread` is set to `None`. 
However, in `toggle_tracking`, the code checks `if self.thread and self.thread.isRunning():`. If the user clicks the button quickly, or if the event loop processes things in an unexpected order, this check throws the `AttributeError`. The UI state (button text) and the thread state are getting desynced. Furthermore, when the UI window is closed (`closeEvent`), it attempts to stop the thread using the same unsafe logic, leading to the core dump upon exit.

## 📋 TODO for AntiGravity

### Immediate Fixes
- [x] **Fix `toggle_tracking` Race Condition**: Refactor `toggle_tracking` and `_on_worker_finished` to use thread-safe state flags instead of directly querying `self.thread.isRunning()`, which is prone to `NoneType` errors when the thread is being torn down.
- [x] **Fix `closeEvent` Crash**: Ensure `closeEvent` gracefully waits for the `HardwareManager` to close all file descriptors without trying to call methods on a potentially `None` `self.thread`.
- [x] **Verify `pyfakewebcam` Cleanup**: Ensure `HardwareManager.close_output()` is successfully releasing the `os.open` file descriptor for `/dev/video20` so that subsequent starts don't hit the `[Errno 22] Invalid argument` block.

### Next Steps / Refinements
- [x] **Verify Hardware Render Consistency**: Ensure ModernGL context destruction (`ctx.release()`) is completely clean between stop/start cycles.
- [x] **SDK Initialization UX**: Ensure the UI smoothly handles the OBSBOT SDK taking a few seconds to connect, providing clear visual feedback rather than freezing or logging silent errors.