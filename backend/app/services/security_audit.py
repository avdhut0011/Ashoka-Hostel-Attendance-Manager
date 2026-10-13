import json
from backend.app.models.hardening import SecurityAudit

def account_state(user):
    return {'username': user.Username, 'role': user.Role, 'hostel_id': user.HostelId, 'active': user.IsActive}

def account_audit(db, actor, target, action, before=None, password_changed=False):
    db.flush()
    db.add(SecurityAudit(ActorId=actor.SystemUserId, TargetId=target.SystemUserId, Action=action,
        Details=json.dumps({'before': before, 'after': account_state(target), 'password_changed': password_changed})))
