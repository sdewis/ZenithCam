import sys
import cv2
import numpy as np
import time
import os
import logging
from ml_pipeline import MLPipeline
from ptz_camera import PTZCamera
from renderer import Renderer
from hardware_profiler import HardwareProfiler

# Setup specialized logging for this test
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("NSFW_Test")

def run_test():
    # Model configuration
    model_path = "../models/erax_nsfw/erax_nsfw_yolo11s.onnx"
    # Mapping based on erax-ai/EraX-NSFW-V1.0
    # 0: anus, 1: action_zoom, 2: nipple, 3: penis, 4: vagina
    target_class_ids = [1, 3, 4] # Tracking action_zoom, penis, vagina
    blur_class_ids = [0, 2, 3, 4] # Blurring sensitive parts
    
    # Input source (default to 1 as per main.py logic)
    input_source = 1 
    output_width = 1280
    output_height = 720
    
    profiler = HardwareProfiler()
    hw_config = profiler.probe_system()
    
    logger.info(f"Opening camera {input_source}...")
    cap = cv2.VideoCapture(input_source, cv2.CAP_V4L2)
    if not cap.isOpened():
        logger.error("Could not open camera.")
        return

    # Warmup
    ret, frame = cap.read()
    if not ret:
        logger.error("Cannot read from camera.")
        return
    
    cam_h, cam_w = frame.shape[:2]
    target_ratio = output_width / output_height
    
    # Initialize Pipeline
    try:
        pipeline = MLPipeline(model_path, hw_config, target_class_ids, blur_class_ids)
        pipeline.start()
    except Exception as e:
        logger.error(f"Failed to start pipeline: {e}")
        return

    ptz = PTZCamera(cam_w, cam_h, target_w=output_width, target_h=output_height, smoothing_factor=0.1)
    renderer = Renderer(cam_w, cam_h)
    renderer.set_config(hw_config)

    logger.info("Test Run Started. Press 'Q' to exit.")
    
    try:
        frame_count = 0
        while True:
            ret, frame = cap.read()
            if not ret: 
                logger.error(f"Failed to read frame at count {frame_count}")
                break
            
            frame_count += 1
            if frame_count % 30 == 0:
                logger.info(f"Processed {frame_count} frames...")
            
            # Process
            zoom_boxes, blur_boxes = pipeline.process_frame(frame)
            if zoom_boxes or blur_boxes:
                logger.info(f"Frame {frame_count}: Detected {len(zoom_boxes)} zoom targets, {len(blur_boxes)} blur targets")
            
            crop_rect = ptz.update(zoom_boxes)
            
            # Render
            rendered = renderer.render(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB), crop_rect, blur_boxes)
            display_frame = cv2.cvtColor(rendered, cv2.COLOR_RGB2BGR)
            
            # Draw ROI for debug
            for (bx, by, bw, bh) in zoom_boxes:
                cv2.rectangle(display_frame, (bx-crop_rect[0], by-crop_rect[1]), 
                              (bx+bw-crop_rect[0], by+bh-crop_rect[1]), (0, 255, 0), 2)
            
            cv2.imshow("ZenithCam NSFW Tracking Test", display_frame)
            
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
    finally:
        logger.info("Cleaning up...")
        pipeline.stop()
        cap.release()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    run_test()
