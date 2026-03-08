import cv2
import sys
import pyqtgraph as pg
import numpy as np
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QPushButton, QLabel, QGroupBox, QComboBox, 
                             QLineEdit, QFormLayout, QStatusBar, QTabWidget, QFileDialog,
                             QSlider)
from PySide6.QtCore import Qt, QThread, Signal

# Internal Imports
from app.hardware.manager import HardwareManager
from app.core.scanner import SHGScanner
from .video_worker import VideoWorker
from app.core.reconstructor import SHGReconstructor

class ScanThread(QThread):
    status_update = Signal(str)
    finished = Signal()

    def __init__(self, scanner, margin, speed, rewind, dry_run=False):
        super().__init__()
        self.scanner = scanner
        self.margin = margin
        self.speed = speed
        self.rewind = rewind
        self.dry_run = dry_run

    def run(self):
        mode = "Preview" if self.dry_run else "Capture"
        self.status_update.emit(f"{mode} Scan Started...")
        self.scanner.run_scan(self.margin, self.speed, self.rewind, self.dry_run)
        self.status_update.emit(f"{mode} Finished.")
        self.finished.emit()

class PySolexUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PySolex - Acquisition & Processing")
        self.resize(1200, 800)

        self.hw = HardwareManager()
        
        # Main Tab Widget
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        # Create the two main tabs
        self.acq_tab = QWidget()
        self.proc_tab = QWidget()
        
        self.tabs.addTab(self.acq_tab, "1. Solar Acquisition")
        self.tabs.addTab(self.proc_tab, "2. Image Reconstruction")

        self.setup_acquisition_tab()
        self.setup_processing_tab()

        # Status Bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        self.sun_view.getView().scene().sigMouseClicked.connect(self.on_sun_clicked)





    def run_composite_reconstruction(self):
            try:
                self.status_bar.showMessage("Starting Composite: Step 1/2 (Photosphere)...")
                # Step 1: Reconstruct the Photosphere (6560.0)
                pixel_6562 = self.reconstructor.wavelength_to_pixel(6562.81)
                photo_data = self.reconstructor.process(pixel_6562, rotation_deg=self.rotation_slider.value())

                self.status_bar.showMessage("Starting Composite: Step 2/2 (Chromosphere)...")
                # Step 2: Reconstruct the Chromosphere (6563.0)
                pixel_6563 = self.reconstructor.wavelength_to_pixel(6563.0)
                chromo_data = self.reconstructor.process(pixel_6563, rotation_deg=self.rotation_slider.value())

                # Step 3: Blend them (50/50 mix)
                # You can adjust the weights (0.5, 0.5) to favor one layer
                composite = cv2.addWeighted(photo_data, 0.5, chromo_data, 0.5, 0)

                # Step 4: Save to the class and update UI
                self.current_recon_data = composite
                #self.apply_visual_filters()
                self.sun_view.setImage(self.current_recon_data, autoLevels=True)   




                self.status_bar.showMessage("Composite Reconstruction Complete!")

            except Exception as e:
                self.status_bar.showMessage(f"Composite Error: {e}")







    def update_scan_preview(self, frame, frame_idx):
            # 1. Prepare data
            data = frame.T.astype(np.float32)
            avg_brightness = np.mean(data) # Check how much light is in the slit
            
            # 2. Logic to "Lock" the display levels
            # If we haven't locked levels yet AND we see enough light (e.g. > 10)
            # Or if it's just the very first frame to get the shape right
            if not hasattr(self, 'levels_locked') or frame_idx == 0:
                self.spectrum_view.setImage(data, autoLevels=True)
                self.spectrum_view.getView().setAspectLocked(False)
                self.spectrum_view.autoRange()
                
                # Only "Lock" the levels once we are sure we are looking at the Sun
                # (Adjust '10' based on your camera's dark noise)
                if avg_brightness > 10: 
                    self.current_levels = self.spectrum_view.getHistogramWidget().getLevels()
                    self.levels_locked = True 
            else:
                # Once locked, we use the same levels for the rest of the scan
                # This keeps the H-alpha line stable and prevents over-exposure
                self.spectrum_view.setImage(data, autoLevels=False, levels=self.current_levels)

            # 3. Standard UI updates
            self.status_bar.showMessage(f"Scanning: Frame {frame_idx} (Brightness: {avg_brightness:.1f})")
            if hasattr(self, 'progress_bar'):
                self.progress_bar.setValue(frame_idx)
                
            from PySide6.QtWidgets import QApplication
            QApplication.processEvents()










