import math
from PyQt6.QtWidgets import (
    QWidget, QCheckBox, QFrame, QLabel, QVBoxLayout, QHBoxLayout,
    QPushButton, QGridLayout, QSizePolicy, QSlider
)
from PyQt6.QtCore import (
    Qt, pyqtSignal, QPointF, QRectF, QPropertyAnimation, pyqtProperty,
    QTimer, QSize
)
from PyQt6.QtGui import (
    QPainter, QColor, QPen, QBrush, QRadialGradient, QLinearGradient,
    QFont, QPainterPath
)


# ─── Color Palette ───────────────────────────────────────────────────
PURPLE_PRIMARY = QColor("#B388FF")
PURPLE_HOVER   = QColor("#7C4DFF")
PURPLE_GLOW    = QColor("#9C5CFF")
RED_ACCENT     = QColor("#FF4D6A")
GREEN_ACCENT   = QColor("#00E676")
CARD_BG        = QColor("#141625")
CARD_BORDER    = QColor("#1E2140")
DEEP_BG        = QColor("#0D0F1A")
TEXT_PRIMARY    = QColor("#E8E8F0")
TEXT_SECONDARY  = QColor("#8888AA")
GRID_LINE      = QColor("#252845")


class PTZTrackpad(QWidget):
    """Enhanced PTZ trackpad with concentric grid rings and glow effects."""
    position_changed = pyqtSignal(float, float)  # dx, dy between -1.0 and 1.0

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(160, 160)
        self.setMaximumSize(200, 200)
        self.pos_x = 0.0
        self.pos_y = 0.0
        self.is_tracking = False

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        cx, cy = w / 2, h / 2
        radius = min(w, h) / 2 - 10

        # Radial gradient background
        grad = QRadialGradient(QPointF(cx, cy), radius)
        grad.setColorAt(0.0, QColor("#1A1D35"))
        grad.setColorAt(0.7, QColor("#12142A"))
        grad.setColorAt(1.0, QColor("#0D0F1A"))
        painter.setBrush(QBrush(grad))
        painter.setPen(QPen(CARD_BORDER, 2))
        painter.drawEllipse(QPointF(cx, cy), radius, radius)

        # Concentric grid rings (3 rings at 33%, 66%, 100%)
        ring_pen = QPen(GRID_LINE, 1)
        painter.setPen(ring_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for frac in [0.33, 0.66]:
            painter.drawEllipse(QPointF(cx, cy), radius * frac, radius * frac)

        # Purple crosshairs
        cross_pen = QPen(PURPLE_PRIMARY, 1, Qt.PenStyle.DashLine)
        cross_pen.setDashPattern([4, 4])
        painter.setPen(cross_pen)
        painter.drawLine(int(cx), int(cy - radius), int(cx), int(cy + radius))
        painter.drawLine(int(cx - radius), int(cy), int(cx + radius), int(cy))

        # Target handle
        handle_x = cx + self.pos_x * radius
        handle_y = cy + self.pos_y * radius

        # Handle outer glow
        glow_grad = QRadialGradient(QPointF(handle_x, handle_y), 16)
        glow_grad.setColorAt(0.0, QColor(255, 77, 106, 80))
        glow_grad.setColorAt(1.0, QColor(255, 77, 106, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(glow_grad))
        painter.drawEllipse(QPointF(handle_x, handle_y), 16, 16)

        # Handle crosshair
        painter.setPen(QPen(RED_ACCENT, 2))
        painter.drawLine(int(handle_x - 8), int(handle_y), int(handle_x + 8), int(handle_y))
        painter.drawLine(int(handle_x), int(handle_y - 8), int(handle_x), int(handle_y + 8))

        # Center dot
        if abs(self.pos_x) < 0.01 and abs(self.pos_y) < 0.01:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(PURPLE_PRIMARY))
            painter.drawEllipse(QPointF(cx, cy), 3, 3)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.is_tracking = True
            self._update_pos(event.position())

    def mouseMoveEvent(self, event):
        if self.is_tracking:
            self._update_pos(event.position())

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.is_tracking = False
            self.pos_x = 0.0
            self.pos_y = 0.0
            self.update()
            self.position_changed.emit(0.0, 0.0)

    def _update_pos(self, pos):
        w = self.width()
        h = self.height()
        cx, cy = w / 2, h / 2
        radius = min(w, h) / 2 - 10

        dx = pos.x() - cx
        dy = pos.y() - cy

        dist = math.sqrt(dx * dx + dy * dy)
        if dist > radius:
            dx = dx * radius / dist
            dy = dy * radius / dist

        self.pos_x = dx / radius
        self.pos_y = dy / radius
        self.update()
        self.position_changed.emit(self.pos_x, -self.pos_y)  # Invert Y so up is positive


class ModernToggle(QCheckBox):
    """Animated toggle switch with purple accent."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(44, 24)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._position = 0
        self.animation = QPropertyAnimation(self, b"position")
        self.animation.setDuration(200)
        self.stateChanged.connect(self._start_transition)

    @pyqtProperty(float)
    def position(self):
        return self._position

    @position.setter
    def position(self, pos):
        self._position = pos
        self.update()

    def _start_transition(self, value):
        self.animation.stop()
        if value:
            self.animation.setEndValue(1.0)
        else:
            self.animation.setEndValue(0.0)
        self.animation.start()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Track
        track_rect = QRectF(0, 0, self.width(), self.height())
        if self.isChecked() or self._position > 0:
            # Interpolate between off and on color
            r = int(51 + (179 - 51) * self._position)
            g = int(51 + (136 - 51) * self._position)
            b = int(51 + (255 - 51) * self._position)
            color = QColor(r, g, b)
        else:
            color = QColor("#333344")

        painter.setBrush(QBrush(color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(track_rect, 12, 12)

        # Handle
        handle_r = 10
        handle_x = 2 + (self.width() - 2 * handle_r - 4) * self._position
        handle_y = 2

        # Handle shadow
        shadow = QColor(0, 0, 0, 40)
        painter.setBrush(QBrush(shadow))
        painter.drawEllipse(QRectF(handle_x + 1, handle_y + 1, handle_r * 2, handle_r * 2))

        # Handle
        painter.setBrush(QBrush(QColor("#FFFFFF")))
        painter.drawEllipse(QRectF(handle_x, handle_y, handle_r * 2, handle_r * 2))


class PanelCard(QFrame):
    """Premium card container with optional header tab and overflow menu."""
    def __init__(self, title=None, tab_label=None, show_overflow=False, parent=None):
        super().__init__(parent)
        self.setObjectName("PanelCard")
        self.setProperty("class", "PanelCard")

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(14, 14, 14, 14)
        self.layout.setSpacing(8)

        if title:
            header_layout = QHBoxLayout()
            header_layout.setSpacing(8)
            self.title_label = QLabel(title)
            self.title_label.setObjectName("HeaderLabel")
            header_layout.addWidget(self.title_label)

            if tab_label:
                tab = QLabel(tab_label)
                tab.setObjectName("TabIndicator")
                tab.setStyleSheet(
                    "color: #8888AA; font-size: 12px; font-weight: bold; "
                    "padding: 2px 8px; border: 1px solid #333355; border-radius: 4px;"
                )
                header_layout.addWidget(tab)

            header_layout.addStretch()

            if show_overflow:
                overflow_btn = QPushButton("···")
                overflow_btn.setFixedSize(28, 22)
                overflow_btn.setObjectName("OverflowBtn")
                overflow_btn.setStyleSheet(
                    "color: #8888AA; background: transparent; border: none; "
                    "font-size: 16px; font-weight: bold;"
                )
                header_layout.addWidget(overflow_btn)

            self.layout.addLayout(header_layout)

            # Subtle separator
            sep = QFrame()
            sep.setFixedHeight(1)
            sep.setStyleSheet("background-color: #1E2140;")
            self.layout.addWidget(sep)

    def addWidget(self, widget, alignment=Qt.AlignmentFlag(0)):
        if alignment:
            self.layout.addWidget(widget, alignment=alignment)
        else:
            self.layout.addWidget(widget)

    def addLayout(self, layout):
        self.layout.addLayout(layout)

    def addStretch(self):
        self.layout.addStretch()


class StatusBadge(QLabel):
    """Colored pill-shaped status badge with optional pulse animation."""
    COLORS = {
        "green": ("#00E676", "#0A3020"),
        "red": ("#FF4D6A", "#3A1525"),
        "purple": ("#B388FF", "#2A1845"),
        "orange": ("#FFB74D", "#3A2A15"),
        "blue": ("#64B5F6", "#152A3A"),
    }

    def __init__(self, text="Active", color="green", parent=None):
        super().__init__(text, parent)
        self.setObjectName("StatusBadge")
        self._set_color(color)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFixedHeight(26)
        self.setMinimumWidth(60)

    def _set_color(self, color_name):
        fg, bg = self.COLORS.get(color_name, self.COLORS["green"])
        self.setStyleSheet(
            f"background-color: {bg}; color: {fg}; font-weight: bold; "
            f"font-size: 11px; border: 1px solid {fg}40; border-radius: 12px; "
            f"padding: 2px 12px;"
        )

    def set_color(self, color_name):
        self._set_color(color_name)

    def set_active(self, active):
        if active:
            self._set_color("green")
            self.setText("Active")
        else:
            self._set_color("red")
            self.setText("Inactive")


class VideoCard(QFrame):
    """Video preview container with camera name header and overlay badges."""
    def __init__(self, camera_name="PTZ Camera 1", subtitle="Zenith Studio - Main", parent=None):
        super().__init__(parent)
        self.setObjectName("VideoCard")
        self.setStyleSheet(
            "QFrame#VideoCard { background-color: #141625; border: 1px solid #1E2140; border-radius: 10px; }"
        )

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Camera name header bar
        header = QWidget()
        header.setStyleSheet("background-color: #181A30; border-top-left-radius: 10px; border-top-right-radius: 10px;")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 6, 12, 6)

        cam_icon = QLabel("🎥")
        cam_icon.setStyleSheet("font-size: 14px;")
        header_layout.addWidget(cam_icon)

        name_layout = QVBoxLayout()
        name_layout.setSpacing(0)
        cam_name = QLabel(camera_name)
        cam_name.setStyleSheet("color: #E8E8F0; font-weight: bold; font-size: 13px;")
        cam_sub = QLabel(subtitle)
        cam_sub.setStyleSheet("color: #6666AA; font-size: 10px;")
        name_layout.addWidget(cam_name)
        name_layout.addWidget(cam_sub)
        header_layout.addLayout(name_layout)
        header_layout.addStretch()

        # Header action icons
        for icon_text in ["⊡", "□", "⚙"]:
            icon_btn = QPushButton(icon_text)
            icon_btn.setFixedSize(24, 24)
            icon_btn.setStyleSheet(
                "color: #6666AA; background: transparent; border: none; font-size: 14px;"
            )
            header_layout.addWidget(icon_btn)

        main_layout.addWidget(header)

        # Badge overlay row
        self.badge_row = QWidget()
        badge_layout = QHBoxLayout(self.badge_row)
        badge_layout.setContentsMargins(10, 4, 10, 4)
        badge_layout.setSpacing(8)

        self.live_badge = QLabel("● LIVE - 1080p60")
        self.live_badge.setStyleSheet(
            "color: #FF4D6A; font-weight: bold; font-size: 11px;"
        )
        badge_layout.addWidget(self.live_badge)

        self.rec_badge = StatusBadge("● REC", "red")
        self.rec_badge.setFixedHeight(22)
        badge_layout.addWidget(self.rec_badge)

        self.stream_badge = StatusBadge("● STREAM", "purple")
        self.stream_badge.setFixedHeight(22)
        badge_layout.addWidget(self.stream_badge)

        badge_layout.addStretch()

        self.ai_badge = QLabel("AI ACTIVE")
        self.ai_badge.setStyleSheet(
            "color: #00E676; font-weight: bold; font-size: 11px;"
        )
        badge_layout.addWidget(self.ai_badge)

        main_layout.addWidget(self.badge_row)

        # Video preview area
        self.preview_label = QLabel("Waiting for camera...")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumSize(320, 180)
        self.preview_label.setStyleSheet(
            "background-color: #0A0C18; color: #555577; font-size: 14px; margin: 2px;"
        )
        main_layout.addWidget(self.preview_label, stretch=1)

        # Bottom overlay strip
        self.overlay_strip = QWidget()
        self.overlay_strip.setStyleSheet(
            "background-color: rgba(10, 12, 24, 180); border-bottom-left-radius: 10px; "
            "border-bottom-right-radius: 10px;"
        )
        strip_layout = QHBoxLayout(self.overlay_strip)
        strip_layout.setContentsMargins(12, 4, 12, 4)

        self.res_label = QLabel("LIVE - 1080p60")
        self.res_label.setStyleSheet("color: #AAAACC; font-size: 10px; font-weight: bold;")
        strip_layout.addWidget(self.res_label)
        strip_layout.addStretch()

        self.fps_label = QLabel("FPS: 60")
        self.fps_label.setStyleSheet("color: #AAAACC; font-size: 10px;")
        strip_layout.addWidget(self.fps_label)

        sep = QLabel("|")
        sep.setStyleSheet("color: #444466; font-size: 10px;")
        strip_layout.addWidget(sep)

        self.bitrate_label = QLabel("BITRATE: 6.2Mbps")
        self.bitrate_label.setStyleSheet("color: #AAAACC; font-size: 10px;")
        strip_layout.addWidget(self.bitrate_label)

        main_layout.addWidget(self.overlay_strip)

    def set_simple_mode(self):
        """Use for the bottom/secondary preview - hide badges and overlay."""
        self.badge_row.setVisible(False)
        self.overlay_strip.setVisible(False)
        self.preview_label.setStyleSheet(
            "background-color: #0A0C18; color: #555577; font-size: 13px; margin: 2px;"
        )


class SegmentedButtonGroup(QWidget):
    """Horizontal segmented button group where one button is highlighted."""
    button_clicked = pyqtSignal(int)

    def __init__(self, labels, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        self._buttons = []
        self._active_index = 0

        for i, label in enumerate(labels):
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setChecked(i == 0)
            btn.setFixedHeight(30)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda checked, idx=i: self._on_click(idx))
            layout.addWidget(btn)
            self._buttons.append(btn)

        self._update_styles()

    def _on_click(self, index):
        self._active_index = index
        for i, btn in enumerate(self._buttons):
            btn.setChecked(i == index)
        self._update_styles()
        self.button_clicked.emit(index)

    def _update_styles(self):
        for i, btn in enumerate(self._buttons):
            if i == self._active_index:
                btn.setStyleSheet(
                    "background-color: #B388FF; color: #0D0F1A; font-weight: bold; "
                    "border: none; border-radius: 6px; padding: 4px 12px; font-size: 12px;"
                )
            else:
                btn.setStyleSheet(
                    "background-color: #1E2140; color: #8888AA; font-weight: bold; "
                    "border: 1px solid #2A2D50; border-radius: 6px; padding: 4px 12px; font-size: 12px;"
                )

    def set_active(self, index):
        if 0 <= index < len(self._buttons):
            self._on_click(index)


class AudioMeter(QWidget):
    """Horizontal audio level meter with gradient fill."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(8)
        self.setMinimumWidth(80)
        self._level = 0.6  # 0.0 to 1.0

    def set_level(self, level):
        self._level = max(0.0, min(1.0, level))
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        r = h / 2

        # Background track
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor("#1E2140")))
        painter.drawRoundedRect(QRectF(0, 0, w, h), r, r)

        # Level fill with gradient
        fill_w = w * self._level
        if fill_w > 0:
            grad = QLinearGradient(0, 0, w, 0)
            grad.setColorAt(0.0, QColor("#00E676"))
            grad.setColorAt(0.6, QColor("#FFD54F"))
            grad.setColorAt(1.0, QColor("#FF4D6A"))
            painter.setBrush(QBrush(grad))
            painter.drawRoundedRect(QRectF(0, 0, fill_w, h), r, r)


