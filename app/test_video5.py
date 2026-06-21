import cv2
cap = cv2.VideoCapture(5)
print("Opened:", cap.isOpened())
if cap.isOpened():
    ret, frame = cap.read()
    print("Read:", ret)
    if ret:
        print("Frame shape:", frame.shape)
cap.release()
