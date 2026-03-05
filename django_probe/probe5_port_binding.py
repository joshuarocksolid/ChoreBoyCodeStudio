#!/usr/bin/env python
"""
Probe 5: Localhost port binding
Tests whether the runtime allows binding TCP ports on 127.0.0.1.
Informational -- needed only if we ever want Django's runserver.
"""
from __future__ import annotations

import os
import socket
import sys

probe_root = os.path.dirname(os.path.abspath(__file__))
results = []

print("=== Probe 5: Port Binding ===\n")

results.append(f"[Runtime]")
results.append(f"  Python: {sys.version.split()[0]}")

results.append(f"\n[Port binding tests]")
for port in [8000, 8080, 9000, 0]:
    label = f"127.0.0.1:{port}" if port else "127.0.0.1:0 (OS-assigned)"
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", port))
        s.listen(1)
        actual_port = s.getsockname()[1]
        results.append(f"  {label} -> SUCCESS (bound to :{actual_port})")
    except Exception as e:
        results.append(f"  {label} -> FAILED ({e})")
    finally:
        s.close()

output = "\n".join(results)
print(output)

results_path = os.path.join(probe_root, "probe5_results.txt")
with open(results_path, "w") as f:
    f.write(output)
print(f"\nResults written to {results_path}")
print("\n=== END Probe 5 ===")
