import numpy as np
from PySide6.QtCore import QThread, Signal

class VideoWorker(QThread):
    new_frame = Signal(np.ndarray)

    def __init__(self, camera_device):
        super().__init__()
        self.camera = camera_device
        self.running = False

    def run(self):
        self.running = True
        while self.running:
            try:
                # This calls the capture_frame method we defined in Alpaca/INDI
                frame = self.camera.capture_frame()
                if frame is not None:
                    self.new_frame.emit(frame)
            except Exception as e:
                print(f"Frame capture error: {e}")
                self.sleep(1) # Wait a bit before retrying

    def stop(self):
        self.running = False
        self.wait()
