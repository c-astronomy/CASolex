import os
import struct
import numpy as np

class SERReader:
    def __init__(self, file_path):
        self.file_path = file_path
        self.header_size = 178
        
        # 1. READ RAW HEADER BYTES
        with open(file_path, 'rb') as f:
            header = f.read(self.header_size)
            
            # Extract standard SER fields using Little-Endian format
            h_width = struct.unpack('<I', header[26:30])[0]
            h_height = struct.unpack('<I', header[30:34])[0]
            h_bitdepth = struct.unpack('<I', header[34:38])[0]
            h_frames = struct.unpack('<I', header[38:42])[0]

        # 2. AUTO-CORRECT GEOMETRY
        # Check for the "New Data" bug: Width is 0 but Height is 3840
        if h_width == 0 and h_height == 3840:
            self.width = 3840
            self.height = 200  # Force correct height for the 3840x200 dataset
            self.bit_depth = 16 # New data is 16-bit
            print(f"--- FORCING NEW DATA GEOMETRY: {self.width}x{self.height} ---")
            
        # Check for "Old Data" Format
        elif h_width == 3056:
            self.width = 3056
            self.height = 128
            self.bit_depth = 8   # Old data is 8-bit
            print(f"--- FORCING OLD DATA GEOMETRY: {self.width}x{self.height} ---")
            
        else:
            # Fallback for standard files
            self.width = h_width
            self.height = h_height
            self.bit_depth = h_bitdepth if h_bitdepth in [8, 16] else 16

        # 3. SET CALCULATED PROPERTIES
        self.frame_count = h_frames
        self.bytes_per_pixel = self.bit_depth // 8
        self.frame_size = self.width * self.height * self.bytes_per_pixel
        
        print(f"Initialized: {self.width}x{self.height}, {self.bit_depth}-bit, {self.frame_count} frames")

    def get_frame(self, frame_index):
        """Reads a specific frame and returns a 1D array of pixels."""
        # Calculate dynamic offset based on our corrected geometry
        offset = self.header_size + (frame_index * self.frame_size)
        
        try:
            with open(self.file_path, 'rb') as f:
                f.seek(offset)
                data = f.read(self.frame_size)
                
            if not data or len(data) < self.frame_size:
                # Return zeros if we hit the end of the file unexpectedly
                return np.zeros(self.width * self.height, dtype=np.uint16)

            # 4. FIX NOISE (ENDIANNESS)
            if self.bit_depth == 16:
                # '<u2' forces Little-Endian, fixing the salt-and-pepper noise
                return np.frombuffer(data, dtype='<u2')
            else:
                # Standard 8-bit for old data
                return np.frombuffer(data, dtype='u1')
                
        except Exception as e:
            print(f"Reader Error at frame {frame_index}: {e}")
            return np.zeros(self.width * self.height, dtype=np.uint16)
