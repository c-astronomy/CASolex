import numpy as np
import cv2
import os
import struct

class SHGReconstructor:
    def __init__(self, file_path):
        from app.core.ser_reader import SERReader
        
        self.file_path = file_path
        self.reader = SERReader(file_path)
        
        # 1. DEEP HEADER READ: Pull the truth directly from the file bytes
        try:
            with open(file_path, 'rb') as f:
                header = f.read(178)
                h_width = struct.unpack('<I', header[26:30])[0]
                h_height = struct.unpack('<I', header[30:34])[0]
                h_frames = struct.unpack('<I', header[38:42])[0]
        except Exception as e:
            print(f"Header extraction failed: {e}")
            h_width, h_height, h_frames = 0, 0, 0

        # 2. DYNAMIC GEOMETRY: Fixes the 'Scramble'
        self.width = h_width if h_width > 0 else 3840
        self.height = h_height if h_height > 0 else 200
        
        # 3. BIT-DEPTH DETECTION: Fixes the 'Black Wall'
        file_size = os.path.getsize(file_path)
        data_size = file_size - 178
        
        if h_frames > 0:
            self.frame_count = h_frames
            self.bytes_per_pixel = data_size // (self.width * self.height * h_frames)
        else:
            self.bytes_per_pixel = 2
            self.frame_count = data_size // (self.width * self.height * 2)

        # Update reader properties for the viewer
        self.reader.width = self.width
        self.reader.height = self.height
        self.reader.frame_count = self.frame_count
        self.reader.bit_depth = self.bytes_per_pixel * 8

        # 4. DEFAULT PARAMETERS (Will be overwritten by analyze_dataset)
        self.coeff_b = 0.0
        self.coeff_c = 0.0
        #self.xy_ratio = 0.93  # Baseline ratio from your logs
        #self.xy_ratio = 0.93  # Baseline ratio from your logs
      # Use 0.04 for vertical data (3056 high), or 1.0 for horizontal data
        self.xy_ratio = 0.04 if self.height > self.width else 1.0 



        print(f"--- RECONSTRUCTOR INITIALIZED ---")
        print(f"File: {os.path.basename(file_path)}")
        print(f"Resolution: {self.width}x{self.height}")
        print(f"Frames: {self.frame_count} ({self.reader.bit_depth}-bit)")
        print(f"---------------------------------")



    def analyze_dataset(self, sample_rate=50):
            """
            Full method to detect orientation and spectral curvature.
            Returns the processed average frame for the UI preview.
            """
            # 1. GENERATE RAW AVERAGE
            indices = np.linspace(0, self.frame_count - 1, sample_rate, dtype=int)
            avg_buffer = np.zeros((self.height, self.width), dtype=np.float32)
            
            for idx in indices:
                frame_raw = self.reader.get_frame(idx)
                if self.bytes_per_pixel == 2:
                    frame_raw = frame_raw.byteswap()
                avg_buffer += frame_raw.reshape((self.height, self.width)).astype(np.float32)
                
            avg_frame = avg_buffer / len(indices)

            # 2. ORIENTATION DETECTION
            # We compare horizontal vs vertical variance to detect vertical 'barcodes'
            if np.var(np.mean(avg_frame, axis=0)) > np.var(np.mean(avg_frame, axis=1)):
                print("Detected VERTICAL spectral lines. Transposing for analysis...")
                # Flip the data so the math sees a horizontal line
                analysis_frame = avg_frame.T 
                self.needs_transpose = True
                curr_w, curr_h = self.height, self.width
            else:
                analysis_frame = avg_frame
                self.needs_transpose = False
                curr_w, curr_h = self.width, self.height

            # 3. CURVE FITTING ON THE CORRECTED FRAME
            clean_avg = cv2.GaussianBlur(analysis_frame, (5, 5), 0)
            
            y_points = []
            x_points = []
            
            # Sample the center 80% of the corrected width
            for x in range(int(curr_w * 0.1), int(curr_w * 0.9)):
                y_val = np.argmin(clean_avg[:, x])
                if 0 < y_val < curr_h:
                    y_points.append(y_val)
                    x_points.append(x)

            # Lock the polynomial coefficients for the process loop
            self.poly_coeffs = np.polyfit(x_points, y_points, 2)
            
            # Lock the reference point for the tuning slider
            self.reference_y = np.polyval(self.poly_coeffs, curr_w // 2)

            self.avg_frame = analysis_frame



            # Return the corrected frame so the 'Scan data' preview looks horizontal
            return analysis_frame


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

    def get_raw_preview(self, frame_index=0):
        frame = self.reader.get_frame(frame_index)
        if self.bytes_per_pixel == 2:
            frame = frame.byteswap()
        return cv2.normalize(frame, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)

    def wavelength_to_pixel(self, target_angstrom):
        ref_wavelength = 6562.81 
        ref_pixel = self.height / 2.0  
        dispersion = 0.05 
        return ((target_angstrom - ref_wavelength) / dispersion) + ref_pixel




    def process(self, tuning_val, rotation_deg=0, sharpen=False, callback=None):
            """Vectorized reconstruction handling dynamic sensor sizes and units."""
            # 1. ORIENTATION & UNIT LOGIC
            if hasattr(self, 'needs_transpose') and self.needs_transpose:
                sampling_w, sampling_h = self.height, self.width
            else:
                sampling_w, sampling_h = self.width, self.height
                
            # Unit Logic: Large number = Angstroms, Small number = Pixels
            if tuning_val > 2000:
                center_y = sampling_h / 2
                pixel_y_target = center_y + (tuning_val - 6562.81) / 0.033
            else:
                pixel_y_target = tuning_val

            # 2. VECTORIZED MAP CALCULATION
            f = self.frame_count
            # xy_ratio needs to be very small (~0.04) for vertical data!
            target_h = int(f * self.xy_ratio)
            
            base_curve = np.polyval(self.poly_coeffs, np.arange(sampling_w))
            user_shift = pixel_y_target - getattr(self, 'reference_y', sampling_h / 2)
            target_y_coords = (base_curve + user_shift).astype(np.float32)
            
            map_x = np.arange(sampling_w).astype(np.float32).reshape(1, -1)
            map_y = target_y_coords.reshape(1, -1)
            
            recon = np.zeros((sampling_w, f), dtype=np.float32)

            # 3. FAST EXTRACTION LOOP
            for i in range(f):
                raw_data = self.reader.get_frame(i)
                
                if self.bytes_per_pixel == 2:
                    frame = raw_data.byteswap().view(np.uint16).reshape((self.height, self.width)).astype(np.float32)
                else:
                    frame = raw_data.reshape((self.height, self.width)).astype(np.float32)

                if hasattr(self, 'needs_transpose') and self.needs_transpose:
                    frame = frame.T

                line_data = cv2.remap(frame, map_x, map_y, interpolation=cv2.INTER_LINEAR)
                recon[:, i] = line_data.flatten()

                if callback and i % 100 == 0:
                    callback(frame, i)

            # 4. NORMALIZATION & RESIZE
            recon = cv2.normalize(recon, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
            final_img = cv2.resize(recon, (f, target_h), interpolation=cv2.INTER_CUBIC)
            
            return final_img
