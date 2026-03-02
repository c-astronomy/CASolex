from .alpaca_impl import AlpacaMount, AlpacaCamera
from .indi_impl import IndiDevice

class HardwareManager:
    def __init__(self):
        self.mount = None
        self.camera = None
        self.is_connected = False

    def connect(self, driver_type, host, cam_idx=0, mount_idx=0):
        """
        driver_type: "Alpaca (Cross-Platform)" or "INDI (Linux/macOS)"
        """
        try:
            if "Alpaca" in driver_type:
                self.mount = AlpacaMount(host, mount_idx)
                self.camera = AlpacaCamera(host, cam_idx)
            else:
                # For INDI, we'll assume default names for now, 
                # but these could be passed from the GUI
                self.mount = IndiDevice(host=host.split(':')[0]) 
                self.camera = self.mount # In INDI, one client often handles both

            self.mount.connect()
            self.camera.connect()
            self.is_connected = True
            return True
        except Exception as e:
            print(f"Connection Error: {e}")
            return False

    def disconnect(self):
        self.is_connected = False
        # Add cleanup logic here
