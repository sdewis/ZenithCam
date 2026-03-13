import os
import urllib.request
from ultralytics import YOLO

def main():
    url = "https://github.com/akanametov/yolo-face/releases/download/v0.0.0/yolov8n-face.pt"
    pt_path = "yolov8n-face.pt"
    onnx_path = "yolov8n-face.onnx"
    
    if not os.path.exists(pt_path):
        print(f"Downloading {pt_path} from {url}...")
        urllib.request.urlretrieve(url, pt_path)
    
    print(f"Exporting {pt_path} to {onnx_path}...")
    model = YOLO(pt_path)
    model.export(format="onnx")
    print("Done!")

if __name__ == "__main__":
    main()
