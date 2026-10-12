"""Read-only access to an .msi file's internal database, using Windows' own msi.dll.

An .msi file is a small database: tables such as Property, File, Directory and Registry describe
what the installer *would* do. Opening it read-only and querying these tables runs nothing.

This uses ctypes (Python's built-in way to call Windows DLL functions) instead of a COM wrapper,
because it gives reliable access to binary streams (the embedded cabinet that holds the files).
"""

import ctypes
import re
from ctypes import wintypes
from pathlib import Path
from typing import Self

MSIHANDLE = wintypes.DWORD
ERROR_SUCCESS = 0
ERROR_MORE_DATA = 234
ERROR_NO_MORE_ITEMS = 259
ERROR_INVALID_DATATYPE = 1804  # returned when asking for a binary column as text
MSICOLINFO_NAMES = 0
BINARY_PLACEHOLDER = "<binary>"

_msi = ctypes.WinDLL("msi")
_msi.MsiOpenDatabaseW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, ctypes.POINTER(MSIHANDLE)]
_msi.MsiDatabaseOpenViewW.argtypes = [MSIHANDLE, wintypes.LPCWSTR, ctypes.POINTER(MSIHANDLE)]
_msi.MsiViewExecute.argtypes = [MSIHANDLE, MSIHANDLE]
_msi.MsiViewFetch.argtypes = [MSIHANDLE, ctypes.POINTER(MSIHANDLE)]
_msi.MsiViewGetColumnInfo.argtypes = [MSIHANDLE, ctypes.c_int, ctypes.POINTER(MSIHANDLE)]
_msi.MsiRecordGetFieldCount.argtypes = [MSIHANDLE]
_msi.MsiRecordGetFieldCount.restype = ctypes.c_uint
_msi.MsiRecordIsNull.argtypes = [MSIHANDLE, ctypes.c_uint]
_msi.MsiRecordIsNull.restype = wintypes.BOOL
_msi.MsiRecordGetStringW.argtypes = [MSIHANDLE, ctypes.c_uint, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
_msi.MsiRecordReadStream.argtypes = [MSIHANDLE, ctypes.c_uint, ctypes.c_char_p, ctypes.POINTER(wintypes.DWORD)]
_msi.MsiCloseHandle.argtypes = [MSIHANDLE]

_SAFE_NAME = re.compile(r"^[A-Za-z0-9_.#\-]+$")


class MsiError(Exception):
    pass


def _check(code: int, what: str) -> None:
    if code != ERROR_SUCCESS:
        raise MsiError(f"{what} failed (Windows error {code})")


def _get_string(record: int, field: int) -> str | None:
    if _msi.MsiRecordIsNull(record, field):
        return None
    size = wintypes.DWORD(0)
    buf = ctypes.create_unicode_buffer(1)
    code = _msi.MsiRecordGetStringW(record, field, buf, ctypes.byref(size))
    if code == ERROR_INVALID_DATATYPE:
        return BINARY_PLACEHOLDER  # binary data (e.g. Binary/Icon tables); read it with read_stream()
    if code == ERROR_MORE_DATA:
        size.value += 1  # room for the terminating null
        buf = ctypes.create_unicode_buffer(size.value)
        code = _msi.MsiRecordGetStringW(record, field, buf, ctypes.byref(size))
    _check(code, "MsiRecordGetString")
    return buf.value


class MsiDatabase:
    """Use as: `with MsiDatabase(path) as db: rows = db.rows("File")`."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._handle = MSIHANDLE(0)

    def __enter__(self) -> Self:
        # Second argument None = MSIDBOPEN_READONLY: the file cannot be changed.
        _check(_msi.MsiOpenDatabaseW(str(self.path), None, ctypes.byref(self._handle)), "MsiOpenDatabase")
        return self

    def __exit__(self, *exc) -> None:
        _msi.MsiCloseHandle(self._handle)

    def query(self, sql: str) -> list[dict[str, str | None]]:
        """Run a SELECT and return rows as {column name: value}. All values come back as text."""
        view = MSIHANDLE(0)
        _check(_msi.MsiDatabaseOpenViewW(self._handle, sql, ctypes.byref(view)), f"query {sql!r}")
        try:
            _check(_msi.MsiViewExecute(view, 0), "MsiViewExecute")
            names_rec = MSIHANDLE(0)
            _check(_msi.MsiViewGetColumnInfo(view, MSICOLINFO_NAMES, ctypes.byref(names_rec)), "column info")
            n = _msi.MsiRecordGetFieldCount(names_rec)
            columns = [_get_string(names_rec, i) or f"col{i}" for i in range(1, n + 1)]
            _msi.MsiCloseHandle(names_rec)

            rows = []
            while True:
                rec = MSIHANDLE(0)
                code = _msi.MsiViewFetch(view, ctypes.byref(rec))
                if code == ERROR_NO_MORE_ITEMS:
                    break
                _check(code, "MsiViewFetch")
                rows.append({col: _get_string(rec, i) for i, col in enumerate(columns, start=1)})
                _msi.MsiCloseHandle(rec)
            return rows
        finally:
            _msi.MsiCloseHandle(view)

    def tables(self) -> set[str]:
        return {r["Name"] for r in self.query("SELECT `Name` FROM `_Tables`") if r["Name"]}

    def rows(self, table: str) -> list[dict[str, str | None]]:
        """All rows of a table, or [] if the installer doesn't have that table."""
        if table not in self.tables():
            return []
        return self.query(f"SELECT * FROM `{table}`")

    def read_stream(self, name: str) -> bytes:
        """Read an embedded binary stream (e.g. the cabinet '#cab1.cab' -> name 'cab1.cab')."""
        if not _SAFE_NAME.match(name):
            raise MsiError(f"unexpected stream name: {name!r}")
        view = MSIHANDLE(0)
        sql = f"SELECT `Data` FROM `_Streams` WHERE `Name`='{name}'"
        _check(_msi.MsiDatabaseOpenViewW(self._handle, sql, ctypes.byref(view)), "open stream view")
        try:
            _check(_msi.MsiViewExecute(view, 0), "MsiViewExecute")
            rec = MSIHANDLE(0)
            code = _msi.MsiViewFetch(view, ctypes.byref(rec))
            if code == ERROR_NO_MORE_ITEMS:
                raise MsiError(f"stream not found: {name}")
            _check(code, "MsiViewFetch")
            try:
                chunks = []
                while True:
                    buf = ctypes.create_string_buffer(1024 * 1024)
                    size = wintypes.DWORD(len(buf))
                    _check(_msi.MsiRecordReadStream(rec, 1, buf, ctypes.byref(size)), "MsiRecordReadStream")
                    if size.value == 0:
                        break
                    chunks.append(buf.raw[: size.value])
                return b"".join(chunks)
            finally:
                _msi.MsiCloseHandle(rec)
        finally:
            _msi.MsiCloseHandle(view)
