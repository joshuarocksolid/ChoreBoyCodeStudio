"""Three runtime .ui loaders. The adopt scan treats this file as a fixture.

The paths are variables, so the scan reports the call without guessing a file.
"""


def load_with_qui_loader(path):
    from PySide6.QtUiTools import QUiLoader

    loader = QUiLoader()
    return loader.load(path)


def load_with_loadui(path):
    from PySide6.QtUiTools import loadUi

    return loadUi(path)


def load_with_pyside_uic(path):
    import FreeCADGui

    return FreeCADGui.PySideUic.loadUi(path)
