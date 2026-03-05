#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
from __future__ import annotations

import os
import sys


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "testsite.settings")

    # Ensure vendored packages are importable
    probe_root = os.path.dirname(os.path.abspath(__file__))
    vendor_dir = os.path.join(probe_root, "vendor")
    for path in (vendor_dir, probe_root):
        if path not in sys.path:
            sys.path.insert(0, path)

    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
