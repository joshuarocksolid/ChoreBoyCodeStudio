def helper(name, *, compact=False):
    """Build report summary."""
    if compact:
        return name.strip()
    return f"report:{name}"
