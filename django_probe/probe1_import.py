#!/usr/bin/env python
"""
Probe 1: Django import and setup
Tests whether Django 4.2, asgiref, sqlparse, and typing_extensions
can all import and django.setup() can complete under this Python runtime.
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


def check(label, fn):
    try:
        val = fn()
        results.append(f"  {label}: YES ({val})")
    except Exception:
        results.append(f"  {label}: FAILED\n{traceback.format_exc()}")


print("=== Probe 1: Django Import & Setup ===\n")

results.append("[Runtime]")
results.append(f"  Python: {sys.version}")
results.append(f"  Executable: {sys.executable}")
results.append(f"  Probe root: {probe_root}")

results.append("\n[Package imports]")
def _te_version():
    import typing_extensions
    return getattr(typing_extensions, "__version__", "imported ok (no __version__)")
check("typing_extensions", _te_version)
check("asgiref", lambda: __import__("asgiref").__version__)
check("sqlparse", lambda: __import__("sqlparse").__version__)
check("django", lambda: __import__("django").VERSION)

results.append("\n[Django setup]")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "testsite.settings")
try:
    import django
    django.setup()
    results.append("  django.setup(): SUCCESS")
except Exception:
    results.append(f"  django.setup(): FAILED\n{traceback.format_exc()}")

results.append("\n[Post-setup imports]")
check("django.db", lambda: "ok" if __import__("django.db") else "fail")
check("django.db.models", lambda: "ok" if __import__("django.db.models") else "fail")
check("django.core.management", lambda: "ok" if __import__("django.core.management") else "fail")

output = "\n".join(results)
print(output)

results_path = os.path.join(probe_root, "probe1_results.txt")
with open(results_path, "w") as f:
    f.write(output)
print(f"\nResults written to {results_path}")
print("\n=== END Probe 1 ===")
