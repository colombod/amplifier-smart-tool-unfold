"""Transactional records, stable identities and an ordered public change log."""

import hashlib
import json
import os
import sqlite3
import stat
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from .models import UnfoldError


def uid():
    return uuid.uuid4().hex


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_json(path, data):
    path = Path(path)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, indent=2) + "\n")
    temporary.replace(path)


def write_all(descriptor, data, offset=None):
    """Write every byte or fail loudly; ``os.write`` may legally short-write."""
    view = memoryview(data)
    position = 0
    while position < len(view):
        written = (
            os.pwrite(descriptor, view[position:], offset + position)
            if offset is not None
            else os.write(descriptor, view[position:])
        )
        if written <= 0:
            raise OSError("short write")
        position += written


class Store:
    def __init__(self, root):
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "operations").mkdir(exist_ok=True)
        (self.root / "assets").mkdir(exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS records (
                    id TEXT PRIMARY KEY, kind TEXT NOT NULL, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS events (
                    cursor INTEGER PRIMARY KEY AUTOINCREMENT, time REAL NOT NULL,
                    kind TEXT NOT NULL, subject TEXT NOT NULL, data TEXT NOT NULL);
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.root / "library.sqlite3", timeout=15)
        try:
            with db:
                yield db
        finally:
            db.close()

    def get(self, identity, kind=None, db=None):
        if db is None:
            with self.connect() as connection:
                return self.get(identity, kind, connection)
        row = db.execute("SELECT kind,data FROM records WHERE id=?", (identity,)).fetchone()
        if not row or (kind and row[0] != kind):
            raise UnfoldError("NOT_FOUND", "No such " + (kind or "record") + ": " + identity)
        return json.loads(row[1])

    def put(self, kind, data, db=None):
        if db is None:
            with self.connect() as connection:
                return self.put(kind, data, connection)
        db.execute(
            "INSERT INTO records VALUES (?,?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data",
            (data["id"], kind, json.dumps(data)),
        )

    def event(self, kind, subject, data, db=None):
        if db is None:
            with self.connect() as connection:
                return self.event(kind, subject, data, connection)
        db.execute(
            "INSERT INTO events(time,kind,subject,data) VALUES(?,?,?,?)",
            (time.time(), kind, subject, json.dumps(data)),
        )

    def list(self, kind):
        with self.connect() as db:
            return [
                json.loads(r[0])
                for r in db.execute("SELECT data FROM records WHERE kind=? ORDER BY rowid", (kind,))
            ]

    def events(self, after=0):
        if after < 0:
            raise UnfoldError("INVALID_INPUT", "Cursor must be nonnegative.")
        with self.connect() as db:
            return [
                {
                    "cursor": r[0],
                    "time": r[1],
                    "kind": r[2],
                    "subject": r[3],
                    "data": json.loads(r[4]),
                }
                for r in db.execute("SELECT * FROM events WHERE cursor>? ORDER BY cursor", (after,))
            ]

    def workspace(self, operation_id):
        if len(operation_id) != 32 or any(c not in "0123456789abcdef" for c in operation_id):
            raise UnfoldError("INVALID_INPUT", "Invalid operation identity.")
        path = self.root / "operations" / operation_id
        path.mkdir(exist_ok=True)
        return path

    @contextmanager
    def open_relative(self, relative, flags, mode=0o600):
        """Open one library-owned file through no-follow directory descriptors.

        Callers pass a relative identity-derived path only.  Every component is opened
        from the library root, so a replaced parent directory or symlink cannot turn a
        retained/staging operation into an arbitrary host-file operation.
        """
        relative = Path(relative)
        if (
            relative.is_absolute()
            or not relative.parts
            or any(part in ("", ".", "..") for part in relative.parts)
        ):
            raise UnfoldError("INVALID_INPUT", "Library path must be a confined relative path.")
        descriptors = []
        try:
            descriptors.append(os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW))
            for part in relative.parts[:-1]:
                descriptors.append(
                    os.open(
                        part,
                        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                        dir_fd=descriptors[-1],
                    )
                )
            fd = os.open(
                relative.name,
                flags | os.O_NOFOLLOW,
                mode,
                dir_fd=descriptors[-1],
            )
            try:
                yield fd
            finally:
                os.close(fd)
        except OSError as error:
            raise UnfoldError(
                "MATERIAL_CHANGED", "Library material is missing, changed, or uses a symlink."
            ) from error
        finally:
            for descriptor in reversed(descriptors):
                os.close(descriptor)

    def secure_stat(self, relative):
        """Return a regular-file stat through ``open_relative`` without path following."""
        with self.open_relative(relative, os.O_RDONLY | os.O_NONBLOCK) as fd:
            value = os.fstat(fd)
        if not stat.S_ISREG(value.st_mode):
            raise UnfoldError("MATERIAL_CHANGED", "Library material must be a regular file.")
        return value

    def unlink_relative(self, relative):
        """Remove one confined file without resolving an attacker-controlled path."""
        relative = Path(relative)
        if (
            relative.is_absolute()
            or not relative.parts
            or any(part in ("", ".", "..") for part in relative.parts)
        ):
            raise UnfoldError("INVALID_INPUT", "Library path must be a confined relative path.")
        descriptors = []
        try:
            descriptors.append(os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW))
            for part in relative.parts[:-1]:
                descriptors.append(
                    os.open(
                        part,
                        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                        dir_fd=descriptors[-1],
                    )
                )
            os.unlink(relative.name, dir_fd=descriptors[-1])
        except FileNotFoundError:
            return
        except OSError as error:
            raise UnfoldError(
                "MATERIAL_CHANGED", "Library material is missing, changed, or uses a symlink."
            ) from error
        finally:
            for descriptor in reversed(descriptors):
                os.close(descriptor)

    def unlink_verified_relative(self, relative, expected_sha256):
        """Delete one managed regular file only after checking its held descriptor.

        The parent descriptor chain is retained from the library root through the
        unlink.  A replacement ``assets`` parent therefore cannot redirect deletion
        outside the library, and no path ``exists``/``unlink`` check reopens it.
        ``False`` means the expected library entry was already missing.
        """
        relative = Path(relative)
        if (
            relative.is_absolute()
            or not relative.parts
            or any(part in ("", ".", "..") for part in relative.parts)
        ):
            raise UnfoldError("INVALID_INPUT", "Library path must be a confined relative path.")
        descriptors = []
        try:
            descriptors.append(os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW))
            root_identity = (os.fstat(descriptors[0]).st_dev, os.fstat(descriptors[0]).st_ino)
            parent_identities = []
            for part in relative.parts[:-1]:
                descriptors.append(
                    os.open(
                        part,
                        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                        dir_fd=descriptors[-1],
                    )
                )
                details = os.fstat(descriptors[-1])
                parent_identities.append((details.st_dev, details.st_ino))
            try:
                file_descriptor = os.open(
                    relative.name,
                    os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                    dir_fd=descriptors[-1],
                )
            except FileNotFoundError:
                return False
            try:
                details = os.fstat(file_descriptor)
                if not stat.S_ISREG(details.st_mode):
                    raise UnfoldError(
                        "MATERIAL_CHANGED", "Managed material must be a regular file."
                    )
                checksum = hashlib.sha256()
                while block := os.read(file_descriptor, 1024 * 1024):
                    checksum.update(block)
                if checksum.hexdigest() != expected_sha256:
                    raise UnfoldError(
                        "MATERIAL_CHANGED",
                        "Managed material changed; removal was not performed.",
                    )
                file_identity = (details.st_dev, details.st_ino, details.st_size)

                # A held directory descriptor remains usable after a same-UID rename.
                # Before unlinking through it, prove the library's current namespace
                # still names that exact root, ancestor chain, and file. This catches
                # parent replacement (including the post-hash victim swap) while
                # preserving no-follow descriptor-relative deletion. POSIX cannot make
                # unlink conditional on an inode; a hostile actor able to mutate this
                # process's namespace again after these final checks remains outside
                # this trusted-local-user boundary.
                current_root = os.stat(self.root, follow_symlinks=False)
                if (current_root.st_dev, current_root.st_ino) != root_identity:
                    raise UnfoldError(
                        "MATERIAL_CHANGED", "Library root changed; removal was not performed."
                    )
                for index, (part, expected_parent) in enumerate(
                    zip(relative.parts[:-1], parent_identities)
                ):
                    observed_parent = os.stat(
                        part, dir_fd=descriptors[index], follow_symlinks=False
                    )
                    if (
                        not stat.S_ISDIR(observed_parent.st_mode)
                        or (observed_parent.st_dev, observed_parent.st_ino) != expected_parent
                    ):
                        raise UnfoldError(
                            "MATERIAL_CHANGED",
                            "Library parent changed; removal was not performed.",
                        )
                observed_file = os.stat(
                    relative.name, dir_fd=descriptors[-1], follow_symlinks=False
                )
                if (
                    not stat.S_ISREG(observed_file.st_mode)
                    or (observed_file.st_dev, observed_file.st_ino, observed_file.st_size)
                    != file_identity
                ):
                    raise UnfoldError(
                        "MATERIAL_CHANGED",
                        "Managed material changed; removal was not performed.",
                    )
                # This name is resolved only through the still-open verified parent,
                # never through the mutable library pathname.
                os.unlink(relative.name, dir_fd=descriptors[-1])
            finally:
                os.close(file_descriptor)
            return True
        except OSError as error:
            raise UnfoldError(
                "MATERIAL_CHANGED", "Library material is missing, changed, or uses a symlink."
            ) from error
        finally:
            for descriptor in reversed(descriptors):
                os.close(descriptor)


@contextmanager
def portable_archive(destination):
    """Publish a complete ZIP without overwrite; failures never leave a partial export."""
    import os
    import tempfile
    import zipfile

    destination = Path(destination)
    descriptor, name = tempfile.mkstemp(prefix=".unfold-", suffix=".zip", dir=destination.parent)
    os.close(descriptor)
    temporary = Path(name)
    try:
        with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as archive:
            yield archive
        try:
            os.link(temporary, destination)
        except FileExistsError:
            raise UnfoldError("OUTPUT_EXISTS", "Choose a new ZIP destination.") from None
    finally:
        temporary.unlink(missing_ok=True)
