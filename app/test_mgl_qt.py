from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QOpenGLContext, QOffscreenSurface, QSurfaceFormat
import sys
import moderngl

app = QApplication(sys.argv)

fmt = QSurfaceFormat()
fmt.setVersion(3, 3)
fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
QSurfaceFormat.setDefaultFormat(fmt)

ctx = QOpenGLContext()
ctx.setFormat(fmt)
ctx.create()

surface = QOffscreenSurface()
surface.setFormat(fmt)
surface.create()

ctx.makeCurrent(surface)

mgl_ctx = moderngl.create_context()
print(mgl_ctx.version_code)
