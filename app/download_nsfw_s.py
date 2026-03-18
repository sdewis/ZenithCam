import os
import urllib.request

def main():
    url = "https://huggingface.co/erax-ai/EraX-NSFW-V1.0/resolve/main/erax_nsfw_yolo11s.pt"
    pt_path = "../models/erax_nsfw/erax_nsfw_yolo11s.pt"
    
    if not os.path.exists(pt_path):
        print(f"Downloading {pt_path} from {url}...")
        urllib.request.urlretrieve(url, pt_path)
    
    print(f"Exporting {pt_path} to ONNX...")
    # Need to run YOLO via the virtual environment
    import subprocess
    subprocess.run(["venv/bin/yolo", "export", f"model={pt_path}", "format=onnx"], cwd=os.path.dirname(os.path.abspath(__file__)))
    print("Done!")

if __name__ == "__main__":
    main()
