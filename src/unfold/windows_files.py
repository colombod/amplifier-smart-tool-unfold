"""No-reparse Windows file access with held, non-renamable ancestors.

CreateFile handles deny write/delete sharing while validation and I/O run.
Deletion targets the verified handle, never a reopened pathname.
"""

import ctypes
import errno
import os
from contextlib import contextmanager
from ctypes import wintypes
from pathlib import Path

from .models import UnfoldError


class AttributeTag(ctypes.Structure):
    _fields_ = [("attributes", wintypes.DWORD), ("tag", wintypes.DWORD)]


class Disposition(ctypes.Structure):
    _fields_ = [("delete", ctypes.c_ubyte)]


def _api():
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.CreateFileW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    api.CreateFileW.restype = wintypes.HANDLE
    api.CloseHandle.argtypes = [wintypes.HANDLE]
    api.CloseHandle.restype = wintypes.BOOL
    api.GetFileInformationByHandleEx.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    api.GetFileInformationByHandleEx.restype = wintypes.BOOL
    api.GetFileType.argtypes = [wintypes.HANDLE]
    api.GetFileType.restype = wintypes.DWORD
    api.SetFileInformationByHandle.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    api.SetFileInformationByHandle.restype = wintypes.BOOL
    return api


def _long_path(path):
    value = str(path)
    if value.startswith("\\\\?\\"):
        return value
    if value.startswith("\\\\"):
        return "\\\\?\\UNC\\" + value[2:]
    return "\\\\?\\" + value


def _open(api, path, access, disposition, directory=False):
    # OPEN_REPARSE_POINT prevents following the final component. Held ancestors
    # cannot be replaced or converted to reparse points during the next open.
    handle = api.CreateFileW(
        _long_path(path), access, 1, None, disposition, 0x00200000 | 0x02000000, None
    )
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        info = AttributeTag()
        if not api.GetFileInformationByHandleEx(handle, 9, ctypes.byref(info), ctypes.sizeof(info)):
            raise ctypes.WinError(ctypes.get_last_error())
        if info.attributes & 0x400:
            raise OSError(errno.ELOOP, "Reparse points are not library material")
        if bool(info.attributes & 0x10) != directory or api.GetFileType(handle) != 1:
            raise OSError(errno.EINVAL, "Expected a regular file or directory")
        return handle
    except BaseException:
        api.CloseHandle(handle)
        raise


@contextmanager
def open_file(root, relative, flags, delete=False):
    import msvcrt

    relative = Path(relative)
    if (
        relative.anchor
        or not relative.parts
        or any(
            p in (".", "..") or ":" in p or p.endswith((".", " ")) or Path(p).is_reserved()
            for p in relative.parts
        )
    ):
        raise UnfoldError("INVALID_INPUT", "Library path must be a confined relative path.")
    api = _api()
    handles = []
    handle = None
    descriptor = None
    try:
        root = Path(root).absolute()
        parent = Path(root.anchor)
        handles.append(_open(api, parent, 0, 3, directory=True))
        for part in (*root.parts[1:], *relative.parts[:-1]):
            parent /= part
            handles.append(_open(api, parent, 0, 3, directory=True))
        access_mode = flags & (os.O_WRONLY | os.O_RDWR)
        access = 0x40000000 if access_mode == os.O_WRONLY else 0x80000000
        if access_mode == os.O_RDWR:
            access |= 0x40000000
        if delete:
            access |= 0x10000
        disposition = (
            1 if flags & os.O_CREAT and flags & os.O_EXCL else 4 if flags & os.O_CREAT else 3
        )
        handle = _open(api, parent / relative.name, access, disposition)
        descriptor = msvcrt.open_osfhandle(
            handle, access_mode | os.O_BINARY | (flags & os.O_APPEND)
        )
        handle = None  # The CRT descriptor now owns the native handle.
        if flags & os.O_TRUNC:
            os.ftruncate(descriptor, 0)
        yield descriptor
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if handle is not None:
            api.CloseHandle(handle)
        for ancestor in reversed(handles):
            api.CloseHandle(ancestor)


def delete_open_file(descriptor):
    import msvcrt

    api = _api()
    disposition = Disposition(1)
    if not api.SetFileInformationByHandle(
        msvcrt.get_osfhandle(descriptor), 4, ctypes.byref(disposition), ctypes.sizeof(disposition)
    ):
        raise ctypes.WinError(ctypes.get_last_error())
