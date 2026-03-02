from alpaca.telescope import Telescope
from alpaca.camera import Camera
import time

class AlpacaMount:
    def __init__(self, address, device_number=0):
        # address: "192.168.1.50:6800"
        self.mount = Telescope(address, device_number)

    def connect(self):
        self.mount.Connected = True
        self.mount.Tracking = True # Required for solar scanning

    def get_position(self):
        """Returns RA and Dec in degrees."""
        return {
            'ra': self.mount.RightAscension,
            'dec': self.mount.Declination
        }

    def move_to(self, ra, dec):
        """Slews to a specific RA/Dec coordinate."""
        if not self.mount.CanSlew:
            print("Mount does not support slewing!")
            return
        self.mount.SlewToCoordinates(ra, dec)

    def is_slewing(self):
        return self.mount.Slewing

    def set_slew_rate(self, rate_multiplier):
        """
        Adjusts tracking rate or uses MoveAxis for the scan.
        For SHG, MoveAxis at a specific rate is often smoother.
        """
        # Rate 0 = Right Ascension
        # rate_multiplier = deg/sec
        self.mount.MoveAxis(0, rate_multiplier) 

    def stop_motion(self):
        self.mount.AbortSlew()
        self.mount.MoveAxis(0, 0) # Stop manual movement

class AlpacaCamera:
    def __init__(self, address, device_number=0):
        self.cam = Camera(address, device_number)
        self.is_recording = False

    def connect(self):
        self.cam.Connected = True

    def get_dims(self):
        return self.cam.CameraXSize, self.cam.CameraYSize

    def capture_frame(self):
        """Captures a single frame for the live view."""
        self.cam.StartExposure(0.001, True) # Short exp for SHG
        while not self.cam.ImageReady:
            time.sleep(0.01)
        return self.cam.ImageArray # Returns a numpy-like array

    def set_roi(self, x, y, w, h):
        self.cam.StartX = x
        self.cam.StartY = y
        self.cam.NumX = w
        self.cam.NumY = h
