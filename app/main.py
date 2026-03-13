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
from logging.handlers import TimedRotatingFileHandler
from PyQt6.QtWidgets import (QDockWidget, QApplication, QMainWindow, QWidget, QStyle, QVBoxLayout,
                             QHBoxLayout, QLabel, QComboBox, QPushButton,
                             QSlider, QGroupBox, QFileDialog, QSpinBox,
                             QSplitter, QTextEdit, QCheckBox, QScrollArea, QGridLayout, QLineEdit, QListWidget, QMenu, QSystemTrayIcon)
from PyQt6.QtCore import Qt, QThread, pyqtSignal as Signal, pyqtSlot as Slot, QObject, QTimer, QEventLoop
from PyQt6.QtGui import QImage, QPixmap
import pyfakewebcam

from ultralytics import YOLO

from hardware_profiler import HardwareProfiler
from ml_pipeline import MLPipeline
from ptz_camera import PTZCamera
from renderer import Renderer
from obsbot_wrapper import OBSBOTSDK


def find_obsbot_device():
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

/* Docks styling */
QDockWidget {
    color: #00E676;
    font-weight: bold;
    titlebar-close-icon: url(close.png);
    titlebar-normal-icon: url(undock.png);
}
QDockWidget::title {
    background-color: rgba(30, 30, 35, 200);
    padding: 6px;
    border-radius: 4px;
    text-align: left;
}

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

