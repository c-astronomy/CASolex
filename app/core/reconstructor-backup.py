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
            h, w = reader.frame_shape # h=83, w=4660

            # Create canvas: Height of 4660 x Number of frames
            self.reconstructed_image = np.zeros((w, frame_count), dtype=np.float32)

            # SAFETY: If slider is at 600, bring it back to the 0-82 range
            # This prevents the "Out of Bounds" crash
            safe_index = int(line_x_position) % h 

            for i in range(frame_count):
                try:
                    frame = reader.get_frame(i) # This is (83, 4660)
                    
                    # Grab one horizontal row (the solar slice)
                    # This row has all 4660 pixels of the Sun
                    self.reconstructed_image[:, i] = frame[safe_index, :]
                        
                except Exception as e:
                    print(f"Error at frame {i}: {e}")
                    break

            # Normalization with safety check
            v_min, v_max = np.percentile(self.reconstructed_image, (1, 99))
            if v_max > v_min:
                self.reconstructed_image = np.clip((self.reconstructed_image - v_min) / (v_max - v_min) * 255.0, 0, 255)
            
            return self.reconstructed_image.astype(np.uint8)
