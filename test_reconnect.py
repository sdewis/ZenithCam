import time
import sys
import logging

logging.basicConfig(level=logging.DEBUG)

sys.path.append("/home/sean/CodeFolder/ZenithCam_SDK_Integrated/app")
from obsbot_wrapper import OBSBOTSDK
import cv2

def test_ptz_reconnect():
    print("Testing OBSBOT SDK connection independently...")
    
    obsbot1 = OBSBOTSDK()
    if not obsbot1.init():
        print("Failed to init OBSBOT SDK")
        return
        
    if not obsbot1.connect():
        print("Failed to connect OBSBOT SDK")
        return
        
    print("Instance 1 Connected successfully!")
    
    print("Trying to pan right (speed 30)...")
    res = obsbot1.set_gimbal_speed(0.0, 30.0)
    print("Result 1:", res)
    time.sleep(1.0)
    obsbot1.set_gimbal_speed(0.0, 0.0)
    
    print("\nSimulating stop tracking thread, releasing capture...")
    print("And then start tracking thread again...")
    
    obsbot2 = OBSBOTSDK()
    if not obsbot2.init():
        print("Failed to init OBSBOT SDK 2")
        return
        
    if not obsbot2.connect():
        print("Failed to connect OBSBOT SDK 2")
        return
        
    print("Instance 2 Connected successfully!")
    
    print("Trying to pan left with python float (speed -30)...")
    res = obsbot2.set_gimbal_speed(0.0, -30.0)
    print("Result 2:", res)
    time.sleep(1.0)
    obsbot2.set_gimbal_speed(0.0, 0.0)
    
    print("Test finished.")

if __name__ == "__main__":
    test_ptz_reconnect()