#    def update_scan_preview(self, frame, frame_idx):
#            # 1. Update the top window with the current raw frame
#            # We use .T to orient it horizontally like the final Sun
#            self.spectrum_view.setImage(frame.T, autoLevels=False) 
#            
#            # 2. Update the status bar to show progress
#            self.status_bar.showMessage(f"Scanning Sun... Frame {frame_idx}/3618")
#            
#            # 3. Force the UI to refresh immediately
#            from PySide6.QtWidgets import QApplication
#            QApplication.processEvents()
#







    def on_sun_clicked(self, event):
        if event.button() == Qt.LeftButton:
            view_box = self.sun_view.getView()
            pos = event.scenePos()
            
            if view_box.sceneBoundingRect().contains(pos):
                mouse_point = view_box.mapSceneToView(pos)
                
                # The X-coordinate on the Sun corresponds to the Frame Index
                frame_idx = int(mouse_point.x())
                
                # Constrain to valid frame range
                frame_idx = max(0, min(frame_idx, self.reconstructor.reader.frame_count - 1))
                
                # Load that specific raw frame and show it
                raw_frame = self.reconstructor.reader.get_frame(frame_idx)
                
                # Transpose for correct orientation and set image
                self.spectrum_view.setImage(raw_frame.T)
                self.spectrum_view.autoLevels()
                self.status_bar.showMessage(f"Viewing Raw Frame #{frame_idx}")




    def adjust_wavelength(self, delta):
        try:
            current = float(self.line_x_input.text().replace(',', '.'))
            new_val = round(current + delta, 2)
            self.line_x_input.setText(str(new_val))
            self.run_reconstruction()
        except ValueError:
            pass

    def set_preset(self, value):
        self.line_x_input.setText(str(value))
        self.run_reconstruction()





    def auto_geometry_fix(self):
            if not hasattr(self, 'reconstructor') or self.reconstructor.reconstructed_image is None:
                return

            import cv2
            import numpy as np

            # 1. Get the raw "barcode" data (3618x83)
            data = self.reconstructor.reconstructed_image
            
            # 2. Normalize and threshold to find the Sun's shape
            norm = ((data - data.min()) / (data.max() - data.min()) * 255).astype(np.uint8)
            _, thresh = cv2.threshold(norm, 30, 255, cv2.THRESH_BINARY)
            
            # 3. Find contours
            contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if not contours:
                self.status_bar.showMessage("Could not detect Sun for auto-fix.")
                return

            # 4. Fit an ellipse to the largest contour
            cnt = max(contours, key=cv2.contourArea)
            if len(cnt) < 5: return
            
            ellipse = cv2.fitEllipse(cnt)
            (xc, yc), (d1, d2), angle = ellipse # d1, d2 are diameters; angle is tilt

            # 5. Calculate the true Aspect Ratio
            # In an 83px tall image, the 'minor' axis is vertical.
            # We need the ratio to turn that 83px height into the 3618px width.
            calculated_aspect = max(d1, d2) / min(d1, d2)
            
            # 6. Update the Slider and UI
            self.ratio_slider.setValue(int(calculated_aspect * 100))
            self.update_aspect_from_slider(self.ratio_slider.value())
            
            # 7. Apply Tilt Correction (Shearing)
            # If the angle is > 1 degree, it needs a 'Shear' transform
            self.status_bar.showMessage(f"Auto-fixed: Ratio {calculated_aspect:.2f}, Tilt {angle:.1f}°")







    def update_aspect_from_slider(self, value):
            # Slider is 0-100, we need ~43.6
            aspect = value / 100  # Adjust divisor based on your slider range
            self.speed_input.setText(f"{aspect:.2f}")
            
            # This is the "Magic Wand" that stretches the barcode
            view_box = self.sun_view.getView()
            view_box.setAspectLocked(False) # Ensure this is False!
            
            # Reach into the view and stretch the 83px height
            # Height (83) * aspect = 3618 (Circular Sun)
            view_box.setYRange(0, 83 * aspect, padding=0)


    def update_rotation_label(self, value):
        self.rotation_label.setText(f"Rotation: {value}°")




    def setup_acquisition_tab(self):
        """Move your previous 'Acquisition' layout here."""
        layout = QHBoxLayout(self.acq_tab)
        
        # Sidebar & Panels
        self.sidebar = QVBoxLayout()
        self.setup_connection_panel()
        self.setup_scan_panel()
        self.sidebar.addStretch()
        
        # Live View
        self.view_panel = QVBoxLayout()
        self.setup_live_view()
        
        layout.addLayout(self.sidebar, 1)
        layout.addLayout(self.view_panel, 4)

        # Connect signals (existing)
        self.connect_btn.clicked.connect(self.toggle_connection)
        self.preview_btn.clicked.connect(lambda: self.begin_automation(dry_run=True))
        self.start_scan_btn.clicked.connect(lambda: self.begin_automation(dry_run=False))
        self.abort_btn.clicked.connect(self.handle_abort)

    def setup_processing_tab(self):
        """The new Image Processing interface."""
        layout = QHBoxLayout(self.proc_tab)
      
        # Left side: Controls


        #Load Group

        load_ser = QVBoxLayout()
        load_ser_group = QGroupBox("Load SER sequence")
        load_ser_layout = QFormLayout()

        self.load_ser_btn = QPushButton("LOAD .SER FILE")
        self.load_ser_btn.setEnabled(True)
        self.load_ser_btn.setStyleSheet("background-color: #ef6c00; color: white; font-weight: bold;")
        self.load_ser_btn.clicked.connect(self.select_ser_file)
        load_ser_layout.addRow(self.load_ser_btn)
        load_ser_group.setLayout(load_ser_layout)


        #Controls
        controls = QVBoxLayout()
        proc_group = QGroupBox("Processing Controls")
        proc_layout = QFormLayout()

       

        #self.line_x_input = QLineEdit("6562.81")
        #proc_layout.addRow("Spectral Line X:", self.line_x_input)

        self.reconstruct_btn = QPushButton("RECONSTRUCT SUN")
        self.reconstruct_btn.setEnabled(False)
        self.reconstruct_btn.setStyleSheet("background-color: #ef6c00; color: white; font-weight: bold;")
        self.reconstruct_btn.clicked.connect(self.run_reconstruction)

        # ... inside your processing layout ...
        self.ratio_slider = QSlider(Qt.Horizontal)
        self.ratio_slider.setRange(50, 200) # 0.1x to 50x
        self.ratio_slider.setValue(108)    # Default 1.0x

        
        # X-Position Slider (to tune the wavelength)
        self.x_slider = QSlider(Qt.Horizontal)
        self.x_slider.setRange(0, 3056) # Match your sensor width
        self.x_slider.setValue(656)
        self.x_slider.valueChanged.connect(self.run_reconstruction) # Re-run on move
        #self.ratio_slider.valueChanged.connect(self.update_aspect_from_slider)


