"""CUORE -- companion service over the MES diagnostic toolchain.

One application, two deployment profiles:

* ``bench`` -- runs on the shop machine beside MultiEcuScan. Owns the log
  corpus and every analysis in the :mod:`mes` package.
* ``drive`` -- runs on a small in-car node. Owns the live link and the drive
  recorder. Not built yet; the profile exists so clients can already ask.

The client never assumes which one it reached: it calls ``/api/capabilities``
and renders what that host says it can do. See ``docs/COMPANION_APP_SPEC.md``.
"""

from __future__ import annotations

__version__ = "0.1.0"
__all__ = ["__version__"]
