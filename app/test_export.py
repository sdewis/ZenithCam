import os
import logging
from ultralytics import YOLO

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("TestExport")

MODEL_PT_PATH = os.path.join(os.path.dirname(__file__), "../auto_zoom_cam_V1/models/erax-anti-nsfw-yolo11n-v1.1.pt")

def test_export():
    logger.info(f"Testing export for: {MODEL_PT_PATH}")
    try:
        model = YOLO(MODEL_PT_PATH)
        success = model.export(format="onnx")
        logger.info(f"Export returned: {success}")
    except Exception as e:
        logger.error(f"Export failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_export()
