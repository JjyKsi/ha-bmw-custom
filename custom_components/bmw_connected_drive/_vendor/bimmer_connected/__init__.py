"""Library to read data from the BMW Connected Drive portal.

The library bimmer_connected provides a Python interface to interact
with the BMW Connected Drive web service. It allows you to read
the current state of the vehicle and also trigger remote services.

Disclaimer:
This library is not affiliated with or endorsed by BMW Group.
"""

# In vendored mode (Home Assistant custom component), the package is not installed
# via pip, so importlib.metadata cannot determine the version. Instead, expose a
# static __version__ and optional vendor metadata if available.

try:  # best effort when installed via pip
    from importlib.metadata import version as _pkg_version  # type: ignore
except Exception:  # pragma: no cover - fallback in vendored usage
    _pkg_version = None  # type: ignore

try:
    if _pkg_version is not None:
        __version__ = _pkg_version("bimmer_connected")
    else:
        raise RuntimeError
except Exception:  # pragma: no cover
    # Vendored fallback; optionally enrich with vendor_info
    try:
        from . import vendor_info as _vendor_info  # type: ignore
        __version__ = f"vendored ({getattr(_vendor_info, 'VENDOR', 'unknown')}@{getattr(_vendor_info, 'COMMIT', 'unknown')})"
    except Exception:  # pragma: no cover
        __version__ = "vendored"
