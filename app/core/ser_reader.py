import os
import struct
import numpy as np

class SERReader:
    def __init__(self, file_path):
        
        
        self.file_path = file_path
        self.header_size = 178
        
        # 1. READ RAW HEADER
        with open(file_path, 'rb') as f:
            header = f.read(self.header_size)
            h_width = struct.unpack('<I', header[26:30])[0]
            h_height = struct.unpack('<I', header[30:34])[0]
            h_bitdepth = struct.unpack('<I', header[34:38])[0]
            h_frames = struct.unpack('<I', header[38:42])[0]

        # 2. CALCULATE FOOTPRINT
        file_size = os.path.getsize(file_path)
        actual_data_size = file_size - self.header_size
        self.bit_depth = h_bitdepth if h_bitdepth in [8, 16] else 16
        self.bytes_per_pixel = self.bit_depth // 8

        safe_frames = h_frames if h_frames > 0 else 1
        pixels_per_frame = actual_data_size // (safe_frames * self.bytes_per_pixel)

        # 3. AXIS STANDARDIZATION (The Fix)
        # We find the two dimensions. One is width, one is height.
        # Header values might be 0, so we use pixels_per_frame as the master.
        dim1 = h_width if h_width > 0 else 128 
        dim2 = pixels_per_frame // dim1
        
        # SHG RULE: The SHORTER axis is the Spectrum (Width).
        # The LONGER axis is the Slit (Height).
        self.width = min(dim1, dim2)
        self.height = max(dim1, dim2)

        self.frame_count = h_frames if h_frames > 0 else (actual_data_size // (self.width * self.height * self.bytes_per_pixel))
        self.frame_size = self.width * self.height * self.bytes_per_pixel
        
        print(f"--- GEOMETRY VALIDATED ---")
        print(f"File: {os.path.basename(file_path)}")
        print(f"Detected: {self.width}w (Spectral) x {self.height}h (Spatial/Slit)")
        print(f"Frames: {self.frame_count} | Bit-Depth: {self.bit_depth}-bit")
        print(f"--------------------------")




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
