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
        self.width = self.reader.width
        self.height = self.reader.height
        self.frame_count = self.reader.frame_count
        self.bit_depth = self.reader.bit_depth
        
        # Initialize processing variables
        self.avg_frame = None
        self.poly_coeffs = None
        self.reconstructed_image = None
        
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
        print("\n--- DEBUG: ANALYZING DATASET (DYNAMIC AXIS ALIGNMENT) ---")
        
        # FORCE alignment with the reader's validated "Truth"
        self.width = self.reader.width   # 128
        self.height = self.reader.height # 3056
        
        w, h = self.width, self.height
        print(f"Confirmed: {w}w (Spectral) x {h}h (Spatial/Slit)")
        
        indices = np.linspace(0, self.frame_count - 1, sample_rate, dtype=int)
        avg_buffer = np.zeros((h, w), dtype=np.float32)
        
        for idx in indices:
            frame_raw = self.reader.get_frame(idx)
            # Use (h, w) order: (3056, 128)
            avg_buffer += frame_raw.reshape((h, w)).astype(np.float32)
            
        self.avg_frame = avg_buffer / len(indices)

        # CURVE FITTING
        clean_avg = cv2.GaussianBlur(self.avg_frame, (5, 5), 0)
        y_points, x_points = [], []
        
        # Scan along the LONG axis (3056)
        for y in range(int(h * 0.1), int(h * 0.9), 10):
            # Find dip on the SHORT axis (128)
            x_val = np.argmin(clean_avg[y, :])
            if 0 < x_val < w:
                x_points.append(x_val)
                y_points.append(y)

        self.poly_coeffs = np.polyfit(y_points, x_points, 2)
        self.coeff_a, self.coeff_b, self.coeff_c = self.poly_coeffs
        self.reference_x = np.polyval(self.poly_coeffs, h // 2)
        
        return self.avg_frame














    def process(self, tuning_val, rotation_deg=0, sharpen=False, callback=None):
        """
        Builds the solar image by meshing vertical slit columns.
        Corrects for 'Smile' distortion and handles dynamic geometry.
        """
        # 1. Safety Check: Ensure analysis has run
        if self.avg_frame is None:
            self.analyze_dataset()

        # IMPORTANT: Use the dimensions validated by the Reader
        w = self.reader.width   # Spectral (Short) axis
        h = self.reader.height  # Spatial (Long) axis
        f = self.reader.frame_count

        print(f"\n--- DEBUG: RECONSTRUCTION START ---")
        print(f"Verified Slit Height: {h} | Spectral Width: {w}")
        
        # 2. WAVELENGTH TO PIXEL MAPPING
        if tuning_val > 2000:
            # Standard dispersion math for H-Alpha
            target_x = (w / 2) + (tuning_val - 6562.81) / 0.033
        else:
            target_x = tuning_val
            
        # SAFETY FIX: Prevent out-of-bounds sampling (e.g., the 128.00 bug)
        # Pixel indices must be between 0 and (width - 1)
        target_x = max(0.0, min(float(target_x), float(w - 1.0)))
            
        print(f"Target Spectral X: {target_x:.2f}")

        # 3. ASPECT RATIO (Round Sun Fix)
        # Use 0.75 for tall slit (LUCAM) and 1.0 for wide slit (ZWO)
        ratio = getattr(self, 'xy_ratio', 0.75 if h > 1000 else 1.0)
        target_w = int(f * ratio)

        # 4. VERTICAL SAMPLING MAP (The Mesh Logic)
        y_axis = np.arange(h).astype(np.float32)
        # Calculate where the spectral line center is for every Y pixel
        curve_x = np.polyval(self.poly_coeffs, y_axis)
        shift = target_x - self.reference_x
        
        # map_x: Maps the curved absorption line to a straight vertical line
        map_x = (curve_x + shift).astype(np.float32).reshape(-1, 1)
        # map_y: Keeps the spatial position linear
        map_y = y_axis.reshape(-1, 1)
        
        # 5. INITIALIZE CANVAS
        # Height is 'h' (3056/3840), Width is frame count 'f'
        recon = np.zeros((h, f), dtype=np.float32)

        # 6. EXTRACTION LOOP
        for i in range(f):
            raw = self.reader.get_frame(i)
            
            # Reshape into Slit x Spectrum: (h, w)
            # This aligns with the (3056, 128) data layout
            frame = raw.reshape((h, w)).astype(np.float32)
            
            # Extract the corrected vertical column
            line_slice = cv2.remap(frame, map_x, map_y, 
                                  interpolation=cv2.INTER_LINEAR,
                                  borderMode=cv2.BORDER_CONSTANT,
                                  borderValue=0)
            
            # Insert the slice as a column in the final image
            recon[:, i] = line_slice.flatten()

            if callback and i % 500 == 0:
                callback(frame, i)

        # 7. NORMALIZE & RESIZE
        # Convert 32-bit float data to 8-bit image
        recon_8 = cv2.normalize(recon, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
        
        # Resize adjusts the horizontal 'f' dimension to create a round disk
        final_sun = cv2.resize(recon_8, (target_w, h), interpolation=cv2.INTER_CUBIC)

        # 8. POST-PROCESSING (Rotation & Sharpening)
        if rotation_deg != 0:
            if rotation_deg == 90:
                final_sun = cv2.rotate(final_sun, cv2.ROTATE_90_CLOCKWISE)
            elif rotation_deg == 180:
                final_sun = cv2.rotate(final_sun, cv2.ROTATE_180)
            elif rotation_deg == 270:
                final_sun = cv2.rotate(final_sun, cv2.ROTATE_90_COUNTERCLOCKWISE)

        if sharpen:
            # Simple Unsharp Mask
            gaussian = cv2.GaussianBlur(final_sun, (0, 0), 2.0)
            final_sun = cv2.addWeighted(final_sun, 1.5, gaussian, -0.5, 0)

        print(f"Reconstruction Finished. Output Size: {final_sun.shape[1]}x{final_sun.shape[0]}")
        self.reconstructed_image = final_sun
        return final_sun
