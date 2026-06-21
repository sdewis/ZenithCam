import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer
from new_ui import ModernMainWindow
import traceback

def handle_exception(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    print("Uncaught exception", exc_type, exc_value)
    traceback.print_tb(exc_traceback)
    sys.exit(1)

sys.excepthook = handle_exception

app = QApplication(sys.argv)
window = ModernMainWindow()

def click_it():
    print("Clicking start_btn...")
    window.start_btn.setChecked(not window.start_btn.isChecked())

QTimer.singleShot(1000, click_it)
QTimer.singleShot(7000, lambda: sys.exit(0))

window.show()
sys.exit(app.exec())
