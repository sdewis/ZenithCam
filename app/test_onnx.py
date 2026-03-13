import cv2
import numpy as np
import onnxruntime as ort

model_path = "./auto_zoom_cam_hybrid/ZenithCam/erax-anti-nsfw-yolo11n-v1.1.onnx"
session = ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])
input_name = session.get_inputs()[0].name
output_names = [o.name for o in session.get_outputs()]

dummy_image = np.random.rand(1, 3, 640, 640).astype(np.float32)
outputs = session.run(output_names, {input_name: dummy_image})

predictions = outputs[0]
if len(predictions.shape) == 3: predictions = predictions[0]
predictions = np.transpose(predictions)

print("Output shape:", outputs[0].shape)
print("Transposed predictions shape:", predictions.shape)
print("First row:", predictions[0])