class LabeledSlider(QWidget):
    """Slider with a label and value readout on the right."""
    valueChanged = pyqtSignal(int)

    def __init__(self, label_text, min_val=0, max_val=100, default=50, suffix="", parent=None):
        super().__init__(parent)
        self._suffix = suffix
        self._scale = 1.0

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.label = QLabel(label_text)
        self.label.setStyleSheet("color: #E8E8F0; font-size: 12px;")
        self.label.setMinimumWidth(50)
        layout.addWidget(self.label)

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(min_val, max_val)
        self.slider.setValue(default)
        self.slider.valueChanged.connect(self._on_change)
        layout.addWidget(self.slider, stretch=1)

        self.value_label = QLabel()
        self.value_label.setObjectName("ValueLabel")
        self.value_label.setStyleSheet(
            "color: #B388FF; font-weight: bold; font-size: 11px; min-width: 60px;"
        )
        self.value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self.value_label)

        self._on_change(default)

    def set_scale(self, scale):
        """Set a multiplier for display value (e.g., 0.1 to show 12.4x from value 124)."""
        self._scale = scale
        self._on_change(self.slider.value())

    def _on_change(self, val):
        display = val * self._scale
        if self._scale != 1.0:
            self.value_label.setText(f"Slider: {display:.1f}{self._suffix}")
        else:
            self.value_label.setText(f"Slider{': ' if self._suffix else ''}{display:.0f}{self._suffix}")
        self.valueChanged.emit(val)

    def value(self):
        return self.slider.value()

    def setValue(self, val):
        self.slider.setValue(val)
