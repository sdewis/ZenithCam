from PyQt6.QtCore import QObject, QThread, pyqtSignal, pyqtSlot, QTimer  # type: ignore
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class ZenithEngineManager(QObject):
    """
    Groundbreaking FSM (Finite State Machine) for Thread & Hardware Management.
    Completely decouples thread lifecycle from the UI, fixing race conditions and NoneType core dumps.
    """

    engine_started = pyqtSignal()
    engine_stopped = pyqtSignal()

    def __init__(self, hardware_manager, parent=None):
        super().__init__(parent)  # type: ignore
        self.hw_manager = hardware_manager
        self.thread: Optional[QThread] = None
        self.worker: Optional[QObject] = None
        self._worker_hw: Optional[object] = None
        self._is_tracking = False
        self._is_shutting_down = False
        
        # Instance timer to prevent race conditions during rapid restarts
        self.cleanup_timer = QTimer(self)
        self.cleanup_timer.setSingleShot(True)
        self.cleanup_timer.timeout.connect(self._emergency_terminate)

    def toggle_engine(self, worker_class, params):
        """Safe toggle that ignores spam-clicks and invalid states."""
        if self._is_shutting_down:
            logger.warning("Engine is currently tearing down. Please wait.")
            return

        if self._is_tracking:
            self.stop_engine()
        else:
            self.start_engine(worker_class, params)

    def start_engine(self, worker_class, params):
        if self.thread is not None:
            return  # Already running

        self._is_tracking = True
        self.thread = QThread()
        self.worker = worker_class(params)

        # Capture worker's HardwareManager for cleanup
        self._worker_hw = getattr(self.worker, "hw", None)

        thread = self.thread
        worker = self.worker
        assert thread is not None
        assert worker is not None

        worker.moveToThread(thread)

        # Strict lifecycle wiring
        thread.started.connect(worker.run)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._on_thread_fully_dead)

        thread.start()
        self.engine_started.emit()

    def stop_engine(self):
        """Initiates safe teardown without destroying objects prematurely."""
        if not self._is_tracking or self._is_shutting_down:
            return

        self._is_shutting_down = True
        self._is_tracking = False

        worker = self.worker
        if worker is not None:
            worker.stop()  # Tell the worker's internal loop to break gracefully

        # Provide a fallback timeout in case the worker hangs
        self.cleanup_timer.start(3000)

    @pyqtSlot()
    def _on_thread_fully_dead(self):
        """Called only when the OS confirms the thread is gone."""
        self.cleanup_timer.stop()  # Cancel the emergency cleanup timer
        self.thread = None
        self.worker = None
        self._is_shutting_down = False

        # Now it is 100% safe to close hardware descriptors
        # First clean up worker's hardware (including renderer)
        if self._worker_hw is not None:
            try:
                self._worker_hw.cleanup_all()
            except Exception as e:
                logger.error(f"Worker hardware cleanup failed: {e}")
            self._worker_hw = None

        # Then clean up global output
        self.hw_manager.close_output()
        self.engine_stopped.emit()
        logger.info("Engine safely shut down.")

    def _emergency_terminate(self):
        """Last resort nuclear option if Optical Flow or FFmpeg hangs."""
        thread = self.thread
        if thread is not None and thread.isRunning():  # type: ignore
            logger.critical(
                "Worker hung during teardown. Executing thread termination."
            )
            thread.terminate()
            thread.wait()

            # Worker's finally block won't run, so clean up hardware manually
            if self._worker_hw is not None:
                try:
                    self._worker_hw.cleanup_all()
                except Exception as e:
                    logger.error(f"Worker hardware cleanup failed: {e}")
                self._worker_hw = None

            self._on_thread_fully_dead()
