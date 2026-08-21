"""Finding the bundled artwork.

The media folder sits at the repository root rather than inside the package, so it is
looked up relative to this file. Everything returns None when the file is not there and
every caller treats the logo as optional, so a non editable install without the media
folder still runs, just without the artwork.
"""

import os

LOGO_FILE = "any_karaoke_logo.png"
ICON_FILE = "any_karaoke_logo_128x128.png"

_PACKAGE_DIR = os.path.dirname(os.path.realpath(__file__))

# Checked in order: bundled beside the package first, then the checkout's media folder
_SEARCH_PATHS = (
    os.path.join(_PACKAGE_DIR, "media"),
    os.path.abspath(os.path.join(_PACKAGE_DIR, "..", "..", "media")),
)


def asset_path(name):
    """Full path to a media file, or None when it cannot be found."""
    for folder in _SEARCH_PATHS:
        candidate = os.path.join(folder, name)
        if os.path.isfile(candidate):
            return candidate
    return None


def logo_path():
    """The full resolution logo, for drawing at size."""
    return asset_path(LOGO_FILE)


def icon_path():
    """The small square logo, for window icons."""
    return asset_path(ICON_FILE) or logo_path()
