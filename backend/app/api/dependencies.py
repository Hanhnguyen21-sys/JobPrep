from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.exceptions import UnauthorizedException
from app.core.security import decode_supabase_token
from app.db.session import get_db
from app.models.user import User

bearer_scheme = HTTPBearer(auto_error=False)


# def get_current_user(
#     # extract token from HTTP request
#     credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
#     db: Session = Depends(get_db), # get database session
# ) -> User:
#     if credentials is None:
#         raise UnauthorizedException("Missing bearer token")
#     # decode token to get user information , calling function from security.py
#     token_payload = decode_supabase_token(credentials.credentials)
#     # use that information to check in db
#     user = db.get(User, token_payload.sub)
#     if user is None:
#         # Fallback for the (rare) case the DB trigger hasn't fired yet —
#         # create the profile row lazily from the token claims.
#         user = User(id=token_payload.sub, email=token_payload.email or "")
#         db.add(user)
#         db.commit() # commit to database
#         db.refresh(user)

#     return user

def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
       
        raise UnauthorizedException("Missing bearer token")

   

    token_payload = decode_supabase_token(credentials.credentials)

    

    user = db.get(User, token_payload.sub)

    if user is None:
        user = User(
            id=token_payload.sub,
            email=token_payload.email or "",
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    return user