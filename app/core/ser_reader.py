import numpy as np
import os
import struct

class SERReader:
    def __init__(self, file_path):
        self.file_path = file_path
        self.header_size = 178 # Standard SER header size
        self.read_header()

#    def read_header(self):
#            with open(self.file_path, 'rb') as f:
#                raw_header = f.read(64)
#                print(f"HEADER HEX: {raw_header.hex(' ', 4)}")


#    def read_header(self):
#            with open(self.file_path, 'rb') as f:
#                # Width is at 14 (4 bytes)
#                f.seek(14)
#                self.frame_width = int.from_bytes(f.read(4), 'little')
#                
#                # Height is at 18 (4 bytes)
#                f.seek(18)
#                self.frame_height = int.from_bytes(f.read(4), 'little')
#                
#                # Frame count is at 38 (4 bytes)
#                f.seek(38)
#                self.frame_count = int.from_bytes(f.read(4), 'little')
#                
#                # Byte depth is at 22 (4 bytes) -> Important for frame_size!
#                f.seek(22)
#                pixel_depth_id = int.from_bytes(f.read(4), 'little')
#                # If ID is 0-5 it's 8-bit, if 6-11 it's 16-bit
#                self.bytes_per_pixel = 2 if pixel_depth_id >= 6 else 1
#                
#            self.frame_shape = (self.frame_height, self.frame_width)
#            self.frame_size = self.frame_width * self.frame_height * self.bytes_per_pixel


    def read_header(self):
            file_size = os.path.getsize(self.file_path)
            with open(self.file_path, 'rb') as f:
                data = f.read(42)
                
                self.frame_width = struct.unpack('<I', data[14:18])[0]
                self.frame_height = struct.unpack('<I', data[18:22])[0]
                self.frame_count = struct.unpack('<I', data[38:42])[0]
                
                pixel_depth_id = struct.unpack('<I', data[22:26])[0]
                self.bytes_per_pixel = 2 if pixel_depth_id >= 6 else 1

            # --- SMART AUTO-DETECTION ---
            if self.frame_height == 0:
                print("Height is 0 in header. Calculating based on file size...")
                # Total Data = FileSize - Header(178) - Trailer(maybe 0)
                data_size = file_size - 178
                # Height = DataSize / (Width * Frames * BytesPerPixel)
                calculated_height = data_size // (self.frame_width * self.frame_count * self.bytes_per_pixel)
                self.frame_height = int(calculated_height)
                print(f"Calculated Height: {self.frame_height}")

            self.frame_shape = (self.frame_height, self.frame_width)
            self.frame_size = self.frame_width * self.frame_height * self.bytes_per_pixel






    def get_frame(self, index):
            offset = self.header_size + (index * self.frame_size)
            # Use <u2 for 16-bit, u1 for 8-bit
            dtype = '<u2' if self.bytes_per_pixel == 2 else 'u1'
            
            data = np.memmap(self.file_path, dtype=dtype, mode='r', 
                            offset=offset, shape=self.frame_shape)
            return data.copy()
