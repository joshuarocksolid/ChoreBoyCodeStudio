#!/usr/bin/env python
"""
Probe 4: Django ORM + PySide2 Qt UI in the same process
This is the critical probe: proves Django and PySide2 can coexist
inside the FreeCAD AppRun runtime.

Creates sample data via Django ORM, then displays it in a Qt table widget.
The window stays open until closed manually.
"""
from __future__ import annotations

import os
import sys
import traceback

probe_root = os.path.dirname(os.path.abspath(__file__))
vendor_dir = os.path.join(probe_root, "vendor")
for path in (vendor_dir, probe_root):
    if path not in sys.path:
        sys.path.insert(0, path)

results = []

print("=== Probe 4: Django + PySide2 Integration ===\n")

# --- Step 1: Django setup ---
results.append("[Django setup]")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "testsite.settings")
try:
    import django
    django.setup()
    results.append("  django.setup(): SUCCESS")
except Exception:
    results.append(f"  django.setup(): FAILED\n{traceback.format_exc()}")
    output = "\n".join(results)
    print(output)
    with open(os.path.join(probe_root, "probe4_results.txt"), "w") as f:
        f.write(output)
    sys.exit(1)

# --- Step 2: Ensure DB is migrated and seed data ---
results.append("\n[Seed data]")
try:
    from io import StringIO

    from django.core.management import call_command

    out = StringIO()
    call_command("migrate", verbosity=0, stdout=out)
    results.append("  migrate: SUCCESS")

    from testapp.models import Task

    Task.objects.all().delete()
    sample_tasks = [
        ("Buy groceries", False),
        ("Write probe scripts", True),
        ("Test Django on ChoreBoy", False),
        ("Deploy to production", False),
        ("Celebrate success", False),
    ]
    for title, done in sample_tasks:
        Task.objects.create(title=title, done=done)
    results.append(f"  Seeded {Task.objects.count()} tasks")
except Exception:
    results.append(f"  Seed data: FAILED\n{traceback.format_exc()}")
    output = "\n".join(results)
    print(output)
    with open(os.path.join(probe_root, "probe4_results.txt"), "w") as f:
        f.write(output)
    sys.exit(1)

# --- Step 3: PySide2 import ---
results.append("\n[PySide2 import]")
try:
    from PySide2.QtCore import Qt
    from PySide2.QtWidgets import (
        QApplication,
        QHeaderView,
        QLabel,
        QMainWindow,
        QTableWidget,
        QTableWidgetItem,
        QVBoxLayout,
        QWidget,
    )

    results.append("  PySide2.QtWidgets: SUCCESS")
except ImportError:
    results.append("  PySide2 not available (expected outside FreeCAD AppRun)")
    results.append("  This probe must be run via /opt/freecad/AppRun")
    output = "\n".join(results)
    print(output)
    with open(os.path.join(probe_root, "probe4_results.txt"), "w") as f:
        f.write(output)
    sys.exit(0)

# --- Step 4: Build Qt UI from Django data ---
results.append("\n[Qt UI]")
try:
    app = QApplication.instance() or QApplication(sys.argv)

    window = QMainWindow()
    window.setWindowTitle("Django + PySide2 on ChoreBoy - Probe 4")
    window.resize(600, 400)

    central = QWidget()
    layout = QVBoxLayout(central)

    header_label = QLabel("Tasks from Django ORM (testapp.models.Task)")
    layout.addWidget(header_label)

    tasks = list(Task.objects.all().order_by("id"))
    table = QTableWidget(len(tasks), 4)
    table.setHorizontalHeaderLabels(["ID", "Title", "Done", "Created"])
    table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)

    for row, task in enumerate(tasks):
        table.setItem(row, 0, QTableWidgetItem(str(task.id)))
        table.setItem(row, 1, QTableWidgetItem(task.title))

        done_item = QTableWidgetItem("Yes" if task.done else "No")
        table.setItem(row, 2, done_item)

        created_str = task.created.strftime("%Y-%m-%d %H:%M:%S") if task.created else "N/A"
        table.setItem(row, 3, QTableWidgetItem(created_str))

    layout.addWidget(table)

    info_label = QLabel(
        f"Django {django.VERSION} | Python {sys.version.split()[0]} | "
        f"{len(tasks)} tasks loaded from SQLite via Django ORM"
    )
    layout.addWidget(info_label)

    window.setCentralWidget(central)
    results.append("  Window built: SUCCESS")
    results.append(f"  Rows: {len(tasks)}")

    output = "\n".join(results)
    print(output)
    with open(os.path.join(probe_root, "probe4_results.txt"), "w") as f:
        f.write(output)

    print("\nShowing Qt window... close the window to end the probe.")
    window.show()
    app.exec_()

    print("\n=== END Probe 4 (window closed) ===")

except Exception:
    results.append(f"  Qt UI: FAILED\n{traceback.format_exc()}")
    output = "\n".join(results)
    print(output)
    with open(os.path.join(probe_root, "probe4_results.txt"), "w") as f:
        f.write(output)
    print("\n=== END Probe 4 (failed) ===")
