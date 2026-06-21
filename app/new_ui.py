import os
import time
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSlider, QComboBox,
    QCheckBox, QGridLayout, QFrame, QScrollArea, QMenuBar, QMenu, QSpinBox,
    QSizePolicy, QToolBar
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QAction
from main import MainWindow
from ui_components import (
    PTZTrackpad, ModernToggle, PanelCard, StatusBadge, VideoCard,
    SegmentedButtonGroup, AudioMeter, LabeledSlider
)


class ModernMainWindow(MainWindow):
    def __init__(self):
        super().__init__()
        self.params["show_input_preview"] = True
        self.params["show_output_preview"] = True
        self._stream_start_time = None
        self._rec_start_time = None

        # Load stylesheet
        style_path = os.path.join(os.path.dirname(__file__), "style.qss")
        if os.path.exists(style_path):
            with open(style_path, "r") as f:
                self.setStyleSheet(f.read())

        # Remove old docks and toolbars
        from PyQt6.QtWidgets import QDockWidget, QToolBar as TB
        for dock in self.findChildren(QDockWidget):
            self.removeDockWidget(dock)
        for tb in self.findChildren(TB):
            self.removeToolBar(tb)

        self.setWindowTitle("ZenithCam")

        # ── Menu Bar ──────────────────────────────────────────
        menubar = self.menuBar()
        for name in ["File", "Edit", "View", "Window", "Help"]:
            menu = menubar.addMenu(name)
            if name == "File":
                menu.addAction("New Session")
                menu.addAction("Open Project...")
                menu.addSeparator()
                exit_act = menu.addAction("Exit")
                exit_act.triggered.connect(self.close)
            elif name == "View":
                menu.addAction("Reset Layout")
                menu.addAction("Toggle Fullscreen")
            elif name == "Help":
                menu.addAction("About ZenithCam")

        # Record/Stop buttons in toolbar
        rec_toolbar = QToolBar()
        rec_toolbar.setMovable(False)
        rec_toolbar.setStyleSheet("background: transparent; border: none; spacing: 4px;")
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        rec_toolbar.addWidget(spacer)
        self.rec_btn = QPushButton("●")
        self.rec_btn.setObjectName("RecordBtn")
        self.rec_btn.setFixedSize(30, 30)
        self.rec_btn.setToolTip("Record")
        self.rec_btn.clicked.connect(lambda: self.start_btn.setChecked(not self.start_btn.isChecked()))
        rec_toolbar.addWidget(self.rec_btn)
        self.stop_btn_tb = QPushButton("■")
        self.stop_btn_tb.setObjectName("StopBtn")
        self.stop_btn_tb.setFixedSize(30, 30)
        self.stop_btn_tb.setToolTip("Stop")
        self.stop_btn_tb.clicked.connect(lambda: self.start_btn.setChecked(False))
        rec_toolbar.addWidget(self.stop_btn_tb)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, rec_toolbar)

        # ── Central Layout ────────────────────────────────────
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        root = QVBoxLayout(self.central_widget)
        root.setContentsMargins(8, 4, 8, 0)
        root.setSpacing(6)

        body = QHBoxLayout()
        body.setSpacing(8)
        root.addLayout(body, stretch=1)

        # ══════════════════════════════════════════════════════
        #  LEFT PANEL
        # ══════════════════════════════════════════════════════
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setFixedWidth(310)
        left_scroll.setStyleSheet("QScrollArea{border:none; background:transparent;}")
        left_inner = QWidget()
        left_layout = QVBoxLayout(left_inner)
        left_layout.setContentsMargins(0, 0, 4, 0)
        left_layout.setSpacing(8)

        # ── Robot Control Card ────────────────────────────────
        robot_card = PanelCard("ROBOT CONTROL", tab_label="PTZ")

        # Add Hold toggle to the card header area via a row
        hold_row = QHBoxLayout()
        hold_row.addWidget(QLabel("Hold Target"))
        self.hold_ptz_cb = ModernToggle()
        self.hold_ptz_cb.setChecked(self.params.get("hold_ptz", False))
        self.hold_ptz_cb.stateChanged.connect(self.toggle_hold_ptz)
        hold_row.addWidget(self.hold_ptz_cb)
        hold_row.addStretch()
        robot_card.addLayout(hold_row)

        # Bluetooth Row
        bt_row = QHBoxLayout()
        bt_row.addWidget(QLabel("Bluetooth Mode"))
        self.use_bt_cb = ModernToggle()
        self.use_bt_cb.stateChanged.connect(self.toggle_bluetooth_mode)
        bt_row.addWidget(self.use_bt_cb)
        
        self.scan_bt_btn = QPushButton("Scan")
        self.scan_bt_btn.setObjectName("SmallBtn")
        self.scan_bt_btn.setFixedWidth(60)
        self.scan_bt_btn.setEnabled(False)
        self.scan_bt_btn.clicked.connect(self.scan_bluetooth)
        bt_row.addWidget(self.scan_bt_btn)
        robot_card.addLayout(bt_row)

        self.bt_device_combo = QComboBox()
        self.bt_device_combo.setPlaceholderText("Select Bluetooth Camera...")
        self.bt_device_combo.setVisible(False)
        self.bt_device_combo.currentIndexChanged.connect(self.connect_bluetooth_device)
        robot_card.addWidget(self.bt_device_combo)

        # Pan/Tilt
        pt_lbl = QLabel("Pan/Tilt")
        pt_lbl.setStyleSheet("color:#E8E8F0; font-weight:bold; font-size:12px;")
        robot_card.addWidget(pt_lbl)
        pt_sub = QLabel("Precise trackpad for Pan/Tilt")
        pt_sub.setObjectName("SubText")
        robot_card.addWidget(pt_sub)

        self.trackpad = PTZTrackpad()
        self.trackpad.position_changed.connect(self._on_trackpad_move)
        robot_card.addWidget(self.trackpad, alignment=Qt.AlignmentFlag.AlignCenter)

        # Zoom slider
        self.zoom_slider = LabeledSlider("Zoom", 10, 200, 100, "x")
        self.zoom_slider.set_scale(0.1)
        robot_card.addWidget(self.zoom_slider)

        # Focus slider
        self.focus_slider = LabeledSlider("Focus", 0, 100, 50)
        robot_card.addWidget(self.focus_slider)

        # Presets 2x2
        presets_lbl = QLabel("Presets")
        presets_lbl.setObjectName("SectionLabel")
        robot_card.addWidget(presets_lbl)
        p_grid = QGridLayout()
        p_grid.setSpacing(4)
        preset_names = ["1: Host", "2: Screen", "3: Full", "4: Wide"]
        preset_keys = ["Home", "P1", "P2", "Home"]
        for i, (name, key) in enumerate(zip(preset_names, preset_keys)):
            btn = QPushButton(name)
            btn.setFixedHeight(30)
            btn.clicked.connect(lambda _, k=key: self.recall_preset(k))
            p_grid.addWidget(btn, i // 2, i % 2)
        robot_card.addLayout(p_grid)

        # Manual Zoom override (Slider)
        self.manual_zoom_slider_card = LabeledSlider("Manual Zoom Override", 10, 40, 10, "x")
        self.manual_zoom_slider_card.set_scale(0.1)
        self.manual_zoom_slider_card.slider.valueChanged.connect(self.update_manual_zoom)
        robot_card.addWidget(self.manual_zoom_slider_card)

        # P/T readout
        self.pt_readout = QLabel("P: +0°   T: +0°")
        self.pt_readout.setObjectName("PTReadout")
        robot_card.addWidget(self.pt_readout)

        left_layout.addWidget(robot_card)

        # ── AI Telemetry Card ─────────────────────────────────
        ai_card = PanelCard("AI TELEMETRY", show_overflow=True)
        ai_layout = ai_card.layout

        # ROI Selectors (Target & Blur)
        ai_layout.addWidget(QLabel("Target Classes (Track)"))
        self.class_scroll.setFixedHeight(80)
        ai_layout.addWidget(self.class_scroll)
        
        ai_layout.addWidget(QLabel("Blur Classes (Privacy)"))
        self.blur_scroll.setFixedHeight(80)
        ai_layout.addWidget(self.blur_scroll)

        # Draw ROI overlay toggles
        roi_checks = QHBoxLayout()
        roi_checks.addWidget(self.preview_roi_cb)
        roi_checks.addWidget(self.output_roi_cb)
        ai_layout.addLayout(roi_checks)

        # AI Backend Settings
        ft_row = QHBoxLayout()
        ft_row.addWidget(QLabel("Face Tracking"))
        self.onboard_tracker_cb = ModernToggle()
        self.onboard_tracker_cb.setChecked(self.params.get("enable_onboard_tracker", False))
        self.onboard_tracker_cb.stateChanged.connect(self.toggle_onboard_tracker)
        ft_row.addWidget(self.onboard_tracker_cb)
        self.conf_label = QLabel("98% Conf")
        self.conf_label.setObjectName("ConfLabel")
        ft_row.addWidget(self.conf_label)
        ai_card.addLayout(ft_row)

        self.subjects_label = QLabel("2 Subjects: Host  Guest")
        self.subjects_label.setObjectName("SubjectLabel")
        ai_card.addWidget(self.subjects_label)

        # Auto-Framing
        af_row = QHBoxLayout()
        af_row.addWidget(QLabel("Auto-Framing"))
        self.ptz_cb = ModernToggle()
        self.ptz_cb.setChecked(self.params.get("enable_physical_ptz", True))
        self.ptz_cb.stateChanged.connect(self.toggle_ptz)
        af_row.addWidget(self.ptz_cb)
        af_mode = QLabel("Dynamic")
        af_mode.setObjectName("ValueLabel")
        af_row.addWidget(af_mode)
        ai_card.addLayout(af_row)

        # Subject Selection
        ss_row = QHBoxLayout()
        ss_row.addWidget(QLabel("Subject Selection"))
        ss_info = QLabel("ⓘ")
        ss_info.setStyleSheet("color:#6666AA; font-size:14px;")
        ss_row.addWidget(ss_info)
        ss_row.addStretch()
        ai_card.addLayout(ss_row)
        self.subject_status = QLabel("Host: Active")
        self.subject_status.setObjectName("SubjectLabel")
        ai_card.addWidget(self.subject_status)

        # Heatmap / Stats
        hm_row = QHBoxLayout()
        hm_lbl = QLabel("Heatmap")
        hm_lbl.setStyleSheet("font-weight:bold; color:#E8E8F0;")
        hm_row.addWidget(hm_lbl)
        hm_val = QLabel("Tracked areas")
        hm_val.setObjectName("SubText")
        hm_row.addWidget(hm_val)
        hm_row.addStretch()
        ai_card.addLayout(hm_row)

        st_row = QHBoxLayout()
        st_lbl = QLabel("Stats")
        st_lbl.setStyleSheet("font-weight:bold; color:#E8E8F0;")
        st_row.addWidget(st_lbl)
        self.latency_label = QLabel("Lat: 12ms")
        self.latency_label.setObjectName("SubText")
        st_row.addWidget(self.latency_label)
        st_row.addStretch()
        ai_card.addLayout(st_row)

        left_layout.addWidget(ai_card)
        left_layout.addStretch()
        left_scroll.setWidget(left_inner)
        body.addWidget(left_scroll)

        # ══════════════════════════════════════════════════════
        #  CENTER PANEL — Video Feeds
        # ══════════════════════════════════════════════════════
        center_layout = QVBoxLayout()
        center_layout.setSpacing(8)

        # Top: AI Output VideoCard
        self.top_video = VideoCard("PTZ Camera 1", "Zenith Studio - Main")
        self.output_preview_label = self.top_video.preview_label
        self.output_preview_label.setMinimumSize(480, 270)
        center_layout.addWidget(self.top_video, stretch=2)

        # Bottom: Raw Input VideoCard
        self.bot_video = VideoCard("PTZ Camera 1", "Zenith Studio - Main")
        self.bot_video.set_simple_mode()
        self.input_preview_label = self.bot_video.preview_label
        center_layout.addWidget(self.bot_video, stretch=1)

        body.addLayout(center_layout, stretch=1)

        # ══════════════════════════════════════════════════════
        #  RIGHT PANEL — Streaming Control
        # ══════════════════════════════════════════════════════
        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setFixedWidth(310)
        right_scroll.setStyleSheet("QScrollArea{border:none; background:transparent;}")
        right_inner = QWidget()
        right_layout = QVBoxLayout(right_inner)
        right_layout.setContentsMargins(4, 0, 0, 0)
        right_layout.setSpacing(8)

        stream_card = PanelCard("STREAMING CONTROL")

        # Start/Stop Streaming
        stream_card.addWidget(QLabel("Start/Stop Streaming"))
        ss_row = QHBoxLayout()
        self.stream_badge = StatusBadge("Inactive", "red")
        ss_row.addWidget(self.stream_badge)
        self.stream_timer_label = QLabel("")
        self.stream_timer_label.setObjectName("ValueLabel")
        ss_row.addWidget(self.stream_timer_label)
        ss_row.addStretch()
        self.stream_btn = ModernToggle()
        self.stream_btn.stateChanged.connect(self.toggle_streaming)
        ss_row.addWidget(self.stream_btn)
        stream_card.addLayout(ss_row)

        # Start/Stop Recording (Engine)
        stream_card.addWidget(QLabel("Start/Stop Recording"))
        sr_row = QHBoxLayout()
        self.rec_badge = StatusBadge("Inactive", "red")
        sr_row.addWidget(self.rec_badge)
        sr_row.addStretch()
        self.start_btn = ModernToggle()
        self.start_btn.stateChanged.connect(self.toggle_tracking)
        sr_row.addWidget(self.start_btn)
        stream_card.addLayout(sr_row)

        # Stream Quality
        stream_card.addWidget(QLabel("Stream Quality"))
        self.bitrate_combo = QComboBox()
        self.bitrate_combo.addItems(["1080p | 60 | 8500kbps", "720p | 30 | 4500kbps", "480p | 30 | 2500kbps"])
        stream_card.addWidget(self.bitrate_combo)

        # Inputs
        stream_card.addWidget(QLabel("Inputs"))
        self.mock_input_combo = QComboBox()
        items = []
        for i in range(10):
            if os.path.exists(f"/dev/video{i}"):
                items.append(f"/dev/video{i}")
        self.mock_input_combo.addItems(items)
        if items:
            target_str = f'/dev/video{self.input_spin.value()}'
            if target_str in items:
                self.mock_input_combo.setCurrentText(target_str)
            else:
                self.mock_input_combo.setCurrentIndex(0)
        # We don't have a backend input_combo to sync to anymore
        # Hide it, use segmented buttons visually
        self.mock_input_combo.setVisible(False)
        stream_card.addWidget(self.mock_input_combo)

        self.input_seg = SegmentedButtonGroup(["Cam 1", "Mic 1", "OBS Link"])
        stream_card.addWidget(self.input_seg)

        # Audio
        stream_card.addWidget(QLabel("Audio"))
        audio_top = QHBoxLayout()
        self.audio_src_seg = SegmentedButtonGroup(["Mic 1", "Desktop"])
        audio_top.addWidget(self.audio_src_seg)
        audio_top.addStretch()
        stream_card.addLayout(audio_top)

        level_row = QHBoxLayout()
        level_row.addWidget(QLabel("levels"))
        self.audio_meter = AudioMeter()
        level_row.addWidget(self.audio_meter, stretch=1)
        stream_card.addLayout(level_row)

        mute_row = QHBoxLayout()
        mute_row.addWidget(QLabel("Mute"))
        mute_slider = QSlider(Qt.Orientation.Horizontal)
        mute_slider.setRange(0, 100)
        mute_slider.setValue(75)
        mute_row.addWidget(mute_slider, stretch=1)
        mute_row.addWidget(QLabel("🔊"))
        stream_card.addLayout(mute_row)

        # Chat
        stream_card.addWidget(QLabel("Chat"))
        self.chat_seg = SegmentedButtonGroup(["Twitch", "YouTube"])
        stream_card.addWidget(self.chat_seg)

        right_layout.addWidget(stream_card)
        right_layout.addStretch()
        right_scroll.setWidget(right_inner)
        body.addWidget(right_scroll)

        # ══════════════════════════════════════════════════════
        #  BOTTOM STATUS BAR
        # ══════════════════════════════════════════════════════
        status_frame = QFrame()
        status_frame.setObjectName("StatusBarFrame")
        status_frame.setFixedHeight(32)
        status_layout = QHBoxLayout(status_frame)
        status_layout.setContentsMargins(16, 0, 16, 0)
        status_layout.setSpacing(6)

        self.status_label = QLabel("ZenithCam V1.0 | CPU 18% | NET 8.1MB/s")
        self.status_label.setObjectName("StatusText")
        status_layout.addWidget(self.status_label)

        status_layout.addStretch()

        self.ai_status = QLabel("AI: ENABLED | AUTOFRAME: ON | TRACKING: HOST")
        self.ai_status.setObjectName("StatusHighlight")
        status_layout.addWidget(self.ai_status)

        status_layout.addStretch()

        for i in range(1, 5):
            pl = QLabel(str(i))
            pl.setObjectName("StatusText")
            pl.setStyleSheet("color:#6666AA; font-size:11px; padding:0 2px;")
            status_layout.addWidget(pl)

        sep = QLabel("|")
        sep.setObjectName("StatusText")
        status_layout.addWidget(sep)

        self.ptz_lock_label = QLabel("PTZ Lock")
        self.ptz_lock_label.setObjectName("StatusText")
        status_layout.addWidget(self.ptz_lock_label)

        self.rec_status_label = QLabel("Rec On")
        self.rec_status_label.setObjectName("StatusRec")
        self.rec_status_label.setVisible(False)
        status_layout.addWidget(self.rec_status_label)

        self.stream_status_label = QLabel("Stream Live")
        self.stream_status_label.setObjectName("StatusActive")
        self.stream_status_label.setVisible(False)
        status_layout.addWidget(self.stream_status_label)

        self.clock_label_modern = QLabel(time.strftime("%H:%M"))
        self.clock_label_modern.setObjectName("StatusText")
        status_layout.addWidget(self.clock_label_modern)

        root.addWidget(status_frame)

        # Clock update timer
        self._clock_timer = QTimer(self)
        self._clock_timer.timeout.connect(self._update_clock)
        self._clock_timer.start(1000)

        # Live timer update
        self._live_timer = QTimer(self)
        self._live_timer.timeout.connect(self._update_live_timer)
        self._live_timer.start(1000)

    def toggle_hold_ptz(self, state):
        self.params['hold_ptz'] = bool(state)
        if self.params['hold_ptz']:
            self.update_status("Status: PTZ Locked")
            self.ai_status.setText("AI: ENABLED | AUTOFRAME: HOLD | TRACKING: LOCKED")
            if getattr(self, 'obsbot', None) and getattr(self.obsbot, 'connected', False):
                self.obsbot.set_gimbal_speed(0, 0)
        else:
            self.update_status("Status: PTZ Tracking Active")
            self.ai_status.setText("AI: ENABLED | AUTOFRAME: ON | TRACKING: HOST")

    def update_manual_zoom(self, value):
        self.params['manual_zoom'] = value / 10.0
        if self.params['hold_ptz'] and getattr(self, 'obsbot', None) and getattr(self.obsbot, 'connected', False):
            self.obsbot.set_zoom(self.params['manual_zoom'])

    # ── Trackpad Movement ─────────────────────────────────────
    def _on_trackpad_move(self, dx, dy):
        import time as _time
        if dx == 0 and dy == 0:
            self.stop_manual_move()
            self._trackpad_started = False
            self.pt_readout.setText("P: +0°   T: +0°")
        else:
            if not getattr(self, '_trackpad_started', False):
                if getattr(self, 'obsbot', None) and getattr(self.obsbot, 'connected', False):
                    self.obsbot.set_ai_mode(0)
                    if hasattr(self, 'obsbot_ai_combo'):
                        self.obsbot_ai_combo.setCurrentIndex(0)
                self._trackpad_started = True
                if hasattr(self, 'move_data'):
                    self.move_data["start_time"] = _time.time()

            if hasattr(self, 'move_data'):
                self.move_data.update({"pan": dx, "tilt": dy, "zoom": 0})
            if hasattr(self, 'move_timer') and not self.move_timer.isActive():
                self.move_timer.start(50)

            # Update P/T readout
            pan_deg = int(dx * 180)
            tilt_deg = int(dy * 90)
            p_sign = "+" if pan_deg >= 0 else ""
            t_sign = "+" if tilt_deg >= 0 else ""
            self.pt_readout.setText(f"P: {p_sign}{pan_deg}°   T: {t_sign}{tilt_deg}°")

    # ── Engine Lifecycle ──────────────────────────────────────
    def _on_engine_started(self):
        super()._on_engine_started()
        self.start_btn.setStyleSheet("")
        self.start_btn.setText("")
        self.start_btn.blockSignals(True)
        self.start_btn.setChecked(True)
        self.start_btn.blockSignals(False)
        self.rec_badge.set_active(True)
        self.rec_status_label.setVisible(True)
        self._rec_start_time = time.time()

    def _on_worker_finished(self):
        super()._on_worker_finished()
        self.start_btn.setStyleSheet("")
        self.start_btn.setText("")
        self.start_btn.blockSignals(True)
        self.start_btn.setChecked(False)
        self.start_btn.blockSignals(False)
        self.rec_badge.set_active(False)
        self.rec_status_label.setVisible(False)
        self._rec_start_time = None

    # ── Overrides ─────────────────────────────────────────────
    def update_clock(self):
        pass

    def update_status(self, text):
        self.status_label.setText(text)

    def toggle_tracking(self, state=None):
        cam_text = self.mock_input_combo.currentText()
        if cam_text.startswith("/dev/video"):
            self.input_spin.setValue(int(cam_text.replace("/dev/video", "")))
        super().toggle_tracking()

    def toggle_streaming(self, state=None):
        was_streaming = len(self.params.get("active_streams", [])) > 0
        super().toggle_streaming()
        is_streaming = len(self.params.get("active_streams", [])) > 0

        if is_streaming and not was_streaming:
            self.stream_badge.set_active(True)
            self.stream_badge.setText("Active")
            self.stream_status_label.setVisible(True)
            self._stream_start_time = time.time()
        elif not is_streaming:
            self.stream_badge.set_active(False)
            self.stream_badge.setText("Inactive")
            self.stream_status_label.setVisible(False)
            self.stream_timer_label.setText("")
            self._stream_start_time = None

    def update_toggles(self, *args):
        self.params["draw_preview_roi"] = self.preview_roi_cb.isChecked() if hasattr(self, 'preview_roi_cb') else True
        self.params["draw_output_roi"] = self.output_roi_cb.isChecked() if hasattr(self, 'output_roi_cb') else False
        self.params["flip_video"] = False
        self.params["enable_watermark"] = True

    # ── Timers ────────────────────────────────────────────────
    def _update_clock(self):
        self.clock_label_modern.setText(time.strftime("%H:%M"))

    def _update_live_timer(self):
        if self._stream_start_time:
            elapsed = int(time.time() - self._stream_start_time)
            h, m, s = elapsed // 3600, (elapsed % 3600) // 60, elapsed % 60
            self.stream_timer_label.setText(f"LIVE: {h}h {m:02d}m {s:02d}s")
