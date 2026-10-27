"""Text on screen for the name tools (OCR_UI_PLAN.md O1-O13): Windows' own OCR on a capture of the host's windows.

click_ui and find_ui look here first, then in the UI Automation tree. OCR finds labels that UI Automation can't see
(e.g. tabs and toolbars a host draws itself) and is fast, but it doesn't know an element's type, so:
  - a label is the words of one OCR line between wide gaps, or two such phrases stacked directly (a two-line label);
  - an exact match is a whole label equal to the name; a "contains" match is the shortest run of words of a label
    that contains the name (case- and whitespace-insensitive, no look-alike characters, O5);
  - the caller clicks only a single exact match, or a single "contains" match when there is no exact one (O7).
Nothing here names a host or an app. The capture is read only; nothing is saved.
"""

import asyncio
import ctypes
from dataclasses import dataclass
from typing import Protocol

WORD_GAP = 1.0  # words further apart than this many word heights belong to different labels
STACK_GAP = 1.0  # a label's second line starts at most this many line heights below its first line


class OcrUnavailable(Exception):
    """Windows has no OCR engine for the user's languages (no OCR language installed)."""


@dataclass(frozen=True)
class Word:
    text: str
    left: int  # on screen (physical pixels)
    top: int
    right: int
    bottom: int


@dataclass(frozen=True)
class Hit:
    text: str  # the matched words as read
    left: int
    top: int
    right: int
    bottom: int

    @property
    def centre(self) -> tuple[int, int]:
        return (self.left + self.right) // 2, (self.top + self.bottom) // 2


class OcrReader(Protocol):
    """OCR of one screen rectangle; replaced by a fake in unit tests."""

    def read(self, left: int, top: int, right: int, bottom: int) -> list[list[Word]]: ...


def normalize(text: str) -> str:
    """Like the name tools: case-insensitive, every run of whitespace as one space."""
    return " ".join(text.split()).casefold()


def _join(words: list[Word]) -> str:
    return normalize(" ".join(w.text for w in words))


def _box(words: list[Word]) -> Hit:
    return Hit(" ".join(w.text for w in words), min(w.left for w in words), min(w.top for w in words),
               max(w.right for w in words), max(w.bottom for w in words))


def phrases(lines: list[list[Word]]) -> list[list[Word]]:
    """Each OCR line split into labels where the gap between two words is wider than WORD_GAP word heights."""
    out = []
    for line in lines:
        words = sorted(line, key=lambda w: w.left)
        current: list[Word] = []
        for w in words:
            if current:
                prev = current[-1]
                height = max(prev.bottom - prev.top, w.bottom - w.top, 1)
                if w.left - prev.right > WORD_GAP * height:
                    out.append(current)
                    current = []
            current.append(w)
        if current:
            out.append(current)
    return out


def _stacked(upper: list[Word], lower: list[Word]) -> bool:
    """`lower` is the second line of the same label: directly below `upper` and centred under it."""
    a, b = _box(upper), _box(lower)
    height = max(a.bottom - a.top, b.bottom - b.top, 1)
    gap = b.top - a.bottom
    width = max(a.right - a.left, b.right - b.left)
    return -height / 2 <= gap <= STACK_GAP * height and abs(a.centre[0] - b.centre[0]) <= width / 2


def find(lines: list[list[Word]], name: str) -> tuple[list[Hit], list[Hit]]:
    """(exact matches, "contains" matches) of `name` in OCR lines, in reading order, each box once."""
    wanted = normalize(name)
    if not wanted:
        return [], []
    labels = phrases(lines)
    exact: list[Hit] = []
    contains: list[Hit] = []
    for label in labels:
        if _join(label) == wanted:
            exact.append(_box(label))
            continue
        for i in range(len(label)):  # the shortest runs of words that contain the name
            for j in range(i, len(label)):
                if wanted in _join(label[i:j + 1]):
                    if not (j > i and wanted in _join(label[i + 1:j + 1])):
                        contains.append(_box(label[i:j + 1]))
                    break
    for upper in labels:  # two-line labels: only what neither line holds alone
        for lower in labels:
            if lower is upper or not _stacked(upper, lower):
                continue
            both = _join(upper + lower)
            if wanted not in both or wanted in _join(upper) or wanted in _join(lower):
                continue
            (exact if both == wanted else contains).append(_box(upper + lower))
    seen: set[tuple[int, int, int, int]] = set()

    def once(hits: list[Hit]) -> list[Hit]:
        out = []
        for h in sorted(hits, key=lambda h: (h.top, h.left)):
            key = (h.left, h.top, h.right, h.bottom)
            if key not in seen:
                seen.add(key)
                out.append(h)
        return out

    return once(exact), once(contains)


