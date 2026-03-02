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
        controls = QVBoxLayout()
        proc_group = QGroupBox("Processing Controls")
        proc_layout = QFormLayout()

        self.load_ser_btn = QPushButton("LOAD .SER FILE")
        self.load_ser_btn.clicked.connect(self.select_ser_file)
        
        self.line_x_input = QLineEdit("656")
        proc_layout.addRow(self.load_ser_btn)
        proc_layout.addRow("Spectral Line X:", self.line_x_input)

        self.reconstruct_btn = QPushButton("RECONSTRUCT SUN")
        self.reconstruct_btn.setEnabled(False)
        self.reconstruct_btn.setStyleSheet("background-color: #ef6c00; color: white; font-weight: bold;")
        self.reconstruct_btn.clicked.connect(self.run_reconstruction)

        # ... inside your processing layout ...
        self.ratio_slider = QSlider(Qt.Horizontal)
        self.ratio_slider.setRange(1, 1000) # 0.1x to 50x
        self.ratio_slider.setValue(4360)    # Default 1.0x

        
        # X-Position Slider (to tune the wavelength)
        self.x_slider = QSlider(Qt.Horizontal)
        self.x_slider.setRange(0, 4660) # Match your sensor width
        self.x_slider.setValue(656)
        #self.x_slider.valueChanged.connect(self.run_reconstruction) # Re-run on move
        self.ratio_slider.valueChanged.connect(self.update_aspect_from_slider)


        # Add this near your Reconstruct button
        self.autofix_btn = QPushButton("AUTO-FIX GEOMETRY")
        self.autofix_btn.clicked.connect(self.auto_geometry_fix)
        self.autofix_btn.setStyleSheet("background-color: #512da8; color: white;")
        
        proc_layout.addRow(self.autofix_btn)




        # Save Button
        self.save_btn = QPushButton("SAVE IMAGE")
        self.save_btn.clicked.connect(self.save_processed_image)
        self.save_btn.setStyleSheet("background-color: #004d40; color: white;")

        # Add them to the layout
        proc_layout.addRow("Wavelength (X):", self.x_slider)
        proc_layout.addRow(self.save_btn)

        
        proc_layout.addRow("Aspect Ratio:", self.ratio_slider)

        
        proc_layout.addRow(self.reconstruct_btn)
        proc_group.setLayout(proc_layout)
        controls.addWidget(proc_group)
        controls.addStretch()

        # Right side: Result Displays
        display_layout = QVBoxLayout()
        
        # A view to see the frame and pick the line
        self.spectrum_view = pg.ImageView()
        self.spectrum_view.ui.roiBtn.hide()

        #self.spectrum_view.viewBox().scene().sigMouseClicked.connect(self.on_spectrum_clicked)
        self.spectrum_view.getView().scene().sigMouseClicked.connect(self.on_spectrum_clicked)
        #self.spectrum_view.viewBox().setAspectLocked(False)
        #self.spectrum_view.scene().sigMouseClicked.connect(self.on_spectrum_clicked)

        
        # The final reconstructed Sun
        self.sun_view = pg.ImageView()
        self.sun_view.ui.roiBtn.hide()
        
        display_layout.addWidget(QLabel("Step 1: Select Spectral Line (Click on image)"))
        display_layout.addWidget(self.spectrum_view)
        display_layout.addWidget(QLabel("Step 2: Reconstructed Solar Image"))
        display_layout.addWidget(self.sun_view)

        layout.addLayout(controls, 1)
        layout.addLayout(display_layout, 4)

    def select_ser_file(self):
            file_path, _ = QFileDialog.getOpenFileName(self, "Open SER Scan", "", "SER Files (*.ser)")
            if file_path:
                self.current_ser_path = file_path
                
                # 1. Initialize the Reconstructor for later use
                from app.core.reconstructor import SHGReconstructor
                self.reconstructor = SHGReconstructor(file_path)
                
                # 2. Use the SERReader to get metadata for the UI
                from app.core.ser_reader import SERReader
                reader = SERReader(file_path)
                
                # CALCULATE RATIO: 3618 frames / 83 height = ~43.6
                # Use the calculated values directly from the reader
                #height = reader.frame_shape[0] # You can also use reader.frame_shape[0] if it's reliable
                height = 83 # You can also use reader.frame_shape[0] if it's reliable
                #height = 83 # You can also use reader.frame_shape[0] if it's reliable
                auto_aspect = (reader.frame_count / height) if reader.frame_count > 0 else 1.0
                
                # Update UI controls - Use speed_input as verified earlier
                if hasattr(self, 'speed_input'):
                    self.speed_input.setText(f"{auto_aspect:.1f}")

                # Setup Spectrum View (Top)
                # Use the reader to get the first frame for the preview
                first_frame = reader.get_frame(0)
                self.spectrum_view.getView().setAspectLocked(False)
                self.spectrum_view.setImage(first_frame.T)
                self.spectrum_view.autoLevels() 
                
                # Setup Sun View (Bottom)
                # Unlocking the view allows the aspect ratio to stretch the 83px height
                self.sun_view.getView().setAspectLocked(False)
                
                self.reconstruct_btn.setEnabled(True)
                self.status_bar.showMessage(f"Loaded: {file_path}")



    def run_reconstruction(self):
        try:
            # 1. get the x-line position
            line_x = int(self.line_x_input.text())
            
            # 2. run the processing (the "stacking" of 3,618 slits)
            raw_sun = self.reconstructor.process(line_x)
            
            # 3. update the display
            self.sun_view.setImage(raw_sun)
            
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
                view_box.setYRange(0, 83 * stretch_val, padding=0)
                
            except ValueError:
                # fallback if the text box is empty or invalid
                view_box.setYRange(0, 83 * 43.6, padding=0)

            self.status_bar.showMessage(f"reconstructed at x: {line_x}")

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

    def save_processed_image(self):
            # 1. Check if we actually have an image to save
            if not hasattr(self, 'reconstructor') or self.reconstructor.reconstructed_image is None:
                self.status_bar.showMessage("Error: No reconstructed image to save!")
                return

            # 2. Open a file dialog to choose where to save
            file_path, _ = QFileDialog.getSaveFileName(self, "Save Solar Image", "", "PNG Files (*.png);;TIFF Files (*.tiff)")
            
            if file_path:
                try:
                    import imageio
                    import numpy as np
                    import cv2
                    # Get the raw data from your reconstructor
                    data = self.reconstructor.reconstructed_image
                    
                    # Normalize the 12-bit/16-bit data to 8-bit for standard viewers
                    img_min, img_max = data.min(), data.max()
                    if img_max > img_min:
                        normalized = ((data - img_min) / (img_max - img_min) * 255).astype(np.uint8)
                    else:
                        normalized = data.astype(np.uint8)
                    

                    # Apply the current stretch to the actual file
                    stretch = self.ratio_slider.value() / 100.0
                    new_h = int(83 * stretch)
               

                    norm = ((data - data.min()) / (data.max() - data.min()) * 255).astype(np.uint8)

                    # Stretch the image data so the saved PNG is round
                    final_img = cv2.resize(norm, (3618, new_h), interpolation=cv2.INTER_CUBIC)
                    # Save the file
                    #imageio.imsave(file_path, normalized)
                    cv2.imwrite(file_path, final_img)
                    self.status_bar.showMessage(f"Image saved to: {file_path}")
                    
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
                    self.x_slider.setValue(x_val)
                    self.line_x_input.setText(str(x_val))
                    self.run_reconstruction()
