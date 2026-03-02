import struct
import os
import numpy as np
from datetime import datetime

class SERWriter:
    def __init__(self):
        self.file = None
        self.frame_count = 0
        self.width = 0
        self.height = 0
        self.bit_depth = 0
        self.header_size = 178 # Standard SER header size

    def open(self, filename, width, height, bit_depth=16, mono=True):
        """Initializes the SER file and writes the placeholder header."""
        self.width = width
        self.height = height
        self.bit_depth = bit_depth
        self.frame_count = 0
        
        # Color ID: 0=Mono, 8=BayerRGGB (Common for solar)
        color_id = 0 if mono else 8 
        
        self.file = open(filename, 'wb')
        
        # Create Header (Lucam v3 format)
        # Format string: 14s (FileID), I (LuID), I (ColorID), I (LittleEndian), 
        # I (Width), I (Height), I (BitDepth), I (FrameCount), ... and so on.
        header = bytearray(self.header_size)
        struct.pack_into('14s', header, 0, b'LUCAM-RECORDER')
        struct.pack_into('I', header, 14, 0)           # LuID
        struct.pack_into('I', header, 18, color_id)    # ColorID
        struct.pack_into('I', header, 22, 0)           # LittleEndian (0=Little)
        struct.pack_into('I', header, 26, width)
        struct.pack_into('I', header, 30, height)
        struct.pack_into('I', header, 34, bit_depth)
        struct.pack_into('I', header, 38, 0)           # FrameCount (placeholder)
        
        # Observer/Instrument/Device info
        struct.pack_into('40s', header, 42, b'PySolex SHG')
        struct.pack_into('40s', header, 82, b'Python Acquisition')
        struct.pack_into('40s', header, 122, b'SHG-Scan')
        
        # Timestamp (placeholder for start time)
        now = datetime.now()
        # SER uses a specific Date/Time format; for now, we leave as 0 or simplified
        
        self.file.write(header)

    def add_frame(self, frame_data):
        """
        Appends a raw frame to the file.
        frame_data: a 1D or 2D numpy array (uint8 or uint16)
        """
        if self.file:
            # Ensure the data is in the correct byte order (Little Endian)
            self.file.write(frame_data.tobytes())
            self.frame_count += 1

    def close(self):
        """Updates the frame count in the header and closes the file."""
        if self.file:
            # Go back to the FrameCount position (byte 38)
            self.file.seek(38)
            self.file.write(struct.pack('I', self.frame_count))
            
            # Optional: Add trailer with timestamps here (advanced)
            
            self.file.close()
            self.file = None
            print(f"SER file finalized with {self.frame_count} frames.")
