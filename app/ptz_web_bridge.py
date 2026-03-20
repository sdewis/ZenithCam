import asyncio
import json
import logging
import websockets
from PyQt6.QtCore import QThread, pyqtSignal, QObject

logger = logging.getLogger("ZenithCam.WebBridge")

class PTZWebBridgeWorker(QObject):
    """
    A PyQt-friendly asyncio WebSocket server worker.
    Listens on ws://0.0.0.0:8765 for commands from Tampermonkey scripts.
    It supports multiple clients and broadcasting.
    """
    command_received = pyqtSignal(dict)

    def __init__(self, port=8765):
        super().__init__()
        self.port = port
        self.loop = None
        self.clients = set()

    async def handle_client(self, websocket):
        logger.info(f"Browser connected to PTZ Bridge: {websocket.remote_address}")
        self.clients.add(websocket)
        try:
            async for message in websocket:
                try:
                    data = json.loads(message)
                    logger.debug(f"WebBridge received: {data}")
                    self.command_received.emit(data)
                except json.JSONDecodeError:
                    logger.warning(f"Invalid JSON received from browser: {message}")
        except websockets.exceptions.ConnectionClosed:
            logger.info("Browser disconnected from PTZ Bridge.")
        except Exception as e:
            logger.error(f"WebSocket Error: {e}")
        finally:
            self.clients.discard(websocket)

    async def run_server(self):
        self.loop = asyncio.get_running_loop()
        # Bind to 0.0.0.0 to allow connections from local network or VMs
        async with websockets.serve(self.handle_client, "0.0.0.0", self.port):
            logger.info(f"PTZ Web Bridge listening on ws://0.0.0.0:{self.port}")
            await asyncio.Future()  # run forever

    def start_sync(self):
        """Blocking call to start asyncio, meant to be run in a QThread."""
        asyncio.run(self.run_server())

    def broadcast(self, data: dict):
        """Sends a JSON dictionary to all connected WebSocket clients."""
        if not self.loop or not self.clients:
            return
        message = json.dumps(data)
        asyncio.run_coroutine_threadsafe(self._broadcast_task(message), self.loop)

    async def _broadcast_task(self, message):
        if self.clients:
            await asyncio.gather(*(client.send(message) for client in self.clients), return_exceptions=True)

def initialize_web_bridge(main_app_instance, port=8765):
    """
    Helper to initialize and thread the Web Bridge.
    Returns the thread and the worker object.
    """
    worker = PTZWebBridgeWorker(port=port)
    thread = QThread()
    worker.moveToThread(thread)
    thread.started.connect(worker.start_sync)
    
    if hasattr(main_app_instance, 'handle_web_ptz_command'):
        worker.command_received.connect(main_app_instance.handle_web_ptz_command)
    else:
        logger.warning("Main window missing 'handle_web_ptz_command' slot. Commands will be ignored.")

    thread.start()
    return thread, worker
