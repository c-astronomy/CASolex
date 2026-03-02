import sys
import os

# Get the directory where main.py is located
basedir = os.path.dirname(os.path.abspath(__file__))
# Add it to the system path so Python can see the 'app' folder
sys.path.append(basedir)

from app.gui.main_window import PySolexUI
from PySide6.QtWidgets import QApplication

def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    
    window = PySolexUI()
    window.show()
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
