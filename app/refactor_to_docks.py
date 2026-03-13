import re
import os

filepath = "/home/sean/CodeFolder/ZenithCam_SDK_Integrated/app/main.py"
with open(filepath, "r") as f:
    content = f.read()

# 1. Update Imports
if "from PyQt6.QtWidgets import" in content and "QDockWidget" not in content:
    content = content.replace("from PyQt6.QtWidgets import (", "from PyQt6.QtWidgets import (QDockWidget, ")

# 2. Extract logic into modular methods/classes or just refactor MainWindow.__init__
# Given the complexity, I'll refactor MainWindow.__init__ to create QDockWidgets instead of fixed panels.

# We need to find the start and end of MainWindow.__init__
# The previous cat shows it starts around line 480.

pattern_init = r'class MainWindow\(QMainWindow\):\n\s+def __init__\(self\):.*?global_logger\.info\("Application initialized\."\)'

new_init = '''class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ZenithCam: Plasma Environment")
        self.setMinimumSize(800, 600)
        self.resize(1280, 720)
        
        # Dock Options
        self.setDockOptions(QMainWindow.DockOption.AnimatedDocks | 
                            QMainWindow.DockOption.AllowTabbedDocks | 
                            QMainWindow.DockOption.AllowNestedDocks)
        
        self.presets = {"Home": (0, 0, 1.0), "P1": (0, 0, 1.0), "P2": (0, 0, 1.0)}
        
        # Tracking Parameters
        self.params = {
            'input_source': 1,
            'output_device': "/dev/video20",
            'model_path': os.path.join(os.path.dirname(__file__), "erax-anti-nsfw-yolo11n-v1.1.onnx"),
            'target_class_ids': [1],
            'blur_class_ids': [0, 2, 3, 4],
            'smooth_factor': 0.1,
            'zoom_margin': 20,
            'output_width': 1280,
            'output_height': 720,
            'draw_preview_roi': True,
            'draw_output_roi': False,
            'flip_video': False,
            'show_input_preview': True,
            'show_output_preview': True,
            'enable_physical_ptz': False,
            'enable_onboard_tracker': False,
            'obsbot': None,
            'rtmp_url': "rtmp://localhost:1935/live",
            'stream_key': "test",
            'active_streams': []
        }

        self.stream_process = None

        self.obsbot = OBSBOTSDK()
        if self.obsbot.init() and self.obsbot.connect():
            global_logger.info("Connected to OBSBOT SDK")
            self.obsbot.set_ai_mode(0)
            self.params['obsbot'] = self.obsbot
        else: global_logger.warning("OBSBOT SDK connection failed. Retry via UI.")
        
        self.worker = None
        self.thread = None
        
        # Central widget is just a placeholder to allow docking
        self.central_placeholder = QWidget()
        self.setCentralWidget(self.central_placeholder)
        self.central_placeholder.setMaximumSize(0, 0) # Hide it, use docks for everything

        # --- PANEL 1: CONFIG ---
        self.config_dock = QDockWidget("⚙️ System Configuration", self)
        self.config_dock.setObjectName("ConfigDock")
        self.config_dock.setAllowedAreas(Qt.DockWidgetArea.AllDockWidgetAreas)
        
        config_content = QWidget()
        config_layout = QVBoxLayout(config_content)
        
        self.settings_scroll = QScrollArea()
        self.settings_scroll.setWidgetResizable(True)
        self.settings_scroll.setStyleSheet("border: none; background: transparent;")
        settings_container = QWidget()
        settings_layout = QVBoxLayout(settings_container)
        
        conf_group = QGroupBox("Device Settings")
        group_layout = QVBoxLayout(conf_group)
        
        cam_row = QHBoxLayout()
        cam_row.addWidget(QLabel("Input Camera:"))
        self.input_spin = QSpinBox()
        obs_dev = find_obsbot_device()
        def_idx = int(obs_dev.split("video")[-1]) if obs_dev and "video" in obs_dev else 1
        self.input_spin.setValue(def_idx)
        cam_row.addWidget(self.input_spin)
        group_layout.addLayout(cam_row)

        out_row = QHBoxLayout()
        out_row.addWidget(QLabel("Virtual Output:"))
        self.refresh_btn = QPushButton("↻")
        self.refresh_btn.setFixedSize(30, 30)
        self.refresh_btn.clicked.connect(self.refresh_output_devices)
        out_row.addWidget(self.refresh_btn)
        group_layout.addLayout(out_row)
        self.output_edit = QComboBox()
        self.output_edit.setEditable(True)
        self.output_edit.setFixedHeight(35)
        group_layout.addWidget(self.output_edit)
        self.refresh_output_devices()

        m_row = QHBoxLayout()
        m_row.addWidget(QLabel("Model:"))
        self.model_label = QLabel("YOLO (Default)")
        self.model_label.setStyleSheet("color: #00E676; font-size: 11px;")
        self.model_btn = QPushButton("📁")
        self.model_btn.setFixedSize(30, 30)
        self.model_btn.clicked.connect(self.select_model)
        m_row.addWidget(self.model_label)
        m_row.addWidget(self.model_btn)
        group_layout.addLayout(m_row)

        group_layout.addWidget(QLabel("Target Classes (Zoom):"))
        self.class_scroll = QScrollArea(); self.class_scroll.setMinimumHeight(100)
        self.class_container = QWidget(); self.class_layout = QVBoxLayout(self.class_container)
        self.class_scroll.setWidget(self.class_container); self.class_scroll.setWidgetResizable(True)
        group_layout.addWidget(self.class_scroll)

        group_layout.addWidget(QLabel("Blur Classes:"))
        self.blur_scroll = QScrollArea(); self.blur_scroll.setMinimumHeight(100)
        self.blur_container = QWidget(); self.blur_layout = QVBoxLayout(self.blur_container)
        self.blur_scroll.setWidget(self.blur_container); self.blur_scroll.setWidgetResizable(True)
        group_layout.addWidget(self.blur_scroll)

        group_layout.addWidget(QLabel("PTZ Smoothing:"))
        self.smooth_slider = QSlider(Qt.Orientation.Horizontal)
        self.smooth_slider.setRange(1, 100); self.smooth_slider.setValue(10)
        self.smooth_slider.valueChanged.connect(self.update_smoothing)
        group_layout.addWidget(self.smooth_slider)

        group_layout.addWidget(QLabel("Zoom Margin (%):"))
        self.margin_spin = QSpinBox(); self.margin_spin.setRange(0, 100); self.margin_spin.setValue(20)
        self.margin_spin.valueChanged.connect(self.update_margin)
        group_layout.addWidget(self.margin_spin)

        settings_layout.addWidget(conf_group)
        settings_layout.addStretch()
        self.settings_scroll.setWidget(settings_container)
        config_layout.addWidget(self.settings_scroll)
        self.config_dock.setWidget(config_content)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.config_dock)

        # --- PANEL 2: INPUT PREVIEW ---
        self.input_preview_dock = QDockWidget("📸 Raw Camera Feed", self)
        self.input_preview_dock.setObjectName("InputPreviewDock")
        self.input_preview_group = QGroupBox()
        in_l = QVBoxLayout(self.input_preview_group)
        self.input_preview_label = QLabel("Waiting for camera...")
        self.input_preview_label.setMinimumSize(320, 180)
        self.input_preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        in_l.addWidget(self.input_preview_label)
        self.input_preview_dock.setWidget(self.input_preview_group)
        self.addDockWidget(Qt.DockWidgetArea.TopDockWidgetArea, self.input_preview_dock)

        # --- PANEL 3: OUTPUT PREVIEW ---
        self.output_preview_dock = QDockWidget("🧠 AI Processed View", self)
        self.output_preview_dock.setObjectName("OutputPreviewDock")
        self.output_preview_group = QGroupBox()
        out_l = QVBoxLayout(self.output_preview_group)
        self.output_preview_label = QLabel("Waiting for AI processing...")
        self.output_preview_label.setMinimumSize(320, 180)
        self.output_preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        out_l.addWidget(self.output_preview_label)
        self.output_preview_dock.setWidget(self.output_preview_group)
        self.splitDockWidget(self.input_preview_dock, self.output_preview_dock, Qt.Orientation.Vertical)

        # --- PANEL 4: STREAMING ---
        self.streaming_dock = QDockWidget("📡 Plasma Broadcast", self)
        self.streaming_dock.setObjectName("StreamingDock")
        
        # Profile Management & Streaming
        self.profiles_file = os.path.join(os.path.dirname(__file__), "profiles.json")
        self.stream_profiles = []
        self.load_profiles()
        self.active_streams = []

        stream_content = QWidget()
        stream_layout = QVBoxLayout(stream_content)
        
        prof_row1 = QHBoxLayout()
        self.profile_combo = QComboBox()
        self.profile_combo.setFixedHeight(35)
        self.profile_combo.currentIndexChanged.connect(self.on_profile_selected)
        prof_row1.addWidget(self.profile_combo, stretch=1)
        
        btn_add = QPushButton("+"); btn_add.setFixedSize(35, 35); btn_add.clicked.connect(self.add_profile)
        btn_del = QPushButton("-"); btn_del.setFixedSize(35, 35); btn_del.clicked.connect(self.delete_profile)
        btn_save = QPushButton("💾"); btn_save.setFixedSize(35, 35); btn_save.clicked.connect(self.save_current_profile)
        prof_row1.addWidget(btn_add); prof_row1.addWidget(btn_del); prof_row1.addWidget(btn_save)
        stream_layout.addLayout(prof_row1)

        self.prof_name_edit = QLineEdit(); self.prof_name_edit.setFixedHeight(35); self.prof_name_edit.setPlaceholderText("Profile Name")
        stream_layout.addWidget(self.prof_name_edit)
        self.prof_site_edit = QLineEdit(); self.prof_site_edit.setFixedHeight(35); self.prof_site_edit.setPlaceholderText("Site")
        stream_layout.addWidget(self.prof_site_edit)
        self.rtmp_url_edit = QLineEdit(); self.rtmp_url_edit.setFixedHeight(35); self.rtmp_url_edit.setPlaceholderText("RTMP URL")
        stream_layout.addWidget(self.rtmp_url_edit)
        self.stream_key_edit = QLineEdit(); self.stream_key_edit.setFixedHeight(35); self.stream_key_edit.setPlaceholderText("Key"); self.stream_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        stream_layout.addWidget(self.stream_key_edit)
        
        br_layout = QHBoxLayout()
        br_layout.addWidget(QLabel("Quality:"))
        self.bitrate_combo = QComboBox()
        self.bitrate_combo.addItems(["Fast/WiFi (3000 kbps)", "Medium (4500 kbps)", "High/Ethernet (6000 kbps)"])
        self.bitrate_combo.setCurrentIndex(0)
        br_layout.addWidget(self.bitrate_combo)
        stream_layout.addLayout(br_layout)
        
        stream_layout.addWidget(QLabel("Simultaneous Streaming (Max 3):"))
        self.stream_checkboxes = []
        self.chk_layout = QVBoxLayout()
        stream_layout.addLayout(self.chk_layout)
        self.refresh_profile_ui()

        self.stream_btn = QPushButton("Start Broadcast")
        self.stream_btn.setObjectName("StreamBtn")
        self.stream_btn.setStyleSheet("background-color: #2979FF; padding: 12px; font-weight: bold; border-radius: 6px; color: #FFFFFF;")
        self.stream_btn.clicked.connect(self.toggle_streaming)
        stream_layout.addWidget(self.stream_btn)
        stream_layout.addStretch()
        
        self.streaming_dock.setWidget(stream_content)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.streaming_dock)

        # --- PANEL 5: PTZ ---
        self.ptz_dock = QDockWidget("🕹️ PTZ Controls", self)
        self.ptz_dock.setObjectName("PTZDock")
        ptz_content = QWidget()
        ptz_layout = QVBoxLayout(ptz_content)

        hardware_group = QGroupBox("Robot Control")
        hw_layout = QVBoxLayout(hardware_group)
        self.reconnect_obsbot_btn = QPushButton("🔌 Connect OBSBOT")
        self.reconnect_obsbot_btn.clicked.connect(self.reconnect_obsbot)
        hw_layout.addWidget(self.reconnect_obsbot_btn)
        
        self.ptz_cb = QCheckBox("Enable Physical PTZ"); self.ptz_cb.stateChanged.connect(self.toggle_ptz)
        hw_layout.addWidget(self.ptz_cb)
        self.onboard_tracker_cb = QCheckBox("Use Onboard AI Tracker"); self.onboard_tracker_cb.setStyleSheet("color: #80CBC4; padding-left: 20px;")
        self.onboard_tracker_cb.stateChanged.connect(self.toggle_onboard_tracker)
        hw_layout.addWidget(self.onboard_tracker_cb)

        hw_layout.addWidget(QLabel("OBSBOT AI Mode:"))
        self.obsbot_ai_combo = QComboBox()
        self.obsbot_ai_combo.addItems(["None", "Group", "Human", "Hand", "Whiteboard", "Desk"])
        self.obsbot_ai_combo.currentIndexChanged.connect(self.change_obsbot_ai_mode)
        hw_layout.addWidget(self.obsbot_ai_combo)
        
        self.submode_label = QLabel("Sub-Mode:"); self.obsbot_submode_combo = QComboBox()
        self.obsbot_submode_combo.addItem("Default"); self.obsbot_submode_combo.currentIndexChanged.connect(self.change_obsbot_submode)
        self.submode_label.setVisible(False); self.obsbot_submode_combo.setVisible(False)
        hw_layout.addWidget(self.submode_label); hw_layout.addWidget(self.obsbot_submode_combo)
        self.privacy_cb = QCheckBox("Hardware Privacy Mode"); self.privacy_cb.stateChanged.connect(self.toggle_privacy)
        hw_layout.addWidget(self.privacy_cb)
        ptz_layout.addWidget(hardware_group)

        manual_group = QGroupBox("Manual Movement")
        manual_layout = QVBoxLayout(manual_group)
        
        p_row = QHBoxLayout()
        for p_name in ["Home", "P1", "P2"]:
            btn = PresetButton(p_name); btn.setStyleSheet("background-color: #333; padding: 8px; font-size: 12px; border: 1px solid #555; border-radius: 4px;")
            btn.left_clicked.connect(lambda n=p_name: self.recall_preset(n))
            btn.right_clicked.connect(lambda n=p_name: self.save_preset(n))
            p_row.addWidget(btn)
        manual_layout.addLayout(p_row)

        dpad = QGridLayout()
        self.btn_up, self.btn_down, self.btn_left, self.btn_right, self.btn_center = QPushButton("▲"), QPushButton("▼"), QPushButton("◄"), QPushButton("►"), QPushButton("●")
        self.btn_reset_gimbal = QPushButton("⚡"); self.btn_reset_gimbal.setToolTip("Reset Gimbal")
        self.btn_up.pressed.connect(lambda: self.start_manual_move(0, 1)); self.btn_down.pressed.connect(lambda: self.start_manual_move(0, -1))
        self.btn_left.pressed.connect(lambda: self.start_manual_move(1, 0)); self.btn_right.pressed.connect(lambda: self.start_manual_move(-1, 0))
        for b in [self.btn_up, self.btn_down, self.btn_left, self.btn_right]: b.released.connect(self.stop_manual_move)
        self.btn_center.clicked.connect(self.manual_center); self.btn_reset_gimbal.clicked.connect(self.reset_gimbal)
        for b in [self.btn_up, self.btn_down, self.btn_left, self.btn_right, self.btn_center, self.btn_reset_gimbal]:
            b.setStyleSheet("background-color: #333; padding: 10px; border-radius: 4px;")
        self.btn_reset_gimbal.setStyleSheet("background-color: #5C2222; color: #FF8A80; font-weight: bold; padding: 10px; border-radius: 4px;")
        dpad.addWidget(self.btn_up, 0, 1); dpad.addWidget(self.btn_left, 1, 0); dpad.addWidget(self.btn_center, 1, 1); dpad.addWidget(self.btn_right, 1, 2); dpad.addWidget(self.btn_down, 2, 1); dpad.addWidget(self.btn_reset_gimbal, 2, 2)
        manual_layout.addLayout(dpad)
        
        z_row = QHBoxLayout()
        self.btn_zoom_in, self.btn_zoom_out = QPushButton("Zoom +"), QPushButton("Zoom -")
        self.btn_zoom_in.setStyleSheet("background-color: #333; padding: 10px; border-radius: 4px;")
        self.btn_zoom_out.setStyleSheet("background-color: #333; padding: 10px; border-radius: 4px;")
        self.btn_zoom_in.pressed.connect(lambda: self.start_manual_zoom(1)); self.btn_zoom_out.pressed.connect(lambda: self.start_manual_zoom(-1))
        self.btn_zoom_in.released.connect(self.stop_manual_move); self.btn_zoom_out.released.connect(self.stop_manual_move)
        z_row.addWidget(self.btn_zoom_out); z_row.addWidget(self.btn_zoom_in)
        manual_layout.addLayout(z_row)
        ptz_layout.addWidget(manual_group)
        ptz_layout.addStretch()
        
        self.ptz_dock.setWidget(ptz_content)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.ptz_dock)
        self.tabifyDockWidget(self.streaming_dock, self.ptz_dock)

        # --- BOTTOM TASKBAR ---
        self.taskbar = QWidget()
        self.taskbar.setObjectName("TaskBar")
        self.taskbar.setFixedHeight(60)
        taskbar_layout = QHBoxLayout(self.taskbar)
        taskbar_layout.setContentsMargins(20, 0, 20, 0)
        
        self.app_menu_btn = QPushButton("💠")
        self.app_menu_btn.setStyleSheet("font-size: 20px; color: #00E676;")
        self.app_menu_btn.clicked.connect(self.show_launcher_menu)
        taskbar_layout.addWidget(self.app_menu_btn)
        taskbar_layout.addSpacing(10)

        # Taskbar buttons to toggle docks
        def create_toggle(label, dock):
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setChecked(True)
            btn.toggled.connect(dock.setVisible)
            dock.visibilityChanged.connect(btn.setChecked)
            return btn

        taskbar_layout.addWidget(create_toggle("⚙️ Config", self.config_dock))
        taskbar_layout.addWidget(create_toggle("📸 Raw Feed", self.input_preview_dock))
        taskbar_layout.addWidget(create_toggle("🧠 AI Feed", self.output_preview_dock))
        taskbar_layout.addWidget(create_toggle("📡 Streaming", self.streaming_dock))
        taskbar_layout.addWidget(create_toggle("🕹️ PTZ", self.ptz_dock))

        self.preview_roi_cb = QCheckBox("ROI"); self.preview_roi_cb.setChecked(True); self.preview_roi_cb.stateChanged.connect(self.update_toggles)
        self.output_roi_cb = QCheckBox("Out ROI"); self.output_roi_cb.stateChanged.connect(self.update_toggles)
        self.flip_cb = QCheckBox("Flip"); self.flip_cb.stateChanged.connect(self.update_toggles)
        self.debug_cb = QCheckBox("Debug"); self.debug_cb.stateChanged.connect(self.toggle_debug)
        
        taskbar_layout.addSpacing(20)
        taskbar_layout.addWidget(self.preview_roi_cb); taskbar_layout.addWidget(self.output_roi_cb)
        taskbar_layout.addWidget(self.flip_cb); taskbar_layout.addWidget(self.debug_cb)
        taskbar_layout.addStretch()

        self.status_label = QLabel("Status: Idle")
        self.status_label.setStyleSheet("color: #00E676; font-weight: bold; margin-right: 15px;")
        taskbar_layout.addWidget(self.status_label)

        self.start_btn = QPushButton("▶ START ENGINE")
        self.start_btn.setObjectName("StartBtn")
        self.start_btn.clicked.connect(self.toggle_tracking)
        taskbar_layout.addWidget(self.start_btn)

        # Add taskbar to bottom
        self.setMenuWidget(None) # Make sure no standard menu bar
        
        # We use a container for the bottom because QMainWindow layout is tricky
        main_container = QWidget()
        self.main_vlayout = QVBoxLayout(main_container)
        self.main_vlayout.setContentsMargins(0, 0, 0, 0)
        self.main_vlayout.setSpacing(0)
        
        # We need to move the dock manager area into the layout or just let QMainWindow handle it
        # Actually, QMainWindow handles docks automatically around the central widget.
        # So we just add the taskbar to the bottom of the window manually.
        
        self.addToolBar(Qt.ToolBarArea.BottomToolBarArea, self.wrap_in_toolbar(self.taskbar))

        self.debug_container = QGroupBox("Debug Logs")
        debug_l = QVBoxLayout(self.debug_container)
        self.log_text = QTextEdit(); self.log_text.setReadOnly(True); debug_l.addWidget(self.log_text)
        self.debug_dock = QDockWidget("📝 Logs", self)
        self.debug_dock.setObjectName("DebugDock")
        self.debug_dock.setWidget(self.debug_container)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.debug_dock)
        self.debug_dock.setVisible(False)
        
        self.update_classes({0: "anus", 1: "action_zoom", 2: "nipple", 3: "penis", 4: "vagina", 99: "face"})
        self.move_timer = QTimer(self); self.move_timer.timeout.connect(self.apply_manual_ptz); self.move_data = {"pan": 0, "tilt": 0, "zoom": 0, "start_time": 0}
        qt_handler.emitter.log_signal.connect(self.append_log)
        global_logger.info("Application initialized.")

    def wrap_in_toolbar(self, widget):
        from PyQt6.QtWidgets import QToolBar
        tb = QToolBar()
        tb.setMovable(False)
        tb.addWidget(widget)
        tb.setStyleSheet("background: transparent; border: none;")
        return tb'''

# Replace init
content = re.sub(pattern_init, new_init, content, flags=re.DOTALL)

# Add QDockWidget to imports if needed (handled above)

with open(filepath, "w") as f:
    f.write(content)
