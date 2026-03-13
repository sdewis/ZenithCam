import time
import sys
import logging
import cv2
import threading

logging.basicConfig(level=logging.DEBUG)
sys.path.append("/home/sean/CodeFolder/ZenithCam_SDK_Integrated/app")
from obsbot_wrapper import OBSBOTSDK

def test_full_reconnect():
    print("STARTING RUN 1")
    cap = cv2.VideoCapture(5)
    obs = OBSBOTSDK()
    if obs.init() and obs.connect():
        print("Connected run 1!")
    else:
        print("Failed run 1!")
        
    time.sleep(2)
    print("STOPPING RUN 1")
    cap.release()
    # Notice we NOT clearing obs state or anything
    
    time.sleep(2)
    print("STARTING RUN 2")
    cap2 = cv2.VideoCapture(5)
    obs2 = OBSBOTSDK()
    if obs2.init() and obs2.connect():
        print("Connected run 2!")
    else:
        print("Failed run 2!")
        
    time.sleep(2)
    print("FINISHED")
    cap2.release()

if __name__ == "__main__":
    test_full_reconnect()
