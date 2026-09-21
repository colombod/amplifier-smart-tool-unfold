"""Exercise secure I/O against the host filesystem, including Windows junctions."""

import hashlib
import os
import subprocess

import pytest

from unfold.models import UnfoldError
from unfold.store import Store, read_at, write_all


def test_offset_io_and_verified_deletion(tmp_path, monkeypatch):
    store = Store(tmp_path / "library")
    # Exercise the portable offset path even on POSIX.
    monkeypatch.delattr(os, "pread", raising=False)
    monkeypatch.delattr(os, "pwrite", raising=False)
    with store.open_relative("assets/item", os.O_CREAT | os.O_EXCL | os.O_RDWR) as fd:
        write_all(fd, b"abcdef")
        write_all(fd, b"XY", 2)
        assert read_at(fd, 4, 1) == b"bXYe"
    with pytest.raises(UnfoldError):
        store.unlink_verified_relative("assets/item", "wrong")
    assert (store.root / "assets/item").read_bytes() == b"abXYef"
    assert store.unlink_verified_relative("assets/item", hashlib.sha256(b"abXYef").hexdigest())
    assert not (store.root / "assets/item").exists()
    assert not store.unlink_verified_relative("assets/item", "missing")


def test_exclusive_create_preserves_existing_file(tmp_path):
    store = Store(tmp_path / "library")
    target = store.root / "assets/item"
    target.write_bytes(b"original")
    with pytest.raises(UnfoldError):
        with store.open_relative("assets/item", os.O_CREAT | os.O_EXCL | os.O_WRONLY):
            pytest.fail("Existing file was opened")
    assert target.read_bytes() == b"original"


def test_redirected_parent_cannot_read_write_or_delete(tmp_path):
    store = Store(tmp_path / "library")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "item").write_bytes(b"private")
    link = store.root / "assets/redirect"
    if os.name == "nt":
        subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(outside)], check=True, capture_output=True
        )
    else:
        link.symlink_to(outside, target_is_directory=True)
    try:
        for flags in (os.O_RDONLY, os.O_WRONLY | os.O_TRUNC):
            with pytest.raises(UnfoldError):
                with store.open_relative("assets/redirect/item", flags):
                    pytest.fail("Redirected file was opened")
        with pytest.raises(UnfoldError):
            store.unlink_verified_relative(
                "assets/redirect/item", hashlib.sha256(b"private").hexdigest()
            )
        assert (outside / "item").read_bytes() == b"private"
    finally:
        if os.name == "nt":
            link.rmdir()
        else:
            link.unlink()


@pytest.mark.skipif(os.name != "nt", reason="Windows handle sharing protection")
def test_open_handle_blocks_parent_replacement_and_file_writes(tmp_path):
    store = Store(tmp_path / "library")
    parent = store.root / "assets/nested"
    parent.mkdir()
    target = parent / "item"
    target.write_bytes(b"original")
    with store.open_relative("assets/nested/item", os.O_RDONLY) as fd:
        with pytest.raises(OSError):
            parent.rename(parent.with_name("moved"))
        with pytest.raises(OSError):
            target.write_bytes(b"changed")
        assert os.read(fd, 100) == b"original"
    target.write_bytes(b"released")


@pytest.mark.skipif(os.name != "nt", reason="Windows path aliases")
@pytest.mark.parametrize(
    "name", ["C:item", "assets/item:stream", "assets/NUL", "assets/item.", "assets/item "]
)
def test_windows_aliases_rejected(tmp_path, name):
    store = Store(tmp_path / "library")
    with pytest.raises(UnfoldError):
        with store.open_relative(name, os.O_CREAT | os.O_WRONLY):
            pytest.fail("Windows alias was opened")
