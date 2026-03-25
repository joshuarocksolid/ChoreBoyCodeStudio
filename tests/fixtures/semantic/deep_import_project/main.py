"""Main entry using deeply nested import through re-export chain."""
from pkg import deep_function


def run():
    return deep_function(42)
