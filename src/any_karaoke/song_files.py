"""Reading a karaoke song, whether it is a .ak archive or a legacy folder.

A song is normally a single `.ak` file: a zip holding the stems, the timed lyrics and the
transcription artefacts at its root. Rename it to .zip and any archive tool opens it.

Songs extracted before the switch are plain folders with the same layout, so every reader
here takes a path that may be either and branches on os.path.isdir.
"""

import io
import json
import os
import zipfile
from contextlib import contextmanager

AK_EXTENSION = ".ak"
SONG_INFO_FILE = "any_karaoke_file.json"
LYRICS_ALIGNMENT_FILE = "lyrics_alignment.json"
STEM_NAMES = ("music", "vocals")

# Preferred first
STEM_EXTENSIONS = (".mp3", ".wav")

# mp3 and wav gain nothing from deflating, everything else is text
STORED_EXTENSIONS = (".mp3", ".wav", ".flac", ".ogg")


def is_archive(path):
    return bool(path) and os.path.isfile(path) and zipfile.is_zipfile(path)


def stem_names_for(stem_name):
    return [stem_name + extension for extension in STEM_EXTENSIONS]


# ================================================
# Listing
# ================================================
def list_entries(path):
    """Names held by a song, for either layout. Empty when it is not a song at all."""
    if not path:
        return []

    if os.path.isdir(path):
        return sorted(name for name in os.listdir(path) if os.path.isfile(os.path.join(path, name)))

    if is_archive(path):
        try:
            with zipfile.ZipFile(path) as archive:
                return sorted(archive.namelist())
        except (OSError, zipfile.BadZipFile):
            return []

    return []


def find_stem(song_path, stem_name):
    """Name of the stem entry in whichever supported format is present, or None.

    For a folder this is a full path, for an archive it is the entry name.
    """
    entries = set(list_entries(song_path))
    for candidate in stem_names_for(stem_name):
        if candidate in entries:
            return os.path.join(song_path, candidate) if os.path.isdir(song_path) else candidate

    return None


# ================================================
# Reading
# ================================================
def read_bytes(song_path, entry_name):
    if os.path.isdir(song_path):
        with open(os.path.join(song_path, entry_name), "rb") as handle:
            return handle.read()

    with zipfile.ZipFile(song_path) as archive:
        return archive.read(entry_name)


def read_song_info(song_path):
    """The parsed any_karaoke_file.json for either layout."""
    return json.loads(read_bytes(song_path, SONG_INFO_FILE).decode("utf-8"))


def read_optional_json(song_path, entry_name):
    """Parse an entry that may not be there, returning None instead of raising."""
    if entry_name not in set(list_entries(song_path)):
        return None

    try:
        return json.loads(read_bytes(song_path, entry_name).decode("utf-8"))
    except (OSError, ValueError, KeyError):
        return None


def read_lyrics_alignment(song_path):
    """The timed reference lyrics, or None for songs extracted before they existed."""
    return read_optional_json(song_path, LYRICS_ALIGNMENT_FILE)


@contextmanager
def open_stem(song_path, stem_name):
    """Binary file object for a stem, ready to hand to pygame.mixer.Sound.

    A folder yields a real handle, an archive yields the entry in memory, so callers do
    not care which layout they were given.
    """
    entry = find_stem(song_path, stem_name)
    if entry is None:
        raise FileNotFoundError(f"no {stem_name} stem in {song_path}")

    if os.path.isdir(song_path):
        handle = open(entry, "rb")
    else:
        with zipfile.ZipFile(song_path) as archive:
            handle = io.BytesIO(archive.read(entry))

    try:
        yield handle
    finally:
        handle.close()


# ================================================
# Validating
# ================================================
def is_song(song_path):
    """True when the path holds a song description and both stems."""
    entries = set(list_entries(song_path))
    if SONG_INFO_FILE not in entries:
        return False

    return all(any(name in entries for name in stem_names_for(stem)) for stem in STEM_NAMES)


def missing_parts(song_path):
    """Human readable list of what is missing, for error messages."""
    entries = set(list_entries(song_path))

    missing = []
    if SONG_INFO_FILE not in entries:
        missing.append(SONG_INFO_FILE)

    for stem in STEM_NAMES:
        if not any(name in entries for name in stem_names_for(stem)):
            missing.append(f"{stem} ({' or '.join(STEM_EXTENSIONS)})")

    return missing


def song_display_name(song_path):
    """Falls back to the file name when the song has no title tag."""
    base = os.path.basename(str(song_path).rstrip("\\/"))
    name, extension = os.path.splitext(base)
    return name if extension.lower() == AK_EXTENSION else base


# ================================================
# Writing
# ================================================
def pack_song(staging_dir, ak_path):
    """Zip a staging directory into a .ak file.

    Written to a temporary name alongside the target and renamed into place, so an
    interrupted run never leaves a half written archive that looks like a real song.
    """
    partial_path = ak_path + ".partial"
    os.makedirs(os.path.dirname(os.path.abspath(ak_path)), exist_ok=True)

    try:
        with zipfile.ZipFile(partial_path, "w") as archive:
            for name in sorted(os.listdir(staging_dir)):
                source = os.path.join(staging_dir, name)
                if not os.path.isfile(source):
                    continue
                extension = os.path.splitext(name)[1].lower()
                compression = zipfile.ZIP_STORED if extension in STORED_EXTENSIONS else zipfile.ZIP_DEFLATED
                archive.write(source, name, compress_type=compression)

        if os.path.exists(ak_path):
            os.remove(ak_path)
        os.replace(partial_path, ak_path)
    finally:
        if os.path.exists(partial_path):
            os.remove(partial_path)

    return ak_path
