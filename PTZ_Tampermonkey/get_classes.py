import onnx
model = onnx.load("erax-anti-nsfw-yolo11n-v1.1.onnx")
for prop in model.metadata_props:
    if prop.key == 'names':
        print(prop.value)
