"""Correcting the lyrics of an already extracted song.

The lyrics that come back from api.lyrics.ovh are often wrong or missing, and once a song
is extracted there was no way to fix them short of running the whole pipeline again.

Everything needed to redo the timings is already inside the .ak: the timed words in
alignment_result.json, the detected language in asr_result.json, and the vocals stem. So
correcting lyrics never touches demucs or transcription, only the cheap parts:

* re-match, instant, lines the corrected words up against the timed words already stored
* re-align, a few seconds, force-aligns the corrected words against the vocals for exact
  timings. Needs the "extract" extra.
"""

import os
import shutil
import tempfile

from any_karaoke.extractor import ProgressReporter, build_lyrics_alignment, write_json
from any_karaoke.lyrics_matcher import fill_lyrics_timings
from any_karaoke.song_files import (
    LYRICS_ALIGNMENT_FILE,
    find_stem,
    pack_song,
    read_lyrics_alignment,
    read_optional_json,
    unpack_song,
)

CORRECTED_LYRICS_FILE = "corrected_lyrics.txt"
ALIGNMENT_RESULT_FILE = "alignment_result.json"
ASR_RESULT_FILE = "asr_result.json"

# Checked in order when the song has no scaffold to show yet
FALLBACK_LYRIC_FILES = (CORRECTED_LYRICS_FILE, "pasted_lyrics.txt", "online_lyrics.txt", "mp3_lyrics.txt")


def lyrics_text_from_scaffold(scaffold):
    """Lines back to plain text, with a blank line wherever the verse number changes."""
    lines = (scaffold or {}).get("lines") or []

    out = []
    previous_verse = None
    for line in lines:
        verse = line.get("verse", 0)
        if previous_verse is not None and verse != previous_verse:
            out.append("")
        out.append(line.get("text", ""))
        previous_verse = verse

    return "\n".join(out)


def read_editable_lyrics(song_path):
    """The text to put in the editor: the current reference lyrics, or the best we have."""
    text = lyrics_text_from_scaffold(read_lyrics_alignment(song_path))
    if text.strip():
        return text

    from any_karaoke.song_files import list_entries, read_bytes

    entries = set(list_entries(song_path))
    for name in FALLBACK_LYRIC_FILES:
        if name in entries:
            try:
                return read_bytes(song_path, name).decode("utf-8")
            except (OSError, UnicodeDecodeError):
                continue

    return ""


def song_language(staging_dir):
    """The language whisperX detected, needed to pick an alignment model."""
    asr_path = os.path.join(staging_dir, ASR_RESULT_FILE)
    if os.path.isfile(asr_path):
        import json

        try:
            with open(asr_path, encoding="utf-8") as handle:
                return json.load(handle).get("language") or "en"
        except (OSError, ValueError):
            pass
    return "en"


def force_align_lines(lines, vocals_path, language, models=None, progress=None):
    """Force-align already timed lines against the vocals, for exact word timings.

    The matched timings give each line its rough audio bounds, which is what whisperX
    needs; the aligner then places the words inside them. Lines it does not return keep
    what they had, so a partial result degrades rather than losing the song.
    """
    import whisperx

    from any_karaoke.extractor import WhisperModels

    progress = progress or ProgressReporter()
    models = models or WhisperModels()

    timed = [line for line in lines if line.get("start") is not None and line.get("end") is not None]
    if not timed:
        return lines

    progress.log(f"force aligning {len(timed)} lines against the vocals")
    model_a, metadata = models.align(language, progress=progress)
    audio = whisperx.load_audio(vocals_path)

    result = whisperx.align(
        [{"text": line["text"], "start": line["start"], "end": line["end"]} for line in timed],
        model_a,
        metadata,
        audio,
        models.device,
        return_char_alignments=False,
    )

    aligned = result.get("segments", []) if result else []
    for line, segment in zip(timed, aligned):
        words = [
            {"word": word.get("word", ""), "start": word["start"], "end": word["end"], "timing": "aligned"}
            for word in segment.get("words", [])
            if word.get("start") is not None and word.get("end") is not None
        ]
        if not words:
            continue  # keep the matched timings for this line

        line["words"] = words
        line["start"] = min(word["start"] for word in words)
        line["end"] = max(word["end"] for word in words)

    progress.log(f"aligner returned {len(aligned)} of {len(timed)} lines")
    return lines


def summarise_timings(lines):
    """Recount how each word got its timing. Needed after realigning changes them."""
    counts = {"matched": 0, "approximate": 0, "interpolated": 0, "aligned": 0}
    total = untimed = 0

    for line in lines:
        for word in line.get("words", []):
            total += 1
            if word.get("start") is None:
                untimed += 1
                continue
            kind = word.get("timing")
            if kind in counts:
                counts[kind] += 1

    counts["unmatched"] = untimed
    counts["coverage"] = round((total - untimed) / total, 4) if total else 0.0
    return counts


def apply_corrected_lyrics(song_path, text, realign=False, models=None, progress=None):
    """Rewrite a song's reference lyrics and redo their timings.

    Returns the timing summary, so the caller can show how well the correction matched.
    """
    progress = progress or ProgressReporter()
    staging = tempfile.mkdtemp(prefix="any_karaoke_edit_")

    try:
        unpack_song(song_path, staging)

        scaffold = build_lyrics_alignment(text, "corrected")
        alignment = read_optional_json(song_path, ALIGNMENT_RESULT_FILE) or {}
        filled = fill_lyrics_timings(scaffold, alignment)

        if realign:
            vocals = find_stem(song_path, "vocals")
            if vocals is None:
                raise FileNotFoundError("this song has no vocals stem to align against")
            force_align_lines(
                filled["lines"],
                os.path.join(staging, vocals),
                song_language(staging),
                models=models,
                progress=progress,
            )
            filled["realigned"] = True
            # The words carry new provenance now, so the old counts no longer describe them
            filled["timing"] = summarise_timings(filled["lines"])

        write_json(os.path.join(staging, LYRICS_ALIGNMENT_FILE), filled)
        with open(os.path.join(staging, CORRECTED_LYRICS_FILE), "w", encoding="utf-8") as handle:
            handle.write(text)

        pack_song(staging, song_path)
        summary = filled.get("timing", {})
        progress.log(f"saved corrected lyrics: {filled['line_count']} lines, {summary.get('coverage', 0):.0%} timed")
        return summary
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def describe_timing(summary):
    """One line for the editor's status label."""
    if not summary:
        return "no timings"

    parts = [
        f"{summary[name]} {name}"
        for name in ("aligned", "matched", "approximate", "interpolated", "unmatched")
        if summary.get(name)
    ]
    return f"{', '.join(parts) or 'no words'} ({summary.get('coverage', 0):.0%} timed)"
