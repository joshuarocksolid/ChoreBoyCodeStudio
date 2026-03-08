# vendor/

Pre-downloaded wheels for the FreeCAD AppRun runtime (Python 3.11, Linux x86_64).

These packages are **not** available in the locked-down ChoreBoy system by default and cannot be installed via `pip` on the target machine. They are committed as wheels and extracted into `/opt/freecad/usr/lib/python3.11/site-packages` during environment setup.

## Contents

| Wheel | Version | Type |
|-------|---------|------|
| `tree_sitter-0.21.3-cp311-cp311-manylinux_2_17_x86_64.manylinux2014_x86_64.whl` | 0.21.3 | cp311 native |
| `tree_sitter_languages-1.10.2-cp311-cp311-manylinux_2_17_x86_64.manylinux2014_x86_64.whl` | 1.10.2 | cp311 native |
| `pyflakes-3.4.0-py2.py3-none-any.whl` | 3.4.0 | pure Python |

## Installation into FreeCAD runtime

Extract each wheel into the FreeCAD site-packages directory:

```bash
SITE=/opt/freecad/usr/lib/python3.11/site-packages
for whl in vendor/*.whl; do
  sudo unzip -o "$whl" -d "$SITE"
done
```

## Updating a wheel

1. Download the new wheel targeting `cp311`, `manylinux_2_17_x86_64` (or `py3-none-any` for pure Python):

   ```bash
   pip download --python-version 3.11 --only-binary=:all: \
     --platform manylinux2014_x86_64 --platform manylinux_2_17_x86_64 \
     --implementation cp --no-deps "package==X.Y.Z"
   ```

2. Replace the old wheel in `vendor/`.
3. Re-extract into FreeCAD site-packages per the installation step above.
4. Verify: `/opt/freecad/AppRun -c "import package; print(package.__version__)"`

## Why wheels, not installed packages

The ChoreBoy target system has no `pip`, no internet access, and no system package manager available to the user. Vendoring pre-built wheels in the repository is the only reliable distribution mechanism.