# Rotation Slider (Add this near your other controls)
        #self.rotation_label = QLabel("Rotation: 0°")
        self.rotation_slider = QSlider(Qt.Horizontal)
        self.rotation_slider.setRange(-15, 15)  # Most tilts are within 15 degrees
        self.rotation_slider.setValue(0)
        self.rotation_slider.valueChanged.connect(self.update_rotation_label)
        self.rotation_slider.sliderReleased.connect(self.run_reconstruction) # Trigger rebuild

# Layout (Add to your existing layout)
        #controls.addWidget(self.rotation_label)
        #controls.addWidget(self.rotation_slider)


# --- Wavelength Control Group ---
        wave_group = QGroupBox("Wavelength Tuning (Å)")
        wave_layout = QVBoxLayout()

        # Input and Fine-Tune Row
        tune_layout = QHBoxLayout()
        self.line_x_input = QLineEdit("6562.81")  # Default to Core  Chromosphere
        #self.btn_minus = QPushButton("-0.01")
        #self.btn_plus = QPushButton("+0.01")
        #self.line_x_input_two = QLineEdit("6563")  # Default to Surface  Prothosphere
        #self.line_x_input_three = QLineEdit("6561.5")  # Default to Surface  Prothosphere

        #tune_layout.addWidget(self.btn_minus)
        tune_layout.addWidget(self.line_x_input)
        #tune_layout.addWidget(self.btn_plus)
        #tune_layout.addWidget(self.line_x_input_two)
        #tune_layout.addWidget(self.line_x_input_three)
        wave_layout.addLayout(tune_layout)

        # Quick Presets
        preset_layout = QHBoxLayout()
        #self.btn_blue_wing = QPushButton("Blue Wing")
        self.btn_core = QPushButton("H-α Core")
        #self.btn_red_wing = QPushButton("Red Wing")
        self.btn_protosphere = QPushButton("H-α Protosphere")
        self.btn_sunspot = QPushButton("H-α Sunspot")

        #self.load_ser_btn = QPushButton("LOAD")

        #preset_layout.addWidget(self.btn_blue_wing)
        preset_layout.addWidget(self.btn_core)
        #preset_layout.addWidget(self.btn_red_wing)
        preset_layout.addWidget(self.btn_protosphere)
        preset_layout.addWidget(self.btn_sunspot)
        wave_layout.addLayout(preset_layout)

        wave_group.setLayout(wave_layout)

        
        controls.addWidget(load_ser_group)
        controls.addWidget(wave_group)

        # --- Connections ---
        #self.btn_minus.clicked.connect(lambda: self.adjust_wavelength(-0.01))
        #self.btn_plus.clicked.connect(lambda: self.adjust_wavelength(0.01))
        #self.btn_blue_wing.clicked.connect(lambda: self.set_preset(6562.3))
        self.btn_core.clicked.connect(lambda: self.set_preset(6562.81))
        #self.btn_red_wing.clicked.connect(lambda: self.set_preset(6563.3))
        self.btn_protosphere.clicked.connect(lambda: self.set_preset(6563))
        self.btn_sunspot.clicked.connect(lambda: self.set_preset(6564))






        # Add this near your Reconstruct button
        #self.autofix_btn = QPushButton("AUTO-FIX GEOMETRY")
        #self.autofix_btn.clicked.connect(self.auto_geometry_fix)
        #self.autofix_btn.setStyleSheet("background-color: #512da8; color: white;")
        
        #proc_layout.addRow(self.autofix_btn)





        #I WILL HIDE THIS BUTTON FOR NOW
        # Save the view  image Button  naming is a bit backwards atm
        #self.save_edited_btn = QPushButton("SAVE PROCESSED IMAGE")
        #self.save_edited_btn.clicked.connect(self.save_image)
        #self.save_edited_btn.setStyleSheet("background-color: #004d40; color: white;")
        #proc_layout.addWidget(self.save_edited_btn)


        #Load button test
        #load_ser_layout.addRow(self.load_ser_btn)
        #load_ser_group.setLayout(load_ser_layout)
        #load_ser.addWidget(load_ser_group)



        
        proc_layout.addRow(self.reconstruct_btn)
        proc_group.setLayout(proc_layout)
        controls.addWidget(proc_group)
        controls.addStretch()

        # Right side: Result Displays
        display_layout = QVBoxLayout()
        
        # A view to see the frame and pick the line
        self.spectrum_view = pg.ImageView()
        self.spectrum_view.setFixedHeight(150) # Make it a slim "ribbon"
        self.spectrum_view.ui.roiBtn.hide()
        self.spectrum_view.ui.menuBtn.hide()


        self.spectrum_view.getView().scene().sigMouseClicked.connect(self.on_spectrum_clicked)


        #COMPOSIT TEST
        self.btn_composite = QPushButton("Create Composite (6562.81 + 6563)")
        self.btn_composite.setStyleSheet("background-color: #4B0082; color: white; font-weight: bold;")
        self.btn_composite.clicked.connect(self.run_composite_reconstruction)
        proc_layout.addRow(self.btn_composite) 



        # Save Button
        self.save_btn = QPushButton("SAVE IMAGE")
        self.save_btn.clicked.connect(self.save_processed_image)
        self.save_btn.setStyleSheet("background-color: #004d40; color: white;")

        # Add them to the layout
        #proc_layout.addRow("Wavelength (X):", self.x_slider)
        proc_layout.addRow(self.save_btn)

        
        #proc_layout.addRow("Aspect Ratio:", self.ratio_slider)



        
        # The final reconstructed Sun
        self.sun_view = pg.ImageView()
        self.sun_view.ui.roiBtn.hide()
        
        display_layout.addWidget(QLabel("Scan data: Spectral Line"))
        display_layout.addWidget(self.spectrum_view)
        display_layout.addWidget(QLabel("Reconstructed Solar Image"))
        display_layout.addWidget(self.sun_view)

        layout.addLayout(controls, 1)
        layout.addLayout(display_layout, 4)






    def select_ser_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Open SER Scan", "", "SER Files (*.ser)")
        if file_path:
            self.current_ser_path = file_path
            self.reconstructor = SHGReconstructor(file_path)
            
            from app.core.ser_reader import SERReader
            reader = SERReader(file_path) # Should be updated to width 3056
            
            # Update X-Slider to the real sensor width
            self.x_slider.setRange(0, 3056)
            
            # Update Aspect Ratio Slider based on log data (1.08)
            # 1.08 * 100 = 108
            #self.ratio_slider.setValue(108) 

            # Setup Spectrum View
            first_frame = reader.get_frame(0)
            self.spectrum_view.getView().setAspectLocked(False)
            self.spectrum_view.setImage(first_frame.T)
            self.spectrum_view.autoLevels() 
            
            self.sun_view.getView().setAspectLocked(False)
            self.reconstruct_btn.setEnabled(True)
            self.status_bar.showMessage(f"Loaded: 3056x128 | Frames: {reader.frame_count}")


    def run_reconstruction(self):
        try:
            # 1. get the x-line position
            #line_x = int(self.line_x_input.text())
            raw_text = self.line_x_input.text().replace(',', '.') 
            #target_wl = float(self.line_x_input.text().replace(',', '.'))
            target_wl = float(raw_text)

            #line_x = float(raw_text) # This allows 106.5 without crashing

            # Convert that wavelength to the 105.x pixel coordinate
            line_pixel = self.reconstructor.wavelength_to_pixel(target_wl)

            # 2. run the processing (the "stacking" of 3,618 slits)
            #raw_sun = self.reconstructor.process(line_x)
            #raw_sun = self.reconstructor.process(line_pixel, rotation_deg=self.rotation_slider.value(), callback=self.update_scan_preview)

