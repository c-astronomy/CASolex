# app/hardware/base.py
class TelescopeDevice:
    def move_to(self, ra, dec): raise NotImplementedError()
    def pulse_guide(self, direction, duration): raise NotImplementedError()
    def get_position(self): raise NotImplementedError()

class CameraDevice:
    def capture_frame(self): raise NotImplementedError()
    def set_roi(self, x, y, w, h): raise NotImplementedError()
