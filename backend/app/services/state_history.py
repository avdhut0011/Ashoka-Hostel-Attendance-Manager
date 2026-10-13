from sqlalchemy import or_
from backend.app.models.master import StudentStateHistory, DeviceStateHistory
from backend.app.core.time import local_now


def state_at(db, entity, when):
    model, key = (StudentStateHistory, 'StudentId') if hasattr(entity, 'StudentId') else (DeviceStateHistory, 'DeviceId')
    replay = db.info.get('replay_context')
    if replay:
        return next((state for state in replay['histories'].get((key, getattr(entity, key)), [])
                     if (state.EffectiveFrom is None or state.EffectiveFrom <= when)
                     and (state.EffectiveTo is None or state.EffectiveTo > when)), entity)
    return db.query(model).filter(getattr(model, key) == getattr(entity, key),
        or_(model.EffectiveFrom.is_(None), model.EffectiveFrom <= when),
        or_(model.EffectiveTo.is_(None), model.EffectiveTo > when)
    ).order_by(model.EffectiveFrom.desc(), model.StateId.desc()).first() or entity


def change_state(db, entity, changes, when=None):
    """Preserve a baseline only when a real user operation changes an entity."""
    when = when or local_now()
    student = hasattr(entity, 'StudentId')
    model, key = (StudentStateHistory, 'StudentId') if student else (DeviceStateHistory, 'DeviceId')
    fields = ['HostelId', 'RoomNo', 'RegistrationStatus'] if student else ['HostelId', 'IsActive']
    if not any(getattr(entity, f) != changes.get(f, getattr(entity, f)) for f in fields):
        for name, value in changes.items():
            setattr(entity, name, value)
        return
    previous = db.query(model).filter(getattr(model, key) == getattr(entity, key), model.EffectiveTo.is_(None)).all()
    if not previous:
        db.add(model(**{key: getattr(entity, key)}, **{f: getattr(entity, f) for f in fields}, EffectiveTo=when))
    else:
        for row in previous:
            row.EffectiveTo = when
    for name, value in changes.items():
        setattr(entity, name, value)
    db.add(model(**{key: getattr(entity, key)}, **{f: getattr(entity, f) for f in fields}, EffectiveFrom=when))
    db.flush()
