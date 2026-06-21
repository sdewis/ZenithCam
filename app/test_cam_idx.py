import sys
from PyQt6.QtWidgets import QApplication
from new_ui import ModernMainWindow

app = QApplication(sys.argv)
window = ModernMainWindow()
print("input_combo currentText:", window.input_combo.currentText())
print("mock_input_combo currentText:", window.mock_input_combo.currentText())

