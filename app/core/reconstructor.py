import numpy as np
import cv2
from .ser_reader import SERReader

class SHGReconstructor:
    def __init__(self, file_path):
        self.reader = SERReader(file_path)
        self.reconstructed_image = None

    def process(self, line_x_position, rotation_deg=0):
        # Create a blank canvas: Height=3056, Width=3618 frames
        # We use float32 for processing, then convert to uint8
        recon = np.zeros((self.reader.frame_width, self.reader.frame_count), dtype=np.float32)

        # Line_x_position is the row in the frame (0-127) where the spectral line is
        # Ensure it stays within the 128-pixel height
        y_coord = int(np.clip(line_x_position, 0, self.reader.frame_height - 1))

        for i in range(self.reader.frame_count):
            frame = self.reader.get_frame(i)
            # Take the entire horizontal row at our chosen wavelength
            recon[:, i] = frame[y_coord, :]

        # Apply basic normalization so it's visible
        recon = cv2.normalize(recon, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)

        # Apply Rotation if needed
        if rotation_deg != 0:
            h, w = recon.shape
            center = (w // 2, h // 2)
            M = cv2.getRotationMatrix2D(center, rotation_deg, 1.0)
            recon = cv2.warpAffine(recon, M, (w, h))

        self.reconstructed_image = recon
        return recon
