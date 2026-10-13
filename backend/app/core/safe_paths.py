"""Reject Windows network/device paths before any filesystem resolution."""
def safe_request_path(path):
    return isinstance(path, str) and not (
        path.startswith('//') or any(c in path for c in ('\\', ':', '\x00'))
        or '..' in path.split('/')
    )
