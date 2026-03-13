import cv2
import numpy as np
import onnxruntime as ort
import os
import time
import logging
import threading
import queue
import mediapipe as mp
from mediapipe.tasks.python import BaseOptions
from mediapipe.tasks.python import vision

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("MLPipeline")

class MLPipeline(threading.Thread):
    def __init__(self, model_path, config, target_classes=None, blur_classes=None):
        """
        Initializes the Unified Single-Pass Inference Engine with Async Inference.
        """
        super().__init__()
        self.model_path = model_path
        self.config = config
        self.target_classes = target_classes if target_classes else []
        self.blur_classes = blur_classes if blur_classes else []
        
        self.input_resolution = config.get("inference_resolution", (640,480))
        
        # ONNX Runtime
        self.providers = [config.get("execution_provider", "CPUExecutionProvider")]
        try:
            self.session = ort.InferenceSession(self.model_path, providers=self.providers)
            self.input_name = self.session.get_inputs()[0].name
            self.output_names = [o.name for o in self.session.get_outputs()]
            
            # Override input_resolution if model has a fixed input shape
            input_shape = self.session.get_inputs()[0].shape
            if len(input_shape) == 4 and isinstance(input_shape[2], int):
                self.input_resolution = (input_shape[3], input_shape[2])
                
            logger.info(f"Model loaded from {self.model_path} with providers: {self.providers}")
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            raise

        # Threading State
        self.running = True
        self.frame_queue = queue.Queue(maxsize=1)
        self.result_queue = queue.Queue(maxsize=1)
        self.inference_busy = False
        
        self.current_boxes = [] # [(x, y, w, h, class_id, conf)]
        self.prev_gray = None
        self.smooth_factor = 0.1 # Default
        
        # CLAHE for Face Detection
        self.clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8,8))
        
        # Initialize MediaPipe Face Landmarker
        mp_model_path = os.path.join(os.path.dirname(__file__), "models", "face_landmarker.task")
        try:
            self._mp_landmarker = vision.FaceLandmarker.create_from_options(
                vision.FaceLandmarkerOptions(
                    base_options=BaseOptions(model_asset_path=mp_model_path),
                    running_mode=vision.RunningMode.VIDEO,
                    num_faces=1,
                    min_face_detection_confidence=0.5,
                    min_face_presence_confidence=0.5,
                    min_tracking_confidence=0.5,
                )
            )
            logger.info("MediaPipe FaceLandmarker loaded successfully.")
        except Exception as e:
            logger.error(f"Failed to load MediaPipe model: {e}")
            self._mp_landmarker = None

    def preprocess(self, frame):
        img = cv2.resize(frame, self.input_resolution)
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        img = img.astype(np.float32) / 255.0
        img = np.transpose(img, (2, 0, 1))
        img = np.expand_dims(img, axis=0)
        return img

    def postprocess(self, outputs, original_shape):
        predictions = outputs[0]
        if len(predictions.shape) == 3: predictions = predictions[0]
        predictions = np.transpose(predictions)
        
        boxes = []
        conf_threshold = 0.25
        h, w = original_shape[:2]
        x_factor = w / self.input_resolution[0]
        y_factor = h / self.input_resolution[1]

        for pred in predictions:
            classes_scores = pred[4:]
            class_id = np.argmax(classes_scores)
            confidence = classes_scores[class_id]
            
            if confidence > conf_threshold:
                xc, yc, bw, bh = pred[:4]
                left = int((xc - bw/2) * x_factor)
                top = int((yc - bh/2) * y_factor)
                width = int(bw * x_factor)
                height = int(bh * y_factor)
                boxes.append([left, top, width, height, class_id, confidence])
                
        if not boxes: return []
        boxes_np = np.array(boxes)
        indices = cv2.dnn.NMSBoxes(boxes_np[:, :4].tolist(), boxes_np[:, 5].tolist(), conf_threshold, 0.4)
        return [boxes[i] for i in indices.flatten()] if len(indices) > 0 else []

    def run(self):
        """Inference Loop"""
        while self.running:
            try:
                frame = self.frame_queue.get(timeout=0.1)
                self.inference_busy = True
                
                # Inference YOLO
                input_tensor = self.preprocess(frame)
                outputs = self.session.run(self.output_names, {self.input_name: input_tensor})
                boxes = self.postprocess(outputs, frame.shape)
                
                # Inference MediaPipe
                if self._mp_landmarker:
                    timestamp_ms = int(time.time() * 1000)
                    
                    # Apply intelligent contrast enhancement (CLAHE) for better face detection
                    lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
                    l, a, b = cv2.split(lab)
                    cl = self.clahe.apply(l)
                    limg = cv2.merge((cl,a,b))
                    enhanced_bgr = cv2.cvtColor(limg, cv2.COLOR_LAB2BGR)
                    
                    rgb_frame = cv2.cvtColor(enhanced_bgr, cv2.COLOR_BGR2RGB)
                    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
                    result = self._mp_landmarker.detect_for_video(mp_image, timestamp_ms)
                    
                    face_detected_this_frame = False
                    if result.face_landmarks:
                        face = result.face_landmarks[0]
                        h, w = frame.shape[:2]
                        # Calculate bounding box from landmarks
                        xs = [lm.x * w for lm in face]
                        ys = [lm.y * h for lm in face]
                        x_min, x_max = int(min(xs)), int(max(xs))
                        y_min, y_max = int(min(ys)), int(max(ys))
                        # Add some padding to face box
                        pad_w = int((x_max - x_min) * 0.2)
                        pad_h = int((y_max - y_min) * 0.2)
                        fx = max(0, x_min - pad_w)
                        fy = max(0, y_min - pad_h)
                        fw = min(w - fx, (x_max - x_min) + pad_w * 2)
                        fh = min(h - fy, (y_max - y_min) + pad_h * 2)
                        
                        current_face = [fx, fy, fw, fh]
                        
                        if not hasattr(self, '_last_face_box') or self._last_face_box is None:
                            self._last_face_box = current_face
                        else:
                            # EMA Smoothing to eliminate flickering
                            alpha = self.smooth_factor
                            self._last_face_box = [
                                int(alpha * current_face[i] + (1 - alpha) * self._last_face_box[i])
                                for i in range(4)
                            ]
                        
                        self._face_timeout = 0
                        face_detected_this_frame = True
                    
                    # Persist the face box for a few frames if detection drops
                    if not face_detected_this_frame and hasattr(self, '_last_face_box') and self._last_face_box is not None:
                        if not hasattr(self, '_face_timeout'): self._face_timeout = 0
                        self._face_timeout += 1
                        # Keep the face blurred for up to 10 inference frames if it drops out
                        if self._face_timeout > 10:
                            self._last_face_box = None
                    
                    if hasattr(self, '_last_face_box') and self._last_face_box is not None:
                         lfx, lfy, lfw, lfh = self._last_face_box
                         boxes.append([lfx, lfy, lfw, lfh, 99, 1.0])
                
                # Clear old results and put new
                if not self.result_queue.empty():
                    try: self.result_queue.get_nowait()
                    except: pass
                self.result_queue.put(boxes)
                
                self.inference_busy = False
            except queue.Empty:
                pass
            except Exception as e:
                logger.error(f"Inference error: {e}")
                self.inference_busy = False

    def process_frame(self, frame):
        """
        Called by main loop (60 FPS).
        Returns (zoom_boxes, blur_boxes)
        """
        current_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        # 1. Check for new inference results
        try:
            new_boxes = self.result_queue.get_nowait()
            self.current_boxes = new_boxes
            # When we get new boxes, they are technically "old" (from when inference started)
            # But for simple stabilization, we reset tracking to these reliable boxes.
        except queue.Empty:
            # 2. No new result, Track/Extrapolate using Optical Flow
            if self.prev_gray is not None and self.current_boxes:
                # Use Farneback optical flow (dense) but sampled sparsely at box centers for speed
                # Or just full frame if resolution is low enough?
                # For 720p/1080p, full flow is slow.
                # Let's use a very simplified approach: Calculate flow on a downscaled version.
                
                small_prev = cv2.resize(self.prev_gray, (160, 90), interpolation=cv2.INTER_NEAREST)
                small_curr = cv2.resize(current_gray, (160, 90), interpolation=cv2.INTER_NEAREST)
                
                flow = cv2.calcOpticalFlowFarneback(small_prev, small_curr, None, 0.5, 3, 15, 3, 5, 1.2, 0)
                
                sx = frame.shape[1] / 160.0
                sy = frame.shape[0] / 90.0
                
                tracked_boxes = []
                for box in self.current_boxes:
                    x, y, w, h, cid, conf = box
                    
                    # Center in small coords
                    cx = int((x + w/2) / sx)
                    cy = int((y + h/2) / sy)
                    
                    cx = max(0, min(cx, 159))
                    cy = max(0, min(cy, 89))
                    
                    dx, dy = flow[cy, cx]
                    
                    # Scale flow back
                    dx *= sx
                    dy *= sy
                    
                    tracked_boxes.append([int(x+dx), int(y+dy), w, h, cid, conf])
                self.current_boxes = tracked_boxes

        # 3. Trigger new inference if idle
        if not self.inference_busy and self.frame_queue.empty():
            self.frame_queue.put(frame.copy()) # Copy to avoid race condition
            
        self.prev_gray = current_gray
        
        # Dispatch
        zoom_boxes = []
        blur_boxes = []
        
        for box in self.current_boxes:
            class_id = box[4]
            rect = tuple(box[:4])
            if class_id in self.target_classes:
                zoom_boxes.append(rect)
            if class_id in self.blur_classes:
                blur_boxes.append(rect)
        
        return zoom_boxes, blur_boxes

    def stop(self):
        self.running = False
        if self._mp_landmarker:
            self._mp_landmarker.close()
