"""Layout of an extracted karaoke song folder.

Stems used to always be wav. They are written as mp3 now, so anything reading a song
folder has to accept either and existing wav libraries keep working.
"""

import os

SONG_INFO_FILE = "any_karaoke_file.json"
STEM_NAMES = ("music", "vocals")

# Preferred first
STEM_EXTENSIONS = (".mp3", ".wav")


def find_stem(song_dir, stem_name):
    """Return the path to a stem in whichever supported format is present, or None."""
    if not song_dir:
        return None

    for extension in STEM_EXTENSIONS:
        candidate = os.path.join(song_dir, stem_name + extension)
        if os.path.isfile(candidate):
            return candidate

    return None


def song_info_path(song_dir):
    return os.path.join(song_dir, SONG_INFO_FILE)


def is_karaoke_folder(song_dir):
    """True when the folder holds a song description and both stems."""
    if not song_dir or not os.path.isfile(song_info_path(song_dir)):
        return False

    return all(find_stem(song_dir, stem_name) for stem_name in STEM_NAMES)


def missing_parts(song_dir):
    """Human readable list of what a folder is missing, for error messages."""
    missing = []
    if not song_dir or not os.path.isfile(song_info_path(song_dir)):
        missing.append(SONG_INFO_FILE)

    for stem_name in STEM_NAMES:
        if not find_stem(song_dir, stem_name):
            missing.append(f"{stem_name} ({' or '.join(STEM_EXTENSIONS)})")

    return missing
