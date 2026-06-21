import onnxruntime as ort
import numpy as np
import os

model_path = os.path.join(os.path.dirname(__file__), "../models/erax_nsfw/erax-anti-nsfw-yolo11n-v1.1.onnx")
session = ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])
inputs = session.get_inputs()
outputs = session.get_outputs()
print("Inputs:")
for i in inputs:
    print(f"  - {i.name}: {i.shape} ({i.type})")
print("Outputs:")
for o in outputs:
    print(f"  - {o.name}: {o.shape} ({o.type})")
