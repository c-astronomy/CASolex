import sys
import os
from PySide6.QtWidgets import QApplication

# This ensures the 'app' folder is visible to Python
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.gui.main_window import PySolexUI

def main():
    # Initialize the high-level application
    app = QApplication(sys.argv)
    app.setStyle("Fusion") # Consistent look across Linux/Windows/macOS
    
    # Create and show the main window
    window = PySolexUI()
    window.show()
    
    # Start the event loop
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
