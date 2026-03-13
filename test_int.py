import time
import sys
import logging
sys.path.append("/home/sean/CodeFolder/ZenithCam_SDK_Integrated/app")
from obsbot_wrapper import OBSBOTSDK

def test_types():
    obsbot = OBSBOTSDK()
    obsbot.init()
    obsbot.connect()
    
    print("Testing sending integers to set_gimbal_speed...")
    try:
        # Intentionally sending integers instead of floats to see if ctypes catches it or if it crashes!
        res = obsbot.set_gimbal_speed(0, 0)
        print("Result:", res)
    except Exception as e:
        print("EXCEPTION CAUGHT:", e)

if __name__ == "__main__":
    test_types()
