import ctypes
import os
import time
import logging
import threading
from bluetooth_manager import BluetoothManager

logger = logging.getLogger("OBSBOTWrapper")

class OBSBOTSDK:
    # AI Work Modes
    AI_MODE_NONE = 0
    AI_MODE_GROUP = 1
    AI_MODE_HUMAN = 2
    AI_MODE_HAND = 3
    AI_MODE_WHITEBOARD = 4
    AI_MODE_DESK = 5

    def __init__(self, use_bluetooth=False):
        self.lib = None
        self.initialized = False
        self.connected = False
        self.has_disconnect = False
        self.use_bluetooth = use_bluetooth
        
        if self.use_bluetooth:
            self.bt_manager = BluetoothManager()
            self.bt_thread = threading.Thread(target=self.bt_manager.run_event_loop, daemon=True)
            self.bt_thread.start()
        else:
            self.bt_manager = None

        lib_dir = os.path.join(os.path.dirname(__file__), "libs")
        lib_path = os.path.join(lib_dir, "libobsbot_bridge.so")
        
        try:
            # Pre-load libdev to avoid dependency issues
            libdev_path = os.path.join(lib_dir, "libdev.so")
            if os.path.exists(libdev_path):
                ctypes.CDLL(libdev_path, mode=ctypes.RTLD_GLOBAL)
            self.lib = ctypes.CDLL(lib_path)
        except Exception as e:
            logger.error(f"Failed to load OBSBOT bridge library at {lib_path}: {e}")
            return

        # Define function signatures
        self.lib.obsbot_init.restype = ctypes.c_bool
        self.lib.obsbot_get_device_count.restype = ctypes.c_int
        self.lib.obsbot_get_device_sn.argtypes = [ctypes.c_int, ctypes.c_char_p]
        self.lib.obsbot_get_device_sn.restype = ctypes.c_bool
        self.lib.obsbot_connect.argtypes = [ctypes.c_char_p]
        self.lib.obsbot_connect.restype = ctypes.c_bool
        self.lib.obsbot_set_gimbal_speed.argtypes = [ctypes.c_float, ctypes.c_float]
        self.lib.obsbot_set_gimbal_speed.restype = ctypes.c_bool
        self.lib.obsbot_set_gimbal_angle.argtypes = [ctypes.c_float, ctypes.c_float]
        self.lib.obsbot_set_gimbal_angle.restype = ctypes.c_bool
        self.lib.obsbot_set_zoom.argtypes = [ctypes.c_float]
        self.lib.obsbot_set_zoom.restype = ctypes.c_bool
        try:
            self.lib.obsbot_set_zoom_absolute.argtypes = [ctypes.c_int]
            self.lib.obsbot_set_zoom_absolute.restype = ctypes.c_bool
            self.has_zoom_absolute = True
        except:
            self.has_zoom_absolute = False

        self.lib.obsbot_set_ai_mode.argtypes = [ctypes.c_int, ctypes.c_int]
        self.lib.obsbot_set_ai_mode.restype = ctypes.c_bool
        self.lib.obsbot_set_led.argtypes = [ctypes.c_bool]
        self.lib.obsbot_set_led.restype = ctypes.c_bool
        self.lib.obsbot_get_gimbal_attitude.argtypes = [ctypes.POINTER(ctypes.c_float), ctypes.POINTER(ctypes.c_float), ctypes.POINTER(ctypes.c_float)]
        self.lib.obsbot_get_gimbal_attitude.restype = ctypes.c_bool
        self.lib.obsbot_set_track_target.argtypes = [ctypes.c_float, ctypes.c_float, ctypes.c_float, ctypes.c_float]
        self.lib.obsbot_set_track_target.restype = ctypes.c_bool
        self.lib.obsbot_set_privacy_mode.argtypes = [ctypes.c_bool]
        self.lib.obsbot_reset_gimbal.restype = ctypes.c_bool
        self.lib.obsbot_set_privacy_mode.restype = ctypes.c_bool
        
        # New disconnect function
        try:
            self.lib.obsbot_disconnect.argtypes = []
            self.lib.obsbot_disconnect.restype = None
            self.has_disconnect = True
        except:
            pass

    def init(self):
        if self.use_bluetooth:
            return True # Bluetooth doesn't need SDK init
        if not self.lib: return False
        if not self.initialized:
            self.initialized = self.lib.obsbot_init()
            if self.initialized:
                logger.info("OBSBOT SDK Initialized")
                # Discovery takes time
                time.sleep(2)
        return self.initialized

    def get_device_count(self):
        if not self.initialized: return 0
        return self.lib.obsbot_get_device_count()

    def get_device_sn(self, index=0):
        if not self.initialized: return None
        sn_buf = ctypes.create_string_buffer(32)
        if self.lib.obsbot_get_device_sn(index, sn_buf):
            return sn_buf.value.decode('utf-8')
        return None

    def connect(self, sn=None):
        if self.use_bluetooth:
            if not sn:
                # Start a scan if no address provided
                self.bt_manager.start_scan()
                return False
            self.bt_manager.connect(sn)
            # We assume it succeeds for now or let the UI handle the signal
            self.connected = True 
            return True

        if not self.initialized: 
            if not self.init(): return False
            
        if not sn:
            # Wait a bit longer if no devices found immediately
            logger.info("Looking for OBSBOT devices...")
            for _ in range(10):
                count = self.get_device_count()
                if count > 0: 
                    logger.info(f"Found {count} OBSBOT device(s).")
                    break
                time.sleep(1)
            
            if count == 0:
                logger.warning("No OBSBOT devices found during connection attempt")
                return False
            sn = self.get_device_sn(0)
            
        if not sn: return False
        
        # Ensure we are disconnected before connecting to avoid handle leaks
        self.disconnect()
        
        logger.info(f"Attempting to connect to OBSBOT device: {sn}")
        for i in range(3):
            self.connected = self.lib.obsbot_connect(sn.encode('utf-8'))
            if self.connected:
                logger.info(f"Connected to OBSBOT device: {sn}")
                return True
            logger.warning(f"Connection attempt {i+1} failed, retrying...")
            time.sleep(2)
            
        logger.error(f"Failed to connect to OBSBOT device: {sn} after 3 attempts.")
        return False

    def disconnect(self):
        if self.lib and getattr(self, 'has_disconnect', False):
            self.lib.obsbot_disconnect()
        self.connected = False

    def set_gimbal_speed(self, pitch, pan):
        if not self.connected: return False
        if self.use_bluetooth:
            # Placeholder for BLE protocol command
            # self.bt_manager.set_gimbal_speed(pitch, pan)
            return True
        return self.lib.obsbot_set_gimbal_speed(pitch, pan)

    def set_gimbal_angle(self, pitch, yaw):
        if not self.connected: return False
        if self.use_bluetooth:
            # self.bt_manager.set_gimbal_angle(pitch, yaw)
            return True
        return self.lib.obsbot_set_gimbal_angle(pitch, yaw)

    def set_zoom(self, zoom):
        """zoom value: 1.0 to 4.0 (normalized)"""
        if not self.connected: return False
        
        if self.use_bluetooth:
            # self.bt_manager.set_zoom(zoom)
            return True

        if getattr(self, 'has_zoom_absolute', False):
            # Map 1.0-4.0 to 0-100 (SDK scale)
            # (zoom - 1.0) / 3.0 * 100
            abs_zoom = int((zoom - 1.0) / 3.0 * 100)
            abs_zoom = max(0, min(100, abs_zoom))
            return self.lib.obsbot_set_zoom_absolute(abs_zoom)
        
        # Fallback to normalized float if absolute is not available
        return self.lib.obsbot_set_zoom(zoom)

    def set_ai_mode(self, mode, sub_mode=0):
        if not self.connected: return False
        return self.lib.obsbot_set_ai_mode(mode, sub_mode)

    def set_led(self, enabled):
        if not self.connected: return False
        return self.lib.obsbot_set_led(enabled)

    def get_gimbal_attitude(self):
        if not self.connected: return None, None, None
        p, y, r = ctypes.c_float(), ctypes.c_float(), ctypes.c_float()
        if self.lib.obsbot_get_gimbal_attitude(ctypes.byref(p), ctypes.byref(y), ctypes.byref(r)):
            return p.value, y.value, r.value
        return None, None, None

    def set_track_target(self, x_min, y_min, x_max, y_max):
        """Coords: 0.0 to 1.0"""
        if not self.connected: return False
        return self.lib.obsbot_set_track_target(x_min, y_min, x_max, y_max)

    def reset_gimbal(self):
        if not self.connected: return False
        return self.lib.obsbot_reset_gimbal()

    def set_privacy_mode(self, enabled):
        if not self.connected: return False
        return self.lib.obsbot_set_privacy_mode(enabled)
