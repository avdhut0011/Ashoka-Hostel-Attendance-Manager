from datetime import datetime, timedelta
from typing import Optional, List
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
import jwt
from jwt import PyJWTError as JWTError
import bcrypt
from hashlib import sha256
import secrets
from backend.app.models.hardening import RevokedToken
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.core.database import get_db
from backend.app.models.security import User
from backend.app.models.master import Hostel

# Handle bcrypt version compatibility cleanly
class BcryptContext:
    """Verify existing bcrypt hashes without changing any stored credentials."""
    rounds = 12

    def update(self, bcrypt__rounds=12):
        self.rounds = bcrypt__rounds

    def hash(self, password):
        return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt(rounds=self.rounds)).decode('ascii')

    def verify(self, password, hashed):
        return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('ascii'))

pwd_context = BcryptContext()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except Exception:
        return False

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=settings.JWT_EXPIRATION_MINUTES))
    to_encode.update({"exp": expire, 'jti': secrets.token_urlsafe(24)})
    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    return encoded_jwt

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate authentication credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        if len(token) > 8192:
            raise credentials_exception
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    if db.get(RevokedToken, sha256(token.encode()).hexdigest()) is not None:
        raise credentials_exception

    user = db.query(User).filter(User.Username == username, User.IsActive == True).first()
    if user is None or payload.get("ver", 0) != (user.TokenVersion or 0) or (payload.get("id") is not None and payload["id"] != user.SystemUserId):
        raise credentials_exception
    if user.Role not in ['ADMIN', 'WARDEN', 'IT_ADMIN', 'MANAGEMENT']:
        raise HTTPException(status_code=403, detail='Account has an invalid role')
    if user.Role == 'WARDEN':
        hostel = db.query(Hostel).filter_by(HostelId=user.HostelId, IsActive=True).first() if user.HostelId else None
        if hostel is None:
            raise HTTPException(status_code=403, detail='Warden must be assigned to an active hostel')
    return user

def require_roles(allowed_roles: List[str]):
    def role_checker(current_user: User = Depends(get_current_user)):
        if current_user.Role not in allowed_roles and current_user.Role != "ADMIN":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"User role '{current_user.Role}' does not have permission for this action"
            )
        return current_user
    return role_checker
