import sys
from PyQt6.QtWidgets import QApplication
from new_ui import ModernMainWindow

app = QApplication(sys.argv)
window = ModernMainWindow()
try:
    window.toggle_tracking()
    print("Toggle tracking executed successfully")
except Exception as e:
    import traceback
    traceback.print_exc()

