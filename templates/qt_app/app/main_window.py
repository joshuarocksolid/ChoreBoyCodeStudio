from PySide2.QtWidgets import QLabel, QMainWindow


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Qt Template App")
        self.resize(640, 360)
        self.setCentralWidget(QLabel("Hello from the Qt template."))
