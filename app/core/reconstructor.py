import numpy as np
import cv2
from .ser_reader import SERReader # We'll need a simple SER reader

class SHGReconstructor:
    def __init__(self, file_path):
        self.file_path = file_path
        self.data = None
        self.reconstructed_image = None


    def process(self, line_x_position):
            reader = SERReader(self.file_path)
            frame_count = reader.frame_count
            height, width = reader.frame_shape

            # Initialize: (83 height x 3618 frames width)
            self.reconstructed_image = np.zeros((height, frame_count), dtype=np.float32)

            for i in range(frame_count):
                try:
                    frame = reader.get_frame(i)
                    
                    # FIX: Use 'height' (not 'hight') and ensure correct reshape
                    if frame.size == height * width:
                        frame = frame.reshape((height, width))
                    
                    # Sample the vertical column correctly
                    self.reconstructed_image[:, i] = frame[:, line_x_position]
                        
                except Exception as e:
                    print(f"Error at frame {i}: {e}")
                    break

            # Normalize 12-bit data so it's not black
            img_min, img_max = np.min(self.reconstructed_image), np.max(self.reconstructed_image)
            if img_max > img_min:
                self.reconstructed_image = (self.reconstructed_image - img_min) / (img_max - img_min) * 255.0
            
            return self.reconstructed_image.astype(np.uint8)
