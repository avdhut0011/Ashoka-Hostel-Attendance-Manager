"""Source eligibility: active registered devices, current activation period only."""
from sqlalchemy import and_, or_, false, cast, DateTime
from backend.app.models.master import Device, DeviceStateHistory


def active_device_windows(db, device_ids=None):
    query = db.query(Device).filter(Device.IsActive == True)
    if device_ids is not None:
        query = query.filter(Device.DeviceId.in_(device_ids))
    devices = query.populate_existing().all()
    if not devices:
        return {}
    histories = {device.DeviceId: [] for device in devices}
    ids = list(histories)
    for offset in range(0, len(ids), 500):
        for state in db.query(DeviceStateHistory).filter(DeviceStateHistory.DeviceId.in_(ids[offset:offset + 500])).order_by(
                DeviceStateHistory.EffectiveFrom.desc(), DeviceStateHistory.StateId.desc()):
            histories[state.DeviceId].append(state)
    windows = {}
    for device in devices:
        states = histories[device.DeviceId]
        if states and (not states[0].IsActive or states[0].EffectiveTo is not None):
            # An out-of-band DB toggle has no trustworthy current activation boundary.
            import logging
            logging.getLogger('SyncWorker').error('Active device %s has inconsistent activation history; record its status through the Devices page', device.DeviceId)
            raise ValueError('Active device has inconsistent activation history')
        cutoff = None
        for state in states:
            if not state.IsActive:
                break
            cutoff = state.EffectiveFrom
        # Existing continuously active devices with no history retain the normal
        # checkpoint. No activation time is invented or backfilled for them.
        windows[device.DeviceId] = cutoff
    return windows


def device_predicate(table, windows, sqlserver=False):
    groups = {}
    for device_id, cutoff in windows.items():
        groups.setdefault(cutoff, []).append(device_id)
    clauses = []
    for cutoff, device_ids in groups.items():
        condition = table.c.DeviceId.in_(device_ids)
        if cutoff is not None:
            # Activation history uses SQL Server DATETIME. Match its stored
            # precision, rather than comparing a DATETIME2 driver parameter.
            boundary = cast(cutoff, DateTime) if sqlserver else cutoff
            condition = and_(condition, table.c.LogDate >= boundary)
        clauses.append(condition)
    return or_(*clauses) if clauses else false()


def eligible_source_rows(source, table, windows, conditions, batch_size):
    """Chunk device parameters below SQL Server's limit, then merge by source ID."""
    from sqlalchemy import select
    items = list(windows.items())
    rows = []
    for offset in range(0, len(items), 500):
        group = dict(items[offset:offset + 500])
        rows.extend(source.execute(select(table).where(*conditions, device_predicate(table, group, source.get_bind().dialect.name == 'mssql'))
                                   .order_by(table.c.DeviceLogId).limit(batch_size)).all())
    return sorted(rows, key=lambda row: row.DeviceLogId)[:batch_size]
