"""Print-ready service reminder labels on Avery weatherproof sheets.

Two modules:

* :mod:`cuore.labels.templates` -- sheet geometry data (page size, label
  size, margins, pitch, rows/cols, corner radius) for a set of Avery
  weatherproof/durable film templates, plus a CUSTOM template built from
  user-entered dimensions. Pure data, no I/O.
* :mod:`cuore.labels.render` -- turns one label's field values into a
  print-ready PDF page with reportlab, auto-shrinking text to fit each
  small cell.

Neither module imports ``mes`` or ``cuore`` web/service code -- vehicle and
service-record data is assembled by the caller (see
:mod:`cuore.services.labels_bridge`) and handed in as plain dicts, so this
package stays testable with no corpus and no state directory.
"""

from __future__ import annotations
