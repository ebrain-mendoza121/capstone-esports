"""
Shared slowapi rate-limiter instance.

Defined here (not in app.main) to avoid a circular import:
  app.main imports app.api.router
  app.api.router imports app.api.routes.ingest
  app.api.routes.ingest previously imported limiter from app.main  ← cycle

Any route module that needs the limiter should import from here instead.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address, default_limits=[])
