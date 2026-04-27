"""POST /auth/token — issue JWT for a userId."""

from pydantic import BaseModel
from fastapi import APIRouter

from app.auth.jwt_utils import create_token

router = APIRouter(prefix="/auth", tags=["Auth"])


class TokenRequest(BaseModel):
    userId: str
    name: str


class TokenResponse(BaseModel):
    token: str
    expiresAt: str


@router.post("/token", response_model=TokenResponse)
async def issue_token(body: TokenRequest):
    """Issue a signed JWT. No auth required."""
    result = create_token(user_id=body.userId, name=body.name)
    return TokenResponse(**result)
