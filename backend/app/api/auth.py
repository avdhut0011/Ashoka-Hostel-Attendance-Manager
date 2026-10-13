from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from backend.app.core.database import get_db
from backend.app.core.security import verify_password, create_access_token, get_current_user, oauth2_scheme
from backend.app.models.master import Hostel
from backend.app.models.security import User
from backend.app.schemas.schemas import TokenResponse, UserResponse, LoginRequest
from backend.app.core.login_limit import check_login

router = APIRouter(prefix="/auth", tags=["Authentication"])

@router.post("/login", response_model=TokenResponse)
def login(login_req: LoginRequest, request: Request, db: Session = Depends(get_db)):
    client_ip = request.client.host if request.client else 'unknown'
    check_login(client_ip, login_req.username, db)
    user = db.query(User).filter(User.Username == login_req.username.strip()).first()
    if not user or not verify_password(login_req.password, user.PasswordHash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password"
        )
    if not user.IsActive:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated"
        )

    if user.Role not in ('ADMIN', 'IT_ADMIN', 'MANAGEMENT', 'WARDEN'):
        raise HTTPException(403, 'Account has an invalid role')
    if user.Role == 'WARDEN' and (not user.HostelId or not db.query(Hostel).filter_by(HostelId=user.HostelId, IsActive=True).first()):
        raise HTTPException(403, 'Warden must be assigned to an active hostel')
    access_token = create_access_token(data={"sub": user.Username, "role": user.Role, "id": user.SystemUserId, "hostel_id": user.HostelId, "ver": user.TokenVersion or 0})
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        user_id=user.SystemUserId,
        username=user.Username,
        role=user.Role,
        hostel_id=user.HostelId
    )


@router.post('/logout')
def logout(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from hashlib import sha256
    from datetime import datetime
    import jwt
    from backend.app.core.config import settings
    from backend.app.models.hardening import RevokedToken
    claims = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    db.query(RevokedToken).filter(RevokedToken.ExpiresAt < datetime.utcnow()).delete(synchronize_session=False)
    digest = sha256(token.encode()).hexdigest()
    if db.get(RevokedToken, digest) is None:
        db.add(RevokedToken(TokenHash=digest, UserId=user.SystemUserId, ExpiresAt=datetime.utcfromtimestamp(claims['exp'])))
    db.commit()
    return {'message': 'Logged out'}

@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user
