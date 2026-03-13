# ZenithCam (Auto-Zoom & Face-Blur)

This project implements the Unified Single-Pass Inference Engine (USPIE) for hardware-accelerated auto-zoom and face blurring.

## Components
*   **hardware_profiler.py**: Probes hardware and sets performance tier based on CPU cores, RAM, and ONNX providers.
*   **ml_pipeline.py**: Unified inference using ONNX (YOLOv8/11 support) with Optical Flow tracking for skip-frames.
*   **ptz_camera.py**: Virtual PTZ logic with a Kalman Filter for cinematic smoothing.
*   **renderer.py**: ModernGL-based hardware rendering with Gaussian blur shaders.
*   **main.py**: Main application loop.

## Setup

1.  **Install Requirements:**
    ```bash
    pip install -r requirements.txt
    ```
    (Note: `requirements.txt` is updated with necessary dependencies.)

2.  **Virtual Camera Setup:**
    Run the provided setup script to configure v4l2loopback:
    ```bash
    sudo ../auto_zoom_cam_V1/setup_virtual_cams.sh
    ```
    This sets up `/dev/video20` as `AutoZoomCam`.

3.  **Run:**
    ```bash
    python3 main.py --source 0 --virtual_cam /dev/video20
    ```
    Or use defaults:
    ```bash
    python3 main.py
    ```

    Options:
    *   `--source`: Camera source index (default: 0).
    *   `--virtual_cam`: Path to virtual camera device (default: `/dev/video20`).
    *   `--model`: Path to YOLO .pt model (default: `../auto_zoom_cam_V1/models/erax-anti-nsfw-yolo11n-v1.1.pt`).
    *   `--headless`: Run without debug window.

## Notes
*   The application will attempt to convert the model to ONNX on first run.
*   **Target Classes**: Default is `1` (make_love/action).
*   **Blur Classes**: Default is `0, 2, 3, 4` (private parts).
*   Adjust these in `main.py` or use the command line arguments if added (currently hardcoded defaults in `main.py` based on `erax` model).

## Troubleshooting
Run the diagnostic script to check your environment:
```bash
python3 diagnose.py
```
