import asyncio
import logging
from bleak import BleakScanner, BleakClient
from PyQt6.QtCore import QObject, pyqtSignal as Signal

logger = logging.getLogger("BluetoothManager")

class BluetoothManager(QObject):
    device_discovered = Signal(str, str)  # name, address
    connection_status = Signal(bool, str) # connected, message
    
    # Common OBSBOT BLE UUIDs (based on community research)
    SERVICE_UUID = "0000ff00-0000-1000-8000-00805f9b34fb"
    WRITE_CHARACTERISTIC = "0000ff01-0000-1000-8000-00805f9b34fb"
    NOTIFY_CHARACTERISTIC = "0000ff02-0000-1000-8000-00805f9b34fb"

    def __init__(self):
        super().__init__()
        self.client = None
        self.connected_device = None
        self._loop = asyncio.new_event_loop()
        self._is_scanning = False

    async def _scan(self):
        self._is_scanning = True
        logger.info("Starting BLE scan...")
        devices = await BleakScanner.discover(timeout=5.0)
        for d in devices:
            if d.name and ("OBSBOT" in d.name.upper() or "REMO" in d.name.upper()):
                logger.info(f"Found OBSBOT device: {d.name} ({d.address})")
                self.device_discovered.emit(d.name, d.address)
        self._is_scanning = False

    def start_scan(self):
        if not self._is_scanning:
            asyncio.run_coroutine_threadsafe(self._scan(), self._loop)

    async def _connect(self, address):
        try:
            logger.info(f"Connecting to {address}...")
            self.client = BleakClient(address)
            await self.client.connect()
            self.connected_device = address
            self.connection_status.emit(True, f"Connected to {address}")
            logger.info(f"Connected to {address}")
            
            # Start notifications if possible
            # await self.client.start_notify(self.NOTIFY_CHARACTERISTIC, self._notification_handler)
            
        except Exception as e:
            logger.error(f"Failed to connect: {e}")
            self.connection_status.emit(False, str(e))

    def connect(self, address):
        asyncio.run_coroutine_threadsafe(self._connect(address), self._loop)

    def _notification_handler(self, sender, data):
        logger.debug(f"Received BLE notification from {sender}: {data.hex()}")

    async def _send_command(self, data):
        if self.client and self.client.is_connected:
            try:
                await self.client.write_gatt_char(self.WRITE_CHARACTERISTIC, data)
                return True
            except Exception as e:
                logger.error(f"Failed to send BLE command: {e}")
        return False

    def send_command(self, data):
        asyncio.run_coroutine_threadsafe(self._send_command(data), self._loop)

    # PTZ Control helpers (Proprietary protocol placeholders)
    # Note: These byte sequences are examples and would need to be verified with a sniffer
    def move_left(self):
        # Example: [0x55, 0x01, 0x01, 0x00, 0x64, 0xaa]
        pass

    def stop_move(self):
        pass

    def run_event_loop(self):
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()
