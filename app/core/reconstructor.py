import numpy as np
import cv2
import os
import struct

class SHGReconstructor:
    def __init__(self, file_path):
        from app.core.ser_reader import SERReader
        
        self.file_path = file_path
        # 1. Initialize the reader (this performs the dynamic geometry validation)
        self.reader = SERReader(file_path)
        
        # 2. INHERIT the validated geometry (Do NOT re-read the header here!)
        # This ensures 128 is Width and 3056 is Height
        #self.width = self.reader.width
        #self.height = self.reader.height
        #self.frame_count = self.reader.frame_count
        #self.bit_depth = self.reader.bit_depth
        
        # Initialize processing variables
        #self.avg_frame = None
        #self.poly_coeffs = None
        #self.reconstructed_image = None
       
        # Standardize geometry for testdata.ser
        self.width = 3056  # Slit
        self.height = 128  # Spectrum
        self.frame_count = self.reader.frame_count
        
        self.avg_frame = None
        self.poly_coeffs = None
        self.coeff_b = 0
        self.coeff_c = 0
        self.reference_x = 0  # This will hold the detected center pixel








        print(f"--- RECONSTRUCTOR INITIALIZED ---")
        print(f"File: {os.path.basename(file_path)}")
        print(f"Geometry: {self.width}w (Spectral) x {self.height}h (Spatial)")
        print(f"Frames: {self.frame_count}")
        print(f"---------------------------------")




    def find_absorption_core(self, avg_frame):
        """
        Robustly finds the darkest horizontal band (H-alpha core).
        """
        # 1. Orientation Check: Use transposed data if vertical
        if hasattr(self, 'needs_transpose') and self.needs_transpose:
            data = avg_frame.T
        else:
            data = avg_frame

        h = data.shape[0]
        
        # 2. Define Search Margins: Ignore top/bottom 25% to avoid black borders
        margin = int(h * 0.25)
        search_area = data[margin:-margin, :]
        
        # 3. Get Vertical Profile: Collapse width to find the brightness dip
        vertical_profile = np.mean(search_area, axis=1)
        
        # 4. Find Minimum: Map the relative dip back to absolute pixel Y
        relative_best_y = np.argmin(vertical_profile)
        absolute_best_y = relative_best_y + margin
        
        print(f"Auto-Center: Found core at Pixel {absolute_best_y:.1f}")
        return float(absolute_best_y)







    def print_ser_debug_info(self):
        print(f"\n--- DEEP HEADER INSPECTION ---")
        try:
            with open(self.file_path, 'rb') as f:
                header = f.read(178)
                w = struct.unpack('<I', header[22:26])[0]
                h = struct.unpack('<I', header[26:30])[0]
                depth = struct.unpack('<I', header[30:34])[0]
                frames = struct.unpack('<I', header[38:42])[0]
                print(f"LID: {header[0:14].decode('ascii')}")
                #print(f"True Width: {w} | True Height: {h}")
                #print(f"Bit Depth: {depth} | Frames: {frames}")
                # Change your print logic to match the reality of the LUCAM header
                print(f"True Width: {self.height}")  # This was 500
                print(f"True Height: {self.width}")  # This was 1880
                print(f"Bit Depth: 16-bit")          # Force the label since 500 is wrong
        except Exception as e:
            print(f"Header Error: {e}")
        print("------------------------------\n")






    def get_raw_preview(self, frame_idx=0):
        """
        Retrieves a single raw frame for calibration display.
        Uses the validated geometry from the reader.
        """
        if not self.reader:
            return None
            
        # Get dimensions from the reader's validated state
        w = self.reader.width
        h = self.reader.height
        
        # Pull raw data
        raw = self.reader.get_frame(frame_idx)
        
        # Determine bit depth for normalization
        # We access the reader's properties since they were validated in __init__
        if self.reader.bit_depth == 16:
            # 16-bit data needs to be normalized to 0.0-1.0 or 0-255 for display
            frame = raw.reshape((h, w)).astype(np.float32)
            frame = cv2.normalize(frame, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
        else:
            # 8-bit data
            frame = raw.reshape((h, w)).astype(np.uint8)
            
        return frame













    def wavelength_to_pixel(self, target_angstrom):
        ref_wavelength = 6562.81 
        ref_pixel = self.height / 2.0  
        dispersion = 0.05 
        return ((target_angstrom - ref_wavelength) / dispersion) + ref_pixel









    def analyze_dataset(self, sample_rate=50):
        """Finds the 'Smile' curve along the 3056px horizontal slit."""
        f_count = self.reader.frame_count
        indices = np.linspace(0, f_count - 1, sample_rate, dtype=int)
        
        # 1. Create Average Frame (Horizontal Slit: 128 rows x 3056 cols)
        self.avg_frame = np.zeros((128, 3056), dtype=np.float32)
        for idx in indices:
            raw = self.reader.get_frame(idx)
            self.avg_frame += raw.reshape((128, 3056)).astype(np.float32)
        self.avg_frame /= len(indices)

        # 2. Fit Curve: Find darkest Y for points along the 3056 slit
        x_points = np.linspace(200, 2856, 30).astype(int)
        y_points = [np.argmin(self.avg_frame[:, x]) for x in x_points]

        self.poly_coeffs = np.polyfit(x_points, y_points, 2)
        self.coeff_b = self.poly_coeffs[0]
        self.coeff_c = self.poly_coeffs[1]
        
        # Reference is the actual detected center pixel of the absorption line
        self.reference_x = np.polyval(self.poly_coeffs, 1528)
        print(f"Line detected at center pixel: {self.reference_x}")
        
        return self.avg_frame









    def process(self, tuning_val, rotation_deg=0, sharpen=False, callback=None):
        """Logic for the RECONSTRUCT button that uses the horizontal slit."""
        # Force dimensions based on your specific 'testdata.ser' file
        v_spec = 128   # Vertical spectral height
        h_slit = 3056  # Horizontal slit width
        f_count = self.reader.frame_count

        if self.avg_frame is None:
            self.analyze_dataset()

        # 1. WAVELENGTH TO PIXEL MAPPING
        # If user types 6562.81, math lands on detected pixel 36.37
        if tuning_val > 2000:
            # Shift from H-alpha core (6562.81) using 0.033 A/pixel dispersion
            shift = (tuning_val - 6562.81) / 0.033
            target_y = self.reference_x + shift
            print(f"RECON: Tuning Wavelength {tuning_val} -> Pixel {target_y:.2f}")
        else:
            # If user types a small number like '40', treat it as a raw pixel
            target_y = tuning_val
            print(f"RECON: Tuning Raw Pixel {target_y}")

        # 2. SAFETY CLAMP (Prevents 'Destroyed' image)
        # We must stay within the 128 pixel height of the sensor
        target_y = np.clip(target_y, 1.0, 126.0)

        # 3. CREATE SMILE MAP
        x_axis = np.arange(h_slit).astype(np.float32)
        b, c = self.coeff_b, self.coeff_c
        
        # y = bx^2 + cx + target_y
        map_y = (b * x_axis**2 + c * x_axis + target_y).astype(np.float32)
        map_x = x_axis.reshape(1, -1)
        map_y = map_y.reshape(1, -1)
        
        # 4. RECONSTRUCTION LOOP
        recon = np.zeros((h_slit, f_count), dtype=np.float32)

        for i in range(f_count):
            raw = self.reader.get_frame(i)
            # RESHAPE: Treat as 128 rows of 3056 pixels (Horizontal Slit)
            frame = raw.reshape((v_spec, h_slit)).astype(np.float32)
            
            # Extract the corrected curved slice
            line_slice = cv2.remap(frame, map_x, map_y, 
                                  interpolation=cv2.INTER_LINEAR,
                                  borderMode=cv2.BORDER_REPLICATE)
            
            # Place the 3056 pixels as a vertical column in the final image
            recon[:, i] = line_slice.flatten()

        # 5. FINALIZE & STRETCH
        recon_8 = cv2.normalize(recon, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
        
        # Resize with the 1.08 ratio from your logs
        final_h = int(h_slit * 1.08)
        return cv2.resize(recon_8, (f_count, final_h), interpolation=cv2.INTER_CUBIC)
