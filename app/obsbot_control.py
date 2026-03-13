#!/usr/bin/env python3
"""
OBSBOT PTZ Camera Control Library
Python interface for v4l2-based gimbal control

Supports OBSBOT Tiny SE and similar UVC PTZ cameras.

Usage:
    from obsbot_control import OBSBOTController

    camera = OBSBOTController()
    camera.connect()
    camera.pan_tilt_control(pan_delta=50)
    camera.save_frame()
    camera.disconnect()

Environment Variables:
    OBSBOT_DEVICE: Video device path (default: /dev/video0)
    OBSBOT_OUTPUT_DIR: Capture output directory (default: /tmp/obsbot_captures)

@license MIT
"""

import subprocess
import cv2
import time
import os
from pathlib import Path
from typing import Optional, Tuple, Dict, Any


class OBSBOTController:
    """PTZ camera controller using v4l2-ctl and OpenCV"""

    def __init__(self, device: str = None, output_dir: str = None):
        """
        Initialize OBSBOT controller

        Args:
            device: Video device path (default: from env or /dev/video0)
            output_dir: Capture output directory (default: from env or /tmp/obsbot_captures)
        """
        self.device = device or os.environ.get('OBSBOT_DEVICE', '/dev/video5')
        self.output_dir = Path(output_dir or os.environ.get('OBSBOT_OUTPUT_DIR', '/tmp/obsbot_captures'))
        self.cap = None
        self.current_pan = 0
        self.current_tilt = 0
        self.current_zoom = 0

        # v4l2 control limits for OBSBOT Tiny SE
        self.limits = {
            'pan': {'min': -468000, 'max': 468000, 'step': 3600},
            'tilt': {'min': -324000, 'max': 324000, 'step': 3600},
            'zoom': {'min': 0, 'max': 12, 'step': 1}
        }

        # Ensure output directory exists
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def check_device(self) -> bool:
        """Check if camera is connected and accessible"""
        try:
            result = subprocess.run(
                ['v4l2-ctl', '--list-devices'],
                capture_output=True, text=True
            )
            print("Available video devices:")
            print(result.stdout)
            return self.device in result.stdout or Path(self.device).exists()
        except Exception as e:
            print(f"Error checking video devices: {e}")
            return False

    def connect(self) -> bool:
        """Connect to camera"""
        try:
            self.cap = cv2.VideoCapture(self.device, cv2.CAP_V4L2)
            if not self.cap.isOpened():
                print(f"Cannot open camera device {self.device}")
                return False

            # Set resolution
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
            self.cap.set(cv2.CAP_PROP_FPS, 30)

            print(f"Connected to camera: {self.device}")
            self._get_current_position()
            return True
        except Exception as e:
            print(f"Error connecting to camera: {e}")
            return False

    def _get_current_position(self) -> Dict[str, int]:
        """Get current gimbal position from device"""
        try:
            result = subprocess.run(
                ['v4l2-ctl', '-d', self.device, '--get-ctrl=pan_absolute,tilt_absolute,zoom_absolute'],
                capture_output=True, text=True
            )
            lines = result.stdout.strip().split('\n')
            for line in lines:
                if 'pan_absolute:' in line:
                    self.current_pan = int(line.split(':')[1].strip())
                elif 'tilt_absolute:' in line:
                    self.current_tilt = int(line.split(':')[1].strip())
                elif 'zoom_absolute:' in line:
                    self.current_zoom = int(line.split(':')[1].strip())

            return {
                'pan': self.current_pan,
                'tilt': self.current_tilt,
                'zoom': self.current_zoom
            }
        except Exception as e:
            print(f"Error getting position: {e}")
            return {'pan': 0, 'tilt': 0, 'zoom': 0}

    def capture_frame(self) -> Optional[any]:
        """Capture a single frame from the camera"""
        if not self.cap:
            print("Camera not connected")
            return None

        ret, frame = self.cap.read()
        if ret:
            return frame
        else:
            print("Failed to capture frame")
            return None

    def save_frame(self, filename: str = None) -> Optional[str]:
        """Capture and save a frame"""
        if not filename:
            timestamp = int(time.time())
            filename = str(self.output_dir / f"capture_{timestamp}.jpg")

        frame = self.capture_frame()
        if frame is not None:
            cv2.imwrite(filename, frame)
            print(f"Frame saved: {filename}")
            return filename
        return None

    def set_position(self, pan: int = None, tilt: int = None, zoom: int = None) -> bool:
        """
        Set absolute gimbal position

        Args:
            pan: Absolute pan position (-468000 to 468000)
            tilt: Absolute tilt position (-324000 to 324000)
            zoom: Absolute zoom level (0 to 12)
        """
        controls = []

        if pan is not None:
            pan = max(self.limits['pan']['min'], min(self.limits['pan']['max'], pan))
            controls.append(f'pan_absolute={pan}')
            self.current_pan = pan

        if tilt is not None:
            tilt = max(self.limits['tilt']['min'], min(self.limits['tilt']['max'], tilt))
            controls.append(f'tilt_absolute={tilt}')
            self.current_tilt = tilt

        if zoom is not None:
            zoom = max(self.limits['zoom']['min'], min(self.limits['zoom']['max'], zoom))
            controls.append(f'zoom_absolute={zoom}')
            self.current_zoom = zoom

        if not controls:
            return True

        try:
            cmd = ['v4l2-ctl', '-d', self.device, '--set-ctrl', ','.join(controls)]
            subprocess.run(cmd, check=True, capture_output=True)
            print(f"Position set: pan={self.current_pan}, tilt={self.current_tilt}, zoom={self.current_zoom}")
            return True
        except subprocess.CalledProcessError as e:
            print(f"Position control failed: {e}")
            return False

    def pan_tilt_control(self, pan_delta: int = 0, tilt_delta: int = 0) -> bool:
        """
        Control camera pan/tilt relative to current position

        Args:
            pan_delta: Relative pan change
            tilt_delta: Relative tilt change
        """
        new_pan = self.current_pan + pan_delta
        new_tilt = self.current_tilt + tilt_delta
        return self.set_position(pan=new_pan, tilt=new_tilt)

    def zoom_control(self, zoom_delta: int = 0) -> bool:
        """Control camera zoom relative to current level"""
        new_zoom = self.current_zoom + zoom_delta
        return self.set_position(zoom=new_zoom)

    def center(self) -> bool:
        """Return camera to center position"""
        return self.set_position(pan=0, tilt=0, zoom=0)

    def get_camera_controls(self) -> Optional[str]:
        """Get available camera controls"""
        try:
            result = subprocess.run(
                ['v4l2-ctl', '-d', self.device, '--list-ctrls'],
                capture_output=True, text=True
            )
            print("Available camera controls:")
            print(result.stdout)
            return result.stdout
        except Exception as e:
            print(f"Error getting camera controls: {e}")
            return None

    def preset_position(self, position: str = "center") -> bool:
        """
        Move to preset positions

        Args:
            position: Preset name (center, left, right, up, down)
        """
        presets = {
            "center": (0, 0, 0),
            "left": (200000, 0, None),
            "right": (-200000, 0, None),
            "up": (0, 150000, None),
            "down": (0, -100000, None),
            "left_up": (200000, 150000, None),
            "right_up": (-200000, 150000, None),
            "left_down": (200000, -100000, None),
            "right_down": (-200000, -100000, None),
        }

        if position in presets:
            pan, tilt, zoom = presets[position]
            return self.set_position(pan=pan, tilt=tilt, zoom=zoom)
        else:
            print(f"Unknown preset: {position}")
            print(f"Available presets: {list(presets.keys())}")
            return False

    def scan_horizontal(self, steps: int = 5, capture: bool = True) -> list:
        """
        Perform horizontal pan scan

        Args:
            steps: Number of positions to scan
            capture: Whether to capture frames at each position

        Returns:
            List of capture results or positions
        """
        results = []
        pan_range = self.limits['pan']['max'] - self.limits['pan']['min']
        step_size = pan_range // (steps - 1)

        for i in range(steps):
            pan = self.limits['pan']['min'] + (step_size * i)
            self.set_position(pan=pan, tilt=0)
            time.sleep(1)  # Wait for movement

            if capture:
                filename = str(self.output_dir / f"scan_h_{i+1}_{int(time.time())}.jpg")
                result = self.save_frame(filename)
                results.append({'position': i + 1, 'pan': pan, 'file': result})
            else:
                results.append({'position': i + 1, 'pan': pan})

        self.center()
        return results

    def disconnect(self):
        """Disconnect from camera"""
        if self.cap:
            self.cap.release()
            print("Camera disconnected")


def main():
    """Main function for testing"""
    print("OBSBOT Camera Control Library")
    print("=" * 40)

    controller = OBSBOTController()

    if not controller.check_device():
        print("Camera device not found")
        return

    if controller.connect():
        print("\nCamera connected successfully!")

        # Get available controls
        controller.get_camera_controls()

        # Test movements
        print("\nTesting camera movements...")
        controller.preset_position("center")
        time.sleep(1)
        controller.preset_position("left")
        time.sleep(1)
        controller.preset_position("right")
        time.sleep(1)
        controller.preset_position("center")

        # Capture test frame
        frame_path = controller.save_frame()
        if frame_path:
            print(f"Test frame saved: {frame_path}")

        controller.disconnect()
    else:
        print("Camera not available")


if __name__ == "__main__":
    main()
