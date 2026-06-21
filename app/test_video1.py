import cv2
import time
cap = cv2.VideoCapture(1)
print("Opened:", cap.isOpened())
if cap.isOpened():
    t0 = time.time()
    ret, frame = cap.read()
    print("Read:", ret, "Time:", time.time() - t0)
    if ret:
        print("Frame shape:", frame.shape)
cap.release()
