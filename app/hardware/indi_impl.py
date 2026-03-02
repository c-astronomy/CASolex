import PyIndi
import time
import threading

class IndiDevice:
    def __init__(self, host="localhost", port=7624, camera_name="ZWO CCD ASI178MM", mount_name="EQMod Mount"):
        self.host = host
        self.port = port
        self.camera_name = camera_name
        self.mount_name = mount_name
        
        # Initialize the INDI Client
        self.client = PyIndi.IndiClient()
        self.client.setServer(self.host, self.port)
        
        # Internal state
        self.connected = False

    def connect(self):
        """Starts the INDI network thread and waits for devices."""
        if not self.client.connectServer():
            print(f"Failed to connect to INDI server at {self.host}")
            return False
        
        print(f"Connected to INDI server. Waiting for {self.camera_name} and {self.mount_name}...")
        # Give INDI a moment to enumerate devices
        time.sleep(1)
        
        # Logic to "Switch On" the devices
        self._set_connection_state(self.camera_name, True)
        self._set_connection_state(self.mount_name, True)
        self.connected = True
        return True

    def _get_device_prop(self, device_name, prop_name):
        device = self.client.getDevice(device_name)
        if not device: return None
        return device.getProperty(prop_name)

    def _set_connection_state(self, device_name, state):
        device = self.client.getDevice(device_name)
        if not device: return
        conn = device.getSwitch("CONNECTION")
        if conn:
            conn[0].s = PyIndi.ISS_ON if state else PyIndi.ISS_OFF
            conn[1].s = PyIndi.ISS_OFF if state else PyIndi.ISS_ON
            self.client.sendNewSwitch(conn)

    # --- Mount Methods ---
    def get_position(self):
        prop = self._get_device_prop(self.mount_name, "EQUATORIAL_EOD_COORD")
        if prop:
            ra = prop.getNumber()[0].value  # RA is usually index 0
            dec = prop.getNumber()[1].value # Dec is usually index 1
            return {'ra': ra, 'dec': dec}
        return {'ra': 0, 'dec': 0}

    def move_to(self, ra, dec):
        device = self.client.getDevice(self.mount_name)
        coords = device.getNumber("EQUATORIAL_EOD_COORD")
        coords[0].value = ra
        coords[1].value = dec
        self.client.sendNewNumber(coords)

    def is_slewing(self):
        prop = self._get_device_prop(self.mount_name, "EQUATORIAL_EOD_COORD")
        return prop.getState() == PyIndi.IPS_BUSY

    def set_slew_rate(self, rate_multiplier):
        """Uses TELESCOPE_MOTION_NS/WE for constant speed scanning."""
        # For SHG, we typically move East/West (RA)
        device = self.client.getDevice(self.mount_name)
        motion = device.getNumber("TELESCOPE_MOTION_RATE")
        if motion:
            motion[0].value = rate_multiplier
            self.client.sendNewNumber(motion)
            
        # Trigger the movement
        we_prop = device.getSwitch("TELESCOPE_MOTION_WE")
        we_prop[0].s = PyIndi.ISS_ON # West
        self.client.sendNewSwitch(we_prop)

    # --- Camera Methods ---
    def capture_frame(self, exposure=0.01):
        device = self.client.getDevice(self.camera_name)
        exp_prop = device.getNumber("CCD_EXPOSURE")
        exp_prop[0].value = exposure
        self.client.sendNewNumber(exp_prop)
        # Note: In a real app, we'd use a listener for the 'BLOB' (image data)
