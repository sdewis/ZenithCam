import numpy as np
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("PTZCamera")

class PTZCamera:
    def __init__(self, source_w, source_h, target_w=1280, target_h=720, smoothing_factor=0.1):
        """
        Initializes the Virtual PTZ Camera logic with a Kalman Filter.
        """
        self.source_w = source_w
        self.source_h = source_h
        self.target_w = target_w
        self.target_h = target_h
        self.aspect_ratio = target_w / target_h
        
        # Kalman Filter State: [x, y, w, h, dx, dy, dw, dh]
        self.state = np.array([0.0, 0.0, float(source_w), float(source_w / self.aspect_ratio), 0.0, 0.0, 0.0, 0.0])
        self.uncertainty = np.eye(8) * 1000.0
        
        # Process Noise
        self.Q = np.eye(8) * 0.01
        self.Q[4:, 4:] *= 0.1 # Velocity noise
        
        # Measurement Noise
        self.R = np.eye(4) * 2.0
        
        # Transition Matrix (Constant Velocity)
        self.F = np.eye(8)
        self.F[0, 4] = self.F[1, 5] = self.F[2, 6] = self.F[3, 7] = 1.0
        
        # Measurement Matrix
        self.H = np.zeros((4, 8))
        self.H[:4, :4] = np.eye(4)
        
        self.margin_percentage = 0.20
        self.smoothing_factor = smoothing_factor
        logger.info(f"PTZ Camera initialized: {source_w}x{source_h} with Kalman Filter")

    def update(self, target_boxes):
        """
        Calculates the new crop window using Kalman Filter prediction and update.
        """
        # Dynamically adjust process noise based on smoothing factor
        # Higher smoothing factor (closer to 1.0) = higher noise = more responsive/jittery
        # Lower smoothing factor (closer to 0.0) = lower noise = more damped/smooth
        base_q_scale = max(0.0001, self.smoothing_factor)
        current_Q = self.Q * base_q_scale

        # 1. Prediction
        self.state = self.F @ self.state
        self.uncertainty = self.F @ self.uncertainty @ self.F.T + current_Q
        
        # 2. Measurement
        if not hasattr(self, 'no_detection_counter'):
            self.no_detection_counter = 0
            self.last_valid_z = np.array([0.0, 0.0, float(self.source_w), float(self.source_h)])
            
        if not target_boxes:
            self.no_detection_counter += 1
            if self.no_detection_counter > 60: # Approx 1 second at 60 FPS
                z = np.array([0.0, 0.0, float(self.source_w), float(self.source_h)])
            else:
                z = self.last_valid_z # Hold the last known frame
        else:
            self.no_detection_counter = 0
            # Calculate union box
            min_x = min(b[0] for b in target_boxes)
            min_y = min(b[1] for b in target_boxes)
            max_x = max(b[0] + b[2] for b in target_boxes)
            max_y = max(b[1] + b[3] for b in target_boxes)
            
            union_w, union_h = max_x - min_x, max_y - min_y
            center_x, center_y = min_x + union_w / 2.0, min_y + union_h / 2.0
            
            target_w = union_w * (1.0 + 2 * self.margin_percentage)
            target_h = union_h * (1.0 + 2 * self.margin_percentage)
            
            # Aspect Ratio Adjustment
            if (target_w / target_h) > self.aspect_ratio:
                final_w = target_w
                final_h = target_w / self.aspect_ratio
            else:
                final_h = target_h
                final_w = target_h * self.aspect_ratio
                
            # Clamp and Center
            final_w = min(final_w, self.source_w)
            final_h = min(final_h, self.source_h)
            
            target_x = np.clip(center_x - final_w / 2.0, 0, self.source_w - final_w)
            target_y = np.clip(center_y - final_h / 2.0, 0, self.source_h - final_h)
            
            z = np.array([target_x, target_y, final_w, final_h])
            self.last_valid_z = z

        # 3. Update
        y = z - (self.H @ self.state) # Innovation
        S = self.H @ self.uncertainty @ self.H.T + self.R # Innovation Covariance
        K = self.uncertainty @ self.H.T @ np.linalg.inv(S) # Kalman Gain
        
        self.state = self.state + (K @ y)
        self.uncertainty = (np.eye(8) - (K @ self.H)) @ self.uncertainty
        
        return tuple(self.state[:4].astype(int))

