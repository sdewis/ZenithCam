# ZenithCam UI Stabilization — Gemini CLI Handover

## Objective
Fix the ZenithCam modernized UI so that:
1. **Camera feeds actually appear** in the AI Output and Raw Input preview panes when the engine is started.
2. **No Python crash** occurs on start/stop of the tracking engine.
3. The `start_cam.sh` wrapper exits cleanly (exit code 0) instead of falling into the pip-reinstall error handler.

## Project Root
```
/home/sean/CodeFolder/ZenithCam/
```

## How to Run
```bash
cd /home/sean/CodeFolder/ZenithCam/app
./start_cam.sh
```
Or directly:
```bash
cd /home/sean/CodeFolder/ZenithCam/app
source venv/bin/activate
python3 main.py
```

## Architecture Overview

### Entry Point: `app/main.py` (2325 lines)
- At the bottom (line ~2317), it imports `ModernMainWindow` from `new_ui.py` and instantiates it.
- `ModernMainWindow` **inherits** from `MainWindow` (defined in `main.py` at line 690).
- `MainWindow.__init__()` sets up all backend logic: OBSBOT SDK, ZMQ bridge, params dict, `ZenithEngineManager`, dock-based legacy UI.
- `ModernMainWindow.__init__()` calls `super().__init__()`, then hides the legacy docks and builds a new 3-column layout on top.

### Key Classes

| Class | File | Purpose |
|---|---|---|
| `ZenithWorker` | `main.py:321` | QObject worker that runs the camera capture + ML inference loop in a QThread |
| `ZenithEngineManager` | `core_engine_manager.py:8` | FSM that manages QThread lifecycle (start/stop/emergency terminate) |
| `MLPipeline` | `ml_pipeline.py` | ONNX + MediaPipe inference with optical flow inter-frame tracking |
| `ModernMainWindow` | `new_ui.py:11` | New 3-column UI that inherits from MainWindow |
| `MainWindow` | `main.py:690` | Legacy dock-based UI with all backend signal wiring |

### Signal Flow for Video Feeds
When the engine is running:
1. `ZenithWorker._run_loop()` (line 374) captures frames from the camera.
2. If `params["show_output_preview"]` is True → emits `change_pixmap_signal` with rendered QImage (line 618).
3. If `params["show_input_preview"]` is True → emits `raw_pixmap_signal` with raw QImage (line 598).
4. In `MainWindow.toggle_tracking()` (line 1549), after `engine.toggle_engine()`, the worker signals are wired:
   - `worker.change_pixmap_signal.connect(self.update_image)` (line 1565)
   - `worker.raw_pixmap_signal.connect(self.update_raw_image)` (line 1566)
5. `update_image()` (line 1622) sets a pixmap on `self.output_preview_label`.
6. `update_raw_image()` (line 1632) sets a pixmap on `self.input_preview_label`.

## Identified Bugs (Root Causes)

### BUG 1: No Video Feed — `show_input_preview` and `show_output_preview` are both `False`
**File:** `main.py` line 748-749
```python
"show_input_preview": False,
"show_output_preview": False,
```
The worker loop (line 597-619) checks these flags before emitting pixmap signals. Since both are `False`, **no frames are ever sent to the UI**. The legacy MainWindow has checkboxes (`show_input_cb`, `show_output_cb`) that toggle these, but `ModernMainWindow` never sets them to `True`.

**Fix:** In `ModernMainWindow.__init__()` (in `new_ui.py`), after calling `super().__init__()`, set:
```python
self.params["show_input_preview"] = True
self.params["show_output_preview"] = True
```

### BUG 2: Wrong Camera Index — `mock_input_combo` defaults to index 0 instead of matching `input_combo`
**File:** `new_ui.py` line 212-215

The `mock_input_combo` is populated from `self.input_combo` items but defaults to index 0 (`/dev/video0`), while the backend's `input_combo` has already auto-selected the correct OBSBOT camera (`/dev/video5`). When `toggle_tracking()` runs, it reads `self.input_combo.currentText()` — which gets overridden to the wrong device.

Test output confirmed:
```
input_combo currentText: /dev/video5
mock_input_combo currentText: /dev/video0
```

