import sys
import cv2
import numpy as np
import time
import os
import json
import logging
import subprocess
import fcntl
import threading
import psutil
import signal
from logging.handlers import TimedRotatingFileHandler
from PyQt6.QtWidgets import (QDockWidget, QApplication, QMainWindow, QWidget, QStyle, QVBoxLayout,
                             QHBoxLayout, QLabel, QComboBox, QPushButton,
                             QSlider, QGroupBox, QFileDialog, QSpinBox,
                             QSplitter, QTextEdit, QCheckBox, QScrollArea, QGridLayout, QLineEdit, QListWidget, QMenu, QSystemTrayIcon)
from PyQt6.QtCore import Qt, QThread, pyqtSignal as Signal, pyqtSlot as Slot, QObject, QTimer, QEventLoop, QSettings
from PyQt6.QtGui import QImage, QPixmap
import pyfakewebcam

from ultralytics import YOLO

from hardware_profiler import HardwareProfiler
from ml_pipeline import MLPipeline
from ptz_camera import PTZCamera
from renderer import Renderer
from obsbot_wrapper import OBSBOTSDK


def find_obsbot_device():
    """Return all /dev/videoN nodes listed under OBSBOT Tiny SE in v4l2-ctl."""
    devices = []
    try:
        result = subprocess.run(
            ['v4l2-ctl', '--list-devices'], capture_output=True, text=True)
        lines = result.stdout.split('\n')
        for i, line in enumerate(lines):
            if "OBSBOT Tiny SE" in line:
                j = i + 1
                while j < len(lines):
                    stripped = lines[j].strip()
                    if stripped.startswith('/dev/video'):
                        devices.append(stripped)
                    elif stripped.startswith('/dev/media') or stripped == '':
                        pass
                    elif not stripped.startswith('/dev/'):
                        break
                    j += 1
                break
    except Exception:
        pass
    return devices[0] if devices else None


def find_obsbot_capture_index():
    """Find the OBSBOT video node that can be read by OpenCV.
    Checks for any device with 'OBSBOT' in its name.
    Returns the first video node that supports video capture.
    """
    import glob as _glob
    try:
        result = subprocess.run(
            ['v4l2-ctl', '--list-devices'], capture_output=True, text=True)
        lines = result.stdout.split('\n')
        candidates = []
        in_obsbot = False
        for line in lines:
            if 'OBSBOT' in line.upper():
                in_obsbot = True
                continue
            if in_obsbot:
                stripped = line.strip()
                if stripped.startswith('/dev/video'):
                    candidates.append(stripped)
                elif stripped and not stripped.startswith('/dev/'):
                    in_obsbot = False
        
        for dev in candidates:
            # Check if it has Video Capture (not just Metadata)
            try:
                info = subprocess.run(
                    ['v4l2-ctl', f'--device={dev}', '--info'],
                    capture_output=True, text=True, timeout=2)
                if 'Video Capture' in info.stdout:
                    idx = int(dev.split('video')[-1])
                    global_logger.info(f'Detected OBSBOT capture node: {dev} (idx={idx})')
                    return idx
            except Exception:
                pass
    except Exception:
        pass
    
    # Fallback: search for ANY camera if OBSBOT not found or specific detection failed
    try:
        for dev in sorted(_glob.glob('/dev/video*')):
            try:
                info = subprocess.run(
                    ['v4l2-ctl', f'--device={dev}', '--info'],
                    capture_output=True, text=True, timeout=1)
                if 'Video Capture' in info.stdout:
                    idx = int(dev.split('video')[-1])
                    # Avoid returning virtual device 20 or 10 if possible
                    if idx not in [10, 20]:
                        return idx
            except:
                pass
    except:
        pass

    return 0  # Ultimate fallback to 0


class LogEmitter(QObject):
    log_signal = Signal(str)


class QtLogHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.emitter = LogEmitter()

    def emit(self, record):
        msg = self.format(record)
        self.emitter.log_signal.emit(msg)


os.makedirs('logs', exist_ok=True)
global_logger = logging.getLogger('AutoZoomLogger')
global_logger.setLevel(logging.DEBUG)
log_file = "logs/autozoom.log"
file_handler = TimedRotatingFileHandler(
    log_file, when='M', interval=30, backupCount=5)
file_handler.setFormatter(logging.Formatter(
    '%(asctime)s - %(levelname)s - %(message)s'))
if os.path.exists(log_file) and os.path.getsize(log_file) > 0:
    file_handler.doRollover()
global_logger.addHandler(file_handler)

qt_handler = QtLogHandler()
qt_handler.setFormatter(logging.Formatter('[%(levelname)s] %(message)s'))
global_logger.addHandler(qt_handler)


def detect_loopback_devices():
    """Scan for v4l2loopback virtual camera devices using sysfs to avoid locking."""
    loopback_devs = []
    base_path = "/sys/class/video4linux"
    if not os.path.exists(base_path):
        return []

    try:
        devices = sorted(os.listdir(base_path))
        for dev in devices:
            name_file = os.path.join(base_path, dev, "name")
            if os.path.exists(name_file):
                try:
                    with open(name_file, "r") as f:
                        card_name = f.read().strip()

                    driver_link = os.path.join(
                        base_path, dev, "device", "driver")
                    if os.path.exists(driver_link):
                        driver_name = os.path.basename(
                            os.readlink(driver_link))
                        if driver_name == "v4l2loopback":
                            loopback_devs.append(f"/dev/{dev}")
                            continue

                    if any(label in card_name for label in ["loopback", "Virtual", "Fake", "Zenith", "Cam"]):
                        loopback_devs.append(f"/dev/{dev}")
                except Exception:
                    pass
    except Exception as e:
        print(f"Error scanning sysfs: {e}")
    return loopback_devs


# Ultra-Modern Dark Theme
STYLESHEET = """
QMainWindow { background-color: #0A0A0C; }
QWidget { color: #E2E2E2; font-family: 'Segoe UI', system-ui, sans-serif; font-size: 14px; }

/* The Taskbar */
#TaskBar { background-color: rgba(20, 20, 25, 240); border-top: 1px solid #2A2A30; }
#TaskBar QPushButton {
    background-color: transparent; border-radius: 6px; padding: 10px 16px; font-weight: bold;
    color: #B0B0B0; margin: 4px;
}
#TaskBar QPushButton:hover { background-color: rgba(255, 255, 255, 15); color: #FFF; }
#TaskBar QPushButton:checked { background-color: rgba(0, 230, 118, 30); color: #00E676; border-bottom: 2px solid #00E676; }
#TaskBar #StartBtn { background-color: #00C853; color: #000; padding: 10px 24px; font-size: 15px;}
#TaskBar #StartBtn:hover { background-color: #00E676; }
#TaskBar #StreamBtn { background-color: #2979FF; color: #FFF; }

/* Studio Panels */
PanelWindow { background-color: #0A0A0C; }
QGroupBox {
    border: 1px solid #333; border-radius: 8px; margin-top: 18px; background-color: rgba(40, 40, 45, 100);
}
QGroupBox::title {
    color: #00E676; font-weight: bold; font-size: 15px;
    subcontrol-origin: margin; subcontrol-position: top left; padding: 0 8px;
}
QComboBox, QSpinBox, QTextEdit, QLineEdit, QListWidget {
    background-color: #1E1E24; border: 1px solid #444; border-radius: 6px; padding: 8px; color: #FFFFFF;
}
QComboBox:hover, QSpinBox:hover, QTextEdit:hover, QLineEdit:hover, QListWidget:hover { border: 1px solid #00E676; }
QComboBox QAbstractItemView { background-color: #1E1E24; color: #FFFFFF; selection-background-color: #00E676; selection-color: #000000; border: 1px solid #444; }
QSlider::groove:horizontal { border-radius: 4px; height: 8px; background: #1E1E24; border: 1px solid #333; }
QSlider::handle:horizontal { background: #00E676; border-radius: 8px; width: 16px; height: 16px; margin: -4px 0; }
QScrollBar:vertical { background: #1A1A1A; width: 12px; }
QScrollBar::handle:vertical { background: #444; border-radius: 6px; min-height: 20px; }
QScrollBar::handle:vertical:hover { background: #00E676; }
QCheckBox::indicator { width: 18px; height: 18px; border-radius: 4px; border: 1px solid #555; background: #1E1E24; }
QCheckBox::indicator:checked { background: #00E676; border: 1px solid #00E676; }
QSplitter::handle { background-color: #2A2A30; width: 2px; }
"""

class PanelWindow(QWidget):
    visibility_changed = Signal(bool)

    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setWindowFlags(Qt.WindowType.Tool)
        self.setObjectName("PanelWindow")

    def closeEvent(self, event):
        self.visibility_changed.emit(False)
        super().closeEvent(event)

    def showEvent(self, event):
        self.visibility_changed.emit(True)
        super().showEvent(event)


class PresetButton(QPushButton):
    right_clicked = Signal()
    left_clicked = Signal()

    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.left_clicked.emit()
        elif event.button() == Qt.MouseButton.RightButton:
            self.right_clicked.emit()
        super().mousePressEvent(event)


class ObsbotConnectThread(QThread):
    finished = Signal(bool)

    def __init__(self, obsbot, reconnect=False):
        super().__init__()
        self.obsbot = obsbot
        self.reconnect = reconnect

    def run(self):
        if self.reconnect:
            self.obsbot.disconnect()
            success = self.obsbot.connect()
        else:
            success = self.obsbot.init() and self.obsbot.connect()
        self.finished.emit(bool(success))


class ClickableVideoLabel(QLabel):
    single_clicked = Signal(int, int)
    double_clicked = Signal(int, int)
    right_clicked = Signal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.click_timer = QTimer(self)
        self.click_timer.setSingleShot(True)
        self.click_timer.setInterval(250)  # 250ms debounce for double click
        self.click_timer.timeout.connect(self._emit_single_click)
        self.last_click_pos = None

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.last_click_pos = (event.position().x(), event.position().y())
            self.click_timer.start()
        elif event.button() == Qt.MouseButton.RightButton:
            self.right_clicked.emit(int(event.position().x()), int(event.position().y()))
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.click_timer.stop()  # Cancel single click
            self.double_clicked.emit(int(event.position().x()), int(event.position().y()))
        super().mouseDoubleClickEvent(event)

    def _emit_single_click(self):
        if self.last_click_pos:
            self.single_clicked.emit(int(self.last_click_pos[0]), int(self.last_click_pos[1]))


class HardwareManager:
    """Manages the lifecycle of hardware resources to prevent leaks."""

    def __init__(self):
        self.cap = None
        self.fake_cam = None
        self.renderer = None

    def open_input(self, index, width, height):
        self.close_input()
        global_logger.info(f"HardwareManager: Opening input {index}")
        # Force V4L2 backend to prevent multiple backend probes leaking FDs
        self.cap = cv2.VideoCapture(index, cv2.CAP_V4L2)
        if self.cap.isOpened():
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
            self.cap.set(cv2.CAP_PROP_FPS, 100)
            self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(
                'M', 'J', 'P', 'G'))  # Often better for webcams
        else:
            self.cap = None
        return self.cap is not None

    def open_output(self, device, width, height):
        self.close_output()
        global_logger.info(f"HardwareManager: Opening output {device}")

        # Track FDs to prevent pyfakewebcam constructor leaks
        fds_before = set(os.listdir('/proc/self/fd')
                         ) if os.path.exists('/proc/self/fd') else set()
        try:
            self.fake_cam = pyfakewebcam.FakeWebcam(device, width, height)
            return True
        except Exception as e:
            # Clean up the exact FD leaked by this failed initialization
            fds_after = set(os.listdir('/proc/self/fd')
                            ) if os.path.exists('/proc/self/fd') else set()
            for fd_str in fds_after - fds_before:
                try:
                    fd = int(fd_str)
                    path = os.readlink(f"/proc/self/fd/{fd_str}")
                    if device in path:
                        os.close(fd)
                        global_logger.warning(
                            f"HardwareManager: Plugged FakeWebcam leak on FD {fd}")
                except:
                    pass
            raise e

    def close_input(self):
        if self.cap:
            global_logger.info("HardwareManager: Closing input")
            try:
                self.cap.release()
            except:
                pass
            self.cap = None

    def close_output(self):
        if self.fake_cam:
            global_logger.info("HardwareManager: Closing output")
            try:
                if hasattr(self.fake_cam, '_video_device'):
                    fd = self.fake_cam._video_device
                    if fd > 0:
                        os.close(fd)
                        self.fake_cam._video_device = -1
                        global_logger.info(f"HardwareManager: Successfully closed FD {fd}")
            except Exception as e:
                global_logger.error(f"HardwareManager: Error closing FD: {e}")
            self.fake_cam = None

    def release_renderer(self):
        if self.renderer:
            global_logger.info("HardwareManager: Releasing renderer")
            try:
                if hasattr(self.renderer, 'release'):
                    self.renderer.release()
                elif hasattr(self.renderer, 'ctx'):
                    self.renderer.ctx.release()
            except Exception as e:
                global_logger.error(f"HardwareManager: Error releasing renderer: {e}")
            self.renderer = None

    def cleanup_all(self):
        global_logger.info("HardwareManager: cleanup_all() called")
        self.close_input()
        self.close_output()
        self.release_renderer()


