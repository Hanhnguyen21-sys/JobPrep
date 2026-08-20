"""Auth routes.

Login/signup/logout themselves happen client-side against Supabase Auth
(see frontend/src/lib/supabase.ts) — the frontend never sends passwords to
this backend. This router only exposes what the backend needs once a user
already holds a valid Supabase session: reading/confirming the current
profile.
"""

from fastapi import APIRouter, Depends

from app.api.dependencies import get_current_user
from app.models.user import User
from app.schemas.user import UserRead

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me", response_model=UserRead)
def read_current_user(current_user: User = Depends(get_current_user)) -> User:
    return current_user