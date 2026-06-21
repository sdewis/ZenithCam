import sys
import traceback
from PyQt6.QtWidgets import QApplication
from new_ui import ModernMainWindow
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtTest import QTest

def handle_exception(exc_type, exc_value, exc_traceback):
    print("Uncaught exception", exc_type, exc_value)
    traceback.print_tb(exc_traceback)
    sys.exit(2)

sys.excepthook = handle_exception

app = QApplication(sys.argv)
window = ModernMainWindow()
window.show()

def run_test():
    try:
        print("Simulating click on ModernToggle...")
        # Left click exactly in the center of the toggle
        QTest.mouseClick(window.start_btn, Qt.MouseButton.LeftButton)
        print("Click finished.")
    except Exception as e:
        print(f"Error during click: {e}")
        traceback.print_exc()
        sys.exit(3)

QTimer.singleShot(1000, run_test)
QTimer.singleShot(5000, lambda: sys.exit(0))

sys.exit(app.exec())
