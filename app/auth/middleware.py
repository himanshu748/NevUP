"""FastAPI dependency: extract and verify JWT from Authorization header."""

import uuid
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.auth.jwt_utils import verify_token

bearer_scheme = HTTPBearer(auto_error=False)


def _trace_id(request: Request) -> str:
    """Return the traceId attached by the logging middleware."""
    return getattr(request.state, "trace_id", str(uuid.uuid4()))


async def get_current_user(
    request: Request,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(bearer_scheme)
    ] = None,
) -> dict:
    """Validate the Bearer JWT and return the decoded payload.

    Raises:
        HTTPException 401 – missing, malformed, or expired token.
    """
    trace_id = _trace_id(request)

    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail={
                "error": "UNAUTHORIZED",
                "message": "Missing Authorization header.",
                "traceId": trace_id,
            },
        )

    try:
        payload = verify_token(credentials.credentials)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=401,
            detail={
                "error": "TOKEN_EXPIRED",
                "message": "JWT has expired.",
                "traceId": trace_id,
            },
        )
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=401,
            detail={
                "error": "INVALID_TOKEN",
                "message": "JWT is malformed or signature is invalid.",
                "traceId": trace_id,
            },
        )

    return payload


async def verify_user_access(
    user_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Ensure the JWT sub claim matches the userId path parameter.

    Raises:
        HTTPException 403 – cross-tenant access attempt.
    """
    trace_id = _trace_id(request)

    if current_user.get("sub") != user_id:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "FORBIDDEN",
                "message": "Cross-tenant access denied. JWT sub does not match userId.",
                "traceId": trace_id,
            },
        )
    return current_user
