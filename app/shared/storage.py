import shutil
from pathlib import Path
from typing import BinaryIO, Protocol

from app.shared.config import get_settings


class FileStorage(Protocol):
    def save(self, key: str, data: BinaryIO) -> int:
        """Writes a file to the storage and returns the number of bytes written."""
        ...

    def open(self, key: str) -> BinaryIO: ...

    def delete(self, key: str) -> None:
        """Deletes a file; if it doesn't exist, nothing is done."""
        ...


class LocalFileStorage:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        # Key mustn't leave the root (e.g., "../../etc/passwd").
        if not path.is_relative_to(self.root) or path == self.root:
            raise ValueError(f"Invalid storage key: {key!r}")
        return path

    def save(self, key: str, data: BinaryIO) -> int:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as out:
            shutil.copyfileobj(data, out, length=1024 * 1024)
            return out.tell()

    def open(self, key: str) -> BinaryIO:
        return self._path(key).open("rb")

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)


def get_storage() -> FileStorage:
    return LocalFileStorage(get_settings().local_storage_path)
