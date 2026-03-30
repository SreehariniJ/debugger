from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session

from backend.schemas import LoginRequest, RegisterRequest, TokenResponse
from backend.auth import (
    authenticate_user,
    create_access_token,
    register_user,
    get_user_profile,
)
from backend.database import get_db
from backend.dependencies import get_current_user
from backend.models import User

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(request: LoginRequest, db: Session = Depends(get_db)):
    """Authenticate user and return JWT token. Public endpoint."""
    user = authenticate_user(db, request.username, request.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password.")
    token = create_access_token(user.username)
    return TokenResponse(
        access_token=token,
        user=get_user_profile(user),
    )


@router.post("/register", response_model=TokenResponse)
def register(request: RegisterRequest, db: Session = Depends(get_db)):
    """Register a new user and return JWT token. Public endpoint."""
    user = register_user(db, request.username, request.password, request.display_name)
    if not user:
        raise HTTPException(status_code=409, detail="Username already exists.")
    token = create_access_token(user.username)
    return TokenResponse(
        access_token=token,
        user=get_user_profile(user),
    )


@router.get("/me")
def auth_me(current_user: User = Depends(get_current_user)):
    """Get current user profile. Requires JWT."""
    return get_user_profile(current_user)
