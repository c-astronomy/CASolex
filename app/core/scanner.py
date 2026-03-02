import time
from datetime import datetime

class SHGScanner:
    def __init__(self, mount_device, camera_device):
        self.mount = mount_device
        self.camera = camera_device
        self.is_scanning = False
        self.abort_request = False
        # Standard solar radius in arcminutes (approx)
        self.SOLAR_RADIUS_ARCMIN = 16.0


    def abort(self):
        """Emergency stop for all hardware and loops."""
        self.abort_requested = True
        self.is_scanning = False
        self.mount.stop_motion()
        try:
            self.camera.stop_recording()
        except:
            pass
        print("!!! SCAN ABORTED BY USER !!!")


    def start_recording(self, filename):
        # Get dims from camera
        w, h = self.camera.get_dims()
        self.ser = SERWriter()
        self.ser.open(filename, w, h, bit_depth=16)

    def on_frame_received(self, frame):
        # This would be called by the camera callback
        if self.is_scanning:
            self.ser.add_frame(frame)

    def calculate_scan_range(self, margin_arcmin):
        """
        Determines the RA/Dec offsets needed for the scan.
        For simplicity, we'll assume an RA-based scan (East-West).
        """
        total_offset = self.SOLAR_RADIUS_ARCMIN + margin_arcmin
        # Convert arcminutes to degrees for mount commands
        offset_deg = total_offset / 60.0
        return offset_deg

    def run_scan(self, margin_arcmin, scan_speed_rate, auto_rewind=True):
        """
        The main automation loop.
        scan_speed_rate: Multiplier of sidereal speed (e.g., 2.0x)
        """
        print("Initializing SHG Scan...")
        
        # 1. Get Current Center (Assumes user has centered the sun)
        center_pos = self.mount.get_position() # Returns {'ra': val, 'dec': val}
        offset = self.calculate_scan_range(margin_arcmin)
        
        start_ra = center_pos['ra'] - offset
        end_ra = center_pos['ra'] + offset

        # 2. Slew to Start Position (Pre-scan margin)
        print(f"Slewing to Start Point: {start_ra}")
        self.mount.move_to(start_ra, center_pos['dec'])
        while self.mount.is_slewing():
            time.sleep(0.5)

        # 3. Start Recording & Movement
        print("Starting Capture...")
        filename = f"sun_scan_{datetime.now().strftime('%H%M%S')}.ser"
        self.camera.start_recording(filename)
        
        self.is_scanning = True
        # Set custom tracking rate or constant slew
        self.mount.set_slew_rate(scan_speed_rate)
        self.mount.move_to(end_ra, center_pos['dec'])

        # 4. Monitor Progress
        while self.is_scanning:
            current_ra = self.mount.get_position()['ra']
            if current_ra >= end_ra:
                self.is_scanning = False
            time.sleep(0.1)

        # 5. Stop & Finalize
        self.camera.stop_recording()
        print(f"Scan Complete. File saved: {filename}")

        # 6. Auto-Rewind
        if auto_rewind:
            print("Rewinding to start position for next pass...")
            self.mount.move_to(start_ra, center_pos['dec'])
