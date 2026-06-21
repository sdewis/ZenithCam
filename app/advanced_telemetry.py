import numpy as np  # type: ignore
import logging
import threading
import time
import urllib.request
import json

logger = logging.getLogger(__name__)

class SensorFusionTracker:
    """
    Groundbreaking Audio-Visual Kalman Filter.
    Fuses OBSBOT 'Direction of Arrival' (DOA) Audio data with YOLOv11 Visual data.
    """
    def __init__(self, obsbot_sdk_bridge):
        self.sdk = obsbot_sdk_bridge
        self.audio_weight = 0.2
        self.visual_weight = 0.8
        self.last_known_visual_vector = None

    def compute_ptz_vector(self, yolo_bbox, audio_doa_angle):
        """
        Calculates the optimal pan/tilt vector based on audio-visual presence.
        doa_angle: Provided by OBSBOT Tiny3 `doa_set.doa_range` via C++ SDK.
        """
        if yolo_bbox is not None:
            # Vision takes priority. Target is in frame.
            center_x = (yolo_bbox[0] + yolo_bbox[2]) / 2.0
            # Normalize to -1.0 to 1.0 motor space
            visual_pan = (center_x / 1280.0) * 2 - 1 
            self.last_known_visual_vector = visual_pan
            return visual_pan
            
        elif audio_doa_angle is not None:
            # TARGET LOST. Rely on Audio DOA to find them.
            logger.info(f"Target Lost computationally. Steering to Audio DOA: {audio_doa_angle}deg")
            # Convert 360 audio degree to relative pan motor instruction
            audio_pan = self._map_doa_to_motor_space(audio_doa_angle)
            return audio_pan * self.audio_weight
            
        # Fallback to last known position
        return self.last_known_visual_vector if self.last_known_visual_vector else 0.0

    def _map_doa_to_motor_space(self, angle):
        """Maps 0-360 audio array direction to -1.0 to 1.0 motor speed."""
        if angle > 180:
            return (angle - 360) / 180.0 # Pan Left
        return angle / 180.0 # Pan Right


class DynamicQoSController:
    """
    Groundbreaking Quality of Service Controller.
    Monitors YOLO inference classes and dynamically triggers FFmpeg bitrate changes.
    """
    def __init__(self):
        self.current_tier = "medium"
        self.bitrate_map = {
            "low": "2000k",
            "medium": "4000k",
            "high": "8000k" # High action / NSFW scene
        }
        
    def analyze_scene(self, yolo_classes_detected, optical_flow_magnitude):
        """Evaluates scene intensity and adjusts streaming bitrate."""
        # Class 1 = action/make_love (from EraX NSFW model)
        is_high_action_class = 1 in yolo_classes_detected
        is_high_motion = optical_flow_magnitude > 15.0
        
        target_tier = "medium"
        if is_high_action_class or is_high_motion:
            target_tier = "high"
        elif len(yolo_classes_detected) == 0 and optical_flow_magnitude < 2.0:
            target_tier = "low" # Static scene, save bandwidth
            
        if target_tier != self.current_tier:
            self._trigger_ffmpeg_reconfigure(self.bitrate_map[target_tier])
            self.current_tier = target_tier
            
    def _trigger_ffmpeg_reconfigure(self, new_bitrate):
        # In a real environment, this interacts with FFmpeg's ZMQ/RPC interface
        logger.info(f"📡 QoS Trigger: Scene dynamics changed. Adjusting Stream Bitrate to {new_bitrate}")

class TeledildonicsController:
    """
    AI-Driven Webhook Controller.
    Maps optical flow to hardware intensity (0-100) and dispatches it via HTTP POST.
    """
    def __init__(self):
        self.webhook_url = ""
        self.enabled = False
        self.current_intensity = 0
        self.last_sent_intensity = -1
        self.last_send_time = 0.0
        self.running = True
        self.thread = threading.Thread(target=self._worker_loop, daemon=True)
        self.thread.start()
        
    def set_config(self, enabled: bool, url: str):
        self.enabled = enabled
        self.webhook_url = url
        if not enabled and self.current_intensity > 0:
            self.current_intensity = 0 # zero out on disable

    def analyze_scene(self, yolo_classes_detected, optical_flow_magnitude):
        if not self.enabled:
            return
            
        # Target classes (action = 1, penis = 3, vagina = 4)
        # Linear map optical flow 0-25 into 0-100 intensity
        base_intensity = min(100, int((optical_flow_magnitude / 25.0) * 100))
        
        if 1 in yolo_classes_detected or 3 in yolo_classes_detected or 4 in yolo_classes_detected:
            base_intensity = max(base_intensity, 20)
            
        # Temporal smoothing 
        self.current_intensity = int(0.7 * self.current_intensity + 0.3 * base_intensity)
        
    def _worker_loop(self):
        while self.running:
            if not self.enabled or not self.webhook_url:
                time.sleep(0.5)
                continue
                
            # Rate limiting: Max 4 transmissions per second
            now = time.time()
            if (now - self.last_send_time > 0.25) and (abs(self.current_intensity - self.last_sent_intensity) > 2 or self.current_intensity == 0):
                self._send_command(self.current_intensity)
                self.last_sent_intensity = self.current_intensity
                self.last_send_time = now
            else:
                time.sleep(0.05)
                
    def _send_command(self, intensity):
        try:
            req = urllib.request.Request(self.webhook_url, method="POST")
            req.add_header('Content-Type', 'application/json')
            # XToys webhooks require an 'action' parameter to map to the script trigger
            data = json.dumps({"action": "AI_Intensity", "intensity": intensity}).encode('utf-8')
            with urllib.request.urlopen(req, data=data, timeout=0.2) as response:
                pass
        except Exception as e:
            # We fail silently to not flood the logs if hardware server goes offline.
            pass
            
    def stop(self):
        self.running = False
        self.thread.join(timeout=1.0)