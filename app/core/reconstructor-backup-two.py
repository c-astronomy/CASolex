import numpy as np
import cv2
from .ser_reader import SERReader


class SHGReconstructor:
    def __init__(self, file_path):
        self.reader = SERReader(file_path)
        self.reconstructed_image = None


    def wavelength_to_pixel(self, target_angstrom):
        # Data from your specific log:
        ref_wavelength = 6562.81  # H-alpha core in Angstroms
        ref_pixel = 105.8457      # The 'd' coefficient from your log
        
        # Typical SHG scale (This varies by setup, usually ~0.02 - 0.1 A/pixel)
        # You can tune this 'dispersion' value until 6563.3 gives you the red wing
        dispersion = 0.05 
        
        pixel_coord = ((target_angstrom - ref_wavelength) / dispersion) + ref_pixel
        return pixel_coord



    def process(self, line_offset, rotation_deg=0, callback=None):
        # Data from your log
        width = 3056
        frames = 3618
        
        # Polynomial Coefficients from your specific scan
        # ax^2 + bx + c (Note: 'a' was 0 in your log, so we use b, c, d)
        coeff_b = 3.350568650591704E-5
        coeff_c = -0.09713130267097969
        coeff_d = 105.84569818285735
        
        # Create canvas
        recon = np.zeros((width, frames), dtype=np.float32)

        # Apply the curve correction

        for i in range(frames):
                frame = self.reader.get_frame(i).astype(np.float32)
                
                for x in range(width):
                    user_shift = line_offset - coeff_d
                    target_y = (coeff_b * x**2) + (coeff_c * x) + coeff_d + user_shift
                    
                    # --- SUB-PIXEL INTERPOLATION ---
                    # We extract a 1x1 pixel area centered at the exact float coordinate
                    # This eliminates the "banding" layers by blending pixels
                    pixel_value = cv2.getRectSubPix(frame, (1, 1), (float(x), float(target_y)))
                    recon[x, i] = pixel_value[0, 0]

# --- THE LIVE SCAN UPDATE ---
                # Update the UI every 50 frames so it looks smooth but fast
                if callback and i % 50 == 0:
                    callback(frame, i)


        #Test to make view edit image save as well
        #self.current_recon_data = recon


        # Contrast Enhancement (Crucial for H-alpha details)
        recon = cv2.normalize(recon, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
        
        # Apply the 1.08 Aspect Ratio Stretch from the log
        final_h = int(width * 1.08)
        recon = cv2.resize(recon, (frames, final_h), interpolation=cv2.INTER_CUBIC)

        self.reconstructed_image = recon
        return recon
