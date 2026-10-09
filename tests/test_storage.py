import io

import pytest

from app.shared.storage import LocalFileStorage


@pytest.fixture
def storage(tmp_path):
    return LocalFileStorage(tmp_path / "files")


def test_save_open_roundtrip_and_returns_size(storage):
    size = storage.save("u1/s1/a.pdf", io.BytesIO(b"sadrzaj"))
    assert size == 7
    with storage.open("u1/s1/a.pdf") as f:
        assert f.read() == b"sadrzaj"


def test_delete_removes_file_and_is_idempotent(storage):
    storage.save("a.txt", io.BytesIO(b"x"))
    storage.delete("a.txt")
    storage.delete("a.txt")
    with pytest.raises(FileNotFoundError):
        storage.open("a.txt")


@pytest.mark.parametrize("key", ["../izvan.txt", "/etc/passwd", "a/../../izvan.txt", "", "."])
def test_keys_cannot_escape_root(storage, key):
    with pytest.raises(ValueError):
        storage.save(key, io.BytesIO(b"x"))


def test_large_file_is_streamed_without_loss(storage):
    data = b"ab" * (3 * 1024 * 1024)
    assert storage.save("big.bin", io.BytesIO(data)) == len(data)
    with storage.open("big.bin") as f:
        assert f.read() == data
