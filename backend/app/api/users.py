from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator
from sqlalchemy.orm import Session

from backend.app.core.database import get_db
from backend.app.core.security import get_current_user, require_roles, get_password_hash
from backend.app.models.security import User
from backend.app.models.master import Hostel

from backend.app.core.locking import attendance_lock
from backend.app.services.security_audit import account_state, account_audit

router = APIRouter(prefix="/users", tags=["User Management"])

class UserRequest(BaseModel):
    @model_validator(mode='before')
    @classmethod
    def normalize_assignment(cls, values):
        if isinstance(values, dict):
            values = dict(values)
            role = values.get('role')
            if isinstance(role, str):
                role = role.strip().upper()
                values['role'] = role
            if role in ('ADMIN', 'IT_ADMIN', 'MANAGEMENT'):
                values['hostel_id'] = None
            elif values.get('hostel_id') == '':
                values['hostel_id'] = None
        return values

    @field_validator('username', mode='before', check_fields=False)
    @classmethod
    def trim_username(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator('password', check_fields=False)
    @classmethod
    def password_bytes(cls, value):
        if value is not None and len(value.encode('utf-8')) > 72:
            raise ValueError('Password must not exceed 72 UTF-8 bytes')
        return value


class UserCreate(UserRequest):
    username: str = Field(min_length=1, max_length=100, pattern=r"\S")
    password: str = Field(min_length=8, max_length=72)
    role: str # ADMIN, WARDEN, IT_ADMIN, MANAGEMENT
    hostel_id: Optional[int] = None

class UserUpdate(UserRequest):
    username: Optional[str] = Field(None, min_length=1, max_length=100, pattern=r"\S")
    password: Optional[str] = Field(None, min_length=8, max_length=72)
    role: Optional[str] = None
    hostel_id: Optional[int] = None
    is_active: Optional[bool] = None

    @field_validator('password', mode='before')
    @classmethod
    def unchanged_password(cls, value):
        return None if value == '' else value

class UserStatusUpdate(BaseModel):
    is_active: bool

class UserDetailResponse(BaseModel):
    SystemUserId: int
    Username: str
    Role: str
    HostelId: Optional[int] = None
    HostelName: Optional[str] = None
    IsActive: bool

    model_config = ConfigDict(from_attributes=True)

def validate_assignment(db, role, hostel_id):
    if role not in ['ADMIN', 'WARDEN', 'IT_ADMIN', 'MANAGEMENT']:
        raise HTTPException(400, 'Invalid role')
    if role == 'WARDEN' and (not hostel_id or not db.query(Hostel).filter_by(HostelId=hostel_id, IsActive=True).first()):
        raise HTTPException(400, 'Warden requires an active assigned hostel')


def protect_last_admin(db, user, role, active):
    if user.Role == 'ADMIN' and user.IsActive and (role != 'ADMIN' or not active):
        others = db.query(User).filter(User.Role == 'ADMIN', User.IsActive == True, User.SystemUserId != user.SystemUserId).count()
        if not others:
            raise HTTPException(409, 'Cannot remove the last active administrator')


@router.get("", response_model=List[UserDetailResponse])
def list_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(["ADMIN"]))
):
    users = db.query(User).all()
    hostels_map = {h.HostelId: h.HostelName for h in db.query(Hostel).all()}
    
    result = []
    for u in users:
        h_name = hostels_map.get(u.HostelId) if u.HostelId else None
        result.append(UserDetailResponse(
            SystemUserId=u.SystemUserId,
            Username=u.Username,
            Role=u.Role,
            HostelId=u.HostelId,
            HostelName=h_name,
            IsActive=u.IsActive
        ))
    return result

@router.post("", response_model=UserDetailResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    req: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(["ADMIN"]))
):
    with attendance_lock(db, "accounts"):
        pass
    validate_assignment(db, req.role, req.hostel_id)
    existing = db.query(User).filter(User.Username == req.username).first()
    if existing:
        raise HTTPException(status_code=400, detail="Username already exists")

    new_user = User(
        Username=req.username,
        PasswordHash=get_password_hash(req.password),
        Role=req.role,
        HostelId=req.hostel_id if req.role == "WARDEN" else None,
        IsActive=True
    )
    db.add(new_user)
    account_audit(db, current_user, new_user, 'ACCOUNT_CREATED')
    db.commit()
    db.refresh(new_user)

    h_name = None
    if new_user.HostelId:
        h = db.query(Hostel).filter(Hostel.HostelId == new_user.HostelId).first()
        if h:
            h_name = h.HostelName

    return UserDetailResponse(
        SystemUserId=new_user.SystemUserId,
        Username=new_user.Username,
        Role=new_user.Role,
        HostelId=new_user.HostelId,
        HostelName=h_name,
        IsActive=new_user.IsActive
    )

