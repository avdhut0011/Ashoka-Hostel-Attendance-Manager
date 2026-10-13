"""Resolve installed runtime metadata only; never imports application/database code."""
from importlib.metadata import distribution
from pathlib import Path
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

ROOTS = ['fastapi', 'uvicorn[standard]', 'sqlalchemy', 'pydantic', 'pydantic-settings', 'pyodbc',
         'alembic', 'PyJWT[crypto]', 'bcrypt', 'openpyxl', 'tzdata']

def lock():
    queued = [Requirement(value) for value in ROOTS]
    resolved, extras_seen = {}, {}
    while queued:
        requirement = queued.pop()
        name = canonicalize_name(requirement.name)
        extras = set(requirement.extras)
        previous = extras_seen.get(name)
        if previous is not None and extras <= previous:
            continue
        extras_seen[name] = (previous or set()) | extras
        dist = distribution(name)
        resolved[name] = dist.version
        for value in dist.requires or []:
            dependency = Requirement(value)
            if dependency.marker is None or any(dependency.marker.evaluate({'extra': extra}) for extra in {''} | extras_seen[name]):
                queued.append(dependency)
    Path('backend/requirements.lock').write_text('# Tested Python 3.11 / Windows runtime; install with -r this file.\n' + '\n'.join(f'{name}=={version}' for name, version in sorted(resolved.items())) + '\n', encoding='utf-8')
    roots = [Requirement(value) for value in ROOTS]
    Path('backend/requirements.txt').write_text('# Direct runtime dependencies; reproducible installs use requirements.lock.\n' + '\n'.join(
        f'{r.name}' + ('[' + ','.join(sorted(r.extras)) + ']' if r.extras else '') + '==' + resolved[canonicalize_name(r.name)] for r in roots) + '\n', encoding='utf-8')
    print(f'Locked {len(resolved)} runtime packages; test/audit tools excluded.')

if __name__ == '__main__':
    lock()
