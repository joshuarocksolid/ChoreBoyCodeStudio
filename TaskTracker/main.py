"""Task Tracker - Simple Qt app for Phase 15 workflow."""
import sys
from PySide2.QtWidgets import (
    QApplication, QMainWindow, QWidget,
    QVBoxLayout, QListWidget, QPushButton
)

class TaskTrackerWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Task Tracker")
        self.setGeometry(100, 100, 400, 300)

        # Central widget and layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # List widget for tasks
        self.task_list = QListWidget()
        layout.addWidget(self.task_list)

        # Add task button
        add_button = QPushButton("Add Task")
        add_button.clicked.connect(self.add_task)
        layout.addWidget(add_button)

        self.task_counter = 0

    def add_task(self):
        self.task_counter += 1
        self.task_list.addItem(f"Task {self.task_counter}")

def main():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)

    window = TaskTrackerWindow()
    window.show()
    return app.exec_()

if __name__ == "__main__":
    sys.exit(main())
