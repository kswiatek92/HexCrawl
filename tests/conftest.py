"""Root pytest conftest.

Sets required environment variables at module load time — before any test
module is imported — so that ``Settings()`` instantiation inside module-level
code (e.g. ``app = create_app()`` in ``main.py``) does not fail in environments
without a ``.env`` file (CI, fresh checkouts).

Only sets variables that are absent; real values from ``.env`` or the shell
environment take precedence (``os.environ.setdefault``).
"""

import os

os.environ.setdefault("JWT_SECRET", "pytest-test-secret-not-for-production")