And the V4L2 error:
```
[ WARN:0@12.344] global cap_v4l.cpp:914 open VIDEOIO(V4L2:/dev/video5): can't open camera by index
```

**Fix:** After populating `mock_input_combo`, sync its index:
```python
self.mock_input_combo.setCurrentIndex(self.input_combo.currentIndex())
```

### BUG 3: Toggle Recursion — `start_btn` (ModernToggle) emits `stateChanged` when engine stops
**File:** `new_ui.py` line 199-200, `main.py` line 1577-1586

When the engine fails or stops, `_on_worker_finished()` is called. The legacy code resets button text, but `ModernMainWindow` uses a `ModernToggle` (QCheckBox subclass) for `start_btn`. If the engine stops on its own (e.g., camera open failure), the toggle stays checked. On next user interaction or when the UI tries to uncheck it programmatically, `stateChanged` fires, which calls `toggle_tracking()` again, creating a loop.

**Fix:** Override `_on_engine_started` and `_on_worker_finished` in `ModernMainWindow` to block signals on the toggle:
```python
def _on_engine_started(self):
    super()._on_engine_started()
    self.start_btn.blockSignals(True)
    self.start_btn.setChecked(True)
    self.start_btn.blockSignals(False)

def _on_worker_finished(self):
    super()._on_worker_finished()
    self.start_btn.blockSignals(True)
    self.start_btn.setChecked(False)
    self.start_btn.blockSignals(False)
```

### BUG 4 (Already Fixed): MLPipeline deadlock on stop
**File:** `ml_pipeline.py` line 278-281

Previously `stop()` called `self._mp_landmarker.close()` which deadlocked the inference thread. This has been fixed — `stop()` now only sets `self.running = False`.

## Files to Edit

### `app/new_ui.py` — Primary fix target
All three remaining bugs are fixed here. The corrected file needs:

1. **Line ~14 (after `super().__init__()`):** Add `self.params["show_input_preview"] = True` and `self.params["show_output_preview"] = True`
2. **Line ~215 (after `mock_input_combo.addItems`):** Add `self.mock_input_combo.setCurrentIndex(self.input_combo.currentIndex())`
3. **After line 236 (before `toggle_tracking` override):** Add `_on_engine_started` and `_on_worker_finished` overrides with `blockSignals`
4. **Line 269 (`update_status` override):** This currently does `pass`, which means the status label never updates. Change to call `self.status_label.setText(text)`.

### `app/main.py` — No further edits needed
The legacy `MainWindow` and `ZenithEngineManager` are stable. The `_on_engine_started` (line 1570) and `_on_worker_finished` (line 1577) methods work correctly for the legacy UI.

### `app/ml_pipeline.py` — Already fixed
The `stop()` method no longer calls `_mp_landmarker.close()`.

### `app/core_engine_manager.py` — No edits needed
The FSM is solid. It correctly handles start/stop/emergency-terminate lifecycle.

## Key Params Dict (main.py line 728-760)
```python
self.params = {
    "input_source": 1,          # Camera device index (integer, NOT path string)
    "output_device": "/dev/video20",  # v4l2loopback virtual cam
    "show_input_preview": False,      # BUG: Must be True for raw feed
    "show_output_preview": False,     # BUG: Must be True for AI feed
    "smooth_factor": 0.02,
    "zoom_margin": 45,
    "output_width": 1280,
    "output_height": 720,
    ...
}
```

## Hardware Context
- **Camera:** OBSBOT Tiny SE connected at `/dev/video5` (serial: RMOWCYH5081UKJ)
- **Virtual Cam:** v4l2loopback at `/dev/video20`
- **GPU:** Intel UHD Graphics (CML GT2) — CPU-only inference
- **OS:** Ubuntu/Debian (Wayland), Python 3.13, PyQt6

## Verification
After applying fixes, run:
```bash
cd /home/sean/CodeFolder/ZenithCam/app
source venv/bin/activate
python3 main.py
```
Then click the "Start/Stop Recording" toggle in the right panel. You should see:
1. Camera feed appears in both video panes (AI Output on top, Raw on bottom)
2. Status label updates to "Tracking active."
3. Clicking the toggle again stops cleanly without crash
4. No `QThread: Destroyed while thread is still running` warning
5. Process exits with code 0 (not triggering the pip reinstall in `start_cam.sh`)
