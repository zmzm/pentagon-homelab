"""Safety checks shared by disposable application recovery tests."""
import os
from pathlib import Path


def require_private_restore(value):
    supplied = Path(value).absolute()
    path = supplied.resolve()
    if (supplied != path or len(path.parts) != 5 or path.parts[1] != 'tmp'
            or not path.parts[2].startswith('homelab-restore-')
            or path.parts[3:] != ('userdata', 'homelab')):
        raise RuntimeError('Application checks require a private temporary backup restore')
    root = Path('/tmp') / path.parts[2]
    if root.stat().st_mode & 0o777 != 0o700 or root.stat().st_uid != os.geteuid():
        raise RuntimeError('Temporary restore root must be private and owned by the verifier')
    return path