class WindowsOcr:
    """Windows' own OCR (Windows.Media.Ocr) on a screen capture (pywin32 BitBlt). Use it only from the name tools'
    worker thread: that thread is per-monitor DPI aware, so the capture and the UI Automation rectangles share
    physical pixels."""

    def __init__(self):
        self._engine = None

    def read(self, left: int, top: int, right: int, bottom: int) -> list[list[Word]]:
        from winrt.windows.graphics.imaging import (
            BitmapAlphaMode,
            BitmapPixelFormat,
            SoftwareBitmap,
        )
        from winrt.windows.media.ocr import OcrEngine
        from winrt.windows.storage.streams import DataWriter

        if self._engine is None:
            self._engine = OcrEngine.try_create_from_user_profile_languages()
            if self._engine is None:
                raise OcrUnavailable("Windows has no OCR language for the user's languages")
        left, top, right, bottom = _on_screen(left, top, right, bottom, OcrEngine.max_image_dimension)
        width, height = right - left, bottom - top
        if width <= 0 or height <= 0:
            return []
        writer = DataWriter()
        writer.write_bytes(_capture(left, top, width, height))
        bitmap = SoftwareBitmap.create_copy_from_buffer(writer.detach_buffer(), BitmapPixelFormat.BGRA8, width, height,
                                                        BitmapAlphaMode.PREMULTIPLIED)
        result = asyncio.run(_wait(self._engine.recognize_async(bitmap)))
        lines = []
        for line in result.lines:
            words = []
            for w in line.words:
                r = w.bounding_rect
                words.append(Word(w.text, left + int(r.x), top + int(r.y), left + int(r.x + r.width),
                                  top + int(r.y + r.height)))
            lines.append(words)
        return lines


async def _wait(operation):
    return await operation


def _on_screen(left: int, top: int, right: int, bottom: int, max_side: int) -> tuple[int, int, int, int]:
    """The rectangle cut to the desktop (a maximized window reaches a few pixels beyond it) and to OCR's size limit."""
    metrics = ctypes.windll.user32.GetSystemMetrics
    x0, y0 = metrics(76), metrics(77)  # SM_XVIRTUALSCREEN, SM_YVIRTUALSCREEN
    x1, y1 = x0 + metrics(78), y0 + metrics(79)  # SM_CXVIRTUALSCREEN, SM_CYVIRTUALSCREEN
    left, top = max(left, x0), max(top, y0)
    right, bottom = min(right, x1, left + max_side), min(bottom, y1, top + max_side)
    return left, top, right, bottom


def _capture(left: int, top: int, width: int, height: int) -> bytes:
    """The screen pixels of the rectangle as BGRA, top row first."""
    import win32con
    import win32gui
    import win32ui

    desktop = win32gui.GetDesktopWindow()
    screen = win32gui.GetWindowDC(desktop)
    source = win32ui.CreateDCFromHandle(screen)
    memory = source.CreateCompatibleDC()
    bitmap = win32ui.CreateBitmap()
    try:
        bitmap.CreateCompatibleBitmap(source, width, height)
        memory.SelectObject(bitmap)
        memory.BitBlt((0, 0), (width, height), source, (left, top), win32con.SRCCOPY)
        return bitmap.GetBitmapBits(True)
    finally:
        memory.DeleteDC()
        source.DeleteDC()
        win32gui.ReleaseDC(desktop, screen)
        win32gui.DeleteObject(bitmap.GetHandle())
