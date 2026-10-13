"""Transactional invalidations shared by API and the separate sync worker."""
from sqlalchemy import event, select
from sqlalchemy.orm import Session
from backend.app.models import Student, Device, Hostel, ProcessedPunch, StudentCurrentStatus, AttendanceOverride
from backend.app.models.review import VerifiedRoomChange
from backend.app.models.hardening import AttendanceRevision

WATCHED = (Student, Device, Hostel, ProcessedPunch, StudentCurrentStatus, AttendanceOverride, VerifiedRoomChange)


@event.listens_for(Session, 'after_flush')
def record_change(session, context):
    changed = any(isinstance(row, WATCHED) for row in session.new | session.deleted)
    changed = changed or any(isinstance(row, WATCHED) and session.is_modified(row, include_collections=False)
                             for row in session.dirty)
    if changed:
        # Same transaction as the changes; rollback removes this notification too.
        connection = session.connection()
        table = AttendanceRevision.__table__
        statement = select(table.c.Version).where(table.c.RevisionId == 1).with_hint(table, 'WITH (UPDLOCK, HOLDLOCK)', 'mssql')
        version = connection.execute(statement).scalar_one_or_none()
        if version is None:
            connection.execute(table.insert().values(RevisionId=1, Version=1))
        else:
            connection.execute(table.update().where(table.c.RevisionId == 1).values(Version=table.c.Version + 1))


def change_marker(db):
    # The revision write lock lasts until commit; rollback/savepoints restore it.
    # This remains correct for out-of-order commits without scanning a growing log.
    version = db.query(AttendanceRevision.Version).filter_by(RevisionId=1).scalar() or 0
    return 0, int(version)
