import logging

__version__ = "0.1.0"  # default for development

try:
    from importlib.metadata import version as _version
    __version__ = _version("dincli")
except Exception:
    # Keep "dev" if package is not installed
    pass
