import time
import sys
import logging

logging.basicConfig(level=logging.DEBUG)

sys.path.append("/home/sean/CodeFolder/ZenithCam_SDK_Integrated/app")
from obsbot_wrapper import OBSBOTSDK

def test_spam():
    obsbot = OBSBOTSDK()
    if not obsbot.init() or not obsbot.connect():
        print("Failed to connect")
        return
        
    print("Connected successfully! Spamming commands at 20Hz...")
    
    # Simulate move_timer 50ms interval
    for i in range(40): # 2 seconds
        res = obsbot.set_gimbal_speed(10.0, 0.0)
        time.sleep(0.05)
        
    print("Done spamming pitch. Spamming pan...")
    for i in range(20):
        res = obsbot.set_gimbal_speed(0.0, -10.0)
        time.sleep(0.05)
        
    obsbot.set_gimbal_speed(0.0, 0.0)
    print("Test finished.")

if __name__ == "__main__":
    test_spam()
