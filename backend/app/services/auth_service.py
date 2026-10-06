from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette import status

from app.core.errors import AppError
from app.core.security import create_access_token, hash_password, verify_password
from app.models.auth import User
from app.schemas.auth import Token, UserCreate


class AuthService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def register(self, payload: UserCreate) -> User:
        normalized_email = payload.email.lower()
        existing_user = self.db.scalar(select(User).where(User.email == normalized_email))
        if existing_user is not None:
            raise AppError("A user with this email already exists.", status.HTTP_409_CONFLICT)

        user = User(
            email=normalized_email,
            full_name=payload.full_name,
            hashed_password=hash_password(payload.password),
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def login(self, email: str, password: str) -> Token:
        user = self.db.scalar(select(User).where(User.email == email.lower()))
        if user is None or not verify_password(password, user.hashed_password):
            raise AppError("Invalid email or password.", status.HTTP_401_UNAUTHORIZED)
        if not user.is_active:
            raise AppError("This user account is inactive.", status.HTTP_403_FORBIDDEN)
        return Token(access_token=create_access_token(user.id))