@router.put("/{user_id}", response_model=UserDetailResponse)
def update_user(
    user_id: int,
    req: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(["ADMIN"]))
):
    with attendance_lock(db, 'accounts'):
        pass
    user = db.query(User).filter(User.SystemUserId == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    with attendance_lock(db, 'accounts'):
        pass
    effective_role = req.role or user.Role
    before = account_state(user)
    effective_hostel = (req.hostel_id if 'hostel_id' in req.model_fields_set else user.HostelId) if effective_role == 'WARDEN' else None
    validate_assignment(db, effective_role, effective_hostel)
    protect_last_admin(db, user, req.role or user.Role, req.is_active if req.is_active is not None else user.IsActive)
    if req.username and req.username != user.Username:
        dup = db.query(User).filter(User.Username == req.username).first()
        if dup:
            raise HTTPException(status_code=400, detail="Username already taken")
        user.Username = req.username

    if req.password:
        user.PasswordHash = get_password_hash(req.password)
        user.TokenVersion = (user.TokenVersion or 0) + 1

    if req.role:
        if req.role not in ["ADMIN", "WARDEN", "IT_ADMIN", "MANAGEMENT"]:
            raise HTTPException(status_code=400, detail="Invalid role specified")
        user.Role = req.role

    if user.Role != 'WARDEN':
        user.HostelId = None
    else:
        user.HostelId = effective_hostel

    if req.is_active is not None:
        user.IsActive = req.is_active
    user.TokenVersion = (user.TokenVersion or 0) + 1

    account_audit(db, current_user, user, 'ACCOUNT_CHANGED', before, bool(req.password))
    db.commit()
    db.refresh(user)

    h_name = None
    if user.HostelId:
        h = db.query(Hostel).filter(Hostel.HostelId == user.HostelId).first()
        if h:
            h_name = h.HostelName

    return UserDetailResponse(
        SystemUserId=user.SystemUserId,
        Username=user.Username,
        Role=user.Role,
        HostelId=user.HostelId,
        HostelName=h_name,
        IsActive=user.IsActive
    )

@router.put("/{user_id}/status", response_model=UserDetailResponse)
def update_user_status(
    user_id: int,
    req: UserStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(["ADMIN"]))
):
    with attendance_lock(db, 'accounts'):
        pass
    user = db.query(User).filter(User.SystemUserId == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.SystemUserId == current_user.SystemUserId and not req.is_active:
        raise HTTPException(status_code=400, detail="Cannot deactivate your own active admin account")

    with attendance_lock(db, 'accounts'):
        pass
    protect_last_admin(db, user, user.Role, req.is_active)
    before = account_state(user)
    user.IsActive = req.is_active
    user.TokenVersion = (user.TokenVersion or 0) + 1
    account_audit(db, current_user, user, 'ACCOUNT_STATUS_CHANGED', before)
    db.commit()
    db.refresh(user)

    h_name = None
    if user.HostelId:
        h = db.query(Hostel).filter(Hostel.HostelId == user.HostelId).first()
        if h:
            h_name = h.HostelName

    return UserDetailResponse(
        SystemUserId=user.SystemUserId,
        Username=user.Username,
        Role=user.Role,
        HostelId=user.HostelId,
        HostelName=h_name,
        IsActive=user.IsActive
    )

@router.delete("/{user_id}")
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(["ADMIN"]))
):
    with attendance_lock(db, 'accounts'):
        pass
    user = db.query(User).filter(User.SystemUserId == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user.SystemUserId == current_user.SystemUserId:
        raise HTTPException(status_code=400, detail="Cannot soft delete your own active admin account")

    with attendance_lock(db, 'accounts'):
        pass
    protect_last_admin(db, user, user.Role, False)
    before = account_state(user)
    user.IsActive = False
    user.TokenVersion = (user.TokenVersion or 0) + 1
    account_audit(db, current_user, user, 'ACCOUNT_DEACTIVATED', before)
    db.commit()
    return {"message": f"User '{user.Username}' deactivated successfully (Soft Deleted)"}
