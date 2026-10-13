from backend.app.models.review import VerifiedRoomChange
from backend.app.models.master import StudentStateHistory
from backend.app.core.time import business_day


def historical_room(db, punch):
    if punch.RoomNoSnapshot is not None:
        return punch.RoomNoSnapshot, 'PUNCH_SNAPSHOT'
    if not punch.StudentId:
        return None, 'UNKNOWN'
    # Exact captured application history takes precedence over date-only evidence.
    cache = db.info.setdefault('historical_rooms', {})
    if punch.StudentId not in cache:
        states = db.query(StudentStateHistory).filter_by(StudentId=punch.StudentId).order_by(StudentStateHistory.EffectiveFrom.desc()).all()
        changes = db.query(VerifiedRoomChange).filter_by(StudentId=punch.StudentId).order_by(VerifiedRoomChange.ChangeDate).all()
        cache[punch.StudentId] = states, changes
    states, changes = cache[punch.StudentId]
    state = next((row for row in states if row.EffectiveFrom is not None and row.EffectiveFrom <= punch.LogDate
                  and (row.EffectiveTo is None or row.EffectiveTo > punch.LogDate)), None)
    if state:
        return state.RoomNo, 'CAPTURED_STATE_HISTORY'
    day = business_day(punch.LogDate)
    for change in changes:
        if day == change.ChangeDate and change.EffectiveAt is None:
            return None, 'CHANGE_TIME_UNKNOWN'
    previous = [change for change in changes if change.ChangeDate <= day]
    if previous:
        change = previous[-1]
        if change.EffectiveAt and punch.LogDate < change.EffectiveAt:
            return change.OldRoomNo, 'OPERATOR_CONFIRMED'
        return change.NewRoomNo, 'OPERATOR_CONFIRMED'
    # A reported old room establishes a transition, not unlimited past history.
    return None, 'UNKNOWN'
