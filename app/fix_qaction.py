import os
filepath = "/home/sean/CodeFolder/ZenithCam_SDK_Integrated/app/main.py"
with open(filepath, "r") as f:
    content = f.read()

# Remove QAction from QtWidgets
content = content.replace(", QAction)", ")")

# Add QAction to QtGui
if "from PyQt6.QtGui import" in content:
    content = content.replace("from PyQt6.QtGui import (", "from PyQt6.QtGui import (QAction, ")
else:
    # If not using parentheses
    content = content.replace("from PyQt6.QtGui import QImage, QPixmap", "from PyQt6.QtGui import QImage, QPixmap, QAction")

with open(filepath, "w") as f:
    f.write(content)
