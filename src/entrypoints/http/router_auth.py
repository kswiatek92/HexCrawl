"""Auth router — intentionally empty (task 3.5, see DECISIONS.md ADR-0007).

The backend exposes **no** ``/auth`` routes. It is a *stateless resource server*:
it only **verifies** Supabase access-token JWTs (``get_current_user`` in
``src/entrypoints/http/auth.py``, task 2.10) and never logs anyone in. Signup,
login, and refresh are owned by the **frontend** via the Supabase JS SDK, which
holds the credentials and the refresh token — the backend never sees either
(``docs/auth-setup.md``; QUESTIONS.md Phase 2 line 82).

This empty router is kept mounted as a namespace placeholder so the decision is
discoverable where someone would look for the missing endpoints. If a concrete
need for a backend ``/auth`` route ever surfaces, it would supersede ADR-0007.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/auth", tags=["auth"])
