import os
import sys
import logging
import importlib
import subprocess
import shutil

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger("Diagnostic")

def check_path(path, desc):
    if os.path.exists(path):
        logger.info(f"[PASS] {desc} found: {path}")
        return True
    else:
        logger.error(f"[FAIL] {desc} NOT found: {path}")
        return False

def check_import(module_name):
    try:
        importlib.import_module(module_name)
        logger.info(f"[PASS] Python module '{module_name}' is installed.")
        return True
    except ImportError as e:
        logger.error(f"[FAIL] Python module '{module_name}' is NOT installed: {e}")
        return False

def check_virtual_cam(device="/dev/video20"):
    logger.info(f"--- Checking Virtual Camera: {device} ---")
    if not os.path.exists(device):
        logger.error(f"[FAIL] Device {device} does not exist.")
        logger.info("       💡 Fix: Run 'sudo modprobe v4l2loopback devices=3 video_nr=0,10,20 exclusive_caps=1'")
        return False
    
    logger.info(f"[PASS] Device {device} exists.")
    
    # Check if in use
    if shutil.which("fuser"):
        try:
            result = subprocess.run(['fuser', device], capture_output=True, text=True)
            pids = result.stdout.strip().split()
            if pids:
                logger.warning(f"[WARN] Virtual Camera {device} is currently in use by PID(s): {', '.join(pids)}")
                logger.warning("       💡 This causes [Errno 22] Invalid argument.")
                for pid in pids:
                    try:
                        pname = subprocess.check_output(['ps', '-p', pid, '-o', 'comm='], text=True).strip()
                        logger.warning(f"       Process '{pname}' (PID {pid}) is blocking the device.")
                    except: pass
            else:
                logger.info(f"[PASS] Device {device} is free (no blocking processes).")
        except Exception as e:
            logger.debug(f"fuser check failed: {e}")

    # Check for exclusive_caps
    param_path = "/sys/module/v4l2loopback/parameters/exclusive_caps"
    if os.path.exists(param_path):
        try:
            with open(param_path, "r") as f:
                caps = f.read().strip()
                logger.info(f"[INFO] v4l2loopback exclusive_caps: {caps}")
                if "Y" not in caps and "1" not in caps:
                    logger.warning("[WARN] exclusive_caps=1 not set. Browsers will likely NOT see the virtual camera.")
        except: pass
    
    return True

def check_moderngl():
    logger.info("--- Checking Hardware Rendering (ModernGL) ---")
    try:
        import moderngl
        ctx = moderngl.create_context(standalone=True)
        logger.info(f"[PASS] ModernGL Context created. GPU: {ctx.info['GL_RENDERER']}")
        ctx.release()
        return True
    except Exception as e:
        logger.error(f"[FAIL] ModernGL Context failed: {e}")
        logger.error("       💡 If on Linux, check if you have an active X11/Wayland display or proper GPU drivers.")
        return False

def check_model():
    logger.info("--- Checking ML Models ---")
    base_dir = os.path.dirname(os.path.abspath(__file__))
    onnx_path = os.path.join(base_dir, "erax-anti-nsfw-yolo11n-v1.1.onnx")
    pt_path = os.path.join(base_dir, "erax-anti-nsfw-yolo11n-v1.1.pt")
    
    if os.path.exists(onnx_path):
        logger.info(f"[PASS] ONNX Model found (Optimal): {onnx_path}")
    elif os.path.exists(pt_path):
        logger.warning(f"[WARN] YOLO .pt model found, but ONNX is highly recommended for performance.")
    else:
        logger.error(f"[FAIL] No YOLO model found in {base_dir}")
    
    check_path(os.path.join(base_dir, "models/face_landmarker.task"), "Face Landmarker Task")

def main():
    print("="*60)
    print(" ZENITHCAM INTEGRATED SYSTEM DIAGNOSTIC ")
    print("="*60)
    
    # 1. Core Files
    check_model()
    base_dir = os.path.dirname(os.path.abspath(__file__))
    check_path(os.path.join(base_dir, "libs/libobsbot_bridge.so"), "SDK Bridge")
    check_path(os.path.join(base_dir, "libs/libdev.so"), "SDK Core Lib")
    
    # 2. Python Environment
    logger.info("--- Checking Dependencies ---")
    for mod in ["cv2", "onnxruntime", "moderngl", "pyfakewebcam", "ultralytics", "numpy"]:
        check_import(mod)
    
    # 3. Virtual Camera
    check_virtual_cam("/dev/video20")
    
    # 4. Rendering
    check_moderngl()
    
    print("="*60)
    print(" DIAGNOSTIC COMPLETE ")
    print("="*60)

if __name__ == "__main__":
    main()
