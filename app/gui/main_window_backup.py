import sys
import pyqtgraph as pg
import numpy as np
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QPushButton, QLabel, QGroupBox, QComboBox, 
                             QLineEdit, QFormLayout, QStatusBar)
from PySide6.QtCore import Qt, QThread, Signal

# Internal Imports
from app.hardware.manager import HardwareManager
from app.core.scanner import SHGScanner
from .video_worker import VideoWorker

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
        self.setWindowTitle("PySolex - SHG Acquisition Control")
        self.resize(1100, 750)

        # 1. Initialize Hardware Manager
        self.hw = HardwareManager()
        self.video_thread = None

        # 2. Main UI Layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        self.main_layout = QHBoxLayout(central_widget)

        # 3. Build Sidebar (This creates the buttons)
        self.sidebar = QVBoxLayout()
        self.setup_connection_panel()
        self.setup_scan_panel()
        self.sidebar.addStretch()
        self.main_layout.addLayout(self.sidebar, 1)

        # 4. Build Live View Panel
        self.view_panel = QVBoxLayout()
        self.setup_live_view()
        self.main_layout.addLayout(self.view_panel, 4)

        # 5. Status Bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready.")

        # 6. NOW connect signals (Now that all widgets exist)
        self.connect_btn.clicked.connect(self.toggle_connection)
        self.preview_btn.clicked.connect(lambda: self.begin_automation(dry_run=True))
        self.start_scan_btn.clicked.connect(lambda: self.begin_automation(dry_run=False))

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