# Save it to the CLASS (self) so other buttons can see it
            self.current_recon_data = self.reconstructor.process(line_pixel, rotation_deg=self.rotation_slider.value(), callback=self.update_scan_preview)
            self.sun_view.setImage(self.current_recon_data)




            #rotation 
            rotation_val = self.rotation_slider.value()
            #rotation_deg = rotation_val

            # 3. update the display
            #self.sun_view.setImage(raw_sun)
            
            # Corrected: Access imageItem to set options
            self.sun_view.imageItem.setOpts(axisOrder='row-major') 
            
            # This 'linear' interpolation will help smooth out the 
            # "diagonal mesh" patterns you are seeing in the 83px height.
            self.sun_view.imageItem.setOpts(interpolation='linear')
            
            # To standardize brightness without crashing:
            self.sun_view.setLevels(0, 255)


            # 4. fix the fixed values: pull the current live aspect ratio
            view_box = self.sun_view.getView()
            view_box.setAspectLocked(False) # critical: allows stretching
            
            try:
                # use whatever your text box is named (speed_input or aspect_input)
                #stretch_val = float(self.speed_input.text())
                stretch_val = self.ratio_slider.value() / 100.0
                #current_aspect = float(self.speed_input.text())
                current_aspect = stretch_val
                # apply the stretch to the 83-pixel height
                # this turns the "barcode" into a circle based on your slider
                view_box.setYRange(0, 3056 * stretch_val, padding=0)
                
            except ValueError:
                # fallback if the text box is empty or invalid
                view_box.setYRange(0, 3056 * 43.6, padding=0)

            #self.status_bar.showMessage(f"reconstructed at x: {line_x}")
            self.status_bar.showMessage(f"Target: {target_wl}Å (Pixel: {line_pixel:.2f})")

        except Exception as e:
            print(f"detailed error: {e}")






    def setup_connection_panel(self):
        conn_group = QGroupBox("Hardware Connection")
        layout = QFormLayout()

        self.driver_type = QComboBox()
        self.driver_type.addItems(["Alpaca (Cross-Platform)", "INDI (Linux/macOS)"])
        
        self.host_input = QLineEdit("localhost:6800")
        self.cam_index = QLineEdit("0")
        self.mount_index = QLineEdit("0")
        
        self.connect_btn = QPushButton("CONNECT ALL")
        self.connect_btn.setStyleSheet("background-color: #1a5f7a; color: white; font-weight: bold; padding: 5px;")

        layout.addRow("Interface:", self.driver_type)
        layout.addRow("Host/IP:", self.host_input)
        layout.addRow("Cam Index:", self.cam_index)
        layout.addRow("Mount Index:", self.mount_index)
        layout.addRow(self.connect_btn)
        conn_group.setLayout(layout)
        self.sidebar.addWidget(conn_group)

    def setup_scan_panel(self):
        scan_group = QGroupBox("SHG Scan Automation")
        layout = QFormLayout()

        self.margin_input = QLineEdit("10.0")
        self.speed_input = QLineEdit("2.0")
        self.rewind_cb = QComboBox()
        self.rewind_cb.addItems(["Auto-Rewind: Yes", "Auto-Rewind: No"])

        # Buttons
        btn_layout = QHBoxLayout()
        self.preview_btn = QPushButton("PREVIEW")
        self.preview_btn.setEnabled(False)
        
        self.start_scan_btn = QPushButton("START SCAN")
        self.start_scan_btn.setEnabled(False)
        self.start_scan_btn.setStyleSheet("background-color: #2e7d32; color: white; font-weight: bold;")

        # NEW: Abort Button (Big and Red)
        self.abort_btn = QPushButton("ABORT")
        self.abort_btn.setEnabled(False) # Only active during a scan
        self.abort_btn.setStyleSheet("background-color: #b71c1c; color: white; font-weight: bold;")
        self.abort_btn.clicked.connect(self.handle_abort) # Link to function below


        btn_layout.addWidget(self.preview_btn)
        btn_layout.addWidget(self.start_scan_btn)
        btn_layout.addWidget(self.abort_btn) # Add to the layout

        layout.addRow("Margin (arcmin):", self.margin_input)
        layout.addRow("Speed (x):", self.speed_input)
        layout.addRow("Post-Scan:", self.rewind_cb)
        layout.addRow(btn_layout)
        scan_group.setLayout(layout)
        self.sidebar.addWidget(scan_group)

    def setup_live_view(self):
        self.view_widget = pg.ImageView()
        self.view_widget.ui.roiBtn.hide()
        self.view_widget.ui.menuBtn.hide()
        self.view_panel.addWidget(self.view_widget)
        
        self.stats_label = QLabel("FPS: 0 | RA: 0.00 | Dec: 0.00")
        self.view_panel.addWidget(self.stats_label)

    def toggle_connection(self):
        if not self.hw.is_connected:
            success = self.hw.connect(
                self.driver_type.currentText(),
                self.host_input.text(),
                int(self.cam_index.text()),
                int(self.mount_index.text())
            )
            if success:
                self.status_bar.showMessage("Hardware Online.")
                self.connect_btn.setText("DISCONNECT")
                self.connect_btn.setStyleSheet("background-color: #c62828; color: white;")
                self.start_scan_btn.setEnabled(True)
                self.preview_btn.setEnabled(True)
                self.start_live_view()
        else:
            self.hw.disconnect()
            if self.video_thread: self.video_thread.stop()
            self.status_bar.showMessage("Disconnected.")
            self.connect_btn.setText("CONNECT ALL")
            self.connect_btn.setStyleSheet("background-color: #1a5f7a; color: white;")
            self.start_scan_btn.setEnabled(False)
            self.preview_btn.setEnabled(False)

    def start_live_view(self):
        self.video_thread = VideoWorker(self.hw.camera)
        self.video_thread.new_frame.connect(self.update_image)
        self.video_thread.start()

    def update_image(self, frame):
        self.view_widget.setImage(frame.T, autoLevels=False)

