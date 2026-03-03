import os
import struct
import numpy as np

class SERReader:
    def __init__(self, file_path):
        self.file_path = file_path
        self.header_size = 178
        # Hard-coded from your specific log file data
        self.frame_width = 3056 
        self.frame_height = 128
        self.frame_count = 3618
        self.bytes_per_pixel = 1 # MONO 8-bit
        self.bytes_per_frame = self.frame_width * self.frame_height
        self.frame_shape = (self.frame_height, self.frame_width)

    def get_frame(self, index):
        offset = self.header_size + (index * self.bytes_per_frame)
        # Read the 1D array of bytes
        data = np.fromfile(self.file_path, dtype=np.uint8, 
                          count=self.bytes_per_frame, 
                          offset=offset)
        # Reshape into a 2D frame (128 rows, 3056 columns)
        return data.reshape(self.frame_shape)
