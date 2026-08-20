from dataclasses import dataclass

import jwt
from jwt import PyJWTError, PyJWKClient

from app.core.config import get_settings
from app.core.exceptions import UnauthorizedException


@dataclass
class SupabaseTokenPayload:
    sub: str
    email: str | None


def decode_supabase_token(token: str) -> SupabaseTokenPayload:
    settings = get_settings()

    jwks_url = (
        f"{settings.supabase_url}/auth/v1/.well-known/jwks.json"
    )

    try:
        jwks_client = PyJWKClient(jwks_url)

        signing_key = jwks_client.get_signing_key_from_jwt(token)

        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["ES256"],
            audience="authenticated",
        )

    except PyJWTError as exc:
        
        raise UnauthorizedException("Invalid or expired token") from exc

    sub = payload.get("sub")

    if not sub:
        raise UnauthorizedException("Token missing subject")

    return SupabaseTokenPayload(
        sub=sub,
        email=payload.get("email"),
    )