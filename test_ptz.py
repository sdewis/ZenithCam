import time
import sys
import logging

logging.basicConfig(level=logging.DEBUG)

sys.path.append("/home/sean/CodeFolder/ZenithCam_SDK_Integrated/app")
from obsbot_wrapper import OBSBOTSDK

def test_ptz():
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
    
    time.sleep(1.0)
    print("Trying to pan left with python float (speed -30)...")
    obsbot.set_gimbal_speed(0.0, -30.0)
    time.sleep(1.0)
    obsbot.set_gimbal_speed(0.0, 0.0)
    
    print("Test finished.")

if __name__ == "__main__":
    test_ptz()
