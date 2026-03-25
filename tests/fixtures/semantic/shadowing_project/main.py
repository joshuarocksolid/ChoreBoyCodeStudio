from service import calculate as imported_calculate


def calculate(value):
    """Local shadowing function."""
    return value + 1


def run():
    local_value = calculate(1)
    imported_value = imported_calculate(2)
    return local_value, imported_value
