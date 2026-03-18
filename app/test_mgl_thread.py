from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QOpenGLContext, QOffscreenSurface, QSurfaceFormat
from PyQt6.QtCore import QThread, pyqtSignal
import sys
import moderngl

class Worker(QThread):
    finished = pyqtSignal(bool)
    def run(self):
        try:
            fmt = QSurfaceFormat()
            fmt.setVersion(3, 3)
            fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
            
            ctx = QOpenGLContext()
            ctx.setFormat(fmt)
            ctx.create()
            
            surface = QOffscreenSurface()
            surface.setFormat(fmt)
            surface.create()
            
            ctx.makeCurrent(surface)
            
            mgl_ctx = moderngl.create_context()
            print("ModernGL Context Version:", mgl_ctx.version_code)
            self.finished.emit(True)
        except Exception as e:
            print("Error:", e)
            self.finished.emit(False)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    w = Worker()
    w.finished.connect(app.quit)
    w.start()
    app.exec()
