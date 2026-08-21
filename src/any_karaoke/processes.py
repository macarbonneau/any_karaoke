"""Launching the sibling app in its own process.

The player and the manager can each start the other. Both run as `python -m <module>`
rather than by calling the console script, so it works from an editable checkout, from an
installed package and from `uv run` alike.
"""

import subprocess
import sys


def launch_module(module, *args):
    """Start `python -m module args...` without blocking. Returns the Popen handle."""
    return subprocess.Popen([sys.executable, "-m", module, *[str(a) for a in args]])


def is_running(process):
    """True while a handle from launch_module is still alive."""
    return process is not None and process.poll() is None
