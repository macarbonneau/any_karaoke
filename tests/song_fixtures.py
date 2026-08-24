"""Song fixtures shared by the tests that need a real .ak on disk."""

import json
import os
import tempfile

from any_karaoke.extractor import build_lyrics_alignment
from any_karaoke.lyrics_matcher import fill_lyrics_timings
from any_karaoke.song_files import LYRICS_ALIGNMENT_FILE, SONG_INFO_FILE, pack_song

LYRIC_TEXT = "one two three\nfour five\n\nsix seven\neight"

# Timed words the matcher lines the corrected lyrics up against
ALIGNMENT = {
    "segments": [
        {
            "start": 0.0,
            "end": 8.0,
            "text": "one two three four five six seven eight",
            "words": [
                {"word": word, "start": float(i), "end": i + 0.9}
                for i, word in enumerate("one two three four five six seven eight".split())
            ],
        }
    ]
}


def build_song(lyrics=LYRIC_TEXT, with_scaffold=True, extras=None):
    staging = tempfile.mkdtemp(prefix="staging_")
    with open(os.path.join(staging, SONG_INFO_FILE), "w", encoding="utf-8") as handle:
        json.dump({"title": "Test Song", "lyrics": []}, handle)
    with open(os.path.join(staging, "alignment_result.json"), "w", encoding="utf-8") as handle:
        json.dump(ALIGNMENT, handle)
    with open(os.path.join(staging, "asr_result.json"), "w", encoding="utf-8") as handle:
        json.dump({"language": "fr", "segments": []}, handle)
    for stem in ("music", "vocals"):
        with open(os.path.join(staging, stem + ".mp3"), "wb") as handle:
            handle.write(b"STEM-BYTES")
    if with_scaffold:
        scaffold = fill_lyrics_timings(build_lyrics_alignment(lyrics, "online"), ALIGNMENT)
        with open(os.path.join(staging, LYRICS_ALIGNMENT_FILE), "w", encoding="utf-8") as handle:
            json.dump(scaffold, handle)
    for name, body in (extras or {}).items():
        with open(os.path.join(staging, name), "w", encoding="utf-8") as handle:
            handle.write(body)

    return pack_song(staging, os.path.join(tempfile.mkdtemp(prefix="library_"), "Test Song.ak"))
