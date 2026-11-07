"""Kernel-owned exclusivity; stale metadata never proves an active session."""
import fcntl
import json
from pathlib import Path


class SessionLock:
    def __init__(self, root):
        self.root = Path(root)
        self.file = None

    def __enter__(self):
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.file = (self.root / '.session.lock').open('a+')
        try:
            fcntl.flock(self.file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BaseException:
            self.file.close()
            raise
        self.publish(None)
        return self

    def publish(self, trial):
        self.file.seek(0)
        self.file.truncate()
        json.dump({'trial': str(trial) if trial else None}, self.file)
        self.file.flush()

    def __exit__(self, *_):
        self.publish(None)
        fcntl.flock(self.file, fcntl.LOCK_UN)
        self.file.close()


def active_trial(root):
    path = Path(root) / '.session.lock'
    if not path.exists():
        return None
    with path.open() as file:
        try:
            fcntl.flock(file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            try:
                value = json.load(file).get('trial')
                return Path(value) if value else None
            except (ValueError, OSError):
                return None
        else:
            fcntl.flock(file, fcntl.LOCK_UN)
            return None
