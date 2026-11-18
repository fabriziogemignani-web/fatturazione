# Shared test setup: since iteration 103 every POST/PUT/PATCH/DELETE under /api requires "X-Requested-With: invoix"
# (CSRF guard in server.py security_guard). Inject it into every requests.Session (also used by requests.get/post helpers).
# Tests that must check the 403 can remove it per request: headers={"X-Requested-With": None}.
import requests

_orig_init = requests.Session.__init__


def _init(self, *a, **kw):
    _orig_init(self, *a, **kw)
    self.headers.setdefault("X-Requested-With", "invoix")


requests.Session.__init__ = _init
