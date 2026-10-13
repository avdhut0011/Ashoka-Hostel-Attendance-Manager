from typing import List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload
from backend.app.core.database import get_db
from backend.app.core.security import get_current_user, require_roles
from backend.app.core.locking import attendance_lock
from backend.app.models.master import Device, Hostel, DeviceStateHistory
from backend.app.models.security import User, SystemEvent
from backend.app.schemas.schemas import DeviceResponse, DeviceCreate
from backend.app.services.state_history import change_state
from backend.app.core.time import local_now

router = APIRouter(prefix='/devices', tags=['Devices'])
class DeviceStatusUpdate(BaseModel):
    is_active: bool

def validate_hostel(db, hostel_id, active):
    if active and (not hostel_id or not db.query(Hostel).filter_by(HostelId=hostel_id, IsActive=True).first()):
        raise HTTPException(400, 'Active devices require an active assigned hostel')
    if hostel_id and not db.query(Hostel).filter_by(HostelId=hostel_id).first():
        raise HTTPException(400, 'Hostel not found')

def response(device):
    res = DeviceResponse.model_validate(device)
    res.HostelName = device.hostel.HostelName if device.hostel else None
    return res

@router.get('', response_model=List[DeviceResponse])
def list_devices(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    query = db.query(Device).options(joinedload(Device.hostel))
    if current_user.Role == 'WARDEN':
        query = query.filter(Device.HostelId == current_user.HostelId)
    return [response(d) for d in query.all()]

@router.post('', response_model=DeviceResponse)
def create_device(device_in: DeviceCreate, db: Session = Depends(get_db), current_user: User = Depends(require_roles(['ADMIN', 'IT_ADMIN']))):
    with attendance_lock(db):
        validate_hostel(db, device_in.HostelId, device_in.IsActive)
        if db.query(Device).filter_by(DeviceId=device_in.DeviceId).first():
            raise HTTPException(400, 'Device already exists')
        device = Device(**device_in.model_dump())
        db.add(device)
        db.flush()
        db.add(DeviceStateHistory(DeviceId=device.DeviceId, HostelId=device.HostelId,
                                  IsActive=device.IsActive, EffectiveFrom=local_now()))
        db.add(SystemEvent(EventType='DEVICE_CREATED', Description=f'Device {device.DeviceId} configured', CreatedBy=current_user.Username))
        db.commit()
        db.refresh(device)
        return response(device)

@router.put('/{device_id}', response_model=DeviceResponse)
def update_device(device_id: int, device_in: DeviceCreate, db: Session = Depends(get_db), current_user: User = Depends(require_roles(['ADMIN', 'IT_ADMIN']))):
    with attendance_lock(db):
        device = db.query(Device).filter_by(DeviceId=device_id).populate_existing().first()
        if not device:
            raise HTTPException(404, 'Device not found')
        if device_in.DeviceId != device_id:
            raise HTTPException(400, 'DeviceId cannot change')
        validate_hostel(db, device_in.HostelId, device_in.IsActive)
        change_state(db, device, {'DeviceName': device_in.DeviceName, 'HostelId': device_in.HostelId, 'IsActive': device_in.IsActive})
        db.add(SystemEvent(EventType='DEVICE_UPDATED', Description=f'Device {device_id} configuration changed', CreatedBy=current_user.Username))
        db.commit()
        db.refresh(device)
        return response(device)

@router.put('/{device_id}/status', response_model=DeviceResponse)
def update_device_status(device_id: int, status_in: DeviceStatusUpdate, db: Session = Depends(get_db), current_user: User = Depends(require_roles(['ADMIN', 'IT_ADMIN']))):
    with attendance_lock(db):
        device = db.query(Device).filter_by(DeviceId=device_id).populate_existing().first()
        if not device:
            raise HTTPException(404, 'Device not found')
        return update_device(device_id, DeviceCreate(DeviceId=device_id, DeviceName=device.DeviceName, HostelId=device.HostelId, IsActive=status_in.is_active), db, current_user)

@router.delete('/{device_id}')
def delete_device(device_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_roles(['ADMIN', 'IT_ADMIN']))):
    update_device_status(device_id, DeviceStatusUpdate(is_active=False), db, current_user)
    return {'message': 'Device deactivated'}
