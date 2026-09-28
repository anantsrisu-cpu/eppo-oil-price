"""EPPO retail oil price pipeline (Thailand).

Modules
-------
config     : brand / product / URL settings (edit here when EPPO changes names)
http       : hardened HTTP client (host allow-list, timeouts, retries, size cap)
api        : daily per-brand retail prices from EPPO JSON API
structure  : daily price-structure Excel files (reference brand history)
storage    : CSV read / upsert helpers (idempotent)
validate   : data-quality checks
build      : SQLite + pivot reports + dashboard JSON
"""

__version__ = "1.0.0"
