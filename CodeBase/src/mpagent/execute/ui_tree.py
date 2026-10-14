"""Reads the "UI Tree" section of a Windows-MCP Snapshot result (FUNCTIONAL_TESTS_PLAN.md L4, L11, L17).

A Snapshot's text has an "Opened Windows" table (every window title on the desktop, browser tabs and chats
included) and a "UI Tree" structured per window:

    desktop
    ├── window "Programs and Features"
    │   ├── tool bar "Up band"
    │   │   └── (186,154) button "Up to "Programs" (Alt + Up Arrow)"  [action: click]

Only the UI Tree is used, and only the subtree of the host's main window, so a matching name in another
window (a browser tab, a chat, a search box) can never count.
"""

import json
import re
from dataclasses import dataclass

_TREE_START = re.compile(r"^\s*UI Tree:\s*$", re.MULTILINE)
_NODE = re.compile(r'^(?P<indent>[\s│├└─]*)(?:\(-?\d+,\s*-?\d+\)\s+)?(?P<type>[^"]*?)\s*"(?P<name>.*)"'
                   r'(?:\s+\[[^\]]*\])*\s*$')  # trailing [action: …] [value:"…"] groups


@dataclass(frozen=True)
class Node:
    depth: int
    type: str
    name: str


def decode(text: str) -> str:
    """Windows-MCP sometimes returns the Snapshot text as a JSON list of strings (seen in run
    20261013-145150); join it back into plain text. Plain text is returned unchanged."""
    if text.lstrip().startswith("["):
        try:
            items = json.loads(text)
        except json.JSONDecodeError:
            return text
        if isinstance(items, list) and all(isinstance(i, str) for i in items):
            return "\n".join(items)
    return text


def nodes(snapshot_text: str) -> list[Node]:
    """Every named node of the UI Tree section, in order, with its depth (indent width)."""
    snapshot_text = decode(snapshot_text)
    start = _TREE_START.search(snapshot_text)
    if not start:
        return []
    out = []
    for line in snapshot_text[start.end():].splitlines():
        m = _NODE.match(line)
        if m:
            out.append(Node(len(m.group("indent")), m.group("type").strip().casefold(), m.group("name")))
    return out


def host_windows(snapshot_text: str, main_window: str) -> list[list[Node]]:
    """Each host main window (a `window` node whose title matches `main_window`) with its whole subtree;
    the window node itself comes first."""
    pattern = re.compile(main_window, re.IGNORECASE)
    tree = nodes(snapshot_text)
    found: list[list[Node]] = []
    i = 0
    while i < len(tree):
        n = tree[i]
        if n.type == "window" and pattern.search(n.name):
            j = i + 1
            while j < len(tree) and tree[j].depth > n.depth:
                j += 1
            found.append(tree[i:j])
            i = j
        else:
            i += 1
    return found


def window_in_ui(texts: list[str], main_window: str, pattern: str) -> bool:
    """True if a host main window exists whose title, or a node name inside it, matches `pattern`."""
    rx = re.compile(pattern, re.IGNORECASE)
    return any(rx.search(n.name) for t in texts for w in host_windows(t, main_window) for n in w)
