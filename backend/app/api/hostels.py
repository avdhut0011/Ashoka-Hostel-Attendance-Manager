from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.app.core.database import get_db
from backend.app.core.security import get_current_user, require_roles
from backend.app.models.master import Hostel
from backend.app.models.security import User
from backend.app.core.locking import attendance_lock
from backend.app.schemas.schemas import HostelResponse, HostelCreate

router = APIRouter(prefix="/hostels", tags=["Hostels"])

class HostelStatusUpdate(BaseModel):
    is_active: bool

@router.get("", response_model=List[HostelResponse])
def list_hostels(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    query = db.query(Hostel)
    if current_user.Role == "WARDEN":
        query = query.filter(Hostel.HostelId == current_user.HostelId)
    return query.all()

@router.post("", response_model=HostelResponse)
def create_hostel(
    hostel_in: HostelCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(["ADMIN", "IT_ADMIN"]))
):
    with attendance_lock(db):
        pass
    hostel = Hostel(
        HostelName=hostel_in.HostelName,
        HostelCode=hostel_in.HostelCode,
        IsActive=hostel_in.IsActive
    )
    db.add(hostel)
    db.commit()
    db.refresh(hostel)
    return hostel

@router.put("/{hostel_id}", response_model=HostelResponse)
def update_hostel(
    hostel_id: int,
    hostel_in: HostelCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(["ADMIN", "IT_ADMIN"]))
):
    with attendance_lock(db):
        pass
    hostel = db.query(Hostel).filter_by(HostelId=hostel_id).first()
    if not hostel:
        raise HTTPException(status_code=404, detail="Hostel not found")

    hostel.HostelName = hostel_in.HostelName
    hostel.HostelCode = hostel_in.HostelCode
    hostel.IsActive = hostel_in.IsActive
    db.commit()
    db.refresh(hostel)
    return hostel

@router.put("/{hostel_id}/status", response_model=HostelResponse)
def update_hostel_status(
    hostel_id: int,
    status_in: HostelStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(["ADMIN", "IT_ADMIN"]))
):
    with attendance_lock(db):
        pass
    hostel = db.query(Hostel).filter_by(HostelId=hostel_id).first()
    if not hostel:
        raise HTTPException(status_code=404, detail="Hostel not found")

    hostel.IsActive = status_in.is_active
    db.commit()
    db.refresh(hostel)
    return hostel

@router.delete("/{hostel_id}")
def delete_hostel(
    hostel_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(["ADMIN", "IT_ADMIN"]))
):
    with attendance_lock(db):
        pass
    hostel = db.query(Hostel).filter_by(HostelId=hostel_id).first()
    if not hostel:
        raise HTTPException(status_code=404, detail="Hostel not found")

    hostel.IsActive = False
    db.commit()
    return {"message": f"Hostel '{hostel.HostelName}' deactivated (soft-deleted) successfully"}