/* Plasma Panels */
.PlasmaPanel {
    background-color: rgba(26, 26, 30, 230);
    border: 1px solid #333;
    border-radius: 12px;
}
QGroupBox {
    #333; border-radius: 8px; margin-top: 18px; background-color: rgba(40, 40, 45, 100);
    border: 1px solid
}
QGroupBox::title {
    #00E676; font-weight: bold; font-size: 15px;
    subcontrol-origin: margin; subcontrol-position: top left; padding: 0 8px; color:
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

/* Tab styling for docked widgets */
QTabBar::tab {
    background: #1A1A1A;
    color: #888;
    padding: 8px 16px;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
}
QTabBar::tab:selected {
    background: #2A2A2A;
    color: #00E676;
    border-bottom: 2px solid #00E676;
}
"""


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
            except:
                pass
            self.fake_cam = None

    def release_renderer(self):
        if self.renderer:
            global_logger.info("HardwareManager: Releasing renderer")
            try:
                if hasattr(self.renderer, 'ctx'):
                    self.renderer.ctx.release()
            except:
                pass
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
            crop_rect = self.ptz.update(zoom_boxes)

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

    def _to_qt(self, img):
        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        return QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888).copy()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ZenithCam: Plasma Environment")
        self.setMinimumSize(800, 600)
        self.resize(1280, 720)

        # Dock Options
        self.setDockOptions(QMainWindow.DockOption.AnimatedDocks |
                            QMainWindow.DockOption.AllowTabbedDocks |
                            QMainWindow.DockOption.AllowNestedDocks)

        self.presets = {"Home": (0, 0, 1.0), "P1": (
            0, 0, 1.0), "P2": (0, 0, 1.0)}

        # Tracking Parameters
        self.params = {
            'input_source': 1,
            'output_device': "/dev/video20",
            'model_path': os.path.join(os.path.dirname(__file__), "models/erax_nsfw_yolo11n.onnx"),
            'target_class_ids': [3, 4],
            'blur_class_ids': [99],
            'smooth_factor': 0.02,
            'zoom_margin': 45,
            'output_width': 1280,
            'output_height': 720,
            'draw_preview_roi': True,
            'draw_output_roi': False,
            'flip_video': False,
            'show_input_preview': True,
            'show_output_preview': True,
            'enable_physical_ptz': False,
            'enable_onboard_tracker': False,
            'obsbot': None,
            'rtmp_url': "rtmp://localhost:1935/live",
            'stream_key': "test",
            'active_streams': []
        }

        self.stream_process = None

        self.obsbot = OBSBOTSDK()
        if self.obsbot.init() and self.obsbot.connect():
            global_logger.info("Connected to OBSBOT SDK")
            self.obsbot.set_ai_mode(0)
            self.params['obsbot'] = self.obsbot
        else:
            global_logger.warning(
                "OBSBOT SDK connection failed. Retry via UI.")

        self.worker = None
        self.thread = None

        # Central widget is just a placeholder to allow docking
        self.central_placeholder = QWidget()
        self.setCentralWidget(self.central_placeholder)
        self.central_placeholder.setMaximumSize(
            0, 0)  # Hide it, use docks for everything

        # --- PANEL 1: CONFIG ---
        self.config_dock = QDockWidget("⚙️ Config (Drag to Reorder)", self)
        self.config_dock.setObjectName("ConfigDock")
        self.config_dock.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
        self.config_dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable |
                                     QDockWidget.DockWidgetFeature.DockWidgetFloatable | QDockWidget.DockWidgetFeature.DockWidgetClosable)

        config_content = QWidget()
        config_layout = QVBoxLayout(config_content)

        self.settings_scroll = QScrollArea()
        self.settings_scroll.setWidgetResizable(True)
        self.settings_scroll.setStyleSheet(
            "border: none; background: transparent;")
        settings_container = QWidget()
        settings_layout = QVBoxLayout(settings_container)

        conf_group = QGroupBox("Device Settings")
        group_layout = QVBoxLayout(conf_group)

        cam_row = QHBoxLayout()
        cam_row.addWidget(QLabel("Input Camera:"))
        self.input_spin = QSpinBox()
        obs_dev = find_obsbot_device()
        def_idx = int(obs_dev.split("video")
                      [-1]) if obs_dev and "video" in obs_dev else 1
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
        self.config_dock.setWidget(config_content)
        self.addDockWidget(
            Qt.DockWidgetArea.LeftDockWidgetArea, self.config_dock)

        # --- PANEL 2: INPUT PREVIEW ---
        self.input_preview_dock = QDockWidget("📸 Raw Camera Feed", self)
        self.input_preview_dock.setObjectName("InputPreviewDock")
        self.input_preview_group = QGroupBox()
        in_l = QVBoxLayout(self.input_preview_group)
        self.input_preview_label = QLabel("Waiting for camera...")
        self.input_preview_label.setMinimumSize(320, 180)
        self.input_preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        in_l.addWidget(self.input_preview_label)
        self.input_preview_dock.setWidget(self.input_preview_group)
        self.addDockWidget(Qt.DockWidgetArea.TopDockWidgetArea,
                           self.input_preview_dock)

        # --- PANEL 3: OUTPUT PREVIEW ---
        self.output_preview_dock = QDockWidget("🧠 AI Processed View", self)
        self.output_preview_dock.setObjectName("OutputPreviewDock")
        self.output_preview_group = QGroupBox()
        out_l = QVBoxLayout(self.output_preview_group)
        self.output_preview_label = QLabel("Waiting for AI processing...")
        self.output_preview_label.setMinimumSize(320, 180)
        self.output_preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        out_l.addWidget(self.output_preview_label)
        self.output_preview_dock.setWidget(self.output_preview_group)
        self.splitDockWidget(self.input_preview_dock,
                             self.output_preview_dock, Qt.Orientation.Vertical)

        # --- PANEL 4: STREAMING ---
        self.streaming_dock = QDockWidget("📡 Plasma Broadcast", self)
        self.streaming_dock.setObjectName("StreamingDock")

        # Profile Management & Streaming
        self.profiles_file = os.path.join(
            os.path.dirname(__file__), "profiles.json")
        self.stream_profiles = []
        self.load_profiles()
        self.active_streams = []

        stream_content = QWidget()
        stream_layout = QVBoxLayout(stream_content)

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

        self.streaming_dock.setWidget(stream_content)
        self.addDockWidget(
            Qt.DockWidgetArea.RightDockWidgetArea, self.streaming_dock)

        # --- PANEL 5: PTZ ---
        self.ptz_dock = QDockWidget("🕹️ PTZ Controls", self)
        self.ptz_dock.setObjectName("PTZDock")
        ptz_content = QWidget()
        ptz_layout = QVBoxLayout(ptz_content)

        hardware_group = QGroupBox("Robot Control")
        hw_layout = QVBoxLayout(hardware_group)
        self.reconnect_obsbot_btn = QPushButton("🔌 Connect OBSBOT")
        self.reconnect_obsbot_btn.clicked.connect(self.reconnect_obsbot)
        hw_layout.addWidget(self.reconnect_obsbot_btn)

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

        self.ptz_dock.setWidget(ptz_content)
        self.addDockWidget(
            Qt.DockWidgetArea.RightDockWidgetArea, self.ptz_dock)
        self.tabifyDockWidget(self.streaming_dock, self.ptz_dock)

        # --- BOTTOM TASKBAR ---
        self.taskbar = QWidget()
        self.taskbar.setObjectName("TaskBar")
        self.taskbar.setFixedHeight(60)
        taskbar_layout = QHBoxLayout(self.taskbar)
        taskbar_layout.setContentsMargins(20, 0, 20, 0)

        self.app_menu_btn = QPushButton("💠")
        self.app_menu_btn.setStyleSheet("font-size: 20px; color: #00E676;")
        self.app_menu_btn.clicked.connect(self.show_launcher_menu)
        taskbar_layout.addWidget(self.app_menu_btn)
        taskbar_layout.addSpacing(10)

        # Taskbar buttons to toggle docks
        def create_toggle(label, dock):
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setChecked(True)
            btn.toggled.connect(dock.setVisible)
            dock.visibilityChanged.connect(btn.setChecked)
            return btn

        taskbar_layout.addWidget(create_toggle("⚙️ Config", self.config_dock))
        taskbar_layout.addWidget(create_toggle(
            "📸 Raw Feed", self.input_preview_dock))
        taskbar_layout.addWidget(create_toggle(
            "🧠 AI Feed", self.output_preview_dock))
        taskbar_layout.addWidget(create_toggle(
            "📡 Streaming", self.streaming_dock))
        taskbar_layout.addWidget(create_toggle("🕹️ PTZ", self.ptz_dock))

        self.preview_roi_cb = QCheckBox("ROI")
        self.preview_roi_cb.setChecked(True)
        self.preview_roi_cb.stateChanged.connect(self.update_toggles)
        self.output_roi_cb = QCheckBox("Out ROI")
        self.output_roi_cb.stateChanged.connect(self.update_toggles)
        self.flip_cb = QCheckBox("Flip")
        self.flip_cb.stateChanged.connect(self.update_toggles)
        self.debug_cb = QCheckBox("Debug")
        self.debug_cb.stateChanged.connect(self.toggle_debug)

        taskbar_layout.addSpacing(20)
        taskbar_layout.addWidget(self.preview_roi_cb)
        taskbar_layout.addWidget(self.output_roi_cb)
        taskbar_layout.addWidget(self.flip_cb)
        taskbar_layout.addWidget(self.debug_cb)
        taskbar_layout.addStretch()

        # Clock and System Info
        self.clock_label = QLabel()
        self.clock_label.setStyleSheet(
            "color: #AAA; font-weight: bold; font-family: monospace; margin-right: 10px;")
        taskbar_layout.insertWidget(
            taskbar_layout.count() - 2, self.clock_label)

        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(self.update_clock)
        self.clock_timer.start(1000)
        self.update_clock()
        self.status_label = QLabel("Status: Idle")
        self.status_label.setStyleSheet(
            "color: #00E676; font-weight: bold; margin-right: 15px;")
        taskbar_layout.addWidget(self.status_label)

        self.start_btn = QPushButton("▶ START ENGINE")
        self.start_btn.setObjectName("StartBtn")
        self.start_btn.clicked.connect(self.toggle_tracking)
        taskbar_layout.addWidget(self.start_btn)

        # Add taskbar to bottom
        self.setMenuWidget(None)  # Make sure no standard menu bar

        # We use a container for the bottom because QMainWindow layout is tricky
        main_container = QWidget()
        self.main_vlayout = QVBoxLayout(main_container)
        self.main_vlayout.setContentsMargins(0, 0, 0, 0)
        self.main_vlayout.setSpacing(0)

        # We need to move the dock manager area into the layout or just let QMainWindow handle it
        # Actually, QMainWindow handles docks automatically around the central widget.
        # So we just add the taskbar to the bottom of the window manually.

        self.addToolBar(Qt.ToolBarArea.BottomToolBarArea,
                        self.wrap_in_toolbar(self.taskbar))

        self.debug_container = QGroupBox("Debug Logs")
        debug_l = QVBoxLayout(self.debug_container)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        debug_l.addWidget(self.log_text)
        self.debug_dock = QDockWidget("📝 Logs", self)
        self.debug_dock.setObjectName("DebugDock")
        self.debug_dock.setWidget(self.debug_container)
        self.addDockWidget(
            Qt.DockWidgetArea.BottomDockWidgetArea, self.debug_dock)
        self.debug_dock.setVisible(False)

        self.update_classes({0: "anus", 1: "action_zoom",
                            2: "nipple", 3: "penis", 4: "vagina", 99: "face"})
        self.move_timer = QTimer(self)
        self.move_timer.timeout.connect(self.apply_manual_ptz)
        self.move_data = {"pan": 0, "tilt": 0, "zoom": 0, "start_time": 0}
        qt_handler.emitter.log_signal.connect(self.append_log)
        self.init_tray()
        global_logger.info("Application initialized.")

    def wrap_in_toolbar(self, widget):
        from PyQt6.QtWidgets import QToolBar
        tb = QToolBar()
        tb.setMovable(False)
        tb.addWidget(widget)
        tb.setStyleSheet("background: transparent; border: none;")
        return tb

    @Slot(str)
    def append_log(self, text): self.log_text.append(text)

    def init_tray(self):
        self.tray_icon = QSystemTrayIcon(self)
        # Use a generic icon or one from the project if available
        self.tray_icon.setIcon(self.style().standardIcon(
            QStyle.StandardPixmap.SP_ComputerIcon))

        tray_menu = QMenu()
        show_action = tray_menu.addAction("📂 Restore Workspace")
        show_action.triggered.connect(self.showNormal)

        start_action = tray_menu.addAction("▶ Start Tracking")
        start_action.triggered.connect(self.toggle_tracking)

        tray_menu.addSeparator()
        quit_action = tray_menu.addAction("❌ Exit")
        quit_action.triggered.connect(self.close)

        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.show()

    def toggle_panel(self, panel_name, checked):
        panel_map = {
            "config": self.config_dock,
            "raw": self.input_preview_dock,
            "ai": self.output_preview_dock,
            "stream": self.streaming_dock,
            "ptz": self.ptz_dock
        }
        if panel_name in panel_map:
            panel_map[panel_name].setVisible(checked)

    def update_clock(self):
        self.clock_label.setText(time.strftime("%H:%M:%S"))

    def show_launcher_menu(self):
        menu = QMenu(self)
        menu.setStyleSheet("QMenu { background-color: rgba(26, 26, 30, 240); color: white; border: 1px solid #333; padding: 5px; border-radius: 6px; } QMenu::item { padding: 8px 24px; border-radius: 4px; } QMenu::item:selected { background-color: #00E676; color: black; font-weight: bold; }")
        about_action = menu.addAction("ℹ️ About ZenithCam")
        about_action.triggered.connect(
            lambda: self.status_label.setText("ZenithCam v2.0 - Plasma Edition"))
        menu.addSeparator()
        exit_action = menu.addAction("❌ Shut Down")
        exit_action.triggered.connect(self.close)

        # Calculate position to pop UP from the button
        pos = self.app_menu_btn.mapToGlobal(self.app_menu_btn.rect().topLeft())
        pos.setY(pos.y() - menu.sizeHint().height() - 40)
        menu.exec(pos)

    def toggle_debug(self, *args):
        state = self.debug_cb.isChecked()
        self.debug_dock.setVisible(state)

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
            if "action_zoom" in t_name or "penis" in t_name:
                cb.setChecked(True)
            if t_name in ["anus", "nipple", "penis", "vagina", "face"]:
                cb_b.setChecked(True)
            if t_name == "face":
                cb.setEnabled(False)
                cb.setStyleSheet("color: #666;")
            cb.stateChanged.connect(self.update_target_classes)
            cb_b.stateChanged.connect(self.update_target_classes)
            self.class_layout.addWidget(cb)
            self.class_checkboxes.append((cid, cb))
            self.blur_layout.addWidget(cb_b)
            self.blur_checkboxes.append((cid, cb_b))
        self.update_target_classes()

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
        if self.thread and self.thread.isRunning():
            self.start_btn.setEnabled(False)
            self.start_btn.setText("Stopping...")
            self.worker.stop()
            self.thread.quit()
            self.thread.wait()
            self.start_btn.setEnabled(True)
            self.worker = None
            self.thread = None
        else:
            self.params['input_source'], self.params['output_device'] = self.input_spin.value(
            ), self.output_edit.currentText()
            self.update_smoothing()
            self.update_margin()
            self.update_target_classes()
            self.thread = QThread()
            self.worker = ZenithWorker(self.params)
            self.worker.moveToThread(self.thread)
            self.thread.started.connect(self.worker.process)
            self.worker.finished.connect(self.thread.quit)
            self.worker.finished.connect(self._on_worker_finished)
            self.worker.change_pixmap_signal.connect(self.update_image)
            self.worker.raw_pixmap_signal.connect(self.update_raw_image)
            self.worker.status_signal.connect(self.update_status)
            self.thread.start()
            self.start_btn.setText("Stop Tracking")
            self.start_btn.setStyleSheet(
                "background-color: #FF5252; color: white; font-weight: bold; padding: 15px; border-radius: 8px;")

    def _on_worker_finished(self):
        self.start_btn.setEnabled(True)
        self.start_btn.setText("Start Tracking")
        self.start_btn.setStyleSheet(
            "background-color: #00E676; color: black; font-weight: bold; padding: 15px; border-radius: 8px;")
        self.status_label.setText("Stopped.")
        self.input_preview_label.setText("Offline")
        self.output_preview_label.setText("Offline")

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
        if self.obsbot and self.obsbot.connected:
            self.obsbot.set_ai_mode(0)
            self.obsbot_ai_combo.setCurrentIndex(0)
        self.move_data.update(
            {"pan": pan, "tilt": tilt, "zoom": 0, "start_time": time.time()})
        self.move_timer.start(50)

    def start_manual_zoom(self, direction):
        if self.obsbot and self.obsbot.connected:
            self.obsbot.set_ai_mode(0)
            self.obsbot_ai_combo.setCurrentIndex(0)
        self.move_data.update(
            {"pan": 0, "tilt": 0, "zoom": direction, "start_time": time.time()})
        self.move_timer.start(50)

    def stop_manual_move(self):
        self.move_timer.stop()
        if self.obsbot and self.obsbot.connected:
            self.obsbot.set_gimbal_speed(0.0, 0.0)

    def apply_manual_ptz(self):
        if not self.obsbot or not self.obsbot.connected:
            return
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

    def manual_center(self, *args):
        if self.obsbot and self.obsbot.connected:
            self.obsbot.set_ai_mode(0)
            self.obsbot_ai_combo.setCurrentIndex(0)
            self.obsbot.set_gimbal_angle(0, 0)
            self.obsbot.set_zoom(1)
            if self.worker:
                self.worker._last_zoom = 1

    def reset_gimbal(self, *args):
        if self.obsbot and self.obsbot.connected:
            self.obsbot.set_ai_mode(0)
            self.obsbot_ai_combo.setCurrentIndex(0)
            self.obsbot.reset_gimbal()
            self.obsbot.set_zoom(1)
            if self.worker:
                self.worker._last_zoom = 1

    _SUBMODE_OPTIONS = {0: [], 1: ["Default"], 2: [
        "Full Body", "Upper Body"], 3: ["Default"], 4: ["Default"], 5: ["Default"]}

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

    def reconnect_obsbot(self, *args):
        if self.obsbot:
            self.status_label.setText("Reconnecting...")
            self.obsbot.disconnect()
            if self.obsbot.connect():
                self.obsbot.set_ai_mode(0)
                self.obsbot_ai_combo.setCurrentIndex(0)
                self.status_label.setText("Reconnected.")
            else:
                self.status_label.setText("Failed.")

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
                cmd = [
                    "/usr/bin/ffmpeg", "-y", "-thread_queue_size", "1024", "-f", "rawvideo", "-vcodec", "rawvideo", "-s", f"{width}x{height}", "-pix_fmt", "rgb24", "-framerate", "30", "-i", "-", "-thread_queue_size", "1024", "-f", "pulse", "-i", "default", "-c:v", "libx264", "-preset", "veryfast", "-tune", "zerolatency", "-profile:v", "main", "-bf", "0"
                ]
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
                cmd.extend(["-pix_fmt", "yuv420p", "-g", "60", "-keyint_min", "60", "-c:a",
                           "aac", "-b:a", "128k", "-ar", "48000", "-ac", "2", "-f", "flv", full_url])
                global_logger.info(
                    f"Starting stream to {p['name']}: {' '.join(cmd)}")
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
        if self.thread and self.thread.isRunning():
            self.worker.stop()
            self.thread.quit()
            self.thread.wait(3000)
            if self.thread.isRunning():
                self.thread.terminate()
                self.thread.wait()
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyleSheet(STYLESHEET)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
