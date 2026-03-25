def __getattr__(name):
    if name == "dynamic_value":
        return 99
    raise AttributeError(name)