class ZenithWorker(QObject):
    """Worker class for processing camera feed in a separate thread."""
    change_pixmap_signal = Signal(QImage)
    raw_pixmap_signal = Signal(QImage)
    status_signal = Signal(str)
    finished = Signal()
    
    # New Signals for Ninja Features
    gesture_detected = Signal(str)
    nsfw_detected = Signal()
    broll_trigger = Signal()
    posture_detected = Signal(str)

    def __init__(self, params):
        super().__init__()
        self.params = params
        self.running = False
        self.hw = HardwareManager()
        self.ml_pipeline = None
        self.ptz = None

        # Internal state
        self.last_ptz_time = 0.0
        self.last_cx = 0.0
        self.last_cy = 0.0
        self._last_zoom = 1.0
        self._last_led = None
        self.frame_count = 0
        self.last_crop_rect = None

    def handle_click(self, lx, ly, lw, lh, action):
        if not self.ptz or not self.last_crop_rect: return
        cx, cy, cw, ch = self.last_crop_rect
        # Map label click to source image coordinates
        source_x = cx + (lx / lw) * cw
        source_y = cy + (ly / lh) * ch

        if action == "single":
            self.ptz.set_manual_center(source_x, source_y)
        elif action == "zoom_in":
            self.ptz.adjust_zoom(0.5)
        elif action == "zoom_out":
            self.ptz.adjust_zoom(-0.5)
        elif action == "resume":
            self.ptz.manual_mode = False

    @Slot()
    def process(self):
        self.running = True
        try:
            self._run_loop()
        except Exception as e:
            global_logger.error(f"Worker crash: {e}")
            self.status_signal.emit(f"Error: {e}")
        finally:
            self._cleanup()
            self.finished.emit()

    def _cleanup(self):
        self.running = False
        if self.ml_pipeline:
            self.ml_pipeline.stop()
            self.ml_pipeline = None
        self.hw.cleanup_all()

    def stop(self):
        self.running = False

    def _run_loop(self):
        p = self.params
        profiler = HardwareProfiler()
        hw_config = profiler.probe_system()

        if not self.hw.open_input(p['input_source'], p['output_width'], p['output_height']):
            self.status_signal.emit("Error: Could not open input camera.")
            return

        ret, test_frame = self.hw.cap.read()
        if not ret:
            self.status_signal.emit("Error: Cannot read from camera.")
            return

        cam_h, cam_w = test_frame.shape[:2]
        target_ratio = p['output_width'] / p['output_height']

        # Correct dimensions for PTZ and Renderer
        if abs((cam_w/cam_h) - target_ratio) > 0.01:
            if (cam_w/cam_h) > target_ratio:
                cam_w = int(cam_h * target_ratio)
            else:
                cam_h = int(cam_w / target_ratio)

        try:
            self.hw.open_output(p['output_device'],
                                p['output_width'], p['output_height'])
        except Exception as e:
            err_msg = str(e)
            advice = "Device is likely IN USE. Close Browser/Zoom and retry." if "22" in err_msg else "Check v4l2loopback."
            self.status_signal.emit(f"Virtual Cam Error: {advice}")
            # Non-fatal if you just want to see previews

        try:
            self.ml_pipeline = MLPipeline(
                p['model_path'], hw_config, p['target_class_ids'], p['blur_class_ids'])
                
            # Connect ML Pipeline callbacks to ZenithWorker signals
            self.ml_pipeline.gesture_callback = self.gesture_detected.emit
            self.ml_pipeline.nsfw_callback = self.nsfw_detected.emit
            self.ml_pipeline.broll_callback = self.broll_trigger.emit
            self.ml_pipeline.pose_callback = self.posture_detected.emit
            
            self.ml_pipeline.start()
        except Exception as e:
            self.status_signal.emit(f"ML Pipeline Error: {e}")
            return

        self.ptz = PTZCamera(
            cam_w, cam_h, target_w=p['output_width'], target_h=p['output_height'], smoothing_factor=p['smooth_factor'])
        self.hw.renderer = Renderer(cam_w, cam_h)
        self.hw.renderer.set_config(hw_config)

        if p['obsbot'] and p['obsbot'].connected:
            try:
                p['obsbot'].set_ai_mode(0)
            except:
                pass

        self.status_signal.emit("Tracking active.")

        while self.running:
            ret, frame = self.hw.cap.read()
            if not ret:
                break
            
            self.frame_count += 1

            # 16:9 Normalize
            h, w = frame.shape[:2]
            if abs((w/h) - target_ratio) > 0.01:
                if (w/h) > target_ratio:
                    nw = int(h * target_ratio)
                    xo = (w - nw) // 2
                    frame = frame[:, xo:xo+nw]
                else:
                    nh = int(w / target_ratio)
                    yo = (h - nh) // 2
                    frame = frame[yo:yo+nh, :]

            if p['flip_video']:
                frame = cv2.flip(frame, 0)

            # Sync dynamic parameters
            self.ml_pipeline.target_classes = p['target_class_ids']
            self.ml_pipeline.blur_classes = p['blur_class_ids']
            self.ptz.margin_percentage = p['zoom_margin'] / 100.0

            zoom_boxes, blur_boxes = self.ml_pipeline.process_frame(frame)
            
            if not p['hold_ptz']:
                crop_rect = self.ptz.update(zoom_boxes)
            else:
                # If hold is active, keep using the last valid crop_rect
                # but we still need an initial value if we started on Hold
                if not hasattr(self, 'last_crop_rect') or self.last_crop_rect is None:
                    # Default to full frame if no previous rect
                    crop_rect = (0, 0, cam_w, cam_h)
                else:
                    crop_rect = self.last_crop_rect
            
            self.last_crop_rect = crop_rect

            # SDK Interaction
            obs = p['obsbot']
            if obs and obs.connected and p['enable_physical_ptz']:
                self._handle_obsbot(
                    obs, zoom_boxes, blur_boxes, cam_w, cam_h, p)

            # Render
            rendered = self.hw.renderer.render(cv2.cvtColor(
                frame, cv2.COLOR_BGR2RGB), crop_rect, blur_boxes)

            # Output
            if self.hw.fake_cam:
                try:
                    out = rendered if rendered.shape[1] == p['output_width'] else cv2.resize(
                        rendered, (p['output_width'], p['output_height']))
                    self.hw.fake_cam.schedule_frame(out)
                except:
                    pass

            if p.get('active_streams'):
                frame_bytes = rendered.tobytes() if rendered.shape[1] == p['output_width'] else cv2.resize(
                    rendered, (p['output_width'], p['output_height'])).tobytes()
                dead_streams = []
                for sp in p['active_streams']:
                    if sp.poll() is None:
                        try:
                            sp.stdin.write(frame_bytes)
                        except Exception:
                            pass
                    else:
                        dead_streams.append(sp)
                for sp in dead_streams:
                    p['active_streams'].remove(sp)

            if p['show_input_preview']:
                self.raw_pixmap_signal.emit(self._to_qt(frame))
            if p['show_output_preview']:
                prev = rendered.copy()
                if p['draw_preview_roi']:
                    for (bx, by, bw, bh) in zoom_boxes:
                        cv2.rectangle(
                            prev, (bx-crop_rect[0], by-crop_rect[1]), (bx+bw-crop_rect[0], by+bh-crop_rect[1]), (0, 255, 0), 2)
                    for (bx, by, bw, bh) in blur_boxes:
                        cv2.rectangle(
                            prev, (bx-crop_rect[0], by-crop_rect[1]), (bx+bw-crop_rect[0], by+bh-crop_rect[1]), (255, 0, 0), 2)
                self.change_pixmap_signal.emit(self._to_qt(
                    cv2.cvtColor(prev, cv2.COLOR_RGB2BGR)))

    def _handle_obsbot(self, obs, zoom_boxes, blur_boxes, cam_w, cam_h, p):
        now = time.time()
        
        # If HOLD is active, skip all automatic tracking and applying speed.
        if p['hold_ptz']:
            # We already set speed to 0 when hold was toggled, but good to ensure
            # we also apply manual zoom if it's changing
            if abs(self._last_zoom - p['manual_zoom']) > 0.01:
                obs.set_zoom(p['manual_zoom'])
                self._last_zoom = p['manual_zoom']
            return

        try:
            if zoom_boxes and (now - self.last_ptz_time > 0.15):
                min_x = min(b[0] for b in zoom_boxes)
                min_y = min(b[1] for b in zoom_boxes)
                max_x = max(b[0] + b[2] for b in zoom_boxes)
                max_y = max(b[1] + b[3] for b in zoom_boxes)
    
                if p['enable_onboard_tracker']:
                    obs.set_track_target(
                        float(min_x/cam_w), float(min_y/cam_h), float(max_x/cam_w), float(max_y/cam_h))
                else:
                    cx, cy = ((min_x + max_x) / 2) / cam_w - \
                        0.5, ((min_y + max_y) / 2) / cam_h - 0.5
                    dt = max(0.01, now - self.last_ptz_time)
                    dcx, dcy = (cx - self.last_cx) / dt, (cy - self.last_cy) / dt
                    self.last_cx, self.last_cy = cx, cy
                    zs = self._last_zoom
                    kp_p, kd_p = (60.0 + (p['smooth_factor'] * 80.0)) / \
                        zs, (5.0 + (p['smooth_factor'] * 15.0)) / zs
                    kp_t, kd_t = (40.0 + (p['smooth_factor'] * 40.0)) / \
                        zs, (3.0 + (p['smooth_factor'] * 10.0)) / zs
                    ps = float(np.clip(cx * kp_p + dcx * kd_p, -
                               60.0, 60.0)) if abs(cx) > 0.05 else 0.0
                    ts = float(np.clip(cy * kp_t + dcy * kd_t, -
                               40.0, 40.0)) if abs(cy) > 0.05 else 0.0
                    obs.set_gimbal_speed(ts, ps)
    
                self.last_ptz_time = now
                sm = max((max_x - min_x) / cam_w, (max_y - min_y) / cam_h)
                if sm > 0:
                    tz = np.clip(0.4 / sm, 1.0, 2.0)
                    zv = p['smooth_factor'] * tz + \
                        (1 - p['smooth_factor']) * self._last_zoom
                    if abs(self._last_zoom - zv) > 0.01:
                        obs.set_zoom(zv)
                        self._last_zoom = zv
            elif not zoom_boxes and not p['enable_onboard_tracker']:
                obs.set_gimbal_speed(0.0, 0.0)
    
            should_led = len(blur_boxes) > 0
            if self._last_led != should_led:
                obs.set_led(should_led)
                self._last_led = should_led
        except Exception as e:
            global_logger.error(f"OBSBOT Hardware SDK Error: {e}")
            obs.connected = False

    def _to_qt(self, img):
        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        return QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888).copy()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ZenithCam: Control Hub")
        self.setMinimumSize(1, 1)
        self.resize(600, 800)

        self.presets = {"Home": (0, 0, 1.0), "P1": (
            0, 0, 1.0), "P2": (0, 0, 1.0)}

        # Tracking Parameters
        self.wb_worker = None
        self.params = {
            'input_source': 1,
            'output_device': "/dev/video20",
            'model_path': os.path.join(os.path.dirname(__file__), "models/erax_nsfw_yolo11n.onnx"),
            'target_class_ids': [3, 4],
            'blur_class_ids': [99],
            'nsfw_classes': [0, 1, 2], # Assuming classes 0,1,2 are NSFW (make_love, etc.)
            'safe_zone': [0.1, 0.1, 0.9, 0.9], # 10% margin on all sides
            'smooth_factor': 0.02,
            'zoom_margin': 45,
            'output_width': 1280,
            'output_height': 720,
            'draw_preview_roi': True,
            'draw_output_roi': False,
            'flip_video': False,
            'show_input_preview': True,
            'blur_type': 'pixelate',
            'show_output_preview': True,
            'enable_physical_ptz': False,
            'enable_onboard_tracker': False,
            'hold_ptz': False,
            'manual_zoom': 1.0,
            'obsbot': None,
            'rtmp_url': "rtmp://localhost:1935/live",
            'stream_key': "test",
            'active_streams': []
        }

        self.stream_process = None

        self.obsbot = OBSBOTSDK()
        self.params['obsbot'] = self.obsbot
        QTimer.singleShot(100, self.async_init_obsbot)

        self.worker = None
        self.thread = None
        self.is_tracking = False
        self.is_shutting_down = False
        self.is_transitioning = False

        # Initialize Web Bridge for Tampermonkey integration
        
        # Telemetry Timer
        self.telemetry_timer = QTimer(self)
        self.telemetry_timer.timeout.connect(self._broadcast_telemetry)
        self.telemetry_timer.start(500)

        self.panels = {}

        # --- PANEL 1: CONFIG ---
        self.config_window = PanelWindow("⚙️ Config", self)
        self.config_window.resize(400, 750)
        self.panels["config"] = self.config_window
        config_layout = QVBoxLayout(self.config_window)

        self.settings_scroll = QScrollArea()
        self.settings_scroll.setWidgetResizable(True)
        self.settings_scroll.setStyleSheet(
            "border: none; background: transparent;")
        settings_container = QWidget()
        settings_layout = QVBoxLayout(settings_container)

        preset_group = QGroupBox("Presets / Tags")
        preset_layout = QHBoxLayout(preset_group)
        self.preset_combo = QComboBox()
        self.preset_combo.setEditable(True)
        self.preset_combo.lineEdit().setPlaceholderText("Enter tag name...")
        self.preset_combo.currentIndexChanged.connect(self.on_preset_selected)
        btn_save_preset = QPushButton("Save")
        btn_save_preset.clicked.connect(self.save_current_preset)
        btn_del_preset = QPushButton("Del")
        btn_del_preset.clicked.connect(self.delete_current_preset)
        preset_layout.addWidget(self.preset_combo, stretch=1)
        preset_layout.addWidget(btn_save_preset)
        preset_layout.addWidget(btn_del_preset)
        settings_layout.addWidget(preset_group)

        conf_group = QGroupBox("Device Settings")
        group_layout = QVBoxLayout(conf_group)

        cam_row = QHBoxLayout()
        cam_row.addWidget(QLabel("Input Camera:"))
        self.input_spin = QSpinBox()
        def_idx = 1  # Will be auto-detected on engine start via find_obsbot_capture_index()
        self.input_spin.setValue(def_idx)
        cam_row.addWidget(self.input_spin)
        group_layout.addLayout(cam_row)

        out_row = QHBoxLayout()
        out_row.addWidget(QLabel("Virtual Output:"))
        self.refresh_btn = QPushButton("↻")
        self.refresh_btn.setFixedSize(30, 30)
        self.refresh_btn.clicked.connect(self.refresh_output_devices)
        out_row.addWidget(self.refresh_btn)
        group_layout.addLayout(out_row)
        self.output_edit = QComboBox()
        self.output_edit.setEditable(True)
        self.output_edit.setFixedHeight(35)
        group_layout.addWidget(self.output_edit)
        self.refresh_output_devices()

        m_row = QHBoxLayout()
        m_row.addWidget(QLabel("Model:"))
        self.model_label = QLabel("YOLO (Default)")
        self.model_label.setStyleSheet("color: #00E676; font-size: 11px;")
        self.model_btn = QPushButton("📁")
        self.model_btn.setFixedSize(30, 30)
        self.model_btn.clicked.connect(self.select_model)
        m_row.addWidget(self.model_label)
        m_row.addWidget(self.model_btn)
        group_layout.addLayout(m_row)

        group_layout.addWidget(QLabel("Target Classes (Zoom):"))
        self.class_scroll = QScrollArea()
        self.class_scroll.setMinimumHeight(100)
        self.class_container = QWidget()
        self.class_layout = QVBoxLayout(self.class_container)
        self.class_scroll.setWidget(self.class_container)
        self.class_scroll.setWidgetResizable(True)
        group_layout.addWidget(self.class_scroll)

        group_layout.addWidget(QLabel("Blur Classes:"))
        self.blur_scroll = QScrollArea()
        self.blur_scroll.setMinimumHeight(100)
        self.blur_container = QWidget()
        self.blur_layout = QVBoxLayout(self.blur_container)
        self.blur_scroll.setWidget(self.blur_container)
        self.blur_scroll.setWidgetResizable(True)
        group_layout.addWidget(self.blur_scroll)

        group_layout.addWidget(QLabel("PTZ Smoothing:"))
        self.smooth_slider = QSlider(Qt.Orientation.Horizontal)
        self.smooth_slider.setRange(1, 100)
        self.smooth_slider.setValue(10)
        self.smooth_slider.valueChanged.connect(self.update_smoothing)
        group_layout.addWidget(self.smooth_slider)

        group_layout.addWidget(QLabel("Zoom Margin (%):"))
        self.margin_spin = QSpinBox()
        self.margin_spin.setRange(0, 100)
        self.margin_spin.setValue(20)
        self.margin_spin.valueChanged.connect(self.update_margin)
        group_layout.addWidget(self.margin_spin)

        settings_layout.addWidget(conf_group)
        settings_layout.addStretch()
        self.settings_scroll.setWidget(settings_container)
        config_layout.addWidget(self.settings_scroll)

        # --- PANEL 2: INPUT PREVIEW ---
        self.input_preview_window = PanelWindow("📸 Raw Camera Feed", self)
        self.input_preview_window.resize(640, 360)
        self.panels["raw"] = self.input_preview_window
        in_l = QVBoxLayout(self.input_preview_window)
        self.input_preview_label = QLabel("Waiting for camera...")
        self.input_preview_label.setMinimumSize(1, 1)
        self.input_preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        in_l.addWidget(self.input_preview_label)

        # --- PANEL 3: OUTPUT PREVIEW ---
        self.output_preview_window = PanelWindow("🧠 AI Processed View", self)
        self.output_preview_window.resize(800, 450)
        self.panels["ai"] = self.output_preview_window
        out_l = QVBoxLayout(self.output_preview_window)
        self.output_preview_label = ClickableVideoLabel("Waiting for AI processing...")
        self.output_preview_label.setMinimumSize(1, 1)
        self.output_preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.output_preview_label.single_clicked.connect(self.on_output_single_click)
        self.output_preview_label.double_clicked.connect(self.on_output_double_click)
        self.output_preview_label.right_clicked.connect(self.on_output_right_click)
        out_l.addWidget(self.output_preview_label)

        # --- PANEL 4: STREAMING ---
        self.streaming_window = PanelWindow("📡 Broadcast Engine", self)
        self.streaming_window.resize(450, 500)
        self.panels["stream"] = self.streaming_window
        stream_layout = QVBoxLayout(self.streaming_window)

        # Profile Management & Streaming
        self.profiles_file = os.path.join(
            os.path.dirname(__file__), "profiles.json")
        self.stream_profiles = []
        self.load_profiles()
        self.active_streams = []

        prof_row1 = QHBoxLayout()
        self.profile_combo = QComboBox()
        self.profile_combo.setFixedHeight(35)
        self.profile_combo.currentIndexChanged.connect(
            self.on_profile_selected)
        prof_row1.addWidget(self.profile_combo, stretch=1)

        btn_add = QPushButton("+")
        btn_add.setFixedSize(35, 35)
        btn_add.clicked.connect(self.add_profile)
        btn_del = QPushButton("-")
        btn_del.setFixedSize(35, 35)
        btn_del.clicked.connect(self.delete_profile)
        btn_save = QPushButton("💾")
        btn_save.setFixedSize(35, 35)
        btn_save.clicked.connect(self.save_current_profile)
        prof_row1.addWidget(btn_add)
        prof_row1.addWidget(btn_del)
        prof_row1.addWidget(btn_save)
        stream_layout.addLayout(prof_row1)

        self.prof_name_edit = QLineEdit()
        self.prof_name_edit.setFixedHeight(35)
        self.prof_name_edit.setPlaceholderText("Profile Name")
        stream_layout.addWidget(self.prof_name_edit)
        self.prof_site_edit = QLineEdit()
        self.prof_site_edit.setFixedHeight(35)
        self.prof_site_edit.setPlaceholderText("Site")
        stream_layout.addWidget(self.prof_site_edit)
        self.rtmp_url_edit = QLineEdit()
        self.rtmp_url_edit.setFixedHeight(35)
        self.rtmp_url_edit.setPlaceholderText("RTMP URL")
        stream_layout.addWidget(self.rtmp_url_edit)
        self.stream_key_edit = QLineEdit()
        self.stream_key_edit.setFixedHeight(35)
        self.stream_key_edit.setPlaceholderText(
            "Key")
        self.stream_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        stream_layout.addWidget(self.stream_key_edit)

        br_layout = QHBoxLayout()
        br_layout.addWidget(QLabel("Quality:"))
        self.bitrate_combo = QComboBox()
        self.bitrate_combo.addItems(
            ["Fast/WiFi (3000 kbps)", "Medium (4500 kbps)", "High/Ethernet (6000 kbps)"])
        self.bitrate_combo.setCurrentIndex(0)
        br_layout.addWidget(self.bitrate_combo)
        
        br_layout.addWidget(QLabel("Encoder:"))
        self.encoder_combo = QComboBox()
        self.encoder_combo.addItems(["CPU (x264)", "NVIDIA (NVENC)", "AMD/Intel (VA-API)"])
        self.encoder_combo.setCurrentIndex(0)
        br_layout.addWidget(self.encoder_combo)
        stream_layout.addLayout(br_layout)

        stream_layout.addWidget(QLabel("Simultaneous Streaming (Max 3):"))
        self.stream_checkboxes = []
        self.chk_layout = QVBoxLayout()
        stream_layout.addLayout(self.chk_layout)
        self.refresh_profile_ui()

        self.stream_btn = QPushButton("Start Broadcast")
        self.stream_btn.setObjectName("StreamBtn")
        self.stream_btn.setStyleSheet(
            "background-color: #2979FF; padding: 12px; font-weight: bold; border-radius: 6px; color: #FFFFFF;")
        self.stream_btn.clicked.connect(self.toggle_streaming)
        stream_layout.addWidget(self.stream_btn)
        stream_layout.addStretch()

        # --- PANEL 5: PTZ ---
        self.ptz_window = PanelWindow("🕹️ PTZ Controls", self)
        self.ptz_window.resize(400, 600)
        self.panels["ptz"] = self.ptz_window
        ptz_layout = QVBoxLayout(self.ptz_window)

        hardware_group = QGroupBox("Robot Control")
        hw_layout = QVBoxLayout(hardware_group)
        self.reconnect_obsbot_btn = QPushButton("🔌 Connect OBSBOT")
        self.reconnect_obsbot_btn.clicked.connect(self.reconnect_obsbot)
        hw_layout.addWidget(self.reconnect_obsbot_btn)

        # Bluetooth Controls
        bt_row = QHBoxLayout()
        self.use_bt_cb = QCheckBox("Bluetooth Mode")
        self.use_bt_cb.stateChanged.connect(self.toggle_bluetooth_mode)
        self.scan_bt_btn = QPushButton("🔍 Scan")
        self.scan_bt_btn.setFixedWidth(60)
        self.scan_bt_btn.setEnabled(False)
        self.scan_bt_btn.clicked.connect(self.scan_bluetooth)
        bt_row.addWidget(self.use_bt_cb)
        bt_row.addWidget(self.scan_bt_btn)
        hw_layout.addLayout(bt_row)

        self.bt_device_combo = QComboBox()
        self.bt_device_combo.setPlaceholderText("Select Bluetooth Camera...")
        self.bt_device_combo.setVisible(False)
        self.bt_device_combo.currentIndexChanged.connect(self.connect_bluetooth_device)
        hw_layout.addWidget(self.bt_device_combo)

        self.ptz_cb = QCheckBox("Enable Physical PTZ")
        self.ptz_cb.stateChanged.connect(self.toggle_ptz)
        hw_layout.addWidget(self.ptz_cb)
        self.onboard_tracker_cb = QCheckBox("Use Onboard AI Tracker")
        self.onboard_tracker_cb.setStyleSheet(
            "color: #80CBC4; padding-left: 20px;")
        self.onboard_tracker_cb.stateChanged.connect(
            self.toggle_onboard_tracker)
        hw_layout.addWidget(self.onboard_tracker_cb)

        hw_layout.addWidget(QLabel("OBSBOT AI Mode:"))
        self.obsbot_ai_combo = QComboBox()
        self.obsbot_ai_combo.addItems(
            ["None", "Group", "Human", "Hand", "Whiteboard", "Desk"])
        self.obsbot_ai_combo.currentIndexChanged.connect(
            self.change_obsbot_ai_mode)
        hw_layout.addWidget(self.obsbot_ai_combo)

        self.submode_label = QLabel("Sub-Mode:")
        self.obsbot_submode_combo = QComboBox()
        self.obsbot_submode_combo.addItem("Default")
        self.obsbot_submode_combo.currentIndexChanged.connect(
            self.change_obsbot_submode)
        self.submode_label.setVisible(False)
        self.obsbot_submode_combo.setVisible(False)
        hw_layout.addWidget(self.submode_label)
        hw_layout.addWidget(self.obsbot_submode_combo)
        self.privacy_cb = QCheckBox("Hardware Privacy Mode")
        self.privacy_cb.stateChanged.connect(self.toggle_privacy)
        hw_layout.addWidget(self.privacy_cb)
        ptz_layout.addWidget(hardware_group)

        manual_group = QGroupBox("Manual Movement")
        manual_layout = QVBoxLayout(manual_group)

        self.hold_ptz_cb = QCheckBox("HOLD CAMERA (Lock)")
        self.hold_ptz_cb.setStyleSheet("color: #FF5252; font-weight: bold;")
        self.hold_ptz_cb.stateChanged.connect(self.toggle_hold_ptz)
        manual_layout.addWidget(self.hold_ptz_cb)

        manual_layout.addWidget(QLabel("Manual Zoom Override:"))
        self.manual_zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self.manual_zoom_slider.setRange(10, 20) # 1.0x to 2.0x
        self.manual_zoom_slider.setValue(10)
        self.manual_zoom_slider.valueChanged.connect(self.update_manual_zoom)
        manual_layout.addWidget(self.manual_zoom_slider)

        p_row = QHBoxLayout()
        for p_name in ["Home", "P1", "P2"]:
            btn = PresetButton(p_name)
            btn.setStyleSheet(
                "background-color: #333; padding: 8px; font-size: 12px; border: 1px solid #555; border-radius: 4px;")
            btn.left_clicked.connect(lambda n=p_name: self.recall_preset(n))
            btn.right_clicked.connect(lambda n=p_name: self.save_preset(n))
            p_row.addWidget(btn)
        manual_layout.addLayout(p_row)

        dpad = QGridLayout()
        self.btn_up, self.btn_down, self.btn_left, self.btn_right, self.btn_center = QPushButton(
            "▲"), QPushButton("▼"), QPushButton("◄"), QPushButton("►"), QPushButton("●")
        self.btn_reset_gimbal = QPushButton("⚡")
        self.btn_reset_gimbal.setToolTip("Reset Gimbal")
        self.btn_up.pressed.connect(lambda: self.start_manual_move(0, 1))
        self.btn_down.pressed.connect(lambda: self.start_manual_move(0, -1))
        self.btn_left.pressed.connect(lambda: self.start_manual_move(1, 0))
        self.btn_right.pressed.connect(lambda: self.start_manual_move(-1, 0))
        for b in [self.btn_up, self.btn_down, self.btn_left, self.btn_right]:
            b.released.connect(self.stop_manual_move)
        self.btn_center.clicked.connect(self.manual_center)
        self.btn_reset_gimbal.clicked.connect(self.reset_gimbal)
        for b in [self.btn_up, self.btn_down, self.btn_left, self.btn_right, self.btn_center, self.btn_reset_gimbal]:
            b.setStyleSheet(
                "background-color: #333; padding: 10px; border-radius: 4px;")
        self.btn_reset_gimbal.setStyleSheet(
            "background-color: #5C2222; color: #FF8A80; font-weight: bold; padding: 10px; border-radius: 4px;")
        dpad.addWidget(self.btn_up, 0, 1)
        dpad.addWidget(self.btn_left, 1, 0)
        dpad.addWidget(self.btn_center, 1, 1)
        dpad.addWidget(self.btn_right, 1, 2)
        dpad.addWidget(
            self.btn_down, 2, 1)
        dpad.addWidget(self.btn_reset_gimbal, 2, 2)
        manual_layout.addLayout(dpad)

        z_row = QHBoxLayout()
        self.btn_zoom_in, self.btn_zoom_out = QPushButton(
            "Zoom +"), QPushButton("Zoom -")
        self.btn_zoom_in.setStyleSheet(
            "background-color: #333; padding: 10px; border-radius: 4px;")
        self.btn_zoom_out.setStyleSheet(
            "background-color: #333; padding: 10px; border-radius: 4px;")
        self.btn_zoom_in.pressed.connect(lambda: self.start_manual_zoom(1))
        self.btn_zoom_out.pressed.connect(lambda: self.start_manual_zoom(-1))
        self.btn_zoom_in.released.connect(self.stop_manual_move)
        self.btn_zoom_out.released.connect(self.stop_manual_move)
        z_row.addWidget(self.btn_zoom_out)
        z_row.addWidget(self.btn_zoom_in)
        manual_layout.addLayout(z_row)
        ptz_layout.addWidget(manual_group)
        ptz_layout.addStretch()

        # --- PANEL 6: HARDWARE DASHBOARD ---
        self.hw_window = PanelWindow("📊 System Dashboard", self)
        self.hw_window.resize(600, 800)
        self.panels["hw"] = self.hw_window
        hw_l = QVBoxLayout(self.hw_window)
        
        self.hw_cpu_label = QLabel("CPU Usage: --%")
        self.hw_ram_label = QLabel("RAM Usage: --%")
        self.hw_fps_label = QLabel("Output FPS: --")
        
        hw_l.addWidget(self.hw_cpu_label)
        hw_l.addWidget(self.hw_ram_label)
        hw_l.addWidget(self.hw_fps_label)

        # --- PANEL 7: STUDIO EFFECTS ---
        self.effects_window = PanelWindow("✨ Studio Effects", self)
        self.effects_window.resize(400, 400)
        self.panels["effects"] = self.effects_window
        effects_layout = QVBoxLayout(self.effects_window)
        
        visual_group = QGroupBox("Visual Shaders")
        v_layout = QVBoxLayout(visual_group)
        v_layout.addWidget(QLabel("Privacy Mask Style:"))
        self.shader_combo = QComboBox()
        self.shader_combo.addItems(["Gaussian Blur", "8-Bit Pixelation", "Cyber-Glitch", "Neon Edge-Glow"])
        self.shader_combo.setCurrentIndex(1)
        self.shader_combo.currentIndexChanged.connect(self.update_shader_style)
        v_layout.addWidget(self.shader_combo)
        
        v_layout.addWidget(QLabel("Stream Interactivity:"))
        self.hype_train_cb = QCheckBox("Hype Train Camera Shake (Tips)")
        self.fps_mouse_cb = QCheckBox("FPS-Style Mouse Look (Hold Alt)")
        v_layout.addWidget(self.hype_train_cb)
        v_layout.addWidget(self.fps_mouse_cb)
        
        v_layout.addWidget(QLabel("AI Automation:"))
        self.posture_cb = QCheckBox("Posture-Triggered PTZ (Sit/Stand)")
        self.idle_wander_cb = QCheckBox("Idle Auto-Pilot (Wander)")
        v_layout.addWidget(self.posture_cb)
        v_layout.addWidget(self.idle_wander_cb)
        
        effects_layout.addWidget(visual_group)
        effects_layout.addStretch()
        
        # --- PANEL 8: LIVE CHAT ---
        self.chat_window = PanelWindow("💬 Live Chat", self)
        self.chat_window.resize(400, 600)
        self.panels["chat"] = self.chat_window
        chat_layout = QVBoxLayout(self.chat_window)
        self.chat_list = QListWidget()
        self.chat_list.setStyleSheet("background-color: #1A1A1D; border: none;")
        self.chat_list.addItem("System: Unified Chat Aggregator initialized.")
        self.chat_list.addItem("System: Waiting for browser web hook...")
        chat_layout.addWidget(self.chat_list)

        # --- PANEL 9: DEBUG LOGS ---
        self.debug_window = PanelWindow("📝 Logs", self)
        self.debug_window.resize(600, 400)
        self.panels["debug"] = self.debug_window
        debug_l = QVBoxLayout(self.debug_window)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        debug_l.addWidget(self.log_text)

        # --- BOTTOM TASKBAR ---
        self.taskbar = QWidget()
        self.taskbar.setObjectName("TaskBar")
        taskbar_layout = QVBoxLayout(self.taskbar)
        taskbar_layout.setContentsMargins(15, 15, 15, 15)
        taskbar_layout.setSpacing(10)
        
        header_layout = QHBoxLayout()
        toggles_layout = QGridLayout()
        options_layout = QHBoxLayout()

        self.app_menu_btn = QPushButton("💠")
        self.app_menu_btn.setStyleSheet("font-size: 24px; color: #00E676; padding: 5px 15px;")
        self.app_menu_btn.clicked.connect(self.show_launcher_menu)
        header_layout.addWidget(self.app_menu_btn)
        header_layout.addStretch()

        # Clock and System Info
        self.clock_label = QLabel()
        self.clock_label.setStyleSheet(
            "color: #AAA; font-weight: bold; font-family: monospace; margin-right: 10px;")
        header_layout.addWidget(self.clock_label)

        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(self.update_clock)
        self.clock_timer.start(1000)
        self.update_clock()
        
        self.status_label = QLabel("Status: Idle")
        self.status_label.setStyleSheet(
            "color: #00E676; font-weight: bold; margin-right: 15px;")
        header_layout.addWidget(self.status_label)

        self.start_btn = QPushButton("▶ START ENGINE")
        self.start_btn.setObjectName("StartBtn")
        self.start_btn.clicked.connect(self.toggle_tracking)
        header_layout.addWidget(self.start_btn)

        # Taskbar buttons to toggle windows
        def create_toggle(label, window_key):
            window = self.panels[window_key]
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setChecked(window.isVisible())
            btn.toggled.connect(window.setVisible)
            window.visibility_changed.connect(btn.setChecked)
            return btn

        toggles_layout.addWidget(create_toggle("⚙️ Config", "config"), 0, 0)
        toggles_layout.addWidget(create_toggle("📊 Sys", "hw"), 0, 1)
        toggles_layout.addWidget(create_toggle("📸 Raw", "raw"), 0, 2)
        toggles_layout.addWidget(create_toggle("🧠 AI", "ai"), 0, 3)
        toggles_layout.addWidget(create_toggle("🕹️ PTZ", "ptz"), 1, 0)
        toggles_layout.addWidget(create_toggle("✨ FX", "effects"), 1, 1)
        toggles_layout.addWidget(create_toggle("💬 Chat", "chat"), 1, 2)
        toggles_layout.addWidget(create_toggle("📡 Stream", "stream"), 1, 3)

        self.preview_roi_cb = QCheckBox("ROI")
        self.preview_roi_cb.setChecked(True)
        self.preview_roi_cb.stateChanged.connect(self.update_toggles)
        self.output_roi_cb = QCheckBox("Out ROI")
        self.output_roi_cb.stateChanged.connect(self.update_toggles)
        self.flip_cb = QCheckBox("Flip")
        self.flip_cb.stateChanged.connect(self.update_toggles)
        
        self.debug_cb = QCheckBox("Debug")
        self.debug_cb.stateChanged.connect(lambda state: self.panels["debug"].setVisible(bool(state)))
        self.panels["debug"].visibility_changed.connect(self.debug_cb.setChecked)

        options_layout.addWidget(self.preview_roi_cb)
        options_layout.addWidget(self.output_roi_cb)
        options_layout.addWidget(self.flip_cb)
        options_layout.addWidget(self.debug_cb)
        options_layout.addStretch()

        taskbar_layout.addLayout(header_layout)
        taskbar_layout.addLayout(toggles_layout)
        taskbar_layout.addLayout(options_layout)

        central_container = QWidget()
        central_layout = QVBoxLayout(central_container)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.addWidget(self.taskbar)
        central_layout.addStretch()
        self.setCentralWidget(central_container)
        
        # Hardware Update Timer
        self.hw_timer = QTimer(self)
        self.hw_timer.timeout.connect(self.update_hardware_stats)
        self.hw_timer.start(1000)
        self.last_frame_count = 0
        
        # Idle Auto-Pilot Timer
        self.idle_timer = QTimer(self)
        self.idle_timer.setInterval(5 * 60 * 1000) # 5 Minutes
        self.idle_timer.timeout.connect(self.trigger_idle_wander)
        self.idle_timer.start()

        self.update_classes({0: "anus", 1: "action_zoom",
                            2: "nipple", 3: "penis", 4: "vagina", 99: "face"})
        self.move_timer = QTimer(self)
        self.move_timer.timeout.connect(self.apply_manual_ptz)
        self.move_data = {"pan": 0, "tilt": 0, "zoom": 0, "start_time": 0}
        qt_handler.emitter.log_signal.connect(self.append_log)
        self.init_tray()
        
        self.app_settings_file = os.path.join(os.path.dirname(__file__), "settings.json")
        self.app_settings = {}
        self.load_app_settings()
        
        # Restore Window Geometry and Dock States (Niri Window Style)
        self.settings = QSettings("ZenithCam", "NiriStudio")
        
        main_w = self.settings.value("main_w", type=int)
        main_h = self.settings.value("main_h", type=int)
        if main_w and main_h:
            self.resize(main_w, main_h)
        elif self.settings.value("default_main_w", type=int):
            self.resize(self.settings.value("default_main_w", type=int), self.settings.value("default_main_h", type=int))
            
        for key, window in self.panels.items():
            w = self.settings.value(f"{key}_w", type=int)
            h = self.settings.value(f"{key}_h", type=int)
            if w and h:
                window.resize(w, h)
            else:
                dw = self.settings.value(f"default_{key}_w", type=int)
                dh = self.settings.value(f"default_{key}_h", type=int)
                if dw and dh:
                    window.resize(dw, dh)
                    
            # Restore module visibility state
            vis_val = self.settings.value(f"{key}_visible")
            if vis_val is not None:
                window.setVisible(str(vis_val).lower() == 'true')
            else:
                # Fallback to saved default or fresh install logic
                def_vis = self.settings.value(f"default_{key}_visible")
                if def_vis is not None:
                    window.setVisible(str(def_vis).lower() == 'true')
                else:
                    if key in ["config", "hw"]:
                        window.setVisible(True)
                    else:
                        window.setVisible(False)
        
        global_logger.info("Application initialized.")

    def load_app_settings(self):
        try:
            if os.path.exists(self.app_settings_file):
                with open(self.app_settings_file, 'r') as f:
                    self.app_settings = json.load(f)
            else:
                self.app_settings = {"default": self.params.copy()}
                
            self.preset_combo.blockSignals(True)
            self.preset_combo.clear()
            self.preset_combo.addItems(self.app_settings.keys())
            self.preset_combo.blockSignals(False)
            
            # Load default or first available if no default
            tag_to_load = "default" if "default" in self.app_settings else list(self.app_settings.keys())[0]
            self.preset_combo.setCurrentText(tag_to_load)
            self.on_preset_selected(tag_to_load)
        except Exception as e:
            global_logger.error(f"Failed to load settings: {e}")

    def save_current_preset(self):
        tag = self.preset_combo.currentText().strip()
        if not tag:
            tag = "default"
        
        # Build current settings dict
        current_settings = {
            'input_source': self.input_spin.value(),
            'output_device': self.output_edit.currentText(),
            'model_path': self.params.get('model_path', ""),
            'target_class_ids': self.params.get('target_class_ids', []),
            'blur_class_ids': self.params.get('blur_class_ids', []),
            'smooth_factor': self.smooth_slider.value() / 100.0,
            'zoom_margin': self.margin_spin.value(),
            'enable_physical_ptz': self.ptz_cb.isChecked(),
            'enable_onboard_tracker': self.onboard_tracker_cb.isChecked(),
            'draw_preview_roi': self.preview_roi_cb.isChecked(),
            'draw_output_roi': self.output_roi_cb.isChecked(),
            'flip_video': self.flip_cb.isChecked(),
            'stream_encoder': self.encoder_combo.currentIndex(),
            'stream_quality': self.bitrate_combo.currentIndex()
        }
        
        self.app_settings[tag] = current_settings
        try:
            with open(self.app_settings_file, 'w') as f:
                json.dump(self.app_settings, f, indent=4)
            global_logger.info(f"Saved preset: {tag}")
            
            # Refresh combo box
            self.preset_combo.blockSignals(True)
            self.preset_combo.clear()
            self.preset_combo.addItems(self.app_settings.keys())
            self.preset_combo.setCurrentText(tag)
            self.preset_combo.blockSignals(False)
        except Exception as e:
            global_logger.error(f"Failed to save settings: {e}")

    def delete_current_preset(self):
        tag = self.preset_combo.currentText().strip()
        if tag and tag in self.app_settings and tag != "default":
            del self.app_settings[tag]
            try:
                with open(self.app_settings_file, 'w') as f:
                    json.dump(self.app_settings, f, indent=4)
                global_logger.info(f"Deleted preset: {tag}")
                self.preset_combo.blockSignals(True)
                self.preset_combo.clear()
                self.preset_combo.addItems(self.app_settings.keys())
                self.preset_combo.setCurrentText("default")
                self.preset_combo.blockSignals(False)
                self.on_preset_selected("default")
            except Exception as e:
                global_logger.error(f"Failed to delete preset: {e}")

    def on_preset_selected(self, tag):
        if isinstance(tag, int):
            tag = self.preset_combo.currentText()
            
        if tag in self.app_settings:
            settings = self.app_settings[tag]
            
            # Update UI elements
            if 'input_source' in settings:
                self.input_spin.setValue(settings['input_source'])
            if 'output_device' in settings:
                self.output_edit.setCurrentText(settings['output_device'])
            if 'model_path' in settings:
                self.params['model_path'] = settings['model_path']
            if 'smooth_factor' in settings:
                self.smooth_slider.setValue(int(settings['smooth_factor'] * 100))
            if 'zoom_margin' in settings:
                self.margin_spin.setValue(settings['zoom_margin'])
            if 'enable_physical_ptz' in settings:
                self.ptz_cb.setChecked(settings['enable_physical_ptz'])
            if 'enable_onboard_tracker' in settings:
                self.onboard_tracker_cb.setChecked(settings['enable_onboard_tracker'])
            if 'draw_preview_roi' in settings:
                self.preview_roi_cb.setChecked(settings['draw_preview_roi'])
            if 'draw_output_roi' in settings:
                self.output_roi_cb.setChecked(settings['draw_output_roi'])
            if 'flip_video' in settings:
                self.flip_cb.setChecked(settings['flip_video'])
            if 'stream_encoder' in settings:
                self.encoder_combo.setCurrentIndex(settings['stream_encoder'])
            if 'stream_quality' in settings:
                self.bitrate_combo.setCurrentIndex(settings['stream_quality'])
                
            # We also need to restore target/blur class IDs
            target_ids = settings.get('target_class_ids', [])
            blur_ids = settings.get('blur_class_ids', [])
            
            # Update the checkboxes
            if hasattr(self, 'class_checkboxes'):
                for cid, cb in self.class_checkboxes:
                    cb.setChecked(cid in target_ids)
            if hasattr(self, 'blur_checkboxes'):
                for cid, cb in self.blur_checkboxes:
                    cb.setChecked(cid in blur_ids)
                    
            self.update_target_classes()
            global_logger.info(f"Loaded preset: {tag}")

    @Slot(str)
    def append_log(self, text): self.log_text.append(text)

    def update_hardware_stats(self):
        cpu_usage = psutil.cpu_percent()
        ram = psutil.virtual_memory()
        ram_usage = ram.percent
        
        # Calculate FPS based on frames processed in the last second
        current_frames = 0
        if self.worker and hasattr(self.worker, 'frame_count'):
            current_frames = self.worker.frame_count
            
        fps = current_frames - self.last_frame_count
        self.last_frame_count = current_frames
        
        self.hw_cpu_label.setText(f"CPU Usage: {cpu_usage:.1f}%")
        self.hw_ram_label.setText(f"RAM Usage: {ram_usage:.1f}% ({ram.used / (1024**3):.1f} GB)")
        if self.is_tracking:
            self.hw_fps_label.setText(f"Output FPS: {fps}")
        else:
            self.hw_fps_label.setText("Output FPS: --")
            
        # Optional: Add color coding based on usage
        self.hw_cpu_label.setStyleSheet("color: red;" if cpu_usage > 85 else "color: #E2E2E2;")
        self.hw_ram_label.setStyleSheet("color: red;" if ram_usage > 85 else "color: #E2E2E2;")
        
        # Hardware Watchdog for OBSBOT Auto-Reconnect
        if self.obsbot and not self.obsbot.connected and getattr(self, 'ptz_cb', None) and self.ptz_cb.isChecked():
            if getattr(self, 'is_tracking', False) and not getattr(self, 'obsbot_thread', None) and hasattr(self, 'reconnect_obsbot_btn') and self.reconnect_obsbot_btn.isEnabled():
                if time.time() - getattr(self, 'last_reconnect_attempt', 0.0) > 5.0:
                    global_logger.warning("Hardware Watchdog: OBSBOT connection lost. Auto-reconnecting...")
                    self.last_reconnect_attempt = time.time()
                    self.reconnect_obsbot()

    def init_tray(self):
        self.tray_icon = QSystemTrayIcon(self)
        # Use a generic icon or one from the project if available
        self.tray_icon.setIcon(self.style().standardIcon(
            QStyle.StandardPixmap.SP_ComputerIcon))

        tray_menu = QMenu()
        show_action = tray_menu.addAction("📂 Restore Workspace")
        show_action.triggered.connect(self.showNormal)

        start_action = tray_menu.addAction("▶ Toggle Tracking")
        start_action.triggered.connect(self.toggle_tracking)

        tray_menu.addSeparator()
        quit_action = tray_menu.addAction("❌ Exit")
        quit_action.triggered.connect(self.close)

        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.show()

    def update_clock(self):
        self.clock_label.setText(time.strftime("%H:%M:%S"))

    def show_launcher_menu(self):
        menu = QMenu(self)
        menu.setStyleSheet("QMenu { background-color: rgba(26, 26, 30, 240); color: white; border: 1px solid #333; padding: 5px; border-radius: 6px; } QMenu::item { padding: 8px 24px; border-radius: 4px; } QMenu::item:selected { background-color: #00E676; color: black; font-weight: bold; }")
        about_action = menu.addAction("ℹ️ About ZenithCam")
        about_action.triggered.connect(
            lambda: self.status_label.setText("ZenithCam v2.0 - Niri Edition"))
        menu.addSeparator()
        
        reset_action = menu.addAction("🪟 Reset UI Workspace")
        reset_action.triggered.connect(self.reset_workspace)
        
        save_def_action = menu.addAction("💾 Save Layout as Default")
        save_def_action.triggered.connect(self.save_default_layout)
        
        if self.is_tracking:
            track_action = menu.addAction("⏹ Stop Tracking")
        else:
            track_action = menu.addAction("▶ Start Tracking")
        track_action.triggered.connect(self.toggle_tracking)
        
        menu.addSeparator()
        exit_action = menu.addAction("❌ Shut Down")
        exit_action.triggered.connect(self.close)

        # Calculate position to pop UP from the button
        pos = self.app_menu_btn.mapToGlobal(self.app_menu_btn.rect().topLeft())
        pos.setY(pos.y() - menu.sizeHint().height() - 40)
        menu.exec(pos)

    def toggle_ptz(self, *args):
        state = self.ptz_cb.isChecked()
        self.params['enable_physical_ptz'] = state
        if not state:
            self.onboard_tracker_cb.setChecked(False)
        if state and self.params['target_class_ids'] and self.obsbot and self.obsbot.connected:
            self.obsbot.set_ai_mode(0)
            self.obsbot_ai_combo.setCurrentIndex(0)

    def toggle_onboard_tracker(self, *args):
        state = self.onboard_tracker_cb.isChecked()
        if state and not self.ptz_cb.isChecked():
            self.ptz_cb.setChecked(True)
        self.params['enable_onboard_tracker'] = state
        if self.obsbot and self.obsbot.connected:
            if state:
                self.obsbot.set_ai_mode(OBSBOTSDK.AI_MODE_HUMAN, 0)
                self.obsbot_ai_combo.setCurrentIndex(2)
            else:
                self.obsbot.set_ai_mode(0)
                self.obsbot_ai_combo.setCurrentIndex(0)

    def update_toggles(self, *args):
        self.params['draw_preview_roi'] = self.preview_roi_cb.isChecked()
        self.params['draw_output_roi'] = self.output_roi_cb.isChecked()
        self.params['flip_video'] = self.flip_cb.isChecked()

    def refresh_output_devices(self, *args):
        curr = self.output_edit.currentText()
        self.output_edit.clear()
        devs = detect_loopback_devices()
        if devs:
            self.output_edit.addItems(devs)
            self.output_edit.setCurrentText(curr if curr in devs else (
                "/dev/video20" if "/dev/video20" in devs else devs[-1]))
        else:
            self.output_edit.addItem("No loopback devices found")

    def select_model(self, *args):
        fname, _ = QFileDialog.getOpenFileName(
            self, "Select YOLO Model", "", "ONNX Models (*.onnx);;YOLO Models (*.pt)")
        if fname:
            self.model_label.setText(os.path.basename(fname))
            self.params['model_path'] = fname
            self.load_classes_from_model(fname)

    def load_classes_from_model(self, model_path):
        try:
            if model_path.endswith('.pt'):
                names = YOLO(model_path).names
            else:
                import onnxruntime as ort
                session = ort.InferenceSession(
                    model_path, providers=["CPUExecutionProvider"])
                meta = session.get_modelmeta().custom_metadata_map
                import ast
                names = ast.literal_eval(meta['names']) if 'names' in meta else {
                    0: "anus", 1: "action_zoom", 2: "nipple", 3: "penis", 4: "vagina"}
            names[99] = "face"
            self.update_classes(names)
        except:
            pass

    def update_classes(self, names_dict):
        for layout in [self.class_layout, self.blur_layout]:
            while layout.count():
                child = layout.takeAt(0)
                if child.widget():
                    child.widget().deleteLater()
        self.class_checkboxes, self.blur_checkboxes = [], []
        for cid, name in names_dict.items():
            cb, cb_b = QCheckBox(f"{name} (ID: {cid})"), QCheckBox(
                f"{name} (ID: {cid})")
            t_name = str(name).lower()
            
            # Default tracking: face and explicit action classes
            if "make_love" in t_name or "penis" in t_name or "action_zoom" in t_name or t_name == "face":
                cb.setChecked(True)
                
            # Default blurring (if enabled)
            if t_name in ["anus", "nipple", "penis", "vagina"]:
                cb_b.setChecked(True)

            cb.stateChanged.connect(self.update_target_classes)
            cb_b.stateChanged.connect(self.update_target_classes)
            self.class_layout.addWidget(cb)
            self.class_checkboxes.append((cid, cb))
            self.blur_layout.addWidget(cb_b)
            self.blur_checkboxes.append((cid, cb_b))
        self.update_target_classes()

    def reset_workspace(self):
        """Restores the UI layout to the saved custom default or hardcoded state"""
        self.settings.remove("main_w")
        self.settings.remove("main_h")
        for key in self.panels.keys():
            self.settings.remove(f"{key}_w")
            self.settings.remove(f"{key}_h")

        if self.settings.value("default_main_w", type=int):
            self.resize(self.settings.value("default_main_w", type=int), self.settings.value("default_main_h", type=int))
            for key, window in self.panels.items():
                dw = self.settings.value(f"default_{key}_w", type=int)
                dh = self.settings.value(f"default_{key}_h", type=int)
                if dw and dh:
                    window.resize(dw, dh)
                
                vis_val = self.settings.value(f"default_{key}_visible")
                if vis_val is not None:
                    is_vis = str(vis_val).lower() == 'true'
                    window.setVisible(is_vis)
        else:
            for k, w in self.panels.items():
                w.hide()
            self.panels["hw"].show()
            self.panels["hw"].resize(600, 800)
            self.resize(600, 800)
            
        global_logger.info("Workspace layout reset.")
        self.status_label.setText("Workspace reset.")

    def save_default_layout(self):
        """Saves the current geometries and visibility as the new default."""
        self.settings.setValue("default_main_w", self.width())
        self.settings.setValue("default_main_h", self.height())
        for key, window in self.panels.items():
            self.settings.setValue(f"default_{key}_w", window.width())
            self.settings.setValue(f"default_{key}_h", window.height())
            self.settings.setValue(f"default_{key}_visible", window.isVisible())
            
        global_logger.info("Current layout saved as default.")
        self.status_label.setText("Layout saved as default.")

    def update_shader_style(self, index):
        styles = ["gaussian", "pixelate", "cyber_glitch", "edge_glow"]
        if 0 <= index < len(styles):
            self.params['blur_type'] = styles[index]
            # Push to live renderer if active
            if self.worker and hasattr(self.worker, 'hw') and self.worker.hw.renderer:
                self.worker.hw.renderer.set_config({"blur_type": self.params['blur_type']})

    def update_smoothing(self, *args):
        self.params['smooth_factor'] = self.smooth_slider.value() / 100.0

    def update_margin(self, *args):
        self.params['zoom_margin'] = self.margin_spin.value()

    def update_target_classes(self, *args):
        self.params['target_class_ids'] = [cid for cid,
                                           cb in self.class_checkboxes if cb.isChecked()]
        self.params['blur_class_ids'] = [cid for cid,
                                         cb in self.blur_checkboxes if cb.isChecked()]
        if self.params['target_class_ids'] and self.ptz_cb.isChecked() and self.obsbot and self.obsbot.connected and self.obsbot_ai_combo.currentIndex() != 0:
            self.obsbot.set_ai_mode(0)
            self.obsbot_ai_combo.setCurrentIndex(0)

    def toggle_tracking(self, *args):
        if getattr(self, 'is_shutting_down', False) or getattr(self, 'is_transitioning', False):
            return

        if self.is_tracking:
            self.is_transitioning = True
            self.is_tracking = False
            self.start_btn.setEnabled(False)
            self.start_btn.setText("Stopping...")
            
            if self.worker:
                self.worker.stop()
            else:
                self._on_worker_finished()
        else:
            if self.thread is not None:
                return  # Wait for full cleanup before restarting
                
            self.is_transitioning = True
            self.is_tracking = True
            # Auto-detect the correct capture-capable video node for OBSBOT
            # Only auto-detect if the current value is the default (1) or 0
            current_idx = self.input_spin.value()
            if current_idx <= 1:
                capture_idx = find_obsbot_capture_index()
                self.input_spin.setValue(capture_idx)
                global_logger.info(f'Engine starting with auto-detected capture index: {capture_idx}')
            else:
                capture_idx = current_idx
                global_logger.info(f'Engine starting with user-selected capture index: {capture_idx}')
            
            self.params['input_source'], self.params['output_device'] = capture_idx, self.output_edit.currentText()
            self.update_smoothing()
            self.update_margin()
            self.update_target_classes()
            self.thread = QThread()
            self.worker = ZenithWorker(self.params)
            self.worker.moveToThread(self.thread)
            self.thread.started.connect(self.worker.process)
            self.worker.finished.connect(self.thread.quit)
            # Safely schedule deletion ONLY after the respective threads fully quit
            self.worker.finished.connect(self.worker.deleteLater)
            self.thread.finished.connect(self.thread.deleteLater)
            self.worker.finished.connect(self._on_worker_finished)
            self.thread.finished.connect(self._clear_thread_refs)
            self.worker.change_pixmap_signal.connect(self.update_image)
            self.worker.raw_pixmap_signal.connect(self.update_raw_image)
            self.worker.status_signal.connect(self.update_status)
            
            # Ninja Features Signals
            self.worker.gesture_detected.connect(self.handle_gesture)
            self.worker.nsfw_detected.connect(self.handle_nsfw_trigger)
            self.worker.broll_trigger.connect(self.handle_broll_trigger)
            self.worker.posture_detected.connect(self.handle_posture)
            
            self.thread.start()
            self.start_btn.setText("Stop Tracking")
            self.start_btn.setStyleSheet(
                "background-color: #FF5252; color: white; font-weight: bold; padding: 15px; border-radius: 8px;")
            self.is_transitioning = False

    def handle_gesture(self, gesture_type):
        global_logger.info(f"Gesture Detected: {gesture_type}")
        if gesture_type == 'peace':
            # Toggle BRB Shield in frontend
            if self.wb_worker:
                self.wb_worker.broadcast({"type": "brb_trigger", "active": True}) # Or toggle it depending on state, but let's just trigger for now or send toggle signal. 
                # To actually toggle we need to store state or just tell it to invert.
        elif gesture_type == 'palm':
            # Stop tracking
            if self.obsbot and self.obsbot.connected:
                self.obsbot.set_gimbal_speed(0, 0)
                self.obsbot.set_ai_mode(0) # Disable AI

    def handle_nsfw_trigger(self):
        global_logger.info("NSFW Frame Detected! Triggering Auto-Privacy.")
        if self.wb_worker:
            self.wb_worker.broadcast({"type": "brb_trigger", "active": True})

    def handle_broll_trigger(self):
        global_logger.info("Subject lost. Triggering Cinematic B-Roll.")
        if self.obsbot and self.obsbot.connected:
            self.obsbot.set_ai_mode(0)
            self.obsbot.set_gimbal_speed(0.0, 5.0) # Slow horizontal pan

    def trigger_idle_wander(self):
        if not hasattr(self, 'idle_wander_cb') or not self.idle_wander_cb.isChecked():
            return
            
        global_logger.info("Idle Auto-Pilot triggered. Wandering to tease chat...")
        if self.obsbot and self.obsbot.connected:
            self.obsbot.set_ai_mode(0)
            self.obsbot_ai_combo.setCurrentIndex(0)
            self.obsbot.set_gimbal_speed(0.0, 3.0) # Slow pan horizontally
            
            # Smoothly reverse direction after 15 seconds to sweep the room
            QTimer.singleShot(15000, lambda: self.obsbot.set_gimbal_speed(0.0, -3.0) if self.obsbot and self.obsbot.connected else None)
            QTimer.singleShot(30000, lambda: self.obsbot.set_gimbal_speed(0.0, 0.0) if self.obsbot and self.obsbot.connected else None)

    def handle_posture(self, posture_type):
        if not hasattr(self, 'posture_cb') or not self.posture_cb.isChecked():
            return
            
        global_logger.info(f"AI Posture Trigger: {posture_type}")
        if self.obsbot and self.obsbot.connected:
            if posture_type == "reclined":
                self.recall_preset("P2")
                self.status_label.setText("AI: Reclined (Recalled P2)")
            else:
                self.recall_preset("Home")
                self.status_label.setText("AI: Upright (Recalled Home)")

    @Slot()
    def _on_worker_finished(self):
        self.is_tracking = False
        self.is_transitioning = False
        self.start_btn.setEnabled(True)
        self.start_btn.setText("Start Tracking")
        self.start_btn.setStyleSheet(
            "background-color: #00E676; color: black; font-weight: bold; padding: 15px; border-radius: 8px;")
        self.status_label.setText("Stopped.")
        self.input_preview_label.setText("Offline")
        self.output_preview_label.setText("Offline")
        
    @Slot()
    def _clear_thread_refs(self):
        self.worker = None
        self.thread = None

    def save_preset(self, name):
        if self.obsbot and self.obsbot.connected:
            p, y, r = self.obsbot.get_gimbal_attitude()
            if p is not None:
                self.presets[name] = (p, y, getattr(
                    self.worker, "_last_zoom", 1.0) if self.worker else 1.0)

    def recall_preset(self, name):
        if self.obsbot and self.obsbot.connected:
            self.obsbot.set_ai_mode(0)
            self.obsbot_ai_combo.setCurrentIndex(0)
            p, y, z = self.presets[name]
            self.obsbot.set_gimbal_angle(p, y)
            self.obsbot.set_zoom(z)
            if self.worker:
                self.worker._last_zoom = z

    @Slot(int, int)
    def on_output_single_click(self, x, y):
        # Stop AI Tracking by unchecking class boxes
        self.last_active_classes = [cid for cid, cb in self.class_checkboxes if cb.isChecked()]
        for cid, cb in self.class_checkboxes:
            cb.setChecked(False)
        self.update_target_classes()
        if self.worker:
            w = self.output_preview_label.width()
            h = self.output_preview_label.height()
            self.worker.handle_click(x, y, w, h, "single")
            
    @Slot(int, int)
    def on_output_double_click(self, x, y):
        # Resume last tracking settings... wait, I need to store them.
        # If we just re-check "Person" (class 0) for now, or just resume
        # Let's say we have a self.last_active_classes to restore
        if hasattr(self, 'last_active_classes') and self.last_active_classes:
            for cid, cb in self.class_checkboxes:
                cb.setChecked(cid in self.last_active_classes)
        else:
            # default to person
            if self.class_checkboxes:
                self.class_checkboxes[0][1].setChecked(True)
        self.update_target_classes()
        if self.worker:
            w = self.output_preview_label.width()
            h = self.output_preview_label.height()
            self.worker.handle_click(x, y, w, h, "zoom_in")
            self.worker.handle_click(x, y, w, h, "resume")

    @Slot(int, int)
    def on_output_right_click(self, x, y):
        if self.worker:
            w = self.output_preview_label.width()
            h = self.output_preview_label.height()
            self.worker.handle_click(x, y, w, h, "zoom_out")

    @Slot(QImage)
    def update_image(self, qt_img):
        self.output_preview_label.setPixmap(QPixmap.fromImage(qt_img).scaled(self.output_preview_label.size(
        ), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

    @Slot(QImage)
    def update_raw_image(self, qt_img):
        self.input_preview_label.setPixmap(QPixmap.fromImage(qt_img).scaled(self.input_preview_label.size(
        ), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

    @Slot(str)
    def update_status(self, text):
        self.status_label.setText(text)

    def start_manual_move(self, pan, tilt):
        self.idle_timer.start() # Reset idle timer on manual override
        try:
            if self.obsbot and self.obsbot.connected:
                self.obsbot.set_ai_mode(0)
                self.obsbot_ai_combo.setCurrentIndex(0)
        except Exception as e:
            self.obsbot.connected = False
        self.move_data.update(
            {"pan": pan, "tilt": tilt, "zoom": 0, "start_time": time.time()})
        self.move_timer.start(50)

    def start_manual_zoom(self, direction):
        self.idle_timer.start() # Reset idle timer on manual override
        try:
            if self.obsbot and self.obsbot.connected:
                self.obsbot.set_ai_mode(0)
                self.obsbot_ai_combo.setCurrentIndex(0)
        except Exception as e:
            self.obsbot.connected = False
        self.move_data.update(
            {"pan": 0, "tilt": 0, "zoom": direction, "start_time": time.time()})
        self.move_timer.start(50)

    def stop_manual_move(self):
        self.move_timer.stop()
        try:
            if self.obsbot and self.obsbot.connected:
                self.obsbot.set_gimbal_speed(0.0, 0.0)
        except Exception as e:
            self.obsbot.connected = False

    def apply_manual_ptz(self):
        if not self.obsbot or not self.obsbot.connected:
            return
        try:
            accel = float(
                min(1.0, max(0.1, (time.time() - self.move_data["start_time"]) / 2.0)))
            if self.move_data["pan"] or self.move_data["tilt"]:
                self.obsbot.set_gimbal_speed(
                    float(-self.move_data["tilt"] * 30 * accel), float(-self.move_data["pan"] * 60 * accel))
            if self.move_data["zoom"]:
                z = float(self.worker._last_zoom if self.worker else 1.0) + \
                    float(self.move_data["zoom"] * (0.01 + 0.04 * accel))
                nz = float(np.clip(z, 1.0, 2.0))
                self.obsbot.set_zoom(nz)
                if self.worker:
                    self.worker._last_zoom = nz
        except Exception as e:
            global_logger.error(f"Manual PTZ Error: {e}")
            self.obsbot.connected = False
            self.move_timer.stop()

    def manual_center(self, *args):
        self.idle_timer.start() # Reset idle timer on manual override
        try:
            if self.obsbot and self.obsbot.connected:
                self.obsbot.set_ai_mode(0)
                self.obsbot_ai_combo.setCurrentIndex(0)
                self.obsbot.set_gimbal_angle(0, 0)
                self.obsbot.set_zoom(1)
                if self.worker:
                    self.worker._last_zoom = 1
        except Exception as e:
            self.obsbot.connected = False

    def reset_gimbal(self, *args):
        self.idle_timer.start() # Reset idle timer on manual override
        try:
            if self.obsbot and self.obsbot.connected:
                self.obsbot.set_ai_mode(0)
                self.obsbot_ai_combo.setCurrentIndex(0)
                self.obsbot.reset_gimbal()
                self.obsbot.set_zoom(1)
                if self.worker:
                    self.worker._last_zoom = 1
        except Exception as e:
            self.obsbot.connected = False

    _SUBMODE_OPTIONS = {0: [], 1: ["Default"], 2: [
        "Full Body", "Upper Body"], 3: ["Default"], 4: ["Default"], 5: ["Default"]}

    def toggle_hold_ptz(self, state):
        self.params['hold_ptz'] = bool(state)
        if self.params['hold_ptz']:
            global_logger.info("PTZ Hold Activated")
            if self.obsbot and self.obsbot.connected:
                self.obsbot.set_gimbal_speed(0, 0)
        else:
            global_logger.info("PTZ Hold Deactivated")

    def update_manual_zoom(self, value):
        self.params['manual_zoom'] = value / 10.0
        if self.params['hold_ptz'] and self.obsbot and self.obsbot.connected:
            self.obsbot.set_zoom(self.params['manual_zoom'])

    def change_obsbot_ai_mode(self, index):
        subs = self._SUBMODE_OPTIONS.get(index, [])
        self.obsbot_submode_combo.blockSignals(True)
        self.obsbot_submode_combo.clear()
        if subs:
            self.obsbot_submode_combo.addItems(subs)
            self.submode_label.setVisible(True)
            self.obsbot_submode_combo.setVisible(True)
        else:
            self.submode_label.setVisible(False)
            self.obsbot_submode_combo.setVisible(False)
        self.obsbot_submode_combo.blockSignals(False)
        if self.obsbot and self.obsbot.connected:
            self.obsbot.set_ai_mode(index, 0)
            if index != 0 and self.params['enable_physical_ptz']:
                self.ptz_cb.setChecked(False)

    def change_obsbot_submode(self, sub_index):
        if self.obsbot and self.obsbot.connected:
            self.obsbot.set_ai_mode(
                self.obsbot_ai_combo.currentIndex(), sub_index)

    def toggle_privacy(self, *args):
        if self.obsbot and self.obsbot.connected:
            self.obsbot.set_privacy_mode(self.privacy_cb.isChecked())

    def toggle_bluetooth_mode(self, state):
        use_bt = bool(state)
        self.scan_bt_btn.setEnabled(use_bt)
        self.bt_device_combo.setVisible(use_bt)
        
        # Re-initialize SDK with Bluetooth support if changed
        if use_bt != self.obsbot.use_bluetooth:
            self.obsbot.disconnect()
            self.obsbot = OBSBOTSDK(use_bluetooth=use_bt)
            self.params['obsbot'] = self.obsbot
            if use_bt:
                self.obsbot.bt_manager.device_discovered.connect(self.on_bt_device_found)
                self.obsbot.bt_manager.connection_status.connect(self.on_bt_connection_status)
            self.status_label.setText(f"Switched to {'Bluetooth' if use_bt else 'USB'} mode.")

    def scan_bluetooth(self):
        if self.obsbot.use_bluetooth:
            self.bt_device_combo.clear()
            self.status_label.setText("Scanning for Bluetooth cameras...")
            self.obsbot.bt_manager.start_scan()

    @Slot(str, str)
    def on_bt_device_found(self, name, address):
        self.bt_device_combo.addItem(f"{name} ({address})", address)
        self.status_label.setText(f"Found: {name}")

    def connect_bluetooth_device(self, index):
        if index < 0: return
        address = self.bt_device_combo.itemData(index)
        if address:
            self.status_label.setText(f"Connecting to {address}...")
            self.obsbot.connect(address)

    @Slot(bool, str)
    def on_bt_connection_status(self, connected, message):
        if connected:
            self.status_label.setText(f"BT Connected: {message}")
            self.reconnect_obsbot_btn.setText("🔌 BT Connected")
        else:
            self.status_label.setText(f"BT Error: {message}")
            self.reconnect_obsbot_btn.setText("🔌 Connect OBSBOT")

    def async_init_obsbot(self):
        self.status_label.setText("Connecting OBSBOT...")
        if hasattr(self, 'reconnect_obsbot_btn'):
            self.reconnect_obsbot_btn.setEnabled(False)
            
        self.obsbot_thread = ObsbotConnectThread(self.obsbot, reconnect=False)
        self.obsbot_thread.finished.connect(self._on_obsbot_init_finished)
        self.obsbot_thread.start()

    def _on_obsbot_init_finished(self, success):
        if success:
            global_logger.info("Connected to OBSBOT SDK")
            self.obsbot.set_ai_mode(0)
            self.status_label.setText("Status: Idle (OBSBOT Ready)")
        else:
            global_logger.warning("OBSBOT SDK connection failed. Retry via UI.")
            self.status_label.setText("Status: Idle (OBSBOT Offline)")
        if hasattr(self, 'reconnect_obsbot_btn'):
            self.reconnect_obsbot_btn.setEnabled(True)
        self.obsbot_thread.deleteLater()
        self.obsbot_thread = None

    def reconnect_obsbot(self, *args):
        if self.obsbot:
            self.status_label.setText("Reconnecting OBSBOT...")
            self.reconnect_obsbot_btn.setEnabled(False)
            
            self.obsbot_thread = ObsbotConnectThread(self.obsbot, reconnect=True)
            self.obsbot_thread.finished.connect(self._on_obsbot_reconnect_finished)
            self.obsbot_thread.start()

    def _on_obsbot_reconnect_finished(self, success):
        if success:
            self.obsbot.set_ai_mode(0)
            self.obsbot_ai_combo.setCurrentIndex(0)
            self.status_label.setText("OBSBOT Reconnected.")
        else:
            self.status_label.setText("OBSBOT Connection Failed.")
        self.reconnect_obsbot_btn.setEnabled(True)
        self.obsbot_thread.deleteLater()
        self.obsbot_thread = None

    def load_profiles(self):
        try:
            if os.path.exists(self.profiles_file):
                with open(self.profiles_file, 'r') as f:
                    self.stream_profiles = json.load(f)
        except Exception as e:
            global_logger.error(f"Failed to load profiles: {e}")
        if not self.stream_profiles:
            self.stream_profiles = [
                {"name": "Default", "site": "Stripchat", "url": "rtmp://localhost:1935/live", "key": "test"}]

    @Slot(dict)
    def handle_web_ptz_command(self, data):
        """
        Receives dictionary commands from the Tampermonkey WebBridge.
        Translates them into actions on the physical OBSBOT camera.
        """
        # Reset Idle Timer on any incoming interaction/chat data
        if hasattr(self, 'idle_timer'):
            self.idle_timer.start()
            
        if not self.obsbot or not self.obsbot.connected:
            global_logger.warning("Web PTZ Command ignored: OBSBOT not connected.")
            return

        command = data.get("command")
        action = data.get("action")
        
        if command == "ptz":
            try:
                if self.obsbot_ai_combo.currentIndex() != 0:
                    self.obsbot_ai_combo.setCurrentIndex(0)
                    self.obsbot.set_ai_mode(0)
    
                speed = 30.0
                if action == "up":
                    self.obsbot.set_gimbal_speed(-speed, 0.0)
                elif action == "down":
                    self.obsbot.set_gimbal_speed(speed, 0.0)
                elif action == "left":
                    self.obsbot.set_gimbal_speed(0.0, speed)
                elif action == "right":
                    self.obsbot.set_gimbal_speed(0.0, -speed)
                elif action == "stop":
                    self.obsbot.set_gimbal_speed(0.0, 0.0)
                elif action == "reset":
                    self.obsbot.reset_gimbal()
            except Exception as e:
                global_logger.error(f"Web PTZ Command Error: {e}")
                self.obsbot.connected = False
                
        elif command == "chat":
            platform = data.get("platform", "Web")
            username = data.get("username", "User")
            message = data.get("message", "")
            
            if hasattr(self, 'chat_list'):
                self.chat_list.addItem(f"[{platform.capitalize()}] {username}: {message}")
                self.chat_list.scrollToBottom()
                
        elif command == "ptz_aim":
            nx = float(data.get("x", 0.0))
            ny = float(data.get("y", 0.0))
            
            global_logger.info(f"Web PTZ Click-to-Aim received: ({nx}, {ny})")
            
            try:
                # Send burst speed mapping directly since relative pointing is tricky without precise angle feedback
                self.obsbot.set_gimbal_speed(ny * 40.0, nx * 60.0)
                QTimer.singleShot(250, lambda: self.obsbot.set_gimbal_speed(0, 0) if self.obsbot and self.obsbot.connected else None)
            except Exception as e:
                global_logger.error(f"Web PTZ Aim Error: {e}")
                self.obsbot.connected = False
            
        elif command == "ptz_analog":
            # FPS-Style Mouse Look
            if hasattr(self, 'fps_mouse_cb') and self.fps_mouse_cb.isChecked():
                pan_spd = float(data.get("pan_speed", 0.0))
                tilt_spd = float(data.get("tilt_speed", 0.0))
                try:
                    # Send raw analog speeds directly to the SDK
                    if self.obsbot_ai_combo.currentIndex() == 0: # Ensure AI is off while manually aiming
                        self.obsbot.set_gimbal_speed(tilt_spd, pan_spd)
                except Exception as e:
                    global_logger.error(f"Web PTZ Analog Error: {e}")
                    self.obsbot.connected = False
            
        elif command == "reaction":
            if action == "zoom_action":
                global_logger.info("Chat Tip Reaction: Dramatic Action Zoom!")
                try:
                    # Disable AI temporarily
                    self.obsbot.set_ai_mode(0)
                    
                    # Get the center of the best targeted box (from ML pipeline if available)
                    # Instead of just general zoom, attempt to steer the gimbal directly to the action!
                    if self.worker and hasattr(self.worker, 'ml_pipeline') and self.worker.ml_pipeline.current_boxes:
                        boxes = self.worker.ml_pipeline.current_boxes
                        # Filter for only targeted boxes that aren't the face
                        target_boxes = [b for b in boxes if b[4] in self.params.get('target_class_ids', []) and b[4] != 99]
                        
                        if target_boxes:
                            # Sort by confidence
                            target_boxes.sort(key=lambda x: x[5], reverse=True)
                            best_box = target_boxes[0]
                            bx, by, bw, bh = best_box[:4]
                            
                            # Normalize to center (-1.0 to 1.0)
                            cx = (bx + bw/2) / self.params.get('output_width', 1280)
                            cy = (by + bh/2) / self.params.get('output_height', 720)
                            nx = (cx * 2) - 1.0
                            ny = (cy * 2) - 1.0
                            
                            # Quick sprint to the object
                            self.obsbot.set_gimbal_speed(ny * 60.0, nx * 80.0)
                            QTimer.singleShot(200, lambda: self.obsbot.set_gimbal_speed(0, 0) if self.obsbot and self.obsbot.connected else None)
    
                    # Zoom in
                    self.obsbot.set_zoom(1.8)
                    
                    # Set a timer to reset after 3 seconds
                    QTimer.singleShot(3000, lambda: self.obsbot.set_zoom(1.0) if self.obsbot and self.obsbot.connected else None)
                    QTimer.singleShot(3100, lambda: self.obsbot.set_ai_mode(2) if self.obsbot and self.obsbot.connected else None) # Human Tracking
                except Exception as e:
                    global_logger.error(f"Reaction Error: {e}")
                    self.obsbot.connected = False
                
            elif action == "hype_train":
                if hasattr(self, 'hype_train_cb') and self.hype_train_cb.isChecked():
                    if self.worker and self.worker.ptz:
                        self.worker.ptz.trigger_shake(duration=5.0, intensity=50.0)
                        
        elif command == "system":
            if action == "panic":
                global_logger.warning("🚨 GLOBAL PANIC BUTTON TRIGGERED 🚨")
                if hasattr(self, 'wb_worker') and self.wb_worker:
                    self.wb_worker.broadcast({"type": "brb_trigger", "active": True})

    def _broadcast_telemetry(self):
        if not self.obsbot or not self.obsbot.connected or not self.wb_worker:
            return
        try:
            p, y, r = self.obsbot.get_gimbal_attitude()
            if p is not None and y is not None:
                # Note: OBSBOT SDK might return angles or raw values depending on the wrapper, assuming raw v4l2 limits for map in frontend
                self.wb_worker.broadcast({"type": "telemetry", "pan": y, "tilt": p})
        except Exception as e:
            global_logger.debug(f"Telemetry Error: {e}")
            self.obsbot.connected = False

    def save_profiles_to_disk(self):
        try:
            with open(self.profiles_file, 'w') as f:
                json.dump(self.stream_profiles, f, indent=4)
        except Exception as e:
            global_logger.error(f"Failed to save profiles: {e}")

    def refresh_profile_ui(self):
        self.profile_combo.blockSignals(True)
        self.profile_combo.clear()
        for p in self.stream_profiles:
            self.profile_combo.addItem(f"{p['name']} ({p['site']})")
        self.profile_combo.blockSignals(False)
        self.on_profile_selected(self.profile_combo.currentIndex())
        self.update_stream_checkboxes()

    def update_stream_checkboxes(self):
        for i in reversed(range(self.chk_layout.count())):
            w = self.chk_layout.itemAt(i).widget()
            if w:
                w.setParent(None)
        self.stream_checkboxes.clear()
        for i, p in enumerate(self.stream_profiles):
            cb = QCheckBox(f"{p['name']} ({p['site']})")
            if i == 0:
                cb.setChecked(True)
            self.chk_layout.addWidget(cb)
            self.stream_checkboxes.append(cb)

    def on_profile_selected(self, index):
        if 0 <= index < len(self.stream_profiles):
            p = self.stream_profiles[index]
            self.prof_name_edit.setText(p.get("name", ""))
            self.prof_site_edit.setText(p.get("site", ""))
            self.rtmp_url_edit.setText(p.get("url", ""))
            self.stream_key_edit.setText(p.get("key", ""))

    def add_profile(self):
        self.stream_profiles.append(
            {"name": "New Profile", "site": "", "url": "", "key": ""})
        self.refresh_profile_ui()
        self.profile_combo.setCurrentIndex(len(self.stream_profiles) - 1)

    def delete_profile(self):
        idx = self.profile_combo.currentIndex()
        if 0 <= idx < len(self.stream_profiles) and len(self.stream_profiles) > 1:
            del self.stream_profiles[idx]
            self.refresh_profile_ui()
            self.save_profiles_to_disk()

    def save_current_profile(self):
        idx = self.profile_combo.currentIndex()
        if 0 <= idx < len(self.stream_profiles):
            self.stream_profiles[idx] = {
                "name": self.prof_name_edit.text(),
                "site": self.prof_site_edit.text(),
                "url": self.rtmp_url_edit.text(),
                "key": self.stream_key_edit.text()
            }
            self.save_profiles_to_disk()
            self.refresh_profile_ui()
            self.profile_combo.setCurrentIndex(idx)

    def toggle_streaming(self, *args):
        if self.params.get('active_streams'):
            for sp in self.params['active_streams']:
                try:
                    sp.terminate()
                    sp.wait(timeout=2)
                except:
                    sp.kill()
            self.params['active_streams'] = []
            self.stream_btn.setText("Start Broadcast")
            self.stream_btn.setStyleSheet(
                "background-color: #2979FF; padding: 12px; font-weight: bold; border-radius: 6px; color: #FFFFFF;")
            self.status_label.setText("Streaming stopped.")
        else:
            selected_profiles = []
            for i, cb in enumerate(self.stream_checkboxes):
                if cb.isChecked() and i < len(self.stream_profiles):
                    selected_profiles.append(self.stream_profiles[i])
                    if len(selected_profiles) == 3:
                        break
            if not selected_profiles:
                self.status_label.setText(
                    "Select at least 1 profile to stream.")
                return
            self.params['active_streams'] = []
            width = str(self.params['output_width'])
            height = str(self.params['output_height'])
            for p in selected_profiles:
                url = p.get("url", "").strip()
                key = p.get("key", "").strip()
                if not url or not key:
                    continue
                if not url.startswith("rtmp://") and not url.startswith("rtmps://"):
                    url = "rtmp://" + url
                if not url.endswith('/'):
                    url += '/'
                full_url = url + key
                
                encoder_idx = self.encoder_combo.currentIndex()
                cmd = ["/usr/bin/ffmpeg", "-y", "-thread_queue_size", "1024"]
                
                if encoder_idx == 2: # VA-API (Intel/AMD)
                    cmd.extend(["-vaapi_device", "/dev/dri/renderD128"])
                    
                cmd.extend([
                    "-f", "rawvideo", "-vcodec", "rawvideo", "-s", f"{width}x{height}", 
                    "-pix_fmt", "rgb24", "-framerate", "60", "-use_wallclock_as_timestamps", "1", "-i", "-", 
                    "-thread_queue_size", "1024", "-f", "pulse", "-i", "default"
                ])
                
                if encoder_idx == 1: # NVENC (NVIDIA)
                    cmd.extend(["-c:v", "h264_nvenc", "-preset", "p2", "-tune", "ull", "-profile:v", "main", "-bf", "0", "-zerolatency", "1", "-pix_fmt", "yuv420p"])
                elif encoder_idx == 2: # VA-API (Intel/AMD)
                    cmd.extend(["-vf", "format=nv12,hwupload", "-c:v", "h264_vaapi", "-profile:v", "main", "-bf", "0"])
                else: # CPU (x264)
                    cmd.extend(["-c:v", "libx264", "-preset", "veryfast", "-tune", "zerolatency", "-profile:v", "main", "-bf", "0", "-pix_fmt", "yuv420p"])

                br_idx = self.bitrate_combo.currentIndex()
                if br_idx == 0:
                    cmd.extend(["-b:v", "3000k", "-maxrate", "3000k",
                               "-minrate", "3000k", "-bufsize", "3000k"])
                elif br_idx == 1:
                    cmd.extend(["-b:v", "4500k", "-maxrate", "4500k",
                               "-minrate", "4500k", "-bufsize", "4500k"])
                else:
                    cmd.extend(["-b:v", "6000k", "-maxrate", "6000k",
                               "-minrate", "6000k", "-bufsize", "6000k"])
                cmd.extend(["-g", "60", "-keyint_min", "60", "-af", "aresample=async=1", "-c:a",
                               "aac", "-b:a", "128k", "-ar", "48000", "-ac", "2", "-f", "flv", full_url])
                global_logger.info(f"Starting stream to {p['name']}: {' '.join(cmd)}")
                sp = subprocess.Popen(
                    cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE, stdout=subprocess.PIPE)

                def log_stderr(process, p_name):
                    while True:
                        line = process.stderr.readline()
                        if not line:
                            break
                        line_str = line.decode(
                            'utf-8', errors='ignore').strip()
                        if line_str:
                            global_logger.debug(
                                f"[FFmpeg-{p_name}] {line_str}")
                threading.Thread(target=log_stderr, args=(
                    sp, p['name']), daemon=True).start()
                self.params['active_streams'].append(sp)
            if self.params['active_streams']:
                self.stream_btn.setText("Stop Broadcast")
                self.stream_btn.setStyleSheet(
                    "background-color: #F44336; padding: 12px; font-weight: bold; border-radius: 6px; color: #FFFFFF;")
                self.status_label.setText(
                    f"Streaming to {len(self.params['active_streams'])} destination(s)")

    def closeEvent(self, event):
        self.is_shutting_down = True
        if self.params.get('active_streams'):
            for sp in self.params['active_streams']:
                try:
                    sp.terminate()
                    sp.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    sp.kill()
        if hasattr(self, 'stream_process') and self.stream_process:
            try:
                self.stream_process.terminate()
                self.stream_process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.stream_process.kill()
                
        # Save Window Layout State
        self.settings.setValue("main_w", self.width())
        self.settings.setValue("main_h", self.height())
        for key, window in self.panels.items():
            self.settings.setValue(f"{key}_w", window.width())
            self.settings.setValue(f"{key}_h", window.height())
            self.settings.setValue(f"{key}_visible", window.isVisible())
            window.close() # Ensure all floating windows die when main app closes

        # Teardown WebBridge
        if hasattr(self, 'wb_worker') and self.wb_worker:
            try:
                if hasattr(self.wb_worker, 'stop'):
                    self.wb_worker.stop()
                if hasattr(self, 'wb_thread') and self.wb_thread.isRunning():
                    self.wb_thread.quit()
                    self.wb_thread.wait(1000)
            except Exception as e:
                global_logger.debug(f"Error closing Web Bridge: {e}")

        # Keep local references to prevent race conditions during teardown
        worker_ref = self.worker
        thread_ref = self.thread
        
        self.worker = None
        self.thread = None
        
        if worker_ref:
            worker_ref.stop()
            
        if thread_ref and thread_ref.isRunning():
            thread_ref.quit()
            if not thread_ref.wait(3000):
                global_logger.warning("Worker thread timed out, forcing termination.")
                thread_ref.terminate()
                thread_ref.wait()
                # Manually clean up hardware if the finally block didn't execute
                if worker_ref and hasattr(worker_ref, 'hw'):
                    worker_ref.hw.cleanup_all()
                    
        # Disconnect OBSBOT hardware safely
        if self.obsbot and self.obsbot.connected:
            try:
                self.obsbot.set_gimbal_speed(0.0, 0.0)
                self.obsbot.disconnect()
                global_logger.info("OBSBOT Hardware disconnected.")
            except Exception as e:
                global_logger.debug(f"OBSBOT disconnect err: {e}")
            
        global_logger.info("ZenithCam Studio shutdown complete.")
        event.accept()


if __name__ == "__main__":
    os.environ["QT_QPA_PLATFORM"] = "wayland;xcb"
    os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"
    os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"
    app = QApplication(sys.argv)
    app.setStyleSheet(STYLESHEET)
    from new_ui import ModernMainWindow
    window = ModernMainWindow()
    window.show()
    
    # Handle Terminal Ctrl+C to trigger closeEvent gracefully
    signal.signal(signal.SIGINT, lambda sig, frame: window.close())
    sigint_timer = QTimer()
    sigint_timer.start(500) # Yield back to Python interpreter every 500ms to catch the signal
    sigint_timer.timeout.connect(lambda: None)
    
    sys.exit(app.exec())
