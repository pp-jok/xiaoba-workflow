import contextlib
import fcntl
from pathlib import Path


@contextlib.contextmanager
def file_lock(target: Path):
    target.parent.mkdir(parents=True, exist_ok=True)
    lock_path = target.parent / ".xiaoba-write.lock"
    with lock_path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