#    def begin_automation(self, dry_run=False):
#        scanner = SHGScanner(self.hw.mount, self.hw.camera)
#        margin = float(self.margin_input.text())
#        speed = float(self.speed_input.text())
#        rewind = "Yes" in self.rewind_cb.currentText()
#
#        self.scan_thread = ScanThread(scanner, margin, speed, rewind, dry_run)
#        self.scan_thread.status_update.connect(self.status_bar.showMessage)
#        self.scan_thread.start()

    def begin_automation(self, dry_run=False):
            # Store scanner as a class attribute so handle_abort can access it
            self.current_scanner = SHGScanner(self.hw.mount, self.hw.camera)
            
            # UI State: Lock buttons during scan, enable Abort
            self.start_scan_btn.setEnabled(False)
            self.preview_btn.setEnabled(False)
            self.abort_btn.setEnabled(True)

            margin = float(self.margin_input.text())
            speed = float(self.speed_input.text())
            rewind = "Yes" in self.rewind_cb.currentText()

            self.scan_thread = ScanThread(self.current_scanner, margin, speed, rewind, dry_run)
            self.scan_thread.status_update.connect(self.status_bar.showMessage)
            self.scan_thread.finished.connect(self.on_scan_finished) # Reset UI when done
            self.scan_thread.start()

    def handle_abort(self):
        """Called when the Red Abort button is clicked."""
        if hasattr(self, 'current_scanner'):
            self.current_scanner.abort()
        self.status_bar.showMessage("ABORTING...")
        self.abort_btn.setEnabled(False)

    def on_scan_finished(self):
        """Resets the UI buttons after a scan ends or is aborted."""
        self.start_scan_btn.setEnabled(True)
        self.preview_btn.setEnabled(True)
        self.abort_btn.setEnabled(False)
        self.status_bar.showMessage("Ready for next scan.")



    #This naming of the two buttons will be confusing since its pretty much the other way around
    def save_image(self):
            if not hasattr(self, 'current_recon_data'):
                self.status_bar.showMessage("Nothing to save!")
                return

            file_path, _ = QFileDialog.getSaveFileName(self, "Save Solar Image", "", "PNG Image (*.png);;TIFF Image (*.tiff)")
            
            if file_path:
                # 1. Get the Raw Data (The "Default" Save)
                raw_data = self.current_recon_data.copy()
                
                # 2. Apply the Inversion if the box is checked
                if self.invert_check.isChecked():
                    raw_data = 255 - raw_data

                # 3. Apply the Sliders/Levels from the UI
                # We grab the current "Black" and "White" points from the histogram
                levels = self.sun_view.getHistogramWidget().getLevels()
                black_point, white_point = levels
                
                # This "clips" the data to your slider positions
                # and stretches it to fill the full 0-255 range
                processed_img = np.clip(raw_data, black_point, white_point)
                processed_img = ((processed_img - black_point) / (white_point - black_point) * 255).astype(np.uint8)

                # 4. Save the "What You See" version
                cv2.imwrite(file_path, processed_img)
                
                # 5. Optional: Save the "Scientific Raw" alongside it
                raw_path = file_path.replace(".png", "_RAW.tiff").replace(".tiff", "_RAW.tiff")
                cv2.imwrite(raw_path, raw_data.astype(np.uint16) * 256) # Save as 16-bit for science
                
                self.status_bar.showMessage(f"Saved: {file_path}")






    def save_processed_image(self):
            if not hasattr(self, 'current_recon_data') or self.current_recon_data is None:
                self.status_bar.showMessage("Error: No reconstructed image to save!")
                return

            # 1. Capture the 'selected_filter' from the dialog
            # This tells us if the user clicked "PNG Files" or "TIFF Files"
            file_path, selected_filter = QFileDialog.getSaveFileName(
                self, 
                "Save Solar Image", 
                "", 
                "PNG Files (*.png);;TIFF Files (*.tiff)"
            )
            
            if not file_path:
                return

            # 2. Force the correct extension based on the selected filter
            if "PNG" in selected_filter and not file_path.lower().endswith(".png"):
                file_path += ".png"
            elif "TIFF" in selected_filter and not file_path.lower().endswith((".tiff", ".tif")):
                file_path += ".tiff"

            try:
                import cv2
                import numpy as np
                
                # 3. Get the data
                final_data = self.current_recon_data.copy()
                
                # 4. Standardize for OpenCV Writers
                # imwrite often fails if given raw float data, so we force 8-bit uint8
                if final_data.dtype != np.uint8:
                    final_data = cv2.normalize(final_data, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)

                # 5. Write the file
                # This will no longer throw the 'could not find a writer' error
                success = cv2.imwrite(file_path, final_data)
                
                if success:
                    self.status_bar.showMessage(f"Successfully saved: {file_path}")
                else:
                    self.status_bar.showMessage("Failed to write file. Check permissions.")
                        
            except Exception as e:
                self.status_bar.showMessage(f"Save Error: {e}")
                print(f"Detailed Save Error: {e}")




    def on_spectrum_clicked(self, event):
            """Sets the X coordinate when you click the spectral image."""
            if event.button() == Qt.LeftButton:
                pos = event.scenePos()
                
                # Use getView() instead of viewBox()
                view_box = self.spectrum_view.getView()
                
                # Check if the click was inside the image area
                if view_box.sceneBoundingRect().contains(pos):
                    # Convert the "Scene" click to "Image Pixel" coordinates
                    mouse_point = view_box.mapSceneToView(pos)
                    x_val = int(mouse_point.x())
                    
                    # Update UI and trigger reconstruction
                    #self.x_slider.setValue(x_val)
                    #self.line_x_input.setText(str(x_val))
                    #self.run_reconstruction()
