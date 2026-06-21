import time
import sys
import os
import logging
import cv2

logging.basicConfig(level=logging.DEBUG)

sys.path.append(os.path.join(os.path.dirname(__file__), "app"))
from obsbot_wrapper import OBSBOTSDK

def test_opencv_conflict():
    print("Opening cv2 capture...")
    cap = cv2.VideoCapture(1)
    
    time.sleep(1)
    
    print("Testing OBSBOT SDK connection independently...")
    
    obsbot = OBSBOTSDK()
    if not obsbot.init():
        print("Failed to init OBSBOT SDK")
        return
        
    if not obsbot.connect():
        print("Failed to connect OBSBOT SDK")
        return
        
    print("Connected successfully!")
    
    print("Trying to pan right (speed 30)...")
    res = obsbot.set_gimbal_speed(0.0, 30.0)
    print("Result:", res)
    time.sleep(1.0)
    
    print("Trying to stop...")
    obsbot.set_gimbal_speed(0.0, 0.0)
    
    print("Test finished.")
    cap.release()

if __name__ == "__main__":
    test_opencv_conflict()
